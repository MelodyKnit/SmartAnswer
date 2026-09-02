"""运行时日志的脱敏与本地存储辅助。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import os
from pathlib import Path
from threading import Lock
import time
from typing import Any

from ..config import get_global_config
from ..storage.redis_state import build_recent_event_store_from_env

_RECENT_EVENT_STORE = build_recent_event_store_from_env()
_LOG_POLICY_CHECK_INTERVAL_SECONDS = 300.0
_LOG_POLICY_LOCK = Lock()
_LOG_POLICY_PROVIDER: Callable[[], tuple[int, int]] | None = None
_LAST_LOG_POLICY_CHECK = 0.0


def log_path() -> Path:
    """获取运行时 JSONL 日志路径。"""
    return get_global_config().log_path_resolved


def redact(value: Any) -> Any:
    """递归地对敏感字段进行脱敏。"""
    if isinstance(value, dict):
        return {
            key: ("[redacted]" if is_secret_key(key) else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        api_key = os.getenv("STQB_LLM_API_KEY")
        if api_key:
            value = value.replace(api_key, "[redacted]")
        return value
    return value


def is_secret_key(key: str) -> bool:
    """判断键名是否属于敏感字段。"""
    normalized = key.lower()
    return any(
        token in normalized
        for token in (
            "api_key",
            "authorization",
            "token",
            "password",
            "secret",
            "share_url",
            "share_link",
        )
    )


def append_recent_event(entry: dict[str, Any]) -> None:
    """把最近事件写入状态存储。"""
    _RECENT_EVENT_STORE.append(entry)


def load_recent_events(limit: int) -> list[dict[str, Any]]:
    """从状态存储读取最近事件。"""
    return _RECENT_EVENT_STORE.recent(limit)


def configure_log_storage_policy(
    provider: Callable[[], tuple[int, int]] | None,
) -> None:
    """配置日志自动清理策略提供器，应用测试或重建时可替换。"""

    global _LAST_LOG_POLICY_CHECK, _LOG_POLICY_PROVIDER
    with _LOG_POLICY_LOCK:
        _LOG_POLICY_PROVIDER = provider
        _LAST_LOG_POLICY_CHECK = 0.0


def maybe_enforce_log_storage_policy(*, force: bool = False) -> None:
    """按限频策略清理过期或超容量日志，失败时不影响主业务日志写入。"""

    global _LAST_LOG_POLICY_CHECK
    now = time.time()
    with _LOG_POLICY_LOCK:
        provider = _LOG_POLICY_PROVIDER
        if provider is None or (
            not force and now - _LAST_LOG_POLICY_CHECK < _LOG_POLICY_CHECK_INTERVAL_SECONDS
        ):
            return
        _LAST_LOG_POLICY_CHECK = now
    try:
        retention_days, max_size_mb = provider()
        if retention_days < 1 or max_size_mb < 10:
            return
        cleanup_log_storage(
            before_seconds=retention_days * 86400.0,
            max_total_bytes=max_size_mb * 1024 * 1024,
        )
    except Exception:
        # 日志清理属于后台维护，不能让它影响当前请求或启动流程。
        return


def get_log_storage_stats() -> dict[str, Any]:
    """获取服务器日志存储目录的统计信息（文件数、总大小、时间跨度）。"""
    target = log_path()
    log_dir = target.parent
    if not log_dir.exists():
        return {
            "file_count": 0,
            "total_size_bytes": 0,
            "total_size_mb": 0.0,
            "oldest_time": None,
            "newest_time": None,
            "files": [],
        }

    files_info: list[dict[str, Any]] = []
    total_size = 0
    timestamps: list[float] = []

    for item in log_dir.iterdir():
        if item.is_file() and (item.suffix in {".jsonl", ".log", ".txt"} or item.name.startswith("service")):
            try:
                stat = item.stat()
            except OSError:
                continue
            size = stat.st_size
            mtime = stat.st_mtime
            total_size += size
            timestamps.append(mtime)
            files_info.append({
                "name": item.name,
                "size_bytes": size,
                "size_mb": round(size / (1024 * 1024), 2),
                "updated_at": datetime.fromtimestamp(mtime, timezone.utc).isoformat(),
            })

    files_info.sort(key=lambda x: x["updated_at"], reverse=True)

    oldest_str = (
        datetime.fromtimestamp(min(timestamps), timezone.utc).strftime("%Y-%m-%d")
        if timestamps
        else None
    )
    newest_str = (
        datetime.fromtimestamp(max(timestamps), timezone.utc).strftime("%Y-%m-%d")
        if timestamps
        else None
    )

    return {
        "file_count": len(files_info),
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "oldest_time": oldest_str,
        "newest_time": newest_str,
        "files": files_info,
    }


def cleanup_log_storage(
    *,
    before_seconds: float | None = None,
    keep_last_n_files: int | None = None,
    clear_all: bool = False,
    max_total_bytes: int | None = None,
) -> dict[str, Any]:
    """清理日志文件。"""
    target = log_path()
    log_dir = target.parent
    if not log_dir.exists():
        return {"deleted_files": 0, "freed_bytes": 0}

    now = time.time()
    deleted_count = 0
    freed_bytes = 0

    log_files = []
    for item in log_dir.iterdir():
        try:
            if item.is_file() and (
                item.suffix in {".jsonl", ".log", ".txt"} or item.name.startswith("service")
            ):
                log_files.append(item)
        except OSError:
            continue

    def file_mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    # 按修改时间从新到旧排序
    log_files.sort(key=file_mtime, reverse=True)

    if clear_all:
        for p in log_files:
            try:
                size = p.stat().st_size
                if p == target:
                    # 如果是当前写入的日志文件，清空其内容而不删除文件句柄
                    p.write_text("", encoding="utf-8")
                else:
                    p.unlink(missing_ok=True)
                deleted_count += 1
                freed_bytes += size
            except Exception:
                pass
        return {"deleted_files": deleted_count, "freed_bytes": freed_bytes}

    if keep_last_n_files is not None and keep_last_n_files >= 0:
        # 当前日志文件始终保留；keep_last_n_files 表示总保留数量（含当前文件）。
        archive_files = [path for path in log_files if path != target]
        to_delete = archive_files[max(0, keep_last_n_files - 1):]
        for p in to_delete:
            try:
                size = p.stat().st_size
                if p == target:
                    p.write_text("", encoding="utf-8")
                else:
                    p.unlink(missing_ok=True)
                deleted_count += 1
                freed_bytes += size
            except Exception:
                pass
    elif before_seconds is not None and before_seconds > 0:
        threshold = now - before_seconds
        for p in log_files:
            try:
                stat = p.stat()
            except OSError:
                continue
            if stat.st_mtime < threshold:
                size = stat.st_size
                try:
                    if p == target:
                        p.write_text("", encoding="utf-8")
                    else:
                        p.unlink(missing_ok=True)
                    deleted_count += 1
                    freed_bytes += size
                except Exception:
                    pass

    if max_total_bytes is not None and max_total_bytes > 0:
        remaining_files = []
        total_size = 0
        for p in log_files:
            try:
                if p.exists():
                    remaining_files.append(p)
                    total_size += p.stat().st_size
            except OSError:
                continue
        for p in sorted(remaining_files, key=file_mtime):
            if total_size <= max_total_bytes:
                break
            # 不截断当前日志文件，避免清理期间破坏正在追加的日志内容。
            if p == target:
                continue
            try:
                size = p.stat().st_size
                p.unlink(missing_ok=True)
                total_size -= size
                deleted_count += 1
                freed_bytes += size
            except OSError:
                continue

    return {"deleted_files": deleted_count, "freed_bytes": freed_bytes}

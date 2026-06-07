"""附带敏感信息脱敏功能的运行时 JSONL 结构化日志记录助手。

本模块提供将运行时事件（如 LLM 请求、决议结果等）写入本地 JSONL 日志文件的支持，
并且能在保存时自动脱敏 API 密钥、密钥、密码等机密数据。
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections import deque
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any

# 用于保护多线程环境下对内存中最近日志队列及写日志文件操作的并发锁
_LOCK = Lock()
# 在内存中保留的最近日志的双端队列，固定最大长度为 80 条
_RECENT: deque[dict[str, Any]] = deque(maxlen=80)
_LOGGER_NAME = "study_qb_assistant"
SUCCESS_LEVEL = 25
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")


def log_event(event: str, payload: dict[str, Any]) -> None:
    """将运行时事件及其参数负载追加到本地磁盘日志文件和内存队列中，自动脱敏敏感数据。

    Args:
        event: 事件类型名称（如 "service_start", "query_resolved" 等）。
        payload: 与事件相关的详情字典。
    """
    entry = {
        # 使用 UTC 时间戳并格式化为 ISO 8601 标准字符串
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        # 对参数负载进行敏感词/敏感数据脱敏过滤
        **_redact(payload),
    }
    with _LOCK:
        _RECENT.append(entry)
        _log_console_entry(entry)
        log_path = _log_path()
        # 确保日志存储目录存在
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # 以追加模式打开文件并安全地写入单行 JSON
        with log_path.open("a", encoding="utf-8", newline="\n") as handle:
            json.dump(entry, handle, ensure_ascii=False)
            handle.write("\n")


def recent_events(limit: int = 30) -> list[dict[str, Any]]:
    """获取内存中最近记录的运行时事件日志，通常用于本地故障排查和状态监控。

    Args:
        limit: 返回的日志条数限制，默认最多 30 条。

    Returns:
        list[dict[str, Any]]: 最近事件日志的拷贝列表。
    """
    with _LOCK:
        # 从双端队列中提取并截取最新的 limit 条日志
        return list(_RECENT)[-limit:]


def console_log(level: str | int, message: str, *, logger_name: str = _LOGGER_NAME) -> None:
    """Emit a NoneBot-style console log without affecting JSONL persistence."""
    if not _console_enabled():
        return
    logger = _get_console_logger(logger_name)
    logger.log(_coerce_level(level), message)


def configure_external_loggers() -> None:
    """Attach the project formatter to uvicorn/watchfiles loggers for consistency."""
    if not _console_enabled():
        return
    handler = _build_console_handler()
    targets = {
        "uvicorn": logging.INFO,
        "uvicorn.error": logging.INFO,
        "uvicorn.access": logging.INFO,
        "watchfiles.main": logging.WARNING,
    }
    for name, level in targets.items():
        logger = logging.getLogger(name)
        logger.handlers = [handler]
        logger.setLevel(level)
        logger.propagate = False


def _log_path() -> Path:
    """获取日志存储路径，优先使用 STQB_LOG_PATH 环境变量。"""
    return Path(os.getenv("STQB_LOG_PATH", "data/logs/service.jsonl"))


def _log_console_entry(entry: dict[str, Any]) -> None:
    if not _console_enabled():
        return
    event = str(entry.get("event") or "runtime")
    level = _level_for_event(event, entry)
    message = _message_for_event(event, entry)
    logger_name = _logger_name_for_event(event)
    _get_console_logger(logger_name).log(level, message)


def _redact(value: Any) -> Any:
    """递归地对包含 API 密钥或敏感特征的字段值进行脱敏或打码替换。"""
    if isinstance(value, dict):
        # 字典类型：对属于机密名称的键进行打码，对其它键的值递归调用脱敏
        return {key: ("[redacted]" if _is_secret_key(key) else _redact(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        # 字符串类型：如果包含当前环境变量配置的 API Key 原始值，将其整体替换为安全标记
        api_key = os.getenv("STQB_LLM_API_KEY")
        if api_key:
            value = value.replace(api_key, "[redacted]")
        return value
    return value


def _is_secret_key(key: str) -> bool:
    """通过匹配特定的敏感词判断当前键名是否代表机密字段（如 API 密钥、密码等）。"""
    normalized = key.lower()
    return any(token in normalized for token in ("api_key", "authorization", "token", "password", "secret"))


def _console_enabled() -> bool:
    value = os.getenv("STQB_CONSOLE_LOG", "true").strip().lower()
    return value not in {"0", "false", "no", "off", "disabled"}


def _coerce_level(level: str | int) -> int:
    if isinstance(level, int):
        return level
    normalized = str(level).strip().upper()
    if normalized == "SUCCESS":
        return SUCCESS_LEVEL
    return int(getattr(logging, normalized, logging.INFO))


@lru_cache(maxsize=1)
def _env_console_level() -> int:
    value = os.getenv("STQB_CONSOLE_LOG_LEVEL", "INFO")
    return _coerce_level(value)


def _get_console_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(0)
    logger.propagate = False
    if not any(getattr(handler, "_stqb_console", False) for handler in logger.handlers):
        handler = _build_console_handler()
        logger.addHandler(handler)
    return logger


def _build_console_handler() -> logging.Handler:
    handler = logging.StreamHandler(sys.stdout)
    handler._stqb_console = True  # type: ignore[attr-defined]
    handler.setLevel(_env_console_level())
    handler.setFormatter(_NoneBotStyleFormatter(use_color=_use_color()))
    return handler


def _use_color() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


class _NoneBotStyleFormatter(logging.Formatter):
    """Compact console formatter inspired by NoneBot2 default output."""

    _RESET = "\033[0m"
    _GREEN = "\033[32m"
    _CYAN_UNDERLINE = "\033[36;4m"
    _LEVEL_COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[34m",
        "SUCCESS": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[37;41m",
    }

    def __init__(self, *, use_color: bool) -> None:
        super().__init__()
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created).strftime("%m-%d %H:%M:%S")
        time_text = self._colorize(self._GREEN, timestamp)
        level_text = self._colorize(
            self._LEVEL_COLORS.get(record.levelname, self._LEVEL_COLORS["INFO"]),
            record.levelname,
        )
        name_text = self._colorize(self._CYAN_UNDERLINE, record.name)
        message = record.getMessage()
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)
        return f"{time_text} [{level_text}] {name_text} | {message}"

    def _colorize(self, color: str, value: str) -> str:
        if not self.use_color:
            return value
        return f"{color}{value}{self._RESET}"


def _logger_name_for_event(event: str) -> str:
    if event.startswith("model_"):
        return f"{_LOGGER_NAME}.model"
    if event.startswith("web_search"):
        return f"{_LOGGER_NAME}.search"
    if event in {"service_start"}:
        return f"{_LOGGER_NAME}.server"
    if event in {"query", "ocs_answer_fallback_used"}:
        return f"{_LOGGER_NAME}.api"
    return _LOGGER_NAME


def _level_for_event(event: str, entry: dict[str, Any]) -> int:
    if event == "service_start":
        return SUCCESS_LEVEL
    if event == "query":
        return SUCCESS_LEVEL if entry.get("ok") else logging.WARNING
    if event in {"model_error"}:
        return logging.ERROR
    if event in {"web_search_error", "web_search_skipped", "ocs_answer_fallback_used"}:
        return logging.WARNING
    return logging.INFO


def _message_for_event(event: str, entry: dict[str, Any]) -> str:
    if event == "service_start":
        auth = "on" if entry.get("require_auth") else "off"
        return f"Service starting at http://{entry.get('host')}:{entry.get('port')} (auth={auth})"
    if event == "query":
        title = _shorten(str(entry.get("title") or ""), limit=72)
        return (
            f"{entry.get('method')} {entry.get('path')} "
            f"{entry.get('question_type')} answer={entry.get('answer')!s} "
            f"confidence={entry.get('confidence')} mode={entry.get('resolution_mode')} "
            f"title={title}"
        )
    if event == "model_request":
        return (
            f"Model request provider={entry.get('provider')} model={entry.get('model')} "
            f"options={entry.get('options_count')} evidence={entry.get('evidence_count')} "
            f"title={_shorten(str(entry.get('title') or ''), limit=72)}"
        )
    if event == "model_response":
        return (
            f"Model response provider={entry.get('provider')} model={entry.get('model')} "
            f"answer={entry.get('candidate_answer')!s} confidence={entry.get('confidence')}"
        )
    if event == "model_answer_normalized":
        return (
            f"Normalized model answer {entry.get('original_candidate')!s} -> "
            f"{entry.get('normalized_candidate')!s}"
        )
    if event == "model_error":
        return f"Model error provider={entry.get('provider')} error={entry.get('error')}"
    if event == "web_search_results":
        return (
            f"Web search provider={entry.get('provider')} results={entry.get('result_count')} "
            f"title={_shorten(str(entry.get('title') or ''), limit=72)}"
        )
    if event == "web_search_skipped":
        return (
            f"Web search skipped provider={entry.get('provider')} reason={entry.get('reason')} "
            f"title={_shorten(str(entry.get('title') or ''), limit=72)}"
        )
    if event == "web_search_error":
        return f"Web search error provider={entry.get('provider')} error={entry.get('error')}"
    if event == "ocs_answer_fallback_used":
        return (
            f"OCS answer fallback used type={entry.get('question_type')} "
            f"answer_text={entry.get('answer_text')!s}"
        )
    return json.dumps(entry, ensure_ascii=False)


def _shorten(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."

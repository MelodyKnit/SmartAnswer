"""运行时日志的脱敏与本地存储辅助。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..storage.redis_state import build_recent_event_store_from_env

_RECENT_EVENT_STORE = build_recent_event_store_from_env()


def log_path() -> Path:
    """获取运行时 JSONL 日志路径。"""
    return Path(os.getenv("STQB_LOG_PATH", "data/logs/service.jsonl"))


def redact(value: Any) -> Any:
    """递归地对敏感字段进行脱敏。"""
    if isinstance(value, dict):
        return {key: ("[redacted]" if is_secret_key(key) else redact(item)) for key, item in value.items()}
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
    return any(token in normalized for token in ("api_key", "authorization", "token", "password", "secret"))


def append_recent_event(entry: dict[str, Any]) -> None:
    """把最近事件写入状态存储。"""
    _RECENT_EVENT_STORE.append(entry)


def load_recent_events(limit: int) -> list[dict[str, Any]]:
    """从状态存储读取最近事件。"""
    return _RECENT_EVENT_STORE.recent(limit)

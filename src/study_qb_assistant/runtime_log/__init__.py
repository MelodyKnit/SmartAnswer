"""附带敏感信息脱敏功能的运行时 JSONL 结构化日志记录助手。

本模块提供将运行时事件（如 LLM 请求、决议结果等）写入本地 JSONL 日志文件的支持，
并且能在保存时自动脱敏 API 密钥、密钥、密码等机密数据。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from .console import (
    LOGGER_NAME,
    SUCCESS_LEVEL,
    NoneBotStyleFormatter,
    build_console_handler,
    console_enabled,
    coerce_level,
    get_console_logger,
    level_for_event,
    logger_name_for_event,
    message_for_event,
)
from .storage import append_recent_event, load_recent_events, log_path, redact

# 用于保护多线程环境下对内存中最近日志队列及写日志文件操作的并发锁
_LOCK = Lock()

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
        **redact(payload),
    }
    with _LOCK:
        append_recent_event(entry)
        _log_console_entry(entry)
        path = log_path()
        # 确保日志存储目录存在
        path.parent.mkdir(parents=True, exist_ok=True)
        # 以追加模式打开文件并安全地写入单行 JSON
        with path.open("a", encoding="utf-8", newline="\n") as handle:
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
        return load_recent_events(limit)


def console_log(level: str | int, message: str, *, logger_name: str = LOGGER_NAME) -> None:
    """Emit a NoneBot-style console log without affecting JSONL persistence."""
    if not console_enabled():
        return
    logger = get_console_logger(logger_name)
    logger.log(coerce_level(level), message)


def configure_external_loggers() -> None:
    """Attach the project formatter to uvicorn/watchfiles loggers for consistency."""
    import logging

    if not console_enabled():
        return
    handler = build_console_handler()
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

def _log_console_entry(entry: dict[str, Any]) -> None:
    if not console_enabled():
        return
    event = str(entry.get("event") or "runtime")
    level = level_for_event(event, entry)
    message = message_for_event(event, entry)
    logger_name = logger_name_for_event(event)
    get_console_logger(logger_name).log(level, message)


# 兼容现有测试与局部旧调用的最薄私有别名层。
_NoneBotStyleFormatter = NoneBotStyleFormatter
_build_console_handler = build_console_handler
_logger_name_for_event = logger_name_for_event
_level_for_event = level_for_event
_message_for_event = message_for_event

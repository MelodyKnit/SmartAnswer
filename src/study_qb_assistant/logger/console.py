"""运行时控制台日志格式与事件映射。"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from functools import lru_cache
from typing import Any

LOGGER_NAME = "study_qb_assistant"
SUCCESS_LEVEL = 25
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")


def console_enabled() -> bool:
    """判断是否启用控制台日志输出。"""
    value = os.getenv("STQB_CONSOLE_LOG", "true").strip().lower()
    return value not in {"0", "false", "no", "off", "disabled"}


def coerce_level(level: str | int) -> int:
    """把字符串或整数级别统一转换为 logging 级别值。"""
    if isinstance(level, int):
        return level
    normalized = str(level).strip().upper()
    if normalized == "SUCCESS":
        return SUCCESS_LEVEL
    return int(getattr(logging, normalized, logging.INFO))


@lru_cache(maxsize=1)
def env_console_level() -> int:
    """读取控制台日志级别配置。"""
    value = os.getenv("STQB_CONSOLE_LOG_LEVEL", "INFO")
    return coerce_level(value)


def get_console_logger(name: str) -> logging.Logger:
    """获取项目统一控制台 logger。"""
    logger = logging.getLogger(name)
    logger.setLevel(0)
    logger.propagate = False
    if not any(getattr(handler, "_stqb_console", False) for handler in logger.handlers):
        handler = build_console_handler()
        logger.addHandler(handler)
    return logger


def build_console_handler() -> logging.Handler:
    """构建 NoneBot 风格的控制台日志处理器。"""
    handler = logging.StreamHandler(sys.stdout)
    handler._stqb_console = True  # type: ignore[attr-defined]
    handler.setLevel(env_console_level())
    handler.setFormatter(NoneBotStyleFormatter(use_color=use_color()))
    return handler


def use_color() -> bool:
    """判断终端是否适合输出 ANSI 颜色。"""
    if os.getenv("NO_COLOR"):
        return False
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


class NoneBotStyleFormatter(logging.Formatter):
    """受 NoneBot2 启发的控制台日志格式器。"""

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
        """渲染单条日志记录。"""
        timestamp = datetime.fromtimestamp(record.created).strftime("%m-%d %H:%M:%S")
        time_text = self.colorize(self._GREEN, timestamp)
        level_text = self.colorize(
            self._LEVEL_COLORS.get(record.levelname, self._LEVEL_COLORS["INFO"]),
            record.levelname,
        )
        logger_name = record.name
        if logger_name == "uvicorn.error":
            logger_name = "uvicorn"
        name_text = self.colorize(self._CYAN_UNDERLINE, logger_name)
        message = record.getMessage()
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)
        return f"{time_text} [{level_text}] {name_text} | {message}"

    def colorize(self, color: str, value: str) -> str:
        """为输出文本附加 ANSI 颜色。"""
        if not self.use_color:
            return value
        return f"{color}{value}{self._RESET}"


def build_uvicorn_log_config() -> dict[str, Any]:
    """构建与项目 NoneBot 日志风格完全一致的 Uvicorn 日志配置字典。"""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "nonebot": {
                "()": "study_qb_assistant.logger.console.NoneBotStyleFormatter",
                "use_color": use_color(),
            },
        },
        "handlers": {
            "default": {
                "formatter": "nonebot",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
            "access": {
                "formatter": "nonebot",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
            "watchfiles.main": {"handlers": ["default"], "level": "WARNING", "propagate": False},
        },
    }


def logger_name_for_event(event: str) -> str:
    """根据事件名推导日志子系统名称。"""
    if event.startswith("model_"):
        return f"{LOGGER_NAME}.model"
    if event.startswith("web_search"):
        return f"{LOGGER_NAME}.search"
    if event in {
        "service_start",
        "question_index_sync_start",
        "question_index_sync_complete",
        "question_index_load_start",
        "question_index_load_complete",
    }:
        return f"{LOGGER_NAME}.server"
    if event in {"query", "ocs_answer_fallback_used"}:
        return f"{LOGGER_NAME}.api"
    return LOGGER_NAME


def level_for_event(event: str, entry: dict[str, Any]) -> int:
    """根据事件类型和内容推导日志级别。"""
    if event == "service_start":
        return SUCCESS_LEVEL
    if event == "query":
        return SUCCESS_LEVEL if entry.get("ok") else logging.WARNING
    if event in {"model_error"}:
        return logging.ERROR
    if event in {"web_search_error", "web_search_skipped", "ocs_answer_fallback_used"}:
        return logging.WARNING
    return logging.INFO


def message_for_event(event: str, entry: dict[str, Any]) -> str:
    """把结构化事件转换为控制台摘要文本。"""
    if event == "service_start":
        auth = "on" if entry.get("require_auth") else "off"
        return f"Service starting at http://{entry.get('host')}:{entry.get('port')} (auth={auth})"
    if event == "question_index_sync_start":
        return (
            f"Question bank sync starting records={entry.get('record_count')} "
            f"source={shorten(str(entry.get('source_path') or ''), limit=96)}"
        )
    if event == "question_index_sync_complete":
        status = "skipped" if entry.get("skipped") else "completed"
        return (
            f"Question bank sync {status} records={entry.get('record_count')} "
            f"synced={entry.get('synced_count')}"
        )
    if event == "question_index_load_start":
        return "Question bank runtime index loading"
    if event == "question_index_load_complete":
        return f"Question bank runtime index ready records={entry.get('record_count')}"
    if event == "query":
        title = shorten(str(entry.get("title") or ""), limit=72)
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
            f"title={shorten(str(entry.get('title') or ''), limit=72)}"
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
            f"title={shorten(str(entry.get('title') or ''), limit=72)}"
        )
    if event == "web_search_skipped":
        return (
            f"Web search skipped provider={entry.get('provider')} reason={entry.get('reason')} "
            f"title={shorten(str(entry.get('title') or ''), limit=72)}"
        )
    if event == "web_search_error":
        return f"Web search error provider={entry.get('provider')} error={entry.get('error')}"
    if event == "ocs_answer_fallback_used":
        return (
            f"OCS answer fallback used type={entry.get('question_type')} "
            f"answer_text={entry.get('answer_text')!s}"
        )
    return json.dumps(entry, ensure_ascii=False)


def shorten(value: str, *, limit: int) -> str:
    """把长文本裁剪为固定长度摘要。"""
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."

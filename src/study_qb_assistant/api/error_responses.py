"""统一的错误响应辅助函数，确保所有API端点返回一致的错误格式。"""

from __future__ import annotations

from typing import Any

from starlette.responses import JSONResponse

from ..logger import log_event


def internal_error_response(
    exc: Exception,
    *,
    event_name: str = "api_internal_error",
    user_message: str = "服务器内部错误，请稍后重试",
    extra_context: dict[str, Any] | None = None,
) -> JSONResponse:
    """创建统一的500错误响应，包含详细日志和结构化错误信息。

    Args:
        exc: 捕获的异常对象
        event_name: 日志事件名称
        user_message: 用户友好的错误消息
        extra_context: 额外的上下文信息，会记录到日志中

    Returns:
        JSONResponse: 包含详细错误信息的500响应
    """
    context = extra_context or {}
    log_event(
        event_name,
        {
            **context,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        },
    )

    return JSONResponse(
        {
            "ok": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": user_message,
                "type": type(exc).__name__,
                "detail": str(exc),
            },
        },
        status_code=500,
    )


def business_error_response(
    code: str,
    message: str,
    *,
    status_code: int = 400,
    detail: str | None = None,
    **extra: Any,
) -> JSONResponse:
    """创建统一的业务错误响应。

    Args:
        code: 错误代码（大写下划线格式，如 INVALID_INPUT）
        message: 用户友好的错误消息
        status_code: HTTP 状态码
        detail: 可选的详细错误信息
        **extra: 额外的错误字段

    Returns:
        JSONResponse: 统一格式的错误响应
    """
    error_dict: dict[str, Any] = {
        "code": code,
        "message": message,
        **extra,
    }

    if detail is not None:
        error_dict["detail"] = detail

    return JSONResponse(
        {"ok": False, "error": error_dict},
        status_code=status_code,
    )

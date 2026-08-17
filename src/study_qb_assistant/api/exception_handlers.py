"""全局异常处理器，确保未处理错误可审计且不向客户端泄露内部细节。"""

from __future__ import annotations

import traceback
from typing import Any

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

from ..logger import log_event
from .middleware import cors_headers


def install_exception_handlers(app: FastAPI) -> None:
    """安装全局异常处理器，捕获所有未处理异常并返回详细错误信息。"""

    @app.exception_handler(Exception)
    async def catch_all_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """捕获所有未处理的异常，记录详细日志并返回结构化错误响应。"""

        # 获取完整的堆栈跟踪
        error_traceback = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

        # 只记录路径而不记录完整 URL，避免查询参数中的用户输入或凭据进入日志。
        request_info = {
            "method": request.method,
            "path": request.url.path,
            "client": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        }

        # 尝试获取用户信息
        try:
            user = getattr(request.state, "user", None)
            if user:
                request_info["user_id"] = user.get("user_id")
                request_info["username"] = user.get("username")
        except Exception:
            pass

        # 记录详细错误日志
        log_event(
            "unhandled_exception",
            {
                **request_info,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
                "traceback": error_traceback,
            },
        )

        # 原始异常仅保留在服务端日志。API 响应必须稳定且不泄露数据库、路径、
        # 上游服务或认证实现的内部细节。
        error_response: dict[str, Any] = {
            "ok": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "服务器内部错误，请稍后重试",
            },
        }

        # 异常响应会绕过 HTTP 中间件的后半段，需要在此显式补上 CORS 头，
        # 否则浏览器会因跨域策略拦截整个 500 响应，前端读不到结构化错误信息。
        return JSONResponse(
            error_response,
            status_code=500,
            headers=cors_headers(request),
        )


def create_error_response(
    code: str,
    message: str,
    status_code: int = 400,
    **extra: Any,
) -> JSONResponse:
    """创建统一格式的错误响应。

    Args:
        code: 错误代码（大写下划线格式）
        message: 用户友好的错误消息
        status_code: HTTP 状态码
        **extra: 额外的错误详情字段

    Returns:
        JSONResponse: 统一格式的错误响应
    """
    response = {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            **extra,
        },
    }
    return JSONResponse(response, status_code=status_code)

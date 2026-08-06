"""全局异常处理器，确保所有错误都返回结构化响应和详细日志。"""

from __future__ import annotations

import traceback
from typing import Any

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

from ..logger import log_event


def install_exception_handlers(app: FastAPI) -> None:
    """安装全局异常处理器，捕获所有未处理异常并返回详细错误信息。"""

    @app.exception_handler(Exception)
    async def catch_all_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """捕获所有未处理的异常，记录详细日志并返回结构化错误响应。"""

        # 获取完整的堆栈跟踪
        error_traceback = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

        # 提取请求信息用于日志
        request_info = {
            "method": request.method,
            "url": str(request.url),
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

        # 构建用户友好的错误响应（包含足够的调试信息）
        error_response: dict[str, Any] = {
            "ok": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "服务器内部错误，请稍后重试",
                "type": type(exc).__name__,
                "detail": str(exc),
            },
        }

        # 在开发环境中返回完整堆栈跟踪
        try:
            from ..config import get_global_config
            config = get_global_config()
            # 如果配置中有调试模式，添加完整堆栈信息
            if getattr(config, "debug", False):
                error_response["error"]["traceback"] = error_traceback
        except Exception:
            pass

        return JSONResponse(
            error_response,
            status_code=500,
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

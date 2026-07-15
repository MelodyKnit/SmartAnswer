"""应用级 CORS、SPA 导航与旧接口弃用中间件。"""

from __future__ import annotations

from fastapi import FastAPI, Request, Response
from starlette.responses import FileResponse

from ..logger import log_event
from .legacy import successor_path
from .static import STATIC_DIR, should_serve_spa_shell


def install_http_middleware(app: FastAPI) -> None:
    """安装项目统一 HTTP 中间件。"""

    @app.middleware("http")
    async def cors_spa_and_legacy(request: Request, call_next) -> Response:
        if request.method == "OPTIONS":
            return Response(status_code=204, headers=cors_headers(request))
        if request.method == "GET" and should_serve_spa_shell(request, request.url.path):
            html_path = STATIC_DIR / "index.html"
            if html_path.exists():
                response = FileResponse(html_path, media_type="text/html; charset=utf-8")
                apply_cors_headers(response, request)
                return response

        response = await call_next(request)
        if bool(getattr(request.state, "legacy_api", False)):
            successor = successor_path(request.url.path)
            response.headers["Deprecation"] = "true"
            response.headers["Link"] = f'<{successor}>; rel="successor-version"'
            log_event(
                "legacy_api_request",
                {
                    "method": request.method,
                    "path": request.url.path,
                    "successor": successor,
                    "status_code": response.status_code,
                },
            )
        apply_cors_headers(response, request)
        return response


def cors_headers(request: Request) -> dict[str, str]:
    """生成当前请求对应的 CORS 响应头。"""

    origin = request.headers.get("Origin")
    headers = {
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }
    if origin:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Vary"] = "Origin"
        headers["Access-Control-Allow-Credentials"] = "true"
    else:
        headers["Access-Control-Allow-Origin"] = "*"
    return headers


def apply_cors_headers(response: Response, request: Request) -> None:
    """把当前请求的 CORS 头写入响应。"""

    for key, value in cors_headers(request).items():
        response.headers[key] = value

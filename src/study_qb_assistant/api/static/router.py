"""前端静态资源和 SPA 页面路由。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from starlette.responses import FileResponse, JSONResponse, Response

STATIC_DIR = Path(__file__).resolve().parent / "site"
STATIC_PAGES = {
    "/": "index.html",
    "/dashboard": "index.html",
    "/dashboard.html": "index.html",
    "/index.html": "index.html",
}


def build_static_router() -> APIRouter:
    """构建静态资源和 SPA 回退路由。"""

    router = APIRouter()

    @router.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def static_pages(request: Request, path: str) -> Response:
        route = "/" + path
        filename = STATIC_PAGES.get(route)
        if filename is not None:
            html_path = STATIC_DIR / filename
            if html_path.exists():
                return FileResponse(html_path, media_type="text/html; charset=utf-8")

        target_path = safe_static_path(path)
        if target_path is not None and target_path.is_file():
            return FileResponse(target_path)

        if should_serve_spa_shell(request, path):
            html_path = STATIC_DIR / "index.html"
            if html_path.exists():
                return FileResponse(html_path, media_type="text/html; charset=utf-8")

        return JSONResponse(
            {"ok": False, "error": {"code": "NOT_FOUND", "message": "资源不存在"}},
            status_code=404,
        )

    return router


def safe_static_path(path: str) -> Path | None:
    """把资源路径限制在前端构建目录内，避免目录穿越。"""

    try:
        candidate = (STATIC_DIR / path).resolve()
        candidate.relative_to(STATIC_DIR.resolve())
    except (OSError, ValueError):
        return None
    return candidate


def should_serve_spa_shell(request: Request, path: str) -> bool:
    """根据文档导航请求特征判断是否返回 SPA 入口。"""

    normalized_path = "/" + path.strip("/")
    if normalized_path == "/api" or normalized_path.startswith("/api/"):
        return False
    if normalized_path == "/ocs" or normalized_path.startswith("/ocs/"):
        return False

    normalized = normalized_path.strip("/")
    if not normalized:
        return True
    if "." in Path(normalized).name:
        return False
    accept = request.headers.get("Accept", "").lower()
    if "text/html" in accept:
        return True

    fetch_mode = request.headers.get("Sec-Fetch-Mode", "").lower()
    fetch_dest = request.headers.get("Sec-Fetch-Dest", "").lower()
    return fetch_mode == "navigate" and fetch_dest in {"document", "iframe"}

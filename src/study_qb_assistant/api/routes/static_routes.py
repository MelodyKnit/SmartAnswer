"""静态页面路由。"""

from __future__ import annotations

from fastapi import APIRouter
from starlette.responses import FileResponse, JSONResponse, Response

from ..route_support import STATIC_DIR, STATIC_PAGES


def build_static_router() -> APIRouter:
    """构建静态页面路由。"""
    router = APIRouter()

    @router.get("/{path:path}")
    def static_pages(path: str) -> Response:
        route = "/" + path
        filename = STATIC_PAGES.get(route)
        if filename is None:
            return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
        html_path = STATIC_DIR / filename
        if not html_path.exists():
            return JSONResponse({"ok": False, "error": f"failed to load page: {html_path}"}, status_code=500)
        return FileResponse(html_path, media_type="text/html; charset=utf-8")

    return router

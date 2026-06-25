"""静态页面路由。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from starlette.responses import FileResponse, JSONResponse, Response

from ...route_support import STATIC_DIR, STATIC_PAGES, should_serve_spa_shell


def build_static_router() -> APIRouter:
    """构建静态页面路由。"""
    router = APIRouter()

    @router.get("/{path:path}")
    def static_pages(request: Request, path: str) -> Response:
        # 1. 优先从静态页面映射表匹配
        route = "/" + path
        filename = STATIC_PAGES.get(route)
        if filename is not None:
            html_path = STATIC_DIR / filename
            if html_path.exists():
                return FileResponse(html_path, media_type="text/html; charset=utf-8")

        # 2. 如果是静态目录下的实际资源物理文件（如 css/js/png 等），直接返回
        target_path = safe_static_path(path)
        if target_path is not None and target_path.is_file() and target_path.exists():
            return FileResponse(target_path)

        # 3. 浏览器页面访问交给 Vue Router 处理，避免刷新受保护页面时看到 JSON。
        if should_serve_spa_shell(request, path):
            html_path = STATIC_DIR / "index.html"
            if html_path.exists():
                return FileResponse(html_path, media_type="text/html; charset=utf-8")

        # 4. API 或静态资源缺失继续返回机器可读错误。
        return JSONResponse(
            {"ok": False, "error": {"code": "NOT_FOUND", "message": "资源不存在"}},
            status_code=404,
        )

    return router


def safe_static_path(path: str) -> Path | None:
    """把静态资源路径限制在静态目录内，避免目录穿越。"""
    try:
        candidate = (STATIC_DIR / path).resolve()
        candidate.relative_to(STATIC_DIR.resolve())
    except (OSError, ValueError):
        return None
    return candidate

"""运行时媒体资源路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from starlette.responses import FileResponse, JSONResponse, Response

from ....media.question_images import ocs_image_path
from ....media.question_context import fetch_public_image_with_mime, is_public_http_url
from ....config import get_global_config
from ...security import current_user, is_auth_required, unauthorized_response


def build_media_router() -> APIRouter:
    """构建媒体资源路由；本地图床公开，外部图片代理按运行鉴权策略保护。"""

    router = APIRouter()

    @router.get("/media/ocs/images/{filename}")
    def ocs_question_image(filename: str) -> Response:
        """返回已保存的 OCS 题目图片。"""

        path = ocs_image_path(filename)
        if path is None or not path.is_file():
            return JSONResponse(
                {"ok": False, "error": {"code": "NOT_FOUND", "message": "图片不存在"}},
                status_code=404,
            )
        response = FileResponse(path)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    @router.get("/media/brand/{filename}")
    def brand_image(filename: str) -> Response:
        """返回已保存的品牌 Logo 资源文件。"""
        import re

        if not re.match(r"^[a-zA-Z0-9_\-\.]+$", filename) or ".." in filename:
            return JSONResponse(
                {"ok": False, "error": {"code": "NOT_FOUND", "message": "资源不存在"}},
                status_code=404,
            )
        brand_dir = get_global_config().brand_images_dir
        path = brand_dir / filename
        if not path.is_file():
            return JSONResponse(
                {"ok": False, "error": {"code": "NOT_FOUND", "message": "图片不存在"}},
                status_code=404,
            )
        response = FileResponse(path)
        response.headers["Cache-Control"] = "public, max-age=86400"
        return response

    @router.get("/media/proxy")
    def proxy_image(
        request: Request,
        url: str = Query(..., min_length=1, max_length=2048, description="目标图片公网地址"),
    ) -> Response:
        """安全代理抓取防盗链图片，仅供登录用户查看自己的使用记录。"""

        if is_auth_required(request) and current_user(request) is None:
            return unauthorized_response("请先登录")
        target_url = str(url or "").strip()
        if not is_public_http_url(target_url):
            return JSONResponse(
                {"ok": False, "error": {"code": "INVALID_URL", "message": "无效或禁止访问的 URL"}},
                status_code=400,
            )
        content, mime_type = fetch_public_image_with_mime(target_url)
        if content is None or not mime_type:
            return JSONResponse(
                {"ok": False, "error": {"code": "FETCH_FAILED", "message": "获取图片失败"}},
                status_code=404,
            )
        return Response(
            content=content,
            media_type=mime_type,
            headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
        )

    return router

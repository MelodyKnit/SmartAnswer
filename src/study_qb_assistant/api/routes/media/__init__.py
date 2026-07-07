"""运行时媒体资源路由。"""

from __future__ import annotations

from fastapi import APIRouter
from starlette.responses import FileResponse, JSONResponse, Response

from ....media.question_images import ocs_image_path


def build_media_router() -> APIRouter:
    """构建公开只读媒体资源路由。"""

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

    return router

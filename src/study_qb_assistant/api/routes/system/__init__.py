"""平台系统管理与配置相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, File, Request, UploadFile
from starlette.responses import JSONResponse

from ....answering import AnswerService
from ....auth import AuthError
from ....config import get_global_config
from ....media.brand_images import BrandLogoError, process_and_save_brand_logo
from ....updates import ProjectUpdateError
from ...context import (
    auth_error_response,
    current_user,
    get_lookup_service,
    get_platform_service,
    get_project_update_service,
    require_permissions,
    require_roles,
)
from ...route_support import apply_system_config_to_process
from ...schemas import ProjectUpdateApplyPayload, SystemConfigPayload


def build_system_router() -> APIRouter:
    """构建系统配置与管理路由。"""
    router = APIRouter()

    @router.get("/system-config")
    def system_config_get(request: Request) -> JSONResponse:
        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"system:write"})
        if denied:
            return denied
        platform = get_platform_service(request)
        return JSONResponse({"ok": True, "config": platform.get_system_config()})

    @router.get("/site-config")
    def site_config_get(request: Request) -> JSONResponse:
        platform = get_platform_service(request)
        return JSONResponse({"ok": True, **platform.get_site_config()})

    @router.patch("/system-config")
    def system_config_patch(
        request: Request, payload: SystemConfigPayload
    ) -> JSONResponse:
        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"system:write"})
        if denied:
            return denied
        platform = get_platform_service(request)
        values = {
            key: value
            for key, value in payload.model_dump().items()
            if value is not None
        }
        try:
            config = platform.set_system_config(values)
        except AuthError as exc:
            return auth_error_response(exc)
        apply_system_config_to_process(platform)
        lookup = get_lookup_service(request)
        if isinstance(lookup, AnswerService):
            from ....runtime import refresh_answer_service

            refresh_answer_service(lookup)
        return JSONResponse({"ok": True, "config": config, "reload_required": False})

    @router.post("/system/logo/upload")
    async def upload_logo(
        request: Request, file: UploadFile = File(...)
    ) -> JSONResponse:
        """上传网站 Logo 图片，并自动裁剪为大中小正方形尺寸。"""
        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"system:write"})
        if denied:
            return denied

        # 检查是否为图片文件
        content_type = file.content_type or ""
        if not content_type.startswith("image/"):
            return JSONResponse(
                {
                    "ok": False,
                    "error": {
                        "code": "INVALID_INPUT",
                        "message": "上传文件必须是图片格式",
                    },
                },
                status_code=400,
            )

        try:
            content_bytes = await file.read()
            if len(content_bytes) > 5 * 1024 * 1024:
                return JSONResponse(
                    {
                        "ok": False,
                        "error": {
                            "code": "INVALID_INPUT",
                            "message": "图片大小不能超过 5MB",
                        },
                    },
                    status_code=400,
                )

            brand_dir = get_global_config().brand_images_dir
            import time

            timestamp = int(time.time())

            # 进行自动裁切及多分辨率生成
            urls = process_and_save_brand_logo(content_bytes, brand_dir)

            # 为了防止前端浏览器缓存旧的图片，对返回的 URL 加上时间戳缓存破坏器
            cache_busted_urls = {k: f"{v}?t={timestamp}" for k, v in urls.items()}

            # 将 logo_lg.png 作为默认 site_logo_url 更新系统参数
            platform = get_platform_service(request)
            config = platform.set_system_config({"site_logo_url": urls["lg"]})

            # 同样应用热加载重载
            apply_system_config_to_process(platform)
            lookup = get_lookup_service(request)
            if isinstance(lookup, AnswerService):
                from ....runtime import refresh_answer_service

                refresh_answer_service(lookup)

            return JSONResponse(
                {"ok": True, "urls": cache_busted_urls, "config": config}
            )
        except BrandLogoError as exc:
            return JSONResponse(
                {"ok": False, "error": {"code": "INVALID_INPUT", "message": str(exc)}},
                status_code=400,
            )
        except Exception as exc:
            return JSONResponse(
                {
                    "ok": False,
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": f"处理图片失败: {str(exc)}",
                    },
                },
                status_code=500,
            )

    @router.get("/project-update/status")
    def project_update_status(request: Request) -> JSONResponse:
        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"system:write"})
        if denied:
            return denied
        payload = get_project_update_service(request).status()
        return JSONResponse({"ok": True, "update": payload})

    @router.post("/project-update/check")
    def project_update_check(request: Request) -> JSONResponse:
        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"system:write"})
        if denied:
            return denied
        try:
            user = current_user(request) or {}
            operation = get_project_update_service(request).enqueue_check(
                requested_by=str(user.get("username") or "superadmin")
            )
        except ProjectUpdateError as exc:
            return project_update_error_response(exc)
        return JSONResponse(
            {"ok": True, "operation": operation.to_dict()},
            status_code=202,
        )

    @router.post("/project-update/apply")
    def project_update_apply(
        request: Request,
        payload: ProjectUpdateApplyPayload,
    ) -> JSONResponse:
        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"system:write"})
        if denied:
            return denied
        try:
            user = current_user(request) or {}
            operation = get_project_update_service(request).enqueue_apply(
                expected_version=payload.expected_version,
                requested_by=str(user.get("username") or "superadmin"),
            )
        except ProjectUpdateError as exc:
            return project_update_error_response(exc)
        return JSONResponse(
            {"ok": True, "operation": operation.to_dict()},
            status_code=202,
        )

    @router.get("/project-update/operations/{operation_id}")
    def project_update_operation(request: Request, operation_id: str) -> JSONResponse:
        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"system:write"})
        if denied:
            return denied
        try:
            operation = get_project_update_service(request).operation(operation_id)
        except ProjectUpdateError as exc:
            return project_update_error_response(exc)
        return JSONResponse({"ok": True, "operation": operation.to_dict()})

    return router


def project_update_error_response(exc: ProjectUpdateError) -> JSONResponse:
    """把在线更新错误映射成统一 API 错误结构。"""

    return JSONResponse(
        {"ok": False, "error": {"code": exc.code, "message": exc.message}},
        status_code=exc.http_status,
    )

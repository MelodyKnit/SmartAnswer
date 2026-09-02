"""平台系统管理与配置相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, File, Request, UploadFile
from starlette.responses import JSONResponse

from ....answering import AnswerService
from ....auth import AuthError
from ....auth.email_verification import EmailDomainWhitelist
from ....config import get_global_config
from ....logger.console import clear_console_logs, get_console_logs
from ....logger.storage import cleanup_log_storage, get_log_storage_stats
from ....media.brand_images import BrandLogoError, process_and_save_brand_logo
from ....platform.updates import ProjectUpdateError
from ...dependencies import (
    get_lookup_service,
    get_project_update_service,
    get_settings_service,
)
from ...security import (
    auth_error_response,
    require_permissions,
)
from ...error_responses import internal_error_response
from ...runtime_config import apply_system_config_to_process
from .schemas import (
    EmailDomainWhitelistPayload,
    LogCleanupPayload,
    SystemConfigPayload,
)


def build_system_router() -> APIRouter:
    """构建系统配置与管理路由。"""
    router = APIRouter()

    @router.get("/system-config")
    def system_config_get(request: Request) -> JSONResponse:
        denied = require_permissions(request, {"system:write"})
        if denied:
            return denied
        platform = get_settings_service(request)
        return JSONResponse({"ok": True, "config": platform.get_system_config()})

    @router.get("/site-config")
    def site_config_get(request: Request) -> JSONResponse:
        platform = get_settings_service(request)
        return JSONResponse({"ok": True, **platform.get_site_config()})

    @router.patch("/system-config")
    def system_config_patch(
        request: Request, payload: SystemConfigPayload
    ) -> JSONResponse:
        denied = require_permissions(request, {"system:write"})
        if denied:
            return denied
        platform = get_settings_service(request)
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
            from ....bootstrap import refresh_answer_service

            refresh_answer_service(lookup)
        return JSONResponse({"ok": True, "config": config, "reload_required": False})

    @router.get("/system/email-domain-whitelist")
    def email_domain_whitelist_get(request: Request) -> JSONResponse:
        """读取仅供系统管理员维护的注册邮箱域名白名单。"""

        denied = require_permissions(request, {"system:write"})
        if denied:
            return denied
        try:
            domains = EmailDomainWhitelist().list_domains()
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "domains": domains})

    @router.put("/system/email-domain-whitelist")
    def email_domain_whitelist_put(
        request: Request, payload: EmailDomainWhitelistPayload
    ) -> JSONResponse:
        """原子替换注册邮箱域名白名单。"""

        denied = require_permissions(request, {"system:write"})
        if denied:
            return denied
        try:
            domains = EmailDomainWhitelist().replace_domains(payload.domains)
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "domains": domains})

    @router.get("/project-update/status")
    def project_update_status(request: Request) -> JSONResponse:
        """读取当前构建和最近 GitHub Release 检查结果。"""

        denied = require_permissions(request, {"system:write"})
        if denied:
            return denied
        update_service = get_project_update_service(request)
        return JSONResponse({"ok": True, "update": update_service.status()})

    @router.post("/project-update/check")
    def project_update_check(request: Request) -> JSONResponse:
        """从 GitHub 即时检查一个经过 manifest 验证的 Release。"""

        denied = require_permissions(request, {"system:write"})
        if denied:
            return denied
        try:
            update_service = get_project_update_service(request)
            return JSONResponse({"ok": True, "update": update_service.check()})
        except ProjectUpdateError as exc:
            return project_update_error_response(exc)

    @router.post("/system/logo/upload")
    async def upload_logo(
        request: Request, file: UploadFile = File(...)
    ) -> JSONResponse:
        """上传网站 Logo 图片，并自动裁剪为大中小正方形尺寸。"""
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
            platform = get_settings_service(request)
            config = platform.set_system_config({"site_logo_url": urls["lg"]})

            # 同样应用热加载重载
            apply_system_config_to_process(platform)
            lookup = get_lookup_service(request)
            if isinstance(lookup, AnswerService):
                from ....bootstrap import refresh_answer_service

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
            return internal_error_response(
                exc,
                event_name="brand_logo_upload_failed",
                user_message="处理图片失败",
            )

    @router.get("/system/logs/stats")
    def system_logs_stats(request: Request) -> JSONResponse:
        """读取服务器日志目录文件数量、占用大小及时间跨度统计。"""
        denied = require_permissions(request, {"system:read"})
        if denied:
            return denied
        stats = get_log_storage_stats()
        return JSONResponse({"ok": True, **stats})

    @router.post("/system/logs/cleanup")
    def system_logs_cleanup(request: Request, payload: LogCleanupPayload) -> JSONResponse:
        """手动清理历史日志文件。"""
        denied = require_permissions(request, {"system:write"})
        if denied:
            return denied
        if payload.mode == "all":
            res = cleanup_log_storage(clear_all=True)
        elif payload.mode == "files":
            keep = payload.keep_files if payload.keep_files is not None else 10
            res = cleanup_log_storage(keep_last_n_files=keep)
        elif payload.mode == "days":
            days = payload.days if payload.days is not None else 30
            res = cleanup_log_storage(before_seconds=days * 86400.0)
        else:
            return JSONResponse(
                {"ok": False, "error": {"code": "INVALID_INPUT", "message": "不支持的清理模式"}},
                status_code=400,
            )
        return JSONResponse({"ok": True, **res, "stats": get_log_storage_stats()})

    @router.get("/system/logs/console")
    def system_logs_console(
        request: Request,
        limit: int = 500,
        offset: int = 0,
    ) -> JSONResponse:
        """读取内存中的最新控制台终端日志流。"""
        denied = require_permissions(request, {"system:read"})
        if denied:
            return denied
        lines = get_console_logs(limit=min(2000, max(1, limit)), offset=max(0, offset))
        return JSONResponse({"ok": True, "logs": lines})

    @router.post("/system/logs/console/clear")
    def system_logs_console_clear(request: Request) -> JSONResponse:
        """清空内存控制台日志缓冲区。"""
        denied = require_permissions(request, {"system:write"})
        if denied:
            return denied
        clear_console_logs()
        return JSONResponse({"ok": True})

    return router


def project_update_error_response(exc: ProjectUpdateError) -> JSONResponse:
    """把项目更新错误映射为统一的 API 响应。"""

    return JSONResponse(
        {"ok": False, "error": {"code": exc.code, "message": exc.message}},
        status_code=exc.http_status,
    )

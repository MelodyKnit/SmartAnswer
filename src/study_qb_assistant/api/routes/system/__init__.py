"""平台系统管理与配置相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ....answering import AnswerService
from ....auth import AuthError
from ...context import (
    auth_error_response,
    get_lookup_service,
    get_platform_service,
    require_permissions,
    require_roles,
)
from ...route_support import apply_system_config_to_process
from ...schemas import SystemConfigPayload


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
    def system_config_patch(request: Request, payload: SystemConfigPayload) -> JSONResponse:
        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"system:write"})
        if denied:
            return denied
        platform = get_platform_service(request)
        values = {key: value for key, value in payload.model_dump().items() if value is not None}
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

    @router.get("/project-update/status")
    def project_update_status(request: Request) -> JSONResponse:
        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"system:write"})
        if denied:
            return denied
        platform = get_platform_service(request)
        try:
            payload = platform.project_update_status(refresh_remote=False)
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "update": payload})

    @router.post("/project-update/check")
    def project_update_check(request: Request) -> JSONResponse:
        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"system:write"})
        if denied:
            return denied
        platform = get_platform_service(request)
        try:
            payload = platform.project_update_status(refresh_remote=True)
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "update": payload})

    @router.post("/project-update/apply")
    def project_update_apply(request: Request) -> JSONResponse:
        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"system:write"})
        if denied:
            return denied
        platform = get_platform_service(request)
        try:
            payload = platform.apply_project_update()
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "update": payload})

    return router

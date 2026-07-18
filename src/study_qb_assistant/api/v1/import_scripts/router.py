"""平台导入脚本模板相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ....auth import AuthError
from ...dependencies import get_import_script_service, get_settings_service
from ...security import (
    auth_error_response,
    current_user,
    require_permissions,
    require_roles,
)
from ...http import base_url_from_request
from .schemas import ImportScriptCreatePayload, ImportScriptGeneratePayload


def build_import_script_router() -> APIRouter:
    """构建导入脚本模板目录与预览路由。"""
    router = APIRouter()

    @router.get("/import-scripts")
    def import_scripts(request: Request) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"import-scripts:read"})
        if denied:
            return denied
        platform = get_import_script_service(request)
        settings = get_settings_service(request)
        return JSONResponse(
            {
                "ok": True,
                "scripts": platform.list_import_scripts(
                    platform_name=str(settings.get_site_config()["site_title"])
                ),
            }
        )

    @router.post("/import-scripts")
    def import_script_create(request: Request, payload: ImportScriptCreatePayload) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"import-scripts:write"})
        if denied:
            return denied
        platform = get_import_script_service(request)
        actor = current_user(request)
        try:
            script = platform.create_import_script(
                name=payload.name,
                target=payload.target,
                description=payload.description,
                script_template=payload.script_template,
                config_items=list(payload.config_items),
                tags=list(payload.tags),
                requires_token=payload.requires_token,
                is_default=payload.is_default,
                created_by=str(actor["username"]) if actor else "",
            )
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "script": script})

    @router.post("/import-scripts/generate")
    def import_script_generate(
        request: Request, payload: ImportScriptGeneratePayload
    ) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"import-scripts:write"})
        if denied:
            return denied
        platform = get_import_script_service(request)
        try:
            script = platform.generate_import_script(
                name=payload.name,
                token_id=payload.token_id,
                target=payload.target,
                include_test_snippet=payload.include_test_snippet,
            )
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "script": script})

    @router.get("/import-scripts/{script_id}")
    def import_script_get(request: Request, script_id: str) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"import-scripts:read"})
        if denied:
            return denied
        platform = get_import_script_service(request)
        settings = get_settings_service(request)
        try:
            item = platform.get_import_script(
                script_id,
                base_url=base_url_from_request(request, settings),
                platform_name=str(settings.get_site_config()["site_title"]),
            )
        except AuthError as exc:
            return auth_error_response(exc)
        if item is None:
            return auth_error_response(
                AuthError("SCRIPT_NOT_FOUND", "导入脚本不存在", http_status=404)
            )
        return JSONResponse({"ok": True, "script": item})

    @router.delete("/import-scripts/{script_id}")
    def import_script_delete(request: Request, script_id: str) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"import-scripts:write"})
        if denied:
            return denied
        platform = get_import_script_service(request)
        try:
            platform.delete_import_script(script_id)
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True})

    return router

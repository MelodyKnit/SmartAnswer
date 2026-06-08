"""平台接入管理与导入脚本相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ...auth import AuthError
from ..context import auth_error_response, get_platform_service, require_roles
from ..schemas import ImportScriptGeneratePayload, IntegrationCreatePayload, IntegrationUpdatePayload


def build_platform_integration_router() -> APIRouter:
    """构建接入点与导入脚本路由。"""
    router = APIRouter()

    @router.get("/integrations")
    def integrations(request: Request) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        platform = get_platform_service(request)
        return JSONResponse({"ok": True, "integrations": platform.list_integrations()})

    @router.post("/integrations")
    def integration_create(request: Request, payload: IntegrationCreatePayload) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        platform = get_platform_service(request)
        item = platform.create_integration(
            name=payload.name,
            platform=payload.platform,
            base_url=payload.base_url,
            token_id=payload.token_id,
            status=payload.status,
            description=payload.description,
        )
        return JSONResponse({"ok": True, "integration": item})

    @router.get("/integrations/{integration_id}")
    def integration_get(request: Request, integration_id: str) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        platform = get_platform_service(request)
        item = platform.get_integration(integration_id)
        if item is None:
            return JSONResponse({"ok": False, "error": {"code": "INTEGRATION_NOT_FOUND", "message": "接入点不存在"}}, status_code=404)
        return JSONResponse({"ok": True, "integration": item})

    @router.patch("/integrations/{integration_id}")
    def integration_update(request: Request, integration_id: str, payload: IntegrationUpdatePayload) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        platform = get_platform_service(request)
        try:
            item = platform.update_integration(integration_id, payload.model_dump())
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "integration": item})

    @router.delete("/integrations/{integration_id}")
    def integration_delete(request: Request, integration_id: str) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        platform = get_platform_service(request)
        deleted = platform.delete_integration(integration_id)
        if not deleted:
            return JSONResponse({"ok": False, "error": {"code": "INTEGRATION_NOT_FOUND", "message": "接入点不存在"}}, status_code=404)
        return JSONResponse({"ok": True})

    @router.post("/integrations/{integration_id}/test")
    def integration_test(request: Request, integration_id: str) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        platform = get_platform_service(request)
        try:
            result = platform.test_integration(integration_id)
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse(result)

    @router.get("/integrations/{integration_id}/status")
    def integration_status(request: Request, integration_id: str) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        platform = get_platform_service(request)
        item = platform.get_integration(integration_id)
        if item is None:
            return JSONResponse({"ok": False, "error": {"code": "INTEGRATION_NOT_FOUND", "message": "接入点不存在"}}, status_code=404)
        return JSONResponse({"ok": True, "status": item})

    @router.get("/import-scripts")
    def import_scripts(request: Request) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        platform = get_platform_service(request)
        return JSONResponse({"ok": True, "scripts": platform.list_import_scripts()})

    @router.post("/import-scripts/generate")
    def import_script_generate(request: Request, payload: ImportScriptGeneratePayload) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        platform = get_platform_service(request)
        script = platform.generate_import_script(
            name=payload.name,
            integration_id=payload.integration_id,
            token_id=payload.token_id,
            target=payload.target,
            include_test_snippet=payload.include_test_snippet,
        )
        return JSONResponse({"ok": True, "script": script})

    @router.get("/import-scripts/{script_id}")
    def import_script_get(request: Request, script_id: str) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        platform = get_platform_service(request)
        item = platform.get_import_script(script_id)
        if item is None:
            return JSONResponse({"ok": False, "error": {"code": "SCRIPT_NOT_FOUND", "message": "脚本不存在"}}, status_code=404)
        return JSONResponse({"ok": True, "script": item})

    @router.delete("/import-scripts/{script_id}")
    def import_script_delete(request: Request, script_id: str) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        platform = get_platform_service(request)
        deleted = platform.delete_import_script(script_id)
        if not deleted:
            return JSONResponse({"ok": False, "error": {"code": "SCRIPT_NOT_FOUND", "message": "脚本不存在"}}, status_code=404)
        return JSONResponse({"ok": True})

    return router

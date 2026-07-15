"""角色权限接口。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ....auth import AuthError
from ...dependencies import get_permission_service
from ...security import auth_error_response, require_permissions, require_roles
from .schemas import RolePermissionPayload


def build_permission_router() -> APIRouter:
    """构建当前业务域路由。"""

    router = APIRouter()

    @router.get("/roles")
    def roles(request: Request) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"roles:read"})
        if denied:
            return denied
        platform = get_permission_service(request)
        return JSONResponse({"ok": True, "roles": platform.list_role_permissions()})

    @router.get("/roles/{role_id}/permissions")
    def role_permissions(request: Request, role_id: str) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"roles:read"})
        if denied:
            return denied
        platform = get_permission_service(request)
        try:
            item = platform.get_role_permissions(role_id)
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "role": item})

    @router.put("/roles/{role_id}/permissions")
    def role_permissions_update(
        request: Request, role_id: str, payload: RolePermissionPayload
    ) -> JSONResponse:
        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"roles:write"})
        if denied:
            return denied
        platform = get_permission_service(request)
        try:
            item = platform.set_role_permissions(role_id, tuple(payload.permissions))
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "role": item})

    return router

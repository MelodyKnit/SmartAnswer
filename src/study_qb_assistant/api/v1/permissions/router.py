"""角色与权限目录接口。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ....auth import AuthError
from ...dependencies import get_permission_service
from ...security import (
    auth_error_response,
    current_user,
    require_permissions,
    require_roles,
)
from .schemas import RoleCreatePayload, RolePermissionPayload, RoleUpdatePayload


def build_permission_router() -> APIRouter:
    """构建角色资源与权限目录路由。"""

    router = APIRouter()

    @router.get("/roles")
    def roles(request: Request) -> JSONResponse:
        denied = require_permissions(request, {"roles:read"})
        if denied:
            return denied
        service = get_permission_service(request)
        return JSONResponse(
            {
                "ok": True,
                "roles": service.list_roles(),
                "permission_catalog": service.permission_catalog(),
            }
        )

    @router.get("/roles/{role_id}/permissions")
    def role_permissions(request: Request, role_id: str) -> JSONResponse:
        denied = require_permissions(request, {"roles:read"})
        if denied:
            return denied
        service = get_permission_service(request)
        try:
            role = service.get_role(role_id)
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "role": role})

    @router.get("/roles/{role_id}")
    def role_detail(request: Request, role_id: str) -> JSONResponse:
        """读取单个角色，供页面按需刷新角色详情。"""

        denied = require_permissions(request, {"roles:read"})
        if denied:
            return denied
        service = get_permission_service(request)
        try:
            role = service.get_role(role_id)
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "role": role})

    @router.post("/roles", status_code=201)
    def role_create(request: Request, payload: RoleCreatePayload) -> JSONResponse:
        """仅超级管理员可创建不继承权限的自定义角色。"""

        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"roles:write"})
        if denied:
            return denied
        service = get_permission_service(request)
        try:
            role = service.create_role(
                role_id=payload.role_id,
                name=payload.name,
                description=payload.description,
                permissions=tuple(payload.permissions),
            )
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "role": role}, status_code=201)

    @router.patch("/roles/{role_id}")
    def role_update(
        request: Request, role_id: str, payload: RoleUpdatePayload
    ) -> JSONResponse:
        """更新角色；委托管理员只能维护自身权限范围内的自定义角色。"""

        denied = require_permissions(request, {"roles:write"})
        if denied:
            return denied
        service = get_permission_service(request)
        actor = current_user(request) or {}
        try:
            role = service.update_role(
                role_id,
                name=payload.name,
                description=payload.description,
                permissions=tuple(payload.permissions) if payload.permissions is not None else None,
                actor_role_id=str(actor.get("role") or ""),
                actor_permissions=set(actor.get("permissions") or ()),
            )
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "role": role})

    @router.put("/roles/{role_id}/permissions")
    def role_permissions_update(
        request: Request, role_id: str, payload: RolePermissionPayload
    ) -> JSONResponse:
        """兼容既有权限更新接口，并执行委托权限边界。"""

        denied = require_permissions(request, {"roles:write"})
        if denied:
            return denied
        service = get_permission_service(request)
        actor = current_user(request) or {}
        try:
            role = service.set_role_permissions(
                role_id,
                tuple(payload.permissions),
                actor_role_id=str(actor.get("role") or ""),
                actor_permissions=set(actor.get("permissions") or ()),
            )
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "role": role})

    @router.delete("/roles/{role_id}")
    def role_delete(request: Request, role_id: str) -> JSONResponse:
        """仅超级管理员可以删除未被分配的自定义角色。"""

        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"roles:write"})
        if denied:
            return denied
        service = get_permission_service(request)
        try:
            service.delete_role(role_id)
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "role_id": role_id, "deleted": True})

    return router

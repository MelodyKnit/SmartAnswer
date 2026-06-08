"""平台套餐与角色权限相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ...auth import AuthError
from ..context import auth_error_response, get_platform_service, require_roles
from ..schemas import QuotaPackagePayload, RolePermissionPayload


def build_platform_catalog_router() -> APIRouter:
    """构建套餐目录和角色权限路由。"""
    router = APIRouter()

    @router.get("/quota-packages")
    def quota_packages(request: Request) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        platform = get_platform_service(request)
        return JSONResponse({"ok": True, "packages": platform.list_quota_packages()})

    @router.post("/quota-packages")
    def quota_package_create(request: Request, payload: QuotaPackagePayload) -> JSONResponse:
        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        platform = get_platform_service(request)
        item = platform.create_quota_package(
            name=payload.name,
            kind=payload.kind,
            points=payload.points,
            subscription_days=payload.subscription_days,
            price=payload.price,
            status=payload.status,
            description=payload.description,
            sort_order=payload.sort_order,
        )
        return JSONResponse({"ok": True, "package": item})

    @router.patch("/quota-packages/{package_id}")
    def quota_package_update(request: Request, package_id: str, payload: QuotaPackagePayload) -> JSONResponse:
        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        platform = get_platform_service(request)
        try:
            item = platform.update_quota_package(package_id, payload.model_dump())
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "package": item})

    @router.delete("/quota-packages/{package_id}")
    def quota_package_delete(request: Request, package_id: str) -> JSONResponse:
        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        platform = get_platform_service(request)
        deleted = platform.delete_quota_package(package_id)
        if not deleted:
            return JSONResponse({"ok": False, "error": {"code": "PACKAGE_NOT_FOUND", "message": "套餐不存在"}}, status_code=404)
        return JSONResponse({"ok": True})

    @router.get("/roles")
    def roles(request: Request) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        platform = get_platform_service(request)
        return JSONResponse({"ok": True, "roles": platform.list_role_permissions()})

    @router.get("/roles/{role_id}/permissions")
    def role_permissions(request: Request, role_id: str) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        platform = get_platform_service(request)
        try:
            item = platform.get_role_permissions(role_id)
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "role": item})

    @router.put("/roles/{role_id}/permissions")
    def role_permissions_update(request: Request, role_id: str, payload: RolePermissionPayload) -> JSONResponse:
        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        platform = get_platform_service(request)
        item = platform.set_role_permissions(role_id, tuple(payload.permissions))
        return JSONResponse({"ok": True, "role": item})

    return router

"""平台用户相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ....auth import AuthError
from ...context import (
    auth_error_response,
    current_user,
    get_auth_service,
    get_platform_service,
    require_permissions,
    require_roles,
    unauthorized_response,
)
from ...schemas import (
    PasswordChangePayload,
    ProfileUpdatePayload,
    UserUpdatePayload,
    UsersDeletePayload,
)


def build_user_router() -> APIRouter:
    """构建用户域路由。"""
    router = APIRouter()

    @router.get("/users/me")
    def users_me(request: Request) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        return JSONResponse(
            {
                "ok": True,
                "user": user,
                "billing": platform.get_billing(),
                "wallet": platform.wallet_summary(
                    user_id=str(user["user_id"]),
                    username=str(user["username"]),
                    points=int(user["points"]),
                ),
            }
        )

    @router.patch("/users/me/profile")
    def update_profile(request: Request, payload: ProfileUpdatePayload) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        auth = get_auth_service(request)
        try:
            updated = auth.set_display_name(str(user["username"]), payload.display_name)
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "user": updated})

    @router.post("/users/me/password")
    def change_password(request: Request, payload: PasswordChangePayload) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        auth = get_auth_service(request)
        try:
            auth.change_password(str(user["username"]), payload.old_password, payload.new_password)
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "message": "密码已修改，请重新登录"})

    @router.get("/users")
    def users_list(request: Request) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"users:write"})
        if denied:
            return denied
        auth = get_auth_service(request)
        return JSONResponse({"ok": True, "users": auth.list_users()})

    @router.patch("/users/{username}")
    def users_update(request: Request, username: str, payload: UserUpdatePayload) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"users:write"})
        if denied:
            return denied
        auth = get_auth_service(request)
        actor = current_user(request)
        try:
            user = auth.get_user(username)
            if user is None:
                raise AuthError("USER_NOT_FOUND", "用户不存在", http_status=404)
            if actor is None:
                raise AuthError("UNAUTHORIZED", "请先登录", http_status=401)
            if actor["role"] == "admin" and user["role"] != "user":
                raise AuthError("FORBIDDEN", "管理员只能管理普通用户", http_status=403)
            if payload.role is not None and actor["role"] != "superadmin":
                raise AuthError("FORBIDDEN", "只有超级管理员可以调整用户等级", http_status=403)
            if payload.role is not None:
                user = auth.set_role(username, payload.role)
            if payload.points is not None:
                user = auth.set_points(username, payload.points)
            if payload.status is not None:
                user = auth.set_status(username, payload.status)
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "user": user})

    @router.post("/users/batch-delete")
    def users_batch_delete(request: Request, payload: UsersDeletePayload) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"users:write"})
        if denied:
            return denied
        actor = current_user(request)
        if actor is None:
            return unauthorized_response("请先登录")
        auth = get_auth_service(request)
        deleted: list[str] = []
        skipped: list[dict] = []
        for raw_name in payload.usernames:
            name = str(raw_name).strip()
            if not name:
                continue
            if name == actor["username"]:
                skipped.append({"username": name, "reason": "不能删除自己"})
                continue
            target = auth.get_user(name)
            if target is None:
                skipped.append({"username": name, "reason": "用户不存在"})
                continue
            # 管理员只能删除普通用户；超管不能删除其他超管
            if actor["role"] == "admin" and target["role"] != "user":
                skipped.append({"username": name, "reason": "管理员只能删除普通用户"})
                continue
            if actor["role"] == "superadmin" and target["role"] == "superadmin":
                skipped.append({"username": name, "reason": "不能删除超级管理员"})
                continue
            if auth.delete_user(name):
                deleted.append(name)
        return JSONResponse({"ok": True, "deleted": deleted, "skipped": skipped})

    return router

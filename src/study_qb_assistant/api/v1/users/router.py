"""平台用户、用户组分配与个人资料相关路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ....auth import AuthError
from ...dependencies import (
    get_auth_service,
    get_permission_service,
    get_settings_service,
    get_usage_service,
    get_wallet_service,
)
from ...security import (
    auth_error_response,
    current_user,
    require_permissions,
    unauthorized_response,
)
from .schemas import (
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
        settings = get_settings_service(request)
        permission_service = get_permission_service(request)
        wallet_service = get_wallet_service(request)
        invite_reward = settings.get_invite_reward_policy()
        return JSONResponse(
            {
                "ok": True,
                "user": enrich_user_role(user, permission_service),
                "billing": {
                    **settings.get_billing(),
                    "invite_bonus_points": invite_reward["points"],
                    "invite_reward_mode": invite_reward["mode"],
                },
                "wallet": wallet_service.wallet_summary(
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
        permission_service = get_permission_service(request)
        try:
            updated = auth.set_display_name(str(user["username"]), payload.display_name)
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "user": enrich_user_role(updated, permission_service)})

    @router.post("/users/me/invite-code")
    def ensure_invite_code(request: Request) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        auth = get_auth_service(request)
        permission_service = get_permission_service(request)
        updated = auth.ensure_invite_code_for_user(str(user["username"]))
        if updated is None:
            return auth_error_response(AuthError("USER_NOT_FOUND", "用户不存在", http_status=404))
        return JSONResponse({"ok": True, "user": enrich_user_role(updated, permission_service)})

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
        denied = require_permissions(request, {"users:write"})
        if denied:
            return denied
        auth = get_auth_service(request)
        permission_service = get_permission_service(request)
        usage_counts = get_usage_service(request).user_usage_counts()
        users = auth.list_users()
        for user in users:
            user["usage_count"] = usage_counts.get(str(user["username"]), 0)
            user.update(role_summary(str(user["role"]), permission_service))
        return JSONResponse({"ok": True, "users": users})

    @router.patch("/users/{username}")
    def users_update(request: Request, username: str, payload: UserUpdatePayload) -> JSONResponse:
        denied = require_permissions(request, {"users:write"})
        if denied:
            return denied
        auth = get_auth_service(request)
        permission_service = get_permission_service(request)
        actor = current_user(request)
        try:
            user = auth.get_user(username)
            if user is None:
                raise AuthError("USER_NOT_FOUND", "用户不存在", http_status=404)
            if actor is None:
                raise AuthError("UNAUTHORIZED", "请先登录", http_status=401)
            if actor["role"] != "superadmin" and user["role"] != "user":
                raise AuthError("FORBIDDEN", "只能管理普通用户", http_status=403)
            if payload.role is not None and actor["role"] != "superadmin":
                raise AuthError("FORBIDDEN", "只有超级管理员可以调整用户角色", http_status=403)
            if payload.role is not None:
                role_ids = {item["role_id"] for item in permission_service.list_roles()}
                user = auth.set_role(username, payload.role, valid_role_ids=role_ids)
            if payload.points is not None:
                user = auth.set_points(username, payload.points)
            if payload.status is not None:
                user = auth.set_status(username, payload.status)
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "user": enrich_user_role(user, permission_service)})

    @router.post("/users/batch-delete")
    def users_batch_delete(request: Request, payload: UsersDeletePayload) -> JSONResponse:
        denied = require_permissions(request, {"users:write"})
        if denied:
            return denied
        actor = current_user(request)
        if actor is None:
            return unauthorized_response("请先登录")
        auth = get_auth_service(request)
        deleted: list[str] = []
        skipped: list[dict[str, str]] = []
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
            if actor["role"] != "superadmin" and target["role"] != "user":
                skipped.append({"username": name, "reason": "只能删除普通用户"})
                continue
            if actor["role"] == "superadmin" and target["role"] == "superadmin":
                skipped.append({"username": name, "reason": "不能删除超级管理员"})
                continue
            if auth.delete_user(name):
                deleted.append(name)
        return JSONResponse({"ok": True, "deleted": deleted, "skipped": skipped})

    return router


def enrich_user_role(user: dict[str, Any], permission_service: Any) -> dict[str, Any]:
    """为当前用户补充角色名称和生效权限，供前端授权与展示使用。"""

    payload = dict(user)
    role_id = str(user.get("role") or "")
    payload.update(role_summary(role_id, permission_service))
    try:
        payload["permissions"] = sorted(permission_service.role_permissions(role_id))
    except AuthError:
        payload["permissions"] = []
    return payload


def role_summary(role_id: str, permission_service: Any) -> dict[str, str | bool]:
    """返回用户列表可安全展示的角色摘要。"""

    try:
        role = permission_service.get_role(role_id)
    except AuthError:
        return {"role_name": role_id or "未知角色", "role_is_system": False}
    return {"role_name": str(role["name"]), "role_is_system": bool(role["is_system"])}

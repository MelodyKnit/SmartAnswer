"""平台管理后台相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ...answering import AnswerService
from ...auth import AuthError
from ..context import (
    auth_error_response,
    current_user,
    get_auth_service,
    get_lookup_service,
    get_platform_service,
    require_roles,
    unauthorized_response,
)
from ..route_support import apply_system_config_to_process
from ..schemas import BillingPayload, SystemConfigPayload, TokenCreatePayload, UserUpdatePayload


def build_platform_admin_router() -> APIRouter:
    """构建用户管理、令牌管理和系统配置路由。"""
    router = APIRouter()

    @router.get("/users")
    def users_list(request: Request) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        auth = get_auth_service(request)
        return JSONResponse({"ok": True, "users": auth.list_users()})

    @router.patch("/users/{username}")
    def users_update(request: Request, username: str, payload: UserUpdatePayload) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
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

    @router.get("/tokens")
    def tokens_list(request: Request) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        return JSONResponse({"ok": True, "tokens": platform.list_tokens(user_id=str(user["user_id"]))})

    @router.post("/tokens")
    def tokens_create(request: Request, payload: TokenCreatePayload) -> JSONResponse:
        from ...adapters import build_ocs_config
        from ..route_support import base_url_from_request

        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        raw_token, token_info = platform.create_token(user_id=str(user["user_id"]), description=payload.description)
        token_config = build_ocs_config(base_url_from_request(request))[0]
        token_config["headers"] = {"Authorization": f"Bearer {raw_token}"}
        return JSONResponse({"ok": True, "token": raw_token, "token_info": token_info, "ocs_config": token_config})

    @router.post("/tokens/{token_id}/revoke")
    def tokens_revoke(request: Request, token_id: str) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        try:
            token = platform.revoke_token(user_id=str(user["user_id"]), token_id=token_id)
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "token": token})

    @router.get("/billing")
    def billing_get(request: Request) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        platform = get_platform_service(request)
        return JSONResponse({"ok": True, "billing": platform.get_billing()})

    @router.patch("/billing")
    def billing_update(request: Request, payload: BillingPayload) -> JSONResponse:
        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        platform = get_platform_service(request)
        values = {key: value for key, value in payload.model_dump().items() if value is not None}
        try:
            billing = platform.set_billing(values)
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "billing": billing})

    @router.get("/system-config")
    def system_config_get(request: Request) -> JSONResponse:
        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        platform = get_platform_service(request)
        return JSONResponse({"ok": True, "config": platform.get_system_config()})

    @router.patch("/system-config")
    def system_config_patch(request: Request, payload: SystemConfigPayload) -> JSONResponse:
        denied = require_roles(request, {"superadmin"})
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
            from ...runtime import refresh_answer_service

            refresh_answer_service(lookup)
        return JSONResponse({"ok": True, "config": config, "reload_required": False})

    return router

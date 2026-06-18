"""平台 API 令牌相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ....auth import AuthError
from ...context import (
    auth_error_response,
    current_user,
    get_platform_service,
    unauthorized_response,
)
from ...route_support import base_url_from_request
from ...schemas import TokenCreatePayload


def build_token_router() -> APIRouter:
    """构建 API 令牌域路由。"""
    router = APIRouter()

    @router.get("/tokens")
    def tokens_list(request: Request) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        return JSONResponse(
            {"ok": True, "tokens": platform.list_tokens(user_id=str(user["user_id"]))}
        )

    @router.post("/tokens")
    def tokens_create(request: Request, payload: TokenCreatePayload) -> JSONResponse:
        from ....adapters import build_ocs_config

        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        raw_token, token_info = platform.create_token(
            user_id=str(user["user_id"]),
            description=payload.description,
            quota_limit=payload.quota_limit,
            reject_low_confidence=payload.reject_low_confidence,
            min_answer_confidence=payload.min_answer_confidence,
        )
        token_config = build_ocs_config(base_url_from_request(request, platform))
        token_config[0]["headers"] = {"Authorization": f"Bearer {raw_token}"}
        return JSONResponse(
            {"ok": True, "token": raw_token, "token_info": token_info, "ocs_config": token_config}
        )

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

    @router.post("/tokens/{token_id}")
    def tokens_update(request: Request, token_id: str, payload: TokenCreatePayload) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        try:
            token = platform.update_token(
                user_id=str(user["user_id"]),
                token_id=token_id,
                description=payload.description,
                quota_limit=payload.quota_limit,
                reject_low_confidence=payload.reject_low_confidence,
                min_answer_confidence=payload.min_answer_confidence,
            )
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "token": token})

    @router.delete("/tokens/{token_id}")
    def tokens_delete(request: Request, token_id: str) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        try:
            platform.delete_token(user_id=str(user["user_id"]), token_id=token_id)
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "message": "令牌已删除"})

    @router.get("/tokens/import-script")
    def token_import_script(
        request: Request,
        token_id: str | None = None,
        template_id: str | None = None,
    ) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        try:
            payload = platform.token_import_script(
                user_id=str(user["user_id"]),
                base_url=base_url_from_request(request, platform),
                token_id=token_id,
                template_id=template_id,
            )
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, **payload})

    return router

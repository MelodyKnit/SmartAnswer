"""平台 API 令牌相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ....auth import AuthError
from ...dependencies import get_settings_service, get_token_service
from ...security import (
    auth_error_response,
    current_user,
    unauthorized_response,
)
from ...http import base_url_from_request
from .schemas import TokenCreatePayload


def build_token_router() -> APIRouter:
    """构建 API 令牌域路由。"""
    router = APIRouter()

    @router.get("/tokens")
    def tokens_list(request: Request) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_token_service(request)
        return JSONResponse(
            {"ok": True, "tokens": platform.list_tokens(user_id=str(user["user_id"]))}
        )

    @router.post("/tokens")
    def tokens_create(request: Request, payload: TokenCreatePayload) -> JSONResponse:
        from ....adapters import build_ocs_config

        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_token_service(request)
        raw_token, token_info = platform.create_token(
            user_id=str(user["user_id"]),
            description=payload.description,
            quota_limit=payload.quota_limit,
            reject_low_confidence=payload.reject_low_confidence,
            min_answer_confidence=payload.min_answer_confidence,
        )
        settings = get_settings_service(request)
        token_config = build_ocs_config(
            base_url_from_request(request, settings),
            platform_name=str(settings.get_site_config()["site_title"]),
            token_description=str(token_info["description"]),
            token_key_mask=str(token_info["key_mask"]),
        )
        token_config[0]["headers"] = {"Authorization": f"Bearer {raw_token}"}
        return JSONResponse(
            {"ok": True, "token": raw_token, "token_info": token_info, "ocs_config": token_config},
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )

    @router.post("/tokens/{token_id}/revoke")
    def tokens_revoke(request: Request, token_id: str) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_token_service(request)
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
        platform = get_token_service(request)
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
        platform = get_token_service(request)
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
        platform = get_token_service(request)
        try:
            payload = platform.token_import_script(
                user_id=str(user["user_id"]),
                base_url=base_url_from_request(request, get_settings_service(request)),
                platform_name=str(get_settings_service(request).get_site_config()["site_title"]),
                token_id=token_id,
                template_id=template_id,
            )
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse(
            {"ok": True, **payload},
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )

    @router.post("/tokens/{token_id}/copy-value")
    def tokens_copy_value(request: Request, token_id: str) -> JSONResponse:
        """由令牌所有者恢复完整 API Key，不在普通列表中返回原文。"""

        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_token_service(request)
        try:
            raw_token = platform.copy_token_value(user_id=str(user["user_id"]), token_id=token_id)
        except AuthError as exc:
            return auth_error_response(exc)

        return JSONResponse(
            {"ok": True, "token_id": token_id, "token": raw_token},
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )

    @router.post("/tokens/{token_id}/share-link")
    def tokens_share_link(request: Request, token_id: str) -> JSONResponse:
        """生成不落库的 fragment 分享链接。"""

        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_token_service(request)
        try:
            share = platform.create_share_link(
                user_id=str(user["user_id"]),
                token_id=token_id,
                base_url=base_url_from_request(request, get_settings_service(request)),
            )
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse(
            {"ok": True, **share},
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )

    return router

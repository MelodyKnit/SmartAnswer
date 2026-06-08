"""平台钱包与兑换码相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ...auth import AuthError
from ..context import (
    auth_error_response,
    current_user,
    forbidden_response,
    get_auth_service,
    get_platform_service,
    require_roles,
    unauthorized_response,
)
from ..schemas import RedeemCodePayload, WalletGrantPayload, WalletRedeemPayload


def build_platform_wallet_router() -> APIRouter:
    """构建钱包、充值和兑换码相关路由。"""
    router = APIRouter()

    @router.get("/wallet/me")
    def wallet_me(request: Request) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        wallet = platform.wallet_summary(
            user_id=str(user["user_id"]),
            username=str(user["username"]),
            points=int(user["points"]),
        )
        return JSONResponse({"ok": True, "wallet": wallet})

    @router.get("/wallet/orders")
    def wallet_orders(request: Request, username: str | None = None, limit: int = 100) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        if user["role"] not in {"admin", "superadmin"}:
            username = str(user["username"])
        orders = platform.list_wallet_orders(username=username, limit=limit)
        return JSONResponse({"ok": True, "orders": orders})

    @router.post("/wallet/grants")
    def wallet_grants(request: Request, payload: WalletGrantPayload) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        auth = get_auth_service(request)
        platform = get_platform_service(request)
        actor = current_user(request)
        target = auth.get_user(payload.username)
        if actor is None:
            return unauthorized_response("请先登录")
        if target is None:
            return JSONResponse({"ok": False, "error": {"code": "USER_NOT_FOUND", "message": "用户不存在"}}, status_code=404)
        if actor["role"] == "admin" and target["role"] != "user":
            return forbidden_response("管理员只能为普通用户充值")
        order = platform.grant_wallet(
            user_id=str(target["user_id"]),
            username=str(target["username"]),
            created_by=str(actor["username"]),
            kind=payload.kind,
            points=payload.points,
            subscription_days=payload.subscription_days,
            source="manual_credit",
        )
        if payload.kind == "points" and payload.points:
            auth.set_points(payload.username, int(target["points"]) + max(0, int(payload.points)))
        return JSONResponse({"ok": True, "order": order})

    @router.get("/wallet/redeem-codes")
    def wallet_redeem_codes(request: Request) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        platform = get_platform_service(request)
        return JSONResponse({"ok": True, "redeem_codes": platform.list_redeem_codes()})

    @router.post("/wallet/redeem-codes")
    def wallet_redeem_codes_create(request: Request, payload: RedeemCodePayload) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        platform = get_platform_service(request)
        actor = current_user(request)
        if actor is None:
            return unauthorized_response("请先登录")
        try:
            code = platform.create_redeem_code(
                created_by=str(actor["username"]),
                kind=payload.kind,
                points=payload.points,
                subscription_days=payload.subscription_days,
                max_uses=payload.max_uses,
                expires_at=payload.expires_at,
            )
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "redeem_code": code})

    @router.post("/wallet/redeem")
    def wallet_redeem(request: Request, payload: WalletRedeemPayload) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        auth = get_auth_service(request)
        platform = get_platform_service(request)
        try:
            order = platform.redeem_code(
                code=payload.code,
                user_id=str(user["user_id"]),
                username=str(user["username"]),
                created_by=str(user["username"]),
            )
        except AuthError as exc:
            return auth_error_response(exc)
        if order["kind"] == "points" and order["points_delta"] > 0:
            auth.set_points(str(user["username"]), int(user["points"]) + int(order["points_delta"]))
        latest_user = auth.get_user(str(user["username"]))
        wallet = platform.wallet_summary(
            user_id=str(user["user_id"]),
            username=str(user["username"]),
            points=int(latest_user["points"]) if latest_user else int(user["points"]),
        )
        return JSONResponse({"ok": True, "order": order, "wallet": wallet})

    return router

"""平台钱包、积分发放与兑换码相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ....auth import AuthError
from ...dependencies import get_auth_service, get_settings_service, get_wallet_service
from ...security import (
    auth_error_response,
    current_user,
    forbidden_response,
    require_permissions,
    unauthorized_response,
)
from .schemas import (
    BillingPayload,
    RedeemCodePayload,
    WalletGrantPayload,
    WalletRedeemPayload,
)


def build_wallet_router() -> APIRouter:
    """构建钱包与积分兑换域路由。"""
    router = APIRouter()

    # --- 钱包与交易记录 ---
    @router.get("/wallet/me")
    def wallet_me(request: Request) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        wallet_service = get_wallet_service(request)
        wallet = wallet_service.wallet_summary(
            user_id=str(user["user_id"]),
            username=str(user["username"]),
            points=int(user["points"]),
        )
        return JSONResponse({"ok": True, "wallet": wallet})

    @router.get("/wallet/orders")
    def wallet_orders(
        request: Request, source: str = "", limit: int = 100, page: int = 1
    ) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        wallet_service = get_wallet_service(request)
        page = max(1, int(page))
        limit = max(1, min(int(limit), 500))
        offset = (page - 1) * limit
        orders = wallet_service.list_wallet_orders(
            username=str(user["username"]),
            source=source.strip(),
            limit=limit,
            offset=offset,
        )
        total = wallet_service.count_wallet_orders(
            username=str(user["username"]), source=source.strip()
        )
        return JSONResponse(
            {"ok": True, "orders": orders, "total": total, "page": page, "limit": limit}
        )

    @router.get("/wallet/changes")
    def wallet_changes(
        request: Request,
        username: str = "",
        kind: str = "",
        source: str = "",
        limit: int = 100,
        page: int = 1,
    ) -> JSONResponse:
        denied = require_permissions(request, {"wallet:changes:read"})
        if denied:
            return denied
        wallet_service = get_wallet_service(request)
        page = max(1, int(page))
        limit = max(1, min(int(limit), 500))
        offset = (page - 1) * limit
        scoped_username = username.strip() or None
        orders = wallet_service.list_wallet_changes(
            username=scoped_username,
            kind=kind.strip(),
            source=source.strip(),
            limit=limit,
            offset=offset,
        )
        total = wallet_service.count_wallet_orders(
            username=scoped_username, kind=kind.strip(), source=source.strip()
        )
        return JSONResponse(
            {"ok": True, "orders": orders, "total": total, "page": page, "limit": limit}
        )

    @router.post("/wallet/grants")
    def wallet_grants(request: Request, payload: WalletGrantPayload) -> JSONResponse:
        denied = require_permissions(request, {"wallet:changes:write"})
        if denied:
            return denied
        auth = get_auth_service(request)
        wallet_service = get_wallet_service(request)
        actor = current_user(request)
        target = auth.get_user(payload.username)
        if actor is None:
            return unauthorized_response("请先登录")
        if target is None:
            return JSONResponse(
                {
                    "ok": False,
                    "error": {"code": "USER_NOT_FOUND", "message": "用户不存在"},
                },
                status_code=404,
            )
        if actor["role"] != "superadmin" and target["role"] != "user":
            return forbidden_response("只能为内置普通用户发放积分")
        order = wallet_service.grant_wallet(
            user_id=str(target["user_id"]),
            username=str(target["username"]),
            created_by=str(actor["username"]),
            kind=payload.kind,
            points=payload.points,
            source="manual_credit",
        )
        if payload.kind == "points" and payload.points:
            auth.add_points(payload.username, max(0, int(payload.points)))
        return JSONResponse({"ok": True, "order": order})

    # --- 兑换码管理 ---
    @router.get("/wallet/redeem-codes")
    def wallet_redeem_codes(request: Request) -> JSONResponse:
        denied = require_permissions(request, {"wallet:changes:write"})
        if denied:
            return denied
        wallet_service = get_wallet_service(request)
        return JSONResponse(
            {"ok": True, "redeem_codes": wallet_service.list_redeem_codes()}
        )

    @router.post("/wallet/redeem-codes")
    def wallet_redeem_codes_create(
        request: Request, payload: RedeemCodePayload
    ) -> JSONResponse:
        denied = require_permissions(request, {"wallet:changes:write"})
        if denied:
            return denied
        wallet_service = get_wallet_service(request)
        actor = current_user(request)
        if actor is None:
            return unauthorized_response("请先登录")
        try:
            code = wallet_service.create_redeem_code(
                created_by=str(actor["username"]),
                kind=payload.kind,
                points=payload.points,
                max_uses=payload.max_uses,
                expires_at=payload.expires_at,
                code=payload.code,
                count=payload.count,
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
        wallet_service = get_wallet_service(request)
        try:
            order = wallet_service.redeem_code(
                code=payload.code,
                user_id=str(user["user_id"]),
                username=str(user["username"]),
                created_by=str(user["username"]),
            )
        except AuthError as exc:
            return auth_error_response(exc)
        if order["kind"] == "points" and order["points_delta"] > 0:
            auth.add_points(str(user["username"]), int(order["points_delta"]))
        latest_user = auth.get_user(str(user["username"]))
        wallet = wallet_service.wallet_summary(
            user_id=str(user["user_id"]),
            username=str(user["username"]),
            points=int(latest_user["points"]) if latest_user else int(user["points"]),
        )
        return JSONResponse({"ok": True, "order": order, "wallet": wallet})

    @router.get("/points-policy")
    def points_policy_get(request: Request) -> JSONResponse:
        denied = require_permissions(request, {"billing:read"})
        if denied:
            return denied
        settings = get_settings_service(request)
        return JSONResponse({"ok": True, "points_policy": settings.get_points_policy()})

    # --- 计费费率与策略配置 ---
    @router.get("/billing")
    def billing_get(request: Request) -> JSONResponse:
        denied = require_permissions(request, {"billing:read"})
        if denied:
            return denied
        settings = get_settings_service(request)
        return JSONResponse({"ok": True, "billing": settings.get_billing()})

    @router.patch("/billing")
    def billing_update(request: Request, payload: BillingPayload) -> JSONResponse:
        denied = require_permissions(request, {"billing:write"})
        if denied:
            return denied
        settings = get_settings_service(request)
        values = {
            key: value
            for key, value in payload.model_dump().items()
            if value is not None
        }
        try:
            billing = settings.set_billing(values)
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "billing": billing})

    return router

"""平台钱包与积分兑换码业务辅助。"""

from __future__ import annotations

import math
import secrets
import time

from ..auth import AuthError
from .records import RedeemCodeRecord, WalletOrderRecord


def wallet_summary_payload(
    *,
    user_id: str,
    username: str,
    points: int,
) -> dict:
    """汇总用户钱包状态。"""

    return {
        "user_id": user_id,
        "username": username,
        "points": points,
    }


def create_redeem_code_entry(
    redeem_codes: dict[str, RedeemCodeRecord],
    *,
    created_by: str,
    kind: str,
    points: int = 0,
    max_uses: int = 1,
    expires_at: float = 0.0,
) -> dict:
    """创建积分兑换码。"""

    if kind != "points":
        raise AuthError("INVALID_INPUT", "兑换码类型仅支持 points", http_status=400)
    now = time.time()
    expires_at_value = float(expires_at or 0.0)
    if not math.isfinite(expires_at_value):
        raise AuthError("INVALID_INPUT", "兑换码有效期必须是有效时间戳", http_status=400)
    if expires_at_value < 0:
        raise AuthError("INVALID_INPUT", "兑换码有效期不能为负数", http_status=400)
    if expires_at_value and expires_at_value <= now:
        raise AuthError("INVALID_INPUT", "兑换码有效期必须晚于当前时间", http_status=400)
    code = "rc_" + secrets.token_urlsafe(10)
    redeem = RedeemCodeRecord(
        code_id=secrets.token_hex(12),
        code=code,
        kind="points",
        points=max(0, int(points)),
        max_uses=max(1, int(max_uses)),
        used_uses=0,
        status="active",
        created_by=created_by,
        created_at=now,
        expires_at=expires_at_value,
    )
    redeem_codes[redeem.code_id] = redeem
    return redeem.to_dict()


def list_redeem_code_entries(redeem_codes: dict[str, RedeemCodeRecord]) -> list[dict]:
    """列出全部兑换码。"""
    return [
        code.to_dict()
        for code in sorted(redeem_codes.values(), key=lambda item: item.created_at, reverse=True)
    ]


def grant_wallet_entry(
    wallet_orders: list[WalletOrderRecord],
    *,
    user_id: str,
    username: str,
    created_by: str,
    kind: str,
    points: int = 0,
    source: str = "manual_credit",
    source_id: str | None = None,
) -> dict:
    """手动发放积分，并写入钱包流水。"""

    if kind != "points":
        raise AuthError("INVALID_INPUT", "钱包类型仅支持 points", http_status=400)
    order = WalletOrderRecord(
        order_id=secrets.token_hex(12),
        user_id=user_id,
        username=username,
        kind="points",
        points_delta=max(0, int(points)),
        source=source,
        source_id=source_id,
        status="completed",
        created_by=created_by,
        created_at=time.time(),
    )
    wallet_orders.append(order)
    return order.to_dict()


def redeem_code_entry(
    redeem_codes: dict[str, RedeemCodeRecord],
    wallet_orders: list[WalletOrderRecord],
    *,
    code: str,
    user_id: str,
    username: str,
    created_by: str,
) -> dict:
    """核销兑换码，并转换成标准钱包流水。"""
    code = (code or "").strip()
    redeem = next((item for item in redeem_codes.values() if item.code == code), None)
    if redeem is None:
        raise AuthError("REDEEM_CODE_NOT_FOUND", "兑换码不存在", http_status=404)
    now = time.time()
    if redeem.status != "active":
        raise AuthError("REDEEM_CODE_DISABLED", "兑换码不可用", http_status=400)
    if redeem.expires_at and redeem.expires_at < now:
        redeem.status = "expired"
        raise AuthError("REDEEM_CODE_EXPIRED", "兑换码已过期", http_status=400)
    if redeem.used_uses >= redeem.max_uses:
        redeem.status = "exhausted"
        raise AuthError("REDEEM_CODE_EXHAUSTED", "兑换码已用完", http_status=400)
    redeem.used_uses += 1
    if redeem.used_uses >= redeem.max_uses:
        redeem.status = "exhausted"
    return grant_wallet_entry(
        wallet_orders,
        user_id=user_id,
        username=username,
        created_by=created_by,
        kind=redeem.kind,
        points=redeem.points,
        source="redeem_code",
        source_id=redeem.code_id,
    )


def list_wallet_order_entries(
    wallet_orders: list[WalletOrderRecord],
    *,
    username: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """按用户过滤钱包流水。"""
    orders = list(wallet_orders)
    if username:
        orders = [order for order in orders if order.username == username]
    orders = sorted(orders, key=lambda item: item.created_at, reverse=True)
    return [order.to_dict() for order in orders[: max(1, min(limit, 500))]]

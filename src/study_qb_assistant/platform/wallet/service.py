"""积分钱包与兑换码服务。"""

from __future__ import annotations

import math
import re
import secrets
import time
from collections.abc import Sequence
from typing import Any, cast

from ...auth import AuthError
from ..base import PlatformDomainService
from .errors import WalletOperationError
from .records import RedeemCodeRecord, WalletOrderRecord


class WalletService(PlatformDomainService):
    """WalletService 领域实现。"""

    def wallet_summary(
        self,
        *,
        user_id: str,
        username: str,
        points: int,
        unlimited_expires_at: float = 0.0,
    ) -> dict:
        """汇总用户钱包积分状态。"""

        try:
            expires_at = max(0.0, float(unlimited_expires_at or 0.0))
        except (TypeError, ValueError):
            expires_at = 0.0
        if not math.isfinite(expires_at):
            expires_at = 0.0
        with self.lock:
            return {
                "user_id": user_id,
                "username": username,
                "points": points,
                "unlimited_expires_at": expires_at,
                "is_unlimited": expires_at > time.time(),
            }

    def create_redeem_code(
        self,
        *,
        created_by: str,
        kind: str,
        points: int = 0,
        days: int = 0,
        max_uses: int = 1,
        expires_at: float = 0.0,
        code: str | None = None,
        count: int = 1,
    ) -> dict:
        """创建积分或天数兑换码。"""

        if kind not in ("points", "days"):
            raise AuthError("INVALID_INPUT", "兑换码类型仅支持 points 或 days", http_status=400)
        amount = require_positive_amount(
            points if kind == "points" else days,
            "积分数量" if kind == "points" else "兑换天数",
        )
        max_uses_value = require_positive_amount(max_uses, "可用次数")
        count_value = require_positive_amount(count, "批量创建兑换码的数量")
        if count_value > 1000:
            raise AuthError("INVALID_INPUT", "批量创建兑换码的数量必须在 1 到 1000 之间", http_status=400)
        if code and count_value > 1:
            raise AuthError("INVALID_INPUT", "批量创建不支持指定特定兑换码文字", http_status=400)

        now = time.time()
        expires_at_value = float(expires_at or 0.0)
        if not math.isfinite(expires_at_value):
            raise AuthError("INVALID_INPUT", "兑换码有效期必须是有效时间戳", http_status=400)
        if expires_at_value < 0:
            raise AuthError("INVALID_INPUT", "兑换码有效期不能为负数", http_status=400)
        if expires_at_value and expires_at_value <= now:
            raise AuthError("INVALID_INPUT", "兑换码有效期必须晚于当前时间", http_status=400)

        if code:
            code = code.strip()
            if len(code) < 3 or len(code) > 64:
                raise AuthError("INVALID_INPUT", "自定义兑换码长度必须在 3 到 64 之间", http_status=400)
            if not re.match(r"^[a-zA-Z0-9_\-]+$", code):
                raise AuthError("INVALID_INPUT", "自定义兑换码只能包含字母、数字、下划线和连字符", http_status=400)

        created_records = []
        with self.lock:
            if code:
                if self.repository.find_redeem_code_by_code(code):
                    raise AuthError("INVALID_INPUT", f"兑换码 {code} 已存在", http_status=400)

            for _ in range(count_value):
                actual_code = code if code else "rc_" + secrets.token_urlsafe(10)
                if not code:
                    while self.repository.find_redeem_code_by_code(actual_code):
                        actual_code = "rc_" + secrets.token_urlsafe(10)

                record = RedeemCodeRecord(
                    code_id=secrets.token_hex(12),
                    code=actual_code,
                    kind=kind,
                    points=amount if kind == "points" else 0,
                    days=amount if kind == "days" else 0,
                    max_uses=max_uses_value,
                    used_uses=0,
                    status="active",
                    created_by=created_by,
                    created_at=now,
                    expires_at=expires_at_value,
                )
                self.repository.save_redeem_code(record)
                created_records.append(record)

        return created_records[-1].to_dict()

    def list_redeem_codes(self) -> list[dict]:
        """列出全部兑换码。"""
        with self.lock:
            return [item.to_dict() for item in self.repository.list_redeem_codes()]

    def grant_wallet(
        self,
        *,
        user_id: str,
        username: str,
        created_by: str,
        kind: str,
        points: int = 0,
        days: int = 0,
        source: str = "manual_credit",
        source_id: str | None = None,
    ) -> dict:
        """手动发放积分或无限天数，并写入钱包流水。"""

        if kind not in ("points", "days"):
            raise AuthError("INVALID_INPUT", "钱包类型仅支持 points 或 days", http_status=400)
        amount = require_positive_amount(
            points if kind == "points" else days,
            "积分数量" if kind == "points" else "发放天数",
        )
        with self.lock:
            order = WalletOrderRecord(
                order_id=secrets.token_hex(12),
                user_id=user_id,
                username=username,
                kind=kind,
                points_delta=amount if kind == "points" else 0,
                days_delta=amount if kind == "days" else 0,
                source=source,
                source_id=source_id,
                status="completed",
                created_by=created_by,
                created_at=time.time(),
            )
            try:
                self.repository.grant_wallet_benefit(order)
            except WalletOperationError as exc:
                raise wallet_auth_error(exc) from exc
            return order.to_dict()

    def record_wallet_order(self, record: WalletOrderRecord) -> dict:
        """保存已生效的钱包流水记录。"""
        return self.record_wallet_orders((record,))[0]

    def record_wallet_orders(self, records: Sequence[WalletOrderRecord]) -> list[dict]:
        """在一个事务中保存多条已经生效的钱包流水记录。"""

        if not records:
            return []
        with self.lock:
            self.repository.save_wallet_orders(records)
            return [record.to_dict() for record in records]

    def redeem_code(
        self,
        *,
        code: str,
        user_id: str,
        username: str,
        created_by: str,
    ) -> dict:
        """核销兑换码，并转换成标准钱包流水。"""
        normalized_code = (code or "").strip()
        if not normalized_code:
            raise AuthError("INVALID_INPUT", "请输入兑换码", http_status=400)
        with self.lock:
            try:
                order = self.repository.redeem_code_and_grant_benefit(
                    code=normalized_code,
                    order_id=secrets.token_hex(12),
                    user_id=user_id,
                    username=username,
                    created_by=created_by,
                    now=time.time(),
                )
            except WalletOperationError as exc:
                raise wallet_auth_error(exc) from exc
            return order.to_dict()

    def list_wallet_orders(
        self,
        *,
        username: str | None = None,
        kind: str = "",
        source: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """按用户过滤钱包流水。"""
        with self.lock:
            return [
                item.to_dict()
                for item in self.repository.list_wallet_orders(
                    username=username,
                    kind=kind,
                    source=source,
                    limit=limit,
                    offset=offset,
                )
            ]

    def list_wallet_changes(
        self,
        *,
        username: str | None = None,
        kind: str = "",
        source: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """列出钱包变更流水，供管理端分页查看。"""

        return self.list_wallet_orders(
            username=username,
            kind=kind,
            source=source,
            limit=limit,
            offset=offset,
        )

    def count_wallet_orders(
        self,
        *,
        username: str | None = None,
        kind: str = "",
        source: str = "",
    ) -> int:
        """统计钱包流水数量。"""

        return len(
            self.list_wallet_orders(
                username=username,
                kind=kind,
                source=source,
                limit=5000,
            )
        )


def require_positive_amount(value: object, field_name: str) -> int:
    """严格校验正整数，避免小数或非有限数被静默截断。"""

    try:
        if isinstance(value, bool):
            raise ValueError
        if isinstance(value, int):
            amount = value
        elif isinstance(value, str):
            normalized = value.strip()
            if not re.fullmatch(r"\+?\d+", normalized):
                raise ValueError
            amount = int(normalized)
        else:
            numeric = float(cast(Any, value))
            if not math.isfinite(numeric) or not numeric.is_integer():
                raise ValueError
            amount = int(numeric)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AuthError("INVALID_INPUT", f"{field_name}必须是正整数", http_status=400) from exc
    if amount <= 0:
        raise AuthError("INVALID_INPUT", f"{field_name}必须大于 0", http_status=400)
    return amount


def wallet_auth_error(exc: WalletOperationError) -> AuthError:
    """将钱包仓储异常转换为现有统一鉴权业务异常。"""

    return AuthError(exc.code, exc.message, http_status=exc.http_status)

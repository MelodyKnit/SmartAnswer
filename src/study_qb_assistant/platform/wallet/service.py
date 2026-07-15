"""积分钱包与兑换码服务。"""

from __future__ import annotations

import math
import secrets
import time

from ...auth import AuthError
from ..base import PlatformDomainService
from .records import RedeemCodeRecord, WalletOrderRecord


class WalletService(PlatformDomainService):
    """WalletService 领域实现。"""

    def wallet_summary(self, *, user_id: str, username: str, points: int) -> dict:
        """汇总用户钱包积分状态。"""

        with self.lock:
            return {"user_id": user_id, "username": username, "points": points}

    def create_redeem_code(
        self,
        *,
        created_by: str,
        kind: str,
        points: int = 0,
        max_uses: int = 1,
        expires_at: float = 0.0,
        code: str | None = None,
        count: int = 1,
    ) -> dict:
        """创建积分兑换码。"""

        if kind != "points":
            raise AuthError("INVALID_INPUT", "兑换码类型仅支持 points", http_status=400)
        if count < 1 or count > 1000:
            raise AuthError("INVALID_INPUT", "批量创建兑换码的数量必须在 1 到 1000 之间", http_status=400)
        if code and count > 1:
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
            import re
            if not re.match(r"^[a-zA-Z0-9_\-]+$", code):
                raise AuthError("INVALID_INPUT", "自定义兑换码只能包含字母、数字、下划线和连字符", http_status=400)

        created_records = []
        with self.lock:
            if code:
                if self.repository.find_redeem_code_by_code(code):
                    raise AuthError("INVALID_INPUT", f"兑换码 {code} 已存在", http_status=400)

            for _ in range(count):
                actual_code = code if code else "rc_" + secrets.token_urlsafe(10)
                if not code:
                    while self.repository.find_redeem_code_by_code(actual_code):
                        actual_code = "rc_" + secrets.token_urlsafe(10)

                record = RedeemCodeRecord(
                    code_id=secrets.token_hex(12),
                    code=actual_code,
                    kind="points",
                    points=max(0, int(points)),
                    max_uses=max(1, int(max_uses)),
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
        source: str = "manual_credit",
        source_id: str | None = None,
    ) -> dict:
        """手动发放积分，并写入钱包流水。"""

        if kind != "points":
            raise AuthError("INVALID_INPUT", "钱包类型仅支持 points", http_status=400)
        with self.lock:
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
            self.repository.save_wallet_order(order)
            return order.to_dict()

    def redeem_code(
        self,
        *,
        code: str,
        user_id: str,
        username: str,
        created_by: str,
    ) -> dict:
        """核销兑换码，并转换成标准钱包流水。"""
        with self.lock:
            redeem = self.repository.find_redeem_code_by_code((code or "").strip())
            if redeem is None:
                raise AuthError("REDEEM_CODE_NOT_FOUND", "兑换码不存在", http_status=404)
            now = time.time()
            if redeem.status != "active":
                raise AuthError("REDEEM_CODE_DISABLED", "兑换码不可用", http_status=400)
            if redeem.expires_at and redeem.expires_at < now:
                redeem.status = "expired"
                self.repository.save_redeem_code(redeem)
                raise AuthError("REDEEM_CODE_EXPIRED", "兑换码已过期", http_status=400)
            if redeem.used_uses >= redeem.max_uses:
                redeem.status = "exhausted"
                self.repository.save_redeem_code(redeem)
                raise AuthError("REDEEM_CODE_EXHAUSTED", "兑换码已用完", http_status=400)
            redeem.used_uses += 1
            if redeem.used_uses >= redeem.max_uses:
                redeem.status = "exhausted"
            self.repository.save_redeem_code(redeem)
            return self.grant_wallet(
                user_id=user_id,
                username=username,
                created_by=created_by,
                kind=redeem.kind,
                points=redeem.points,
                source="redeem_code",
                source_id=redeem.code_id,
            )

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

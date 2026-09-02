"""积分钱包与兑换码仓储。"""

from __future__ import annotations

import time
from collections.abc import Sequence

from sqlalchemy import select

from ...platform.wallet.errors import WalletOperationError
from ...platform.wallet.records import RedeemCodeRecord, WalletOrderRecord
from ..orm import RedeemCodeEntity, UserEntity, WalletOrderEntity
from .base import SqlAlchemyRepository


class WalletRepository(SqlAlchemyRepository):
    """WalletRepository 实现。"""

    def save_redeem_code(self, record: RedeemCodeRecord) -> None:
        with self.session_factory() as session:
            entity = session.scalar(
                select(RedeemCodeEntity).where(RedeemCodeEntity.code_id == record.code_id)
            )
            if entity is None:
                entity = RedeemCodeEntity(code_id=record.code_id, code=record.code)
                session.add(entity)
            self._apply_redeem_code(entity, record)
            session.commit()

    def list_redeem_codes(self) -> list[RedeemCodeRecord]:
        with self.session_factory() as session:
            entities = session.scalars(
                select(RedeemCodeEntity).order_by(RedeemCodeEntity.created_at.desc())
            ).all()
            return [self._redeem_code_record(entity) for entity in entities]

    def find_redeem_code_by_code(self, code: str) -> RedeemCodeRecord | None:
        with self.session_factory() as session:
            entity = session.scalar(select(RedeemCodeEntity).where(RedeemCodeEntity.code == code))
            return self._redeem_code_record(entity) if entity else None

    def save_wallet_order(self, record: WalletOrderRecord) -> None:
        self.save_wallet_orders((record,))

    def save_wallet_orders(self, records: Sequence[WalletOrderRecord]) -> None:
        """在一个事务中保存多条已经生效的钱包流水。"""

        if not records:
            return
        with self.session_factory() as session:
            try:
                session.add_all(self._wallet_order_entity(record) for record in records)
                session.commit()
            except Exception:
                session.rollback()
                raise

    def grant_wallet_benefit(self, record: WalletOrderRecord) -> WalletOrderRecord:
        """原子发放权益并写入钱包流水。"""

        with self.session_factory() as session:
            try:
                user = self._wallet_user(session, record.user_id, record.username)
                self._apply_benefit(user, record, now=time.time())
                session.add(self._wallet_order_entity(record))
                session.commit()
            except Exception:
                session.rollback()
                raise
        return record

    def redeem_code_and_grant_benefit(
        self,
        *,
        code: str,
        order_id: str,
        user_id: str,
        username: str,
        created_by: str,
        now: float,
    ) -> WalletOrderRecord:
        """在一次事务中完成兑换码核销、权益发放和流水记录。"""

        with self.session_factory() as session:
            try:
                redeem = session.scalar(
                    select(RedeemCodeEntity)
                    .where(RedeemCodeEntity.code == code)
                    .with_for_update()
                )
                if redeem is None:
                    raise WalletOperationError(
                        "REDEEM_CODE_NOT_FOUND", "兑换码不存在", http_status=404
                    )
                if redeem.status == "expired":
                    raise WalletOperationError("REDEEM_CODE_EXPIRED", "兑换码已过期")
                if redeem.status == "exhausted":
                    raise WalletOperationError("REDEEM_CODE_EXHAUSTED", "兑换码已用完")
                if redeem.status != "active":
                    raise WalletOperationError("REDEEM_CODE_DISABLED", "兑换码不可用")
                if redeem.expires_at and redeem.expires_at < now:
                    redeem.status = "expired"
                    session.commit()
                    raise WalletOperationError("REDEEM_CODE_EXPIRED", "兑换码已过期")
                if redeem.used_uses >= redeem.max_uses:
                    redeem.status = "exhausted"
                    session.commit()
                    raise WalletOperationError("REDEEM_CODE_EXHAUSTED", "兑换码已用完")

                record = WalletOrderRecord(
                    order_id=order_id,
                    user_id=user_id,
                    username=username,
                    kind=redeem.kind,
                    points_delta=int(redeem.points or 0)
                    if redeem.kind == "points"
                    else 0,
                    days_delta=int(redeem.days or 0) if redeem.kind == "days" else 0,
                    source="redeem_code",
                    source_id=redeem.code_id,
                    status="completed",
                    created_by=created_by,
                    created_at=now,
                )
                user = self._wallet_user(session, user_id, username)
                self._apply_benefit(user, record, now=now)
                redeem.used_uses += 1
                if redeem.used_uses >= redeem.max_uses:
                    redeem.status = "exhausted"
                session.add(self._wallet_order_entity(record))
                session.commit()
            except Exception:
                session.rollback()
                raise
        return record

    def list_wallet_orders(
        self,
        *,
        username: str | None = None,
        kind: str = "",
        source: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[WalletOrderRecord]:
        with self.session_factory() as session:
            stmt = select(WalletOrderEntity).order_by(WalletOrderEntity.created_at.desc())
            if username:
                stmt = stmt.where(WalletOrderEntity.username == username)
            if kind:
                stmt = stmt.where(WalletOrderEntity.kind == kind)
            if source:
                stmt = stmt.where(WalletOrderEntity.source == source)
            entities = session.scalars(
                stmt.offset(max(0, int(offset))).limit(max(1, min(limit, 500)))
            ).all()
            return [self._wallet_order_record(entity) for entity in entities]

    def _apply_redeem_code(self, entity: RedeemCodeEntity, record: RedeemCodeRecord) -> None:
        entity.code_id = record.code_id
        entity.code = record.code
        entity.kind = record.kind
        entity.points = record.points
        entity.days = record.days
        entity.max_uses = record.max_uses
        entity.used_uses = record.used_uses
        entity.status = record.status
        entity.created_by = record.created_by
        entity.created_at = record.created_at
        entity.expires_at = record.expires_at

    def _wallet_user(self, session, user_id: str, username: str) -> UserEntity:
        """读取并校验钱包操作目标用户。"""

        entity = session.scalar(
            select(UserEntity)
            .where(UserEntity.user_id == user_id)
            .with_for_update()
        )
        if entity is None or entity.username != username:
            raise WalletOperationError("USER_NOT_FOUND", "用户不存在", http_status=404)
        return entity

    def _apply_benefit(
        self,
        user: UserEntity,
        record: WalletOrderRecord,
        *,
        now: float,
    ) -> None:
        """将已校验的钱包权益变更写入用户实体。"""

        if record.kind == "points":
            if record.points_delta <= 0:
                raise WalletOperationError("INVALID_INPUT", "积分数量必须大于 0")
            user.points = int(user.points or 0) + record.points_delta
            return
        if record.kind == "days":
            if record.days_delta <= 0:
                raise WalletOperationError("INVALID_INPUT", "天数必须大于 0")
            current_expiry = float(user.unlimited_expires_at or 0.0)
            user.unlimited_expires_at = max(current_expiry, now) + record.days_delta * 86400.0
            return
        raise WalletOperationError("INVALID_INPUT", "不支持的钱包权益类型")

    def _wallet_order_entity(self, record: WalletOrderRecord) -> WalletOrderEntity:
        """将领域流水记录转换为 ORM 实体。"""

        return WalletOrderEntity(
            order_id=record.order_id,
            user_id=record.user_id,
            username=record.username,
            kind=record.kind,
            points_delta=record.points_delta,
            days_delta=record.days_delta,
            source=record.source,
            source_id=record.source_id,
            status=record.status,
            created_by=record.created_by,
            created_at=record.created_at,
        )

    def _redeem_code_record(self, entity: RedeemCodeEntity) -> RedeemCodeRecord:
        return RedeemCodeRecord(
            code_id=entity.code_id,
            code=entity.code,
            kind=entity.kind,
            points=entity.points,
            days=entity.days,
            max_uses=entity.max_uses,
            used_uses=entity.used_uses,
            status=entity.status,
            created_by=entity.created_by,
            created_at=entity.created_at,
            expires_at=entity.expires_at,
        )

    def _wallet_order_record(self, entity: WalletOrderEntity) -> WalletOrderRecord:
        return WalletOrderRecord(
            order_id=entity.order_id,
            user_id=entity.user_id,
            username=entity.username,
            kind=entity.kind,
            points_delta=entity.points_delta,
            days_delta=entity.days_delta,
            source=entity.source,
            source_id=entity.source_id,
            status=entity.status,
            created_by=entity.created_by,
            created_at=entity.created_at,
        )

"""积分钱包与兑换码仓储。"""

from __future__ import annotations

from sqlalchemy import select

from ...platform.wallet.records import RedeemCodeRecord, WalletOrderRecord
from ..orm import RedeemCodeEntity, WalletOrderEntity
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
        with self.session_factory() as session:
            entity = WalletOrderEntity(
                order_id=record.order_id,
                user_id=record.user_id,
                username=record.username,
                kind=record.kind,
                points_delta=record.points_delta,
                source=record.source,
                source_id=record.source_id,
                status=record.status,
                created_by=record.created_by,
                created_at=record.created_at,
            )
            session.add(entity)
            session.commit()

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
        entity.max_uses = record.max_uses
        entity.used_uses = record.used_uses
        entity.status = record.status
        entity.created_by = record.created_by
        entity.created_at = record.created_at
        entity.expires_at = record.expires_at

    def _redeem_code_record(self, entity: RedeemCodeEntity) -> RedeemCodeRecord:
        return RedeemCodeRecord(
            code_id=entity.code_id,
            code=entity.code,
            kind=entity.kind,
            points=entity.points,
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
            source=entity.source,
            source_id=entity.source_id,
            status=entity.status,
            created_by=entity.created_by,
            created_at=entity.created_at,
        )

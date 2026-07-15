"""用户通知及阅读回执仓储。"""

from __future__ import annotations

from sqlalchemy import select

from ...platform.notifications.records import (
    NotificationReadReceiptRecord,
    NotificationRecord,
)
from ..orm import NotificationEntity, NotificationReadReceiptEntity
from .base import SqlAlchemyRepository


class NotificationRepository(SqlAlchemyRepository):
    """NotificationRepository 实现。"""

    def save_notification(self, record: NotificationRecord) -> None:
        with self.session_factory() as session:
            entity = session.scalar(
                select(NotificationEntity).where(
                    NotificationEntity.notification_id == record.notification_id
                )
            )
            if entity is None:
                entity = NotificationEntity(notification_id=record.notification_id)
                session.add(entity)
            entity.user_id = record.user_id
            entity.level = record.level
            entity.category = record.category
            entity.title = record.title
            entity.content = record.content
            entity.read = 1 if record.read else 0
            entity.created_at = record.created_at
            session.commit()

    def list_notifications(
        self, *, user_id: str | None = None, status: str = "", limit: int = 100
    ) -> list[NotificationRecord]:
        with self.session_factory() as session:
            stmt = select(NotificationEntity).order_by(NotificationEntity.created_at.desc())
            if user_id:
                stmt = stmt.where(
                    (NotificationEntity.user_id == user_id) | (NotificationEntity.user_id.is_(None))
                )
            if status == "read":
                stmt = stmt.where(NotificationEntity.read == 1)
            elif status == "unread":
                stmt = stmt.where(NotificationEntity.read == 0)
            entities = session.scalars(stmt.limit(max(1, min(limit, 500)))).all()
            return [self._notification_record(entity) for entity in entities]

    def get_notification(self, notification_id: str) -> NotificationRecord | None:
        with self.session_factory() as session:
            entity = session.scalar(
                select(NotificationEntity).where(
                    NotificationEntity.notification_id == notification_id
                )
            )
            return self._notification_record(entity) if entity else None

    def save_notification_read_receipt(
        self, record: NotificationReadReceiptRecord
    ) -> NotificationReadReceiptRecord:
        """保存通知中心用户已读回执。"""

        with self.session_factory() as session:
            entity = session.scalar(
                select(NotificationReadReceiptEntity).where(
                    NotificationReadReceiptEntity.user_id == record.user_id,
                    NotificationReadReceiptEntity.source == record.source,
                    NotificationReadReceiptEntity.item_id == record.item_id,
                )
            )
            if entity is None:
                entity = NotificationReadReceiptEntity(
                    user_id=record.user_id,
                    source=record.source,
                    item_id=record.item_id,
                )
                session.add(entity)
            entity.item_updated_at = record.item_updated_at
            entity.read_at = record.read_at
            session.commit()
            return self._notification_read_receipt_record(entity)

    def list_notification_read_receipts(
        self, *, user_id: str, keys: tuple[tuple[str, str], ...]
    ) -> dict[tuple[str, str], NotificationReadReceiptRecord]:
        """按用户读取通知中心回执，返回 (source, item_id) 到回执的映射。"""

        if not keys:
            return {}
        with self.session_factory() as session:
            stmt = select(NotificationReadReceiptEntity).where(
                NotificationReadReceiptEntity.user_id == user_id
            )
            source_values = sorted({source for source, _item_id in keys})
            item_values = sorted({item_id for _source, item_id in keys})
            stmt = stmt.where(NotificationReadReceiptEntity.source.in_(source_values))
            stmt = stmt.where(NotificationReadReceiptEntity.item_id.in_(item_values))
            entities = session.scalars(stmt).all()
            wanted = set(keys)
            return {
                (entity.source, entity.item_id): self._notification_read_receipt_record(entity)
                for entity in entities
                if (entity.source, entity.item_id) in wanted
            }

    def _notification_record(self, entity: NotificationEntity) -> NotificationRecord:
        return NotificationRecord(
            notification_id=entity.notification_id,
            user_id=entity.user_id,
            level=entity.level,
            category=entity.category,
            title=entity.title,
            content=entity.content,
            read=bool(entity.read),
            created_at=entity.created_at,
        )

    def _notification_read_receipt_record(
        self, entity: NotificationReadReceiptEntity
    ) -> NotificationReadReceiptRecord:
        return NotificationReadReceiptRecord(
            user_id=entity.user_id,
            source=entity.source,
            item_id=entity.item_id,
            item_updated_at=float(entity.item_updated_at or 0.0),
            read_at=float(entity.read_at or 0.0),
        )

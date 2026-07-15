"""系统公告仓储。"""

from __future__ import annotations

from sqlalchemy import func, select

from ...platform.announcements.records import AnnouncementRecord
from ..orm import AnnouncementEntity
from .base import SqlAlchemyRepository


class AnnouncementRepository(SqlAlchemyRepository):
    """AnnouncementRepository 实现。"""

    def save_announcement(self, record: AnnouncementRecord) -> AnnouncementRecord:
        """新增或更新系统公告。"""

        with self.session_factory() as session:
            entity = session.scalar(
                select(AnnouncementEntity).where(
                    AnnouncementEntity.announcement_id == record.announcement_id
                )
            )
            if entity is None:
                entity = AnnouncementEntity(announcement_id=record.announcement_id)
                session.add(entity)
            self._apply_announcement(entity, record)
            session.commit()
            return self._announcement_record(entity)

    def get_announcement(self, announcement_id: str) -> AnnouncementRecord | None:
        """按公告 ID 读取公告。"""

        with self.session_factory() as session:
            entity = session.scalar(
                select(AnnouncementEntity).where(
                    AnnouncementEntity.announcement_id == announcement_id
                )
            )
            return self._announcement_record(entity) if entity else None

    def list_announcements(
        self,
        *,
        keyword: str = "",
        status: str = "",
        level: str = "",
        audience: str = "",
        limit: int = 20,
        offset: int = 0,
    ) -> list[AnnouncementRecord]:
        """分页读取公告管理列表。"""

        with self.session_factory() as session:
            stmt = select(AnnouncementEntity).order_by(
                AnnouncementEntity.updated_at.desc(),
                AnnouncementEntity.created_at.desc(),
            )
            stmt = self._apply_announcement_filters(
                stmt, keyword=keyword, status=status, level=level, audience=audience
            )
            entities = session.scalars(
                stmt.offset(max(0, int(offset))).limit(max(1, min(limit, 100)))
            ).all()
            return [self._announcement_record(entity) for entity in entities]

    def count_announcements(
        self,
        *,
        keyword: str = "",
        status: str = "",
        level: str = "",
        audience: str = "",
    ) -> int:
        """统计公告管理列表数量。"""

        with self.session_factory() as session:
            stmt = select(func.count()).select_from(AnnouncementEntity)
            stmt = self._apply_announcement_filters(
                stmt, keyword=keyword, status=status, level=level, audience=audience
            )
            return int(session.scalar(stmt) or 0)

    def list_active_announcements(
        self,
        *,
        role: str,
        now: float,
        limit: int = 10,
    ) -> list[AnnouncementRecord]:
        """读取当前角色可见的有效公告。"""

        with self.session_factory() as session:
            stmt = (
                select(AnnouncementEntity)
                .where(AnnouncementEntity.status == "published")
                .where(
                    (AnnouncementEntity.audience == "all")
                    | (AnnouncementEntity.audience == role)
                )
                .where(
                    (AnnouncementEntity.starts_at <= 0)
                    | (AnnouncementEntity.starts_at <= now)
                )
                .where((AnnouncementEntity.ends_at <= 0) | (AnnouncementEntity.ends_at > now))
                .order_by(
                    AnnouncementEntity.pinned.desc(),
                    AnnouncementEntity.published_at.desc(),
                    AnnouncementEntity.updated_at.desc(),
                )
            )
            entities = session.scalars(stmt.limit(max(1, min(limit, 50)))).all()
            return [self._announcement_record(entity) for entity in entities]

    def _apply_announcement(
        self, entity: AnnouncementEntity, record: AnnouncementRecord
    ) -> None:
        entity.announcement_id = record.announcement_id
        entity.title = record.title
        entity.content = record.content
        entity.level = record.level
        entity.audience = record.audience
        entity.status = record.status
        entity.pinned = 1 if record.pinned else 0
        entity.starts_at = record.starts_at
        entity.ends_at = record.ends_at
        entity.created_by = record.created_by
        entity.created_at = record.created_at
        entity.updated_at = record.updated_at
        entity.published_at = record.published_at

    def _announcement_record(self, entity: AnnouncementEntity) -> AnnouncementRecord:
        return AnnouncementRecord(
            announcement_id=entity.announcement_id,
            title=entity.title,
            content=entity.content,
            level=entity.level,
            audience=entity.audience,
            status=entity.status,
            pinned=bool(entity.pinned),
            starts_at=float(entity.starts_at or 0.0),
            ends_at=float(entity.ends_at or 0.0),
            created_by=entity.created_by,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            published_at=float(entity.published_at or 0.0),
        )

    def _apply_announcement_filters(
        self,
        stmt,
        *,
        keyword: str = "",
        status: str = "",
        level: str = "",
        audience: str = "",
    ):
        normalized_keyword = keyword.strip()
        if normalized_keyword:
            pattern = f"%{normalized_keyword}%"
            stmt = stmt.where(
                (AnnouncementEntity.title.like(pattern))
                | (AnnouncementEntity.content.like(pattern))
            )
        if status:
            stmt = stmt.where(AnnouncementEntity.status == status)
        if level:
            stmt = stmt.where(AnnouncementEntity.level == level)
        if audience:
            stmt = stmt.where(AnnouncementEntity.audience == audience)
        return stmt

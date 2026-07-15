"""API 令牌仓储。"""

from __future__ import annotations

from sqlalchemy import select

from ...platform.tokens.records import ApiTokenRecord
from ..orm import ApiTokenEntity
from .base import SqlAlchemyRepository


class TokenRepository(SqlAlchemyRepository):
    """TokenRepository 实现。"""

    def save_token(self, record: ApiTokenRecord) -> None:
        with self.session_factory() as session:
            entity = session.scalar(
                select(ApiTokenEntity).where(ApiTokenEntity.token_id == record.token_id)
            )
            if entity is None:
                entity = ApiTokenEntity(token_id=record.token_id, key_hash=record.key_hash)
                session.add(entity)
            self._apply_token(entity, record)
            session.commit()

    def list_tokens(self, *, user_id: str) -> list[ApiTokenRecord]:
        with self.session_factory() as session:
            entities = session.scalars(
                select(ApiTokenEntity).where(ApiTokenEntity.user_id == user_id)
            ).all()
            return [self._token_record(entity) for entity in entities]

    def delete_token(self, token_id: str) -> bool:
        """删除指定 API Key 记录。"""
        with self.session_factory() as session:
            entity = session.scalar(
                select(ApiTokenEntity).where(ApiTokenEntity.token_id == token_id)
            )
            if entity is None:
                return False
            session.delete(entity)
            session.commit()
            return True

    def find_token_by_hash(self, key_hash: str) -> ApiTokenRecord | None:
        with self.session_factory() as session:
            entity = session.scalar(
                select(ApiTokenEntity).where(ApiTokenEntity.key_hash == key_hash)
            )
            return self._token_record(entity) if entity else None

    def get_token(self, token_id: str) -> ApiTokenRecord | None:
        with self.session_factory() as session:
            entity = session.scalar(
                select(ApiTokenEntity).where(ApiTokenEntity.token_id == token_id)
            )
            return self._token_record(entity) if entity else None

    def _apply_token(self, entity: ApiTokenEntity, record: ApiTokenRecord) -> None:
        entity.token_id = record.token_id
        entity.user_id = record.user_id
        entity.key_hash = record.key_hash
        entity.key_mask = record.key_mask
        entity.description = record.description
        entity.status = record.status
        entity.created_at = record.created_at
        entity.last_used_at = record.last_used_at
        entity.usage_count = record.usage_count
        entity.quota_used = record.quota_used
        entity.quota_limit = record.quota_limit
        entity.reject_low_confidence = 1 if record.reject_low_confidence else 0
        entity.min_answer_confidence = record.min_answer_confidence

    def _token_record(self, entity: ApiTokenEntity) -> ApiTokenRecord:
        return ApiTokenRecord(
            token_id=entity.token_id,
            user_id=entity.user_id,
            key_hash=entity.key_hash,
            key_mask=entity.key_mask,
            description=entity.description,
            status=entity.status,
            created_at=entity.created_at,
            last_used_at=entity.last_used_at,
            usage_count=entity.usage_count,
            quota_used=max(
                int(getattr(entity, "quota_used", 0) or 0),
                int(getattr(entity, "usage_count", 0) or 0),
            ),
            quota_limit=getattr(entity, "quota_limit", -1),
            reject_low_confidence=bool(getattr(entity, "reject_low_confidence", 0)),
            min_answer_confidence=float(
                getattr(entity, "min_answer_confidence", 0.0) or 0.0
            ),
        )

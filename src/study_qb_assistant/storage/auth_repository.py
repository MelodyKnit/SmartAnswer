"""鉴权数据的 SQLAlchemy 仓储。"""

from __future__ import annotations

from sqlalchemy import select

from ..auth.records import UserRecord
from .database import get_session_factory
from .orm import UserEntity


class SqlAlchemyAuthRepository:
    """用户持久化仓储。"""

    def __init__(self, path_or_url) -> None:
        self.session_factory = get_session_factory(path_or_url)

    def has_users(self) -> bool:
        with self.session_factory() as session:
            return session.scalar(select(UserEntity.id).limit(1)) is not None

    def get_user(self, username: str) -> UserRecord | None:
        with self.session_factory() as session:
            entity = session.scalar(select(UserEntity).where(UserEntity.username == username))
            return self._to_record(entity) if entity else None

    def get_user_by_id(self, user_id: str) -> UserRecord | None:
        with self.session_factory() as session:
            entity = session.scalar(select(UserEntity).where(UserEntity.user_id == user_id))
            return self._to_record(entity) if entity else None

    def list_users(self) -> list[UserRecord]:
        with self.session_factory() as session:
            entities = session.scalars(select(UserEntity)).all()
            return [self._to_record(entity) for entity in entities]

    def save_user(self, record: UserRecord) -> None:
        with self.session_factory() as session:
            entity = session.scalar(select(UserEntity).where(UserEntity.username == record.username))
            if entity is None:
                entity = UserEntity(username=record.username, user_id=record.user_id)
                session.add(entity)
            self._apply_record(entity, record)
            session.commit()

    def _apply_record(self, entity: UserEntity, record: UserRecord) -> None:
        entity.user_id = record.user_id
        entity.username = record.username
        entity.role = record.role
        entity.status = record.status
        entity.salt = record.salt
        entity.password_hash = record.password_hash
        entity.email = record.email
        entity.points = record.points
        entity.created_at = record.created_at
        entity.reset_token_hash = record.reset_token_hash
        entity.reset_expires_at = record.reset_expires_at

    def _to_record(self, entity: UserEntity) -> UserRecord:
        return UserRecord(
            user_id=entity.user_id,
            username=entity.username,
            role=entity.role,
            status=entity.status,
            salt=entity.salt,
            password_hash=entity.password_hash,
            email=entity.email,
            points=entity.points,
            created_at=entity.created_at,
            reset_token_hash=entity.reset_token_hash,
            reset_expires_at=entity.reset_expires_at,
        )

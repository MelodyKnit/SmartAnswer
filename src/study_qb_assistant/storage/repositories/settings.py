"""键值配置仓储。"""

from __future__ import annotations

from sqlalchemy import delete, select

from ..orm import SettingEntity
from .base import SqlAlchemyRepository


class SettingsRepository(SqlAlchemyRepository):
    """SettingsRepository 实现。"""

    def get_settings(self, scope: str, *, keys: set[str] | None = None) -> dict[str, str]:
        with self.session_factory() as session:
            stmt = select(SettingEntity).where(SettingEntity.scope == scope)
            if keys:
                stmt = stmt.where(SettingEntity.key.in_(keys))
            entities = session.scalars(stmt).all()
            return {entity.key: entity.value for entity in entities}

    def set_settings(self, scope: str, values: dict[str, str]) -> None:
        with self.session_factory() as session:
            for key, value in values.items():
                entity = session.scalar(
                    select(SettingEntity).where(
                        SettingEntity.scope == scope, SettingEntity.key == key
                    )
                )
                if entity is None:
                    entity = SettingEntity(scope=scope, key=key, value=value)
                    session.add(entity)
                else:
                    entity.value = value
            session.commit()

    def replace_settings(self, scope: str, values: dict[str, str]) -> None:
        with self.session_factory() as session:
            session.execute(delete(SettingEntity).where(SettingEntity.scope == scope))
            for key, value in values.items():
                session.add(SettingEntity(scope=scope, key=key, value=value))
            session.commit()

    def delete_settings(self, scope: str, *, keys: set[str]) -> None:
        """删除指定作用域内的一组配置；空集合不产生数据库写入。"""

        if not keys:
            return
        with self.session_factory() as session:
            session.execute(
                delete(SettingEntity).where(
                    SettingEntity.scope == scope,
                    SettingEntity.key.in_(keys),
                )
            )
            session.commit()

"""角色与权限的 SQLAlchemy 仓储。"""

from __future__ import annotations

import json

from sqlalchemy import func, select

from ...platform.permissions.records import RoleRecord
from ..orm import RoleEntity, UserEntity
from .base import SqlAlchemyRepository
from .settings import SettingsRepository


class RoleRepository(SqlAlchemyRepository):
    """持久化角色定义及其权限集合。"""

    def __init__(self, session_factory, settings: SettingsRepository) -> None:
        super().__init__(session_factory)
        self.settings = settings

    def list_roles(self) -> list[RoleRecord]:
        """按系统角色优先、名称次序读取所有角色。"""

        with self.session_factory() as session:
            entities = session.scalars(
                select(RoleEntity).order_by(RoleEntity.is_system.desc(), RoleEntity.created_at)
            ).all()
            return [self._to_record(entity) for entity in entities]

    def get_role(self, role_id: str) -> RoleRecord | None:
        """读取单个角色。"""

        with self.session_factory() as session:
            entity = session.scalar(select(RoleEntity).where(RoleEntity.role_id == role_id))
            return self._to_record(entity) if entity else None

    def save_role(self, record: RoleRecord) -> None:
        """新增或更新角色定义。"""

        with self.session_factory() as session:
            entity = session.scalar(select(RoleEntity).where(RoleEntity.role_id == record.role_id))
            if entity is None:
                entity = RoleEntity(role_id=record.role_id)
                session.add(entity)
            entity.name = record.name
            entity.description = record.description
            entity.permissions_json = json.dumps(list(record.permissions), ensure_ascii=False)
            entity.is_system = 1 if record.is_system else 0
            entity.created_at = record.created_at
            entity.updated_at = record.updated_at
            session.commit()

    def delete_role(self, role_id: str) -> bool:
        """删除指定角色定义。"""

        with self.session_factory() as session:
            entity = session.scalar(select(RoleEntity).where(RoleEntity.role_id == role_id))
            if entity is None:
                return False
            session.delete(entity)
            session.commit()
            return True

    def count_assigned_users(self, role_id: str) -> int:
        """统计仍分配指定角色的用户数。"""

        with self.session_factory() as session:
            return int(
                session.scalar(select(func.count(UserEntity.id)).where(UserEntity.role == role_id))
                or 0
            )

    def legacy_role_permission_overrides(self) -> dict[str, tuple[str, ...]]:
        """读取旧 settings 中的角色权限，用于一次性迁移。"""

        result: dict[str, tuple[str, ...]] = {}
        for role_id, raw_value in self.settings.get_settings("role_permissions").items():
            try:
                payload = json.loads(raw_value)
            except (TypeError, json.JSONDecodeError):
                continue
            permissions = payload.get("permissions") if isinstance(payload, dict) else ()
            if isinstance(permissions, list):
                result[role_id] = tuple(str(item) for item in permissions)
        return result

    @staticmethod
    def _to_record(entity: RoleEntity) -> RoleRecord:
        try:
            raw_permissions = json.loads(entity.permissions_json or "[]")
        except json.JSONDecodeError:
            raw_permissions = []
        permissions = tuple(str(item) for item in raw_permissions if str(item).strip())
        return RoleRecord(
            role_id=entity.role_id,
            name=entity.name,
            description=entity.description,
            permissions=permissions,
            is_system=bool(entity.is_system),
            created_at=float(entity.created_at or 0.0),
            updated_at=float(entity.updated_at or 0.0),
        )

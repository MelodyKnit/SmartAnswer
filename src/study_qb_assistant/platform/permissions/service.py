"""角色、权限目录与授权边界服务。"""

from __future__ import annotations

import re
import time

from ...auth import AuthError
from ..base import PlatformDomainService
from .catalog import (
    PERMISSION_CATALOG,
    PERMISSION_KEYS,
    SYSTEM_ROLE_DEFINITIONS,
    SYSTEM_ROLE_IDS,
)
from .records import RoleRecord

ROLE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{2,31}$")
RESERVED_ROLE_IDS = frozenset((*SYSTEM_ROLE_IDS, "all"))
IMAGE_GENERATION_PERMISSION_MIGRATION_KEY = "image_generation_default_granted_v1"


class PermissionService(PlatformDomainService):
    """维护角色数据，并对权限修改执行防越权校验。"""

    def ensure_system_roles(self) -> None:
        """幂等创建系统角色，并从旧设置迁移人工权限覆盖。"""

        with self.lock:
            existing = {role.role_id: role for role in self.repository.list_roles()}
            legacy_overrides = self.repository.legacy_role_permission_overrides()
            now = time.time()
            for definition in SYSTEM_ROLE_DEFINITIONS:
                current = existing.get(definition.role_id)
                if current is not None:
                    if current.is_system:
                        continue
                    self.repository.save_role(
                        RoleRecord(
                            role_id=current.role_id,
                            name=current.name,
                            description=current.description,
                            permissions=current.permissions,
                            is_system=True,
                            created_at=current.created_at or now,
                            updated_at=now,
                        )
                    )
                    continue
                permissions = self.normalize_permissions(
                    legacy_overrides.get(definition.role_id, definition.permissions)
                )
                self.repository.save_role(
                    RoleRecord(
                        role_id=definition.role_id,
                        name=definition.name,
                        description=definition.description,
                        permissions=permissions,
                        is_system=True,
                        created_at=now,
                        updated_at=now,
                    )
                )

    def ensure_image_generation_permission_defaults(self) -> None:
        """为升级前的角色一次性补齐图片生成权限。"""

        with self.lock:
            migration = self.repository.settings.get_settings(
                "permission_migrations", keys={IMAGE_GENERATION_PERMISSION_MIGRATION_KEY}
            )
            if migration.get(IMAGE_GENERATION_PERMISSION_MIGRATION_KEY) == "true":
                return
            now = time.time()
            for role in self.repository.list_roles():
                if "image-generation:use" in role.permissions:
                    continue
                self.repository.save_role(
                    RoleRecord(
                        role_id=role.role_id,
                        name=role.name,
                        description=role.description,
                        permissions=tuple((*role.permissions, "image-generation:use")),
                        is_system=role.is_system,
                        created_at=role.created_at,
                        updated_at=now,
                    )
                )
            self.repository.settings.set_settings(
                "permission_migrations",
                {IMAGE_GENERATION_PERMISSION_MIGRATION_KEY: "true"},
            )

    @staticmethod
    def permission_catalog() -> list[dict[str, str]]:
        """返回唯一的权限展示目录。"""

        return [item.to_dict() for item in PERMISSION_CATALOG]

    @staticmethod
    def allowed_role_permissions() -> set[str]:
        """返回后端当前支持的权限标识集合。"""

        return set(PERMISSION_KEYS)

    def list_roles(self) -> list[dict]:
        """读取全部角色。"""

        with self.lock:
            return [role.to_dict() for role in self.repository.list_roles()]

    def list_role_permissions(self) -> list[dict]:
        """兼容旧调用名称，返回完整角色列表。"""

        return self.list_roles()

    def get_role(self, role_id: str) -> dict:
        """读取单个角色。"""

        normalized_role_id = self.normalize_role_id(role_id)
        with self.lock:
            role = self.repository.get_role(normalized_role_id)
        if role is None:
            raise AuthError("ROLE_NOT_FOUND", "角色不存在", http_status=404)
        return role.to_dict()

    def get_role_permissions(self, role_id: str) -> dict:
        """兼容旧调用名称，返回单个角色。"""

        return self.get_role(role_id)

    def role_permissions(self, role_id: str) -> set[str]:
        """返回指定角色当前生效的权限集合。"""

        return set(self.get_role(role_id).get("permissions") or ())

    def role_exists(self, role_id: str) -> bool:
        """判断角色是否存在。"""

        try:
            normalized_role_id = self.normalize_role_id(role_id)
        except AuthError:
            return False
        with self.lock:
            return self.repository.get_role(normalized_role_id) is not None

    def create_role(
        self,
        *,
        role_id: str,
        name: str,
        description: str,
        permissions: tuple[str, ...],
    ) -> dict:
        """创建一个默认无继承关系的自定义角色。"""

        normalized_role_id = self.normalize_role_id(role_id)
        if normalized_role_id in RESERVED_ROLE_IDS:
            raise AuthError("ROLE_SYSTEM_PROTECTED", "系统角色不可重复创建", http_status=400)
        normalized_name = self.normalize_name(name)
        normalized_description = self.normalize_description(description)
        normalized_permissions = self.normalize_permissions(permissions)
        with self.lock:
            if self.repository.get_role(normalized_role_id) is not None:
                raise AuthError("ROLE_EXISTS", "角色标识已存在", http_status=409)
            now = time.time()
            self.repository.save_role(
                RoleRecord(
                    role_id=normalized_role_id,
                    name=normalized_name,
                    description=normalized_description,
                    permissions=normalized_permissions,
                    is_system=False,
                    created_at=now,
                    updated_at=now,
                )
            )
        return self.get_role(normalized_role_id)

    def update_role(
        self,
        role_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        permissions: tuple[str, ...] | None = None,
        actor_role_id: str,
        actor_permissions: set[str],
    ) -> dict:
        """更新角色，并对非超级管理员实施委托权限边界。"""

        target = self.require_role_record(role_id)
        actor_is_superadmin = actor_role_id == "superadmin"
        if target.is_system and not actor_is_superadmin:
            raise AuthError("ROLE_SYSTEM_PROTECTED", "不能修改系统角色", http_status=403)
        if target.is_system and (name is not None or description is not None):
            raise AuthError("ROLE_SYSTEM_PROTECTED", "系统角色名称和说明不可修改", http_status=400)

        next_permissions = (
            target.permissions if permissions is None else self.normalize_permissions(permissions)
        )
        if not actor_is_superadmin:
            if "roles:write" not in actor_permissions:
                raise AuthError("FORBIDDEN", "权限不足", http_status=403)
            unauthorized = sorted(set(next_permissions) - actor_permissions)
            if unauthorized:
                raise AuthError(
                    "ROLE_PERMISSION_ESCALATION",
                    "只能授予自身已有的权限",
                    http_status=403,
                )

        updated = RoleRecord(
            role_id=target.role_id,
            name=target.name if name is None else self.normalize_name(name),
            description=(
                target.description if description is None else self.normalize_description(description)
            ),
            permissions=next_permissions,
            is_system=target.is_system,
            created_at=target.created_at,
            updated_at=time.time(),
        )
        with self.lock:
            self.repository.save_role(updated)
        return updated.to_dict()

    def set_role_permissions(
        self,
        role_id: str,
        permissions: tuple[str, ...],
        *,
        actor_role_id: str = "superadmin",
        actor_permissions: set[str] | None = None,
    ) -> dict:
        """兼容旧入口更新角色权限，并保留委托边界。"""

        return self.update_role(
            role_id,
            permissions=permissions,
            actor_role_id=actor_role_id,
            actor_permissions=actor_permissions or set(),
        )

    def delete_role(self, role_id: str) -> None:
        """删除未被用户使用的自定义角色。"""

        target = self.require_role_record(role_id)
        if target.is_system:
            raise AuthError("ROLE_SYSTEM_PROTECTED", "系统角色不可删除", http_status=400)
        with self.lock:
            if self.repository.count_assigned_users(target.role_id) > 0:
                raise AuthError(
                    "ROLE_IN_USE",
                    "该角色仍有用户使用，请先重新分配用户角色",
                    http_status=409,
                )
            self.repository.delete_role(target.role_id)

    def require_role_record(self, role_id: str) -> RoleRecord:
        """读取角色记录，不存在时返回统一业务错误。"""

        normalized_role_id = self.normalize_role_id(role_id)
        with self.lock:
            role = self.repository.get_role(normalized_role_id)
        if role is None:
            raise AuthError("ROLE_NOT_FOUND", "角色不存在", http_status=404)
        return role

    @staticmethod
    def normalize_role_id(role_id: str) -> str:
        """规范化并验证稳定的角色标识。"""

        normalized = str(role_id or "").strip().lower()
        if not ROLE_ID_PATTERN.fullmatch(normalized):
            raise AuthError(
                "INVALID_ROLE_ID",
                "角色标识需为 3-32 位小写英文、数字、连字符或下划线",
                http_status=400,
            )
        return normalized

    @staticmethod
    def normalize_name(name: str) -> str:
        """验证角色显示名称。"""

        normalized = str(name or "").strip()
        if not normalized or len(normalized) > 32:
            raise AuthError("INVALID_INPUT", "角色名称长度应为 1-32 个字符", http_status=400)
        return normalized

    @staticmethod
    def normalize_description(description: str) -> str:
        """验证角色说明。"""

        normalized = str(description or "").strip()
        if len(normalized) > 120:
            raise AuthError("INVALID_INPUT", "角色说明不能超过 120 个字符", http_status=400)
        return normalized

    @staticmethod
    def normalize_permissions(permissions: tuple[str, ...]) -> tuple[str, ...]:
        """去重、排序并校验权限标识。"""

        normalized = tuple(sorted({str(item).strip() for item in permissions if str(item).strip()}))
        invalid = sorted(set(normalized) - PERMISSION_KEYS)
        if invalid:
            raise AuthError(
                "INVALID_PERMISSION",
                f"权限项不存在: {', '.join(invalid)}",
                http_status=400,
            )
        return normalized

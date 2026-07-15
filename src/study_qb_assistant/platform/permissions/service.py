"""角色权限服务。"""

from __future__ import annotations

import time

from ...auth import AuthError
from ..base import PlatformDomainService
from .records import RolePermissionRecord

DEFAULT_ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "superadmin": (
        "dashboard:all", "users:write", "roles:read", "roles:write",
        "system:read", "system:write", "billing:read", "billing:write",
        "wallet:changes:read", "wallet:changes:write", "import-scripts:read",
        "import-scripts:write", "questions:read", "questions:write",
        "llm:read", "llm:write", "announcements:read", "announcements:write",
    ),
    "admin": (
        "dashboard:all", "users:write", "roles:read", "billing:read",
        "wallet:changes:read", "wallet:changes:write", "import-scripts:read",
        "import-scripts:write", "questions:read", "questions:write",
        "llm:read", "announcements:read", "announcements:write",
    ),
    "user": ("dashboard:self", "tokens:self", "feedback:self"),
}


class PermissionService(PlatformDomainService):
    """PermissionService 领域实现。"""

    def list_role_permissions(self) -> list[dict]:
        """列出角色权限矩阵。"""
        with self.lock:
            existing = {item.role_id: item for item in self.repository.get_role_permissions()}
            result: list[RolePermissionRecord] = []
            allowed = self.allowed_role_permissions()
            for role_id, permissions in DEFAULT_ROLE_PERMISSIONS.items():
                record = existing.get(
                    role_id,
                    RolePermissionRecord(
                        role_id=role_id, permissions=permissions, updated_at=0.0
                    ),
                )
                result.append(
                    RolePermissionRecord(
                        role_id=record.role_id,
                        permissions=tuple(item for item in record.permissions if item in allowed),
                        updated_at=record.updated_at,
                    )
                )
            return [item.to_dict() for item in result]

    @staticmethod
    def allowed_role_permissions() -> set[str]:
        """返回当前系统真实生效的权限白名单。"""

        return {item for values in DEFAULT_ROLE_PERMISSIONS.values() for item in values}

    def get_role_permissions(self, role_id: str) -> dict:
        """读取单个角色的权限矩阵。"""
        items = {item["role_id"]: item for item in self.list_role_permissions()}
        record = items.get(role_id)
        if record is None:
            raise AuthError("ROLE_NOT_FOUND", "角色不存在", http_status=404)
        return record

    def role_permissions(self, role_id: str) -> set[str]:
        """返回指定角色的权限集合。"""

        record = self.get_role_permissions(role_id)
        return set(record.get("permissions") or ())

    def set_role_permissions(self, role_id: str, permissions: tuple[str, ...]) -> dict:
        """更新角色权限矩阵。"""
        if role_id not in DEFAULT_ROLE_PERMISSIONS:
            raise AuthError("ROLE_NOT_FOUND", "角色不存在", http_status=404)
        normalized = tuple(str(item).strip() for item in permissions if str(item).strip())
        invalid = sorted(set(normalized) - self.allowed_role_permissions())
        if invalid:
            raise AuthError(
                "INVALID_PERMISSION",
                f"权限项不存在: {', '.join(invalid)}",
                http_status=400,
            )
        with self.lock:
            self.repository.set_role_permissions(
                role_id,
                normalized,
                time.time(),
            )
        return self.get_role_permissions(role_id)

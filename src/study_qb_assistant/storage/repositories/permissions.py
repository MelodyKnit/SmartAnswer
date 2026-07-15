"""角色权限仓储。"""

from __future__ import annotations

import json

from ...platform.permissions.records import RolePermissionRecord
from .settings import SettingsRepository


class PermissionRepository:
    """基于键值配置仓储持久化角色权限。"""

    def __init__(self, settings: SettingsRepository) -> None:
        self.settings = settings

    def get_role_permissions(self) -> list[RolePermissionRecord]:
        """读取已覆盖的角色权限配置。"""

        raw = self.settings.get_settings("role_permissions")
        result: list[RolePermissionRecord] = []
        for role_id, value in raw.items():
            try:
                payload = json.loads(value)
            except json.JSONDecodeError:
                continue
            result.append(
                RolePermissionRecord(
                    role_id=role_id,
                    permissions=tuple(str(item) for item in payload.get("permissions") or ()),
                    updated_at=float(payload.get("updated_at") or 0.0),
                )
            )
        return result

    def set_role_permissions(
        self, role_id: str, permissions: tuple[str, ...], updated_at: float
    ) -> None:
        """保存指定角色权限配置。"""

        payload = json.dumps(
            {"permissions": list(permissions), "updated_at": updated_at},
            ensure_ascii=False,
        )
        self.settings.set_settings("role_permissions", {role_id: payload})

"""角色权限记录。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RolePermissionRecord:
    """角色权限矩阵记录。"""

    role_id: str
    permissions: tuple[str, ...]
    updated_at: float

    def to_dict(self) -> dict:
        return {
            "role_id": self.role_id,
            "permissions": list(self.permissions),
            "updated_at": self.updated_at,
        }

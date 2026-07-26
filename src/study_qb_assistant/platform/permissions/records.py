"""角色权限领域的数据记录。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RoleRecord:
    """可分配角色及其权限集合。"""

    role_id: str
    name: str
    description: str
    permissions: tuple[str, ...]
    is_system: bool
    created_at: float
    updated_at: float

    def to_dict(self) -> dict:
        """转换为 API 响应。"""

        return {
            "role_id": self.role_id,
            "name": self.name,
            "description": self.description,
            "permissions": list(self.permissions),
            "is_system": self.is_system,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# 兼容仍以旧名称导入的调用方；新代码应使用 RoleRecord。
RolePermissionRecord = RoleRecord

"""旧角色权限仓储导入兼容层。"""

from .roles import RoleRepository

PermissionRepository = RoleRepository

__all__ = ["PermissionRepository", "RoleRepository"]

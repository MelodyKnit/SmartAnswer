"""角色权限请求模型。"""

from pydantic import BaseModel, ConfigDict


class RolePermissionPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    permissions: list[str] | tuple[str, ...] = ()


class RoleCreatePayload(BaseModel):
    """创建自定义角色的请求。"""

    model_config = ConfigDict(extra="ignore")
    role_id: str = ""
    name: str = ""
    description: str = ""
    permissions: list[str] | tuple[str, ...] = ()


class RoleUpdatePayload(BaseModel):
    """更新自定义角色展示信息或权限的请求。"""

    model_config = ConfigDict(extra="ignore")
    name: str | None = None
    description: str | None = None
    permissions: list[str] | tuple[str, ...] | None = None

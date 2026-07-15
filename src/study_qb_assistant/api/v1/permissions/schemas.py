"""角色权限请求模型。"""

from pydantic import BaseModel, ConfigDict


class RolePermissionPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    permissions: list[str] | tuple[str, ...] = ()

"""用户与个人资料接口请求模型。"""

from pydantic import BaseModel, ConfigDict


class UserUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    role: str | None = None
    points: int | None = None
    status: str | None = None


class UsersDeletePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    usernames: list[str] | tuple[str, ...] = ()


class ProfileUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    display_name: str | None = None
    email: str | None = None


class PasswordChangePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    old_password: str = ""
    new_password: str = ""

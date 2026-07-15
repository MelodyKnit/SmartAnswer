"""认证接口请求模型。"""

from pydantic import BaseModel, ConfigDict


class RegisterPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    username: str = ""
    password: str = ""
    email: str | None = None
    email_code: str | None = None
    invite_code: str = ""


class EmailVerificationCodePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    email: str = ""
    purpose: str = "register"


class LoginPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    username: str = ""
    password: str = ""
    remember: bool = False


class ResetRequestPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    username: str = ""


class ResetConfirmPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    username: str = ""
    token: str = ""
    new_password: str = ""

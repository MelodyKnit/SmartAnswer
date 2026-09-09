"""认证接口请求模型。"""

from pydantic import BaseModel, ConfigDict


class RegisterPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    username: str = ""
    password: str = ""
    email: str | None = None
    email_code: str | None = None
    invite_code: str = ""
    captcha_token: str | None = None

    def get_clean_captcha_token(self) -> str:
        return (self.captcha_token or "").strip()


class EmailVerificationCodePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    email: str = ""
    purpose: str = "register"


class LoginPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    username: str = ""
    password: str = ""
    remember: bool = False
    captcha_token: str | None = None

    def get_clean_captcha_token(self) -> str:
        return (self.captcha_token or "").strip()


class ResetRequestPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    username: str = ""


class SliderVerifyPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    challenge_id: str
    x: float


class ResetConfirmPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    username: str = ""
    token: str = ""
    new_password: str = ""

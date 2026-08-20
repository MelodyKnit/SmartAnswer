"""钱包与积分接口请求模型。"""

from pydantic import BaseModel, ConfigDict, field_validator


class BillingPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    local_hit: int | None = None
    web_search: int | None = None
    llm_fallback: int | None = None


class RedeemCodePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = "points"
    points: int = 0
    days: int = 0
    max_uses: int = 1
    expires_at: float = 0.0
    code: str | None = None
    count: int = 1

    @field_validator("kind")
    @classmethod
    def valid_kind(cls, value: str) -> str:
        normalized = (value or "points").strip().lower()
        if normalized not in ("points", "days"):
            raise ValueError("兑换码类型仅支持 points 或 days")
        return normalized


class WalletGrantPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = ""
    kind: str = "points"
    points: int = 0
    days: int = 0

    @field_validator("kind")
    @classmethod
    def valid_kind(cls, value: str) -> str:
        normalized = (value or "points").strip().lower()
        if normalized not in ("points", "days"):
            raise ValueError("钱包发放类型仅支持 points 或 days")
        return normalized


class WalletRedeemPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    code: str = ""

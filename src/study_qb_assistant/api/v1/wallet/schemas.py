"""钱包与积分接口请求模型。"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class RedeemCodeBatchDeletePayload(BaseModel):
    """批量删除兑换码请求。"""

    model_config = ConfigDict(extra="forbid")
    code_ids: list[str] = Field(default_factory=list, min_length=1, max_length=1000)

    @field_validator("code_ids")
    @classmethod
    def valid_code_ids(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            code_id = value.strip()
            if not code_id:
                raise ValueError("兑换码 ID 不能为空")
            if code_id not in seen:
                normalized.append(code_id)
                seen.add(code_id)
        if not normalized:
            raise ValueError("至少选择一个兑换码")
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

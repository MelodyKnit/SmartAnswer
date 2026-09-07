"""API 令牌接口请求模型。"""

from pydantic import BaseModel, ConfigDict


class TokenCreatePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    description: str = ""
    quota_limit: int = -1
    reject_low_confidence: bool = False
    min_answer_confidence: float = 0.0
    bind_client: bool = False


class TokenUpdatePayload(BaseModel):
    """API Key 更新请求；省略字段时保留已有配置。"""

    model_config = ConfigDict(extra="ignore")
    description: str | None = None
    quota_limit: int | None = None
    reject_low_confidence: bool | None = None
    min_answer_confidence: float | None = None
    bind_client: bool | None = None
    reset_bound_client: bool = False

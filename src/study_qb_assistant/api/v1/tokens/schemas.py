"""API 令牌接口请求模型。"""

from pydantic import BaseModel, ConfigDict


class TokenCreatePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    description: str = ""
    quota_limit: int = -1
    reject_low_confidence: bool = False
    min_answer_confidence: float = 0.0

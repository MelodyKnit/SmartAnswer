"""反馈接口请求模型。"""

from pydantic import BaseModel, ConfigDict


class FeedbackPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    usage_log_id: str | None = None
    title: str = ""
    content: str = ""
    image_urls: list[str] | tuple[str, ...] = ()
    category: str = "answer"


class FeedbackResolvePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    status: str = "resolved"
    admin_note: str = ""
    corrected_answer: str = ""
    reward_points: int = 0

"""题库管理请求模型。"""

from pydantic import BaseModel, ConfigDict


class QuestionUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title_raw: str | None = None
    question_type: str | None = None
    options_raw: list[str] | tuple[str, ...] | None = None
    answer_raw: str | None = None
    status: str | None = None
    answer: str | None = None
    answer_text: str | None = None
    explanation: str | None = None
    subject: str | None = None
    tags: list[str] | tuple[str, ...] | None = None

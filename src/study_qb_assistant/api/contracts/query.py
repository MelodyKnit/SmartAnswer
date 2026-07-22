"""查题接口共享请求模型。"""

from pydantic import BaseModel, ConfigDict, Field


class QueryPayload(BaseModel):
    """规范查题接口与 OCS 接口共用的 JSON 请求体。"""

    model_config = ConfigDict(extra="ignore")

    raw_text: str = ""
    title: str = ""
    options: str | list[str] | tuple[str, ...] = ()
    type: str | None = None
    question_type: str | None = None
    request_id: str | None = None
    page_url: str | None = None
    image_capture_status: str | None = None
    image_capture_failures: int | None = None
    image_urls: list[str] | tuple[str, ...] = Field(default_factory=tuple)
    image_data_urls: list[str] | tuple[str, ...] = Field(default_factory=tuple)
    option_image_urls: dict[str, str] = Field(default_factory=dict)
    option_image_data_urls: dict[str, str] = Field(default_factory=dict)

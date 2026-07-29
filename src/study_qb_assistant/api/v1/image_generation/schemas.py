"""生图与图片编辑接口请求模型。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ImageGenerationInputReferencePayload(BaseModel):
    """一次任务对私有上传图或历史生成图的引用。"""

    model_config = ConfigDict(extra="forbid")

    source_kind: Literal["uploaded", "generated"]
    source_id: str
    source_job_id: str = ""
    role: Literal["source", "reference", "mask"]


class ImageGenerationCreatePayload(BaseModel):
    """用户提交的一次生图/修图请求。"""

    model_config = ConfigDict(extra="forbid")

    prompt: str = ""
    size: str = ""
    mode: Literal["text_to_image", "image_edit", "masked_edit", "multi_reference"] = (
        "text_to_image"
    )
    input_assets: list[ImageGenerationInputReferencePayload] = Field(default_factory=list)
    output: dict[str, object] | None = None
    idempotency_key: str = ""


class ImageGenerationModelTestPayload(BaseModel):
    """管理员明确选择的模型能力测试类型。"""

    model_config = ConfigDict(extra="forbid")

    operation: Literal["text_to_image", "whole_edit", "masked_edit", "multi_reference"] = (
        "text_to_image"
    )


class ImageGenerationModelCreatePayload(BaseModel):
    """管理员创建独立生图模型配置的请求。"""

    model_config = ConfigDict(extra="ignore")

    name: str = ""
    provider: str = "openai-images"
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    timeout_seconds: float = 60.0
    status: str = "active"
    capabilities: list[str] = []
    protocol_config: dict[str, object] | None = None


class ImageGenerationModelUpdatePayload(BaseModel):
    """管理员更新生图模型配置的请求，空密钥保持现有值。"""

    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    provider: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    timeout_seconds: float | None = None
    status: str | None = None
    capabilities: list[str] | None = None
    protocol_config: dict[str, object] | None = None

"""文本生图接口请求模型。"""

from pydantic import BaseModel, ConfigDict


class ImageGenerationCreatePayload(BaseModel):
    """用户提交的一次文本生图请求。"""

    model_config = ConfigDict(extra="ignore")

    prompt: str
    size: str = ""
    idempotency_key: str = ""


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

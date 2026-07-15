"""大模型管理接口请求模型。"""

from pydantic import BaseModel, ConfigDict


class LlmRuntimeConfigPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    llm_fallback: str | None = None
    llm_explain: str | None = None
    allow_known_rules: str | None = None
    no_local_bank_mode: str | None = None
    search_first: str | None = None
    self_consistency_repeats: str | None = None
    web_search_provider: str | None = None
    web_search_configs: str | None = None
    search_proxy: str | None = None
    llm_proxy: str | None = None
    google_search_api_key: str | None = None
    google_search_cx: str | None = None
    baidu_search_api_key: str | None = None
    llm_cache_enabled: str | None = None
    llm_cache_min_confidence: str | None = None
    llm_cache_min_confirmations: str | None = None


class LlmModelCreatePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = ""
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    role: str = "backup"
    priority: int = 100
    stream: bool = True
    max_completion_tokens: int = 700
    timeout_seconds: float = 30.0
    status: str = "active"


class LlmModelUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    role: str | None = None
    priority: int | None = None
    stream: bool | None = None
    max_completion_tokens: int | None = None
    timeout_seconds: float | None = None
    status: str | None = None

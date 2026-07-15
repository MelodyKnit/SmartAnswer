"""导入脚本接口请求模型。"""

from pydantic import BaseModel, ConfigDict, Field


class ImportScriptGeneratePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = ""
    token_id: str | None = None
    target: str = "ocs"
    include_test_snippet: bool = True


class ImportScriptCreatePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = ""
    target: str = "ocs"
    description: str = ""
    script_template: str = ""
    content: str = ""
    config_items: list[dict] = Field(default_factory=list)
    requires_token: bool = True
    tags: list[str] | tuple[str, ...] = ()
    is_default: bool = False
    status: str = "active"

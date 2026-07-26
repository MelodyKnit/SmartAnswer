"""生图领域的持久化记录。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class ImageGenerationModelRecord:
    """生图模型接入配置。"""

    model_id: str
    name: str
    provider: str
    base_url: str
    model: str
    api_key: str
    timeout_seconds: float
    status: str
    capabilities: str
    created_at: float
    updated_at: float
    protocol_config: str = "{}"

    def to_dict(self) -> dict:
        """序列化模型配置，绝不向调用方返回供应商密钥。"""

        payload = asdict(self)
        payload["api_key_configured"] = bool(self.api_key)
        payload.pop("api_key", None)
        payload["capabilities"] = [item for item in self.capabilities.split(",") if item]
        payload["protocol_config"] = json_object(self.protocol_config)
        return payload


@dataclass(slots=True)
class ImageGenerationJobRecord:
    """用户一次生图任务的完整状态快照。"""

    job_id: str
    user_id: str
    username: str
    prompt: str
    size: str
    model_id: str
    model_name: str
    model_snapshot: str
    status: str
    points_cost: int
    reservation_order_id: str
    idempotency_key: str
    error_code: str
    error_message: str
    created_at: float
    started_at: float
    completed_at: float
    updated_at: float
    expires_at: float
    output_options: str = "{}"

    def to_dict(self) -> dict:
        """序列化用户任务，隐藏账务和供应商内部实现细节。"""

        payload = asdict(self)
        payload.pop("model_snapshot", None)
        payload.pop("reservation_order_id", None)
        payload.pop("idempotency_key", None)
        payload["output"] = json_object(self.output_options)
        payload.pop("output_options", None)
        return payload


@dataclass(slots=True)
class ImageGenerationAssetRecord:
    """任务的私有图片输出。"""

    asset_id: str
    job_id: str
    storage_key: str
    content_hash: str
    mime_type: str
    width: int
    height: int
    byte_size: int
    created_at: float
    deleted_at: float = 0.0

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload.pop("storage_key", None)
        payload.pop("content_hash", None)
        return payload


@dataclass(slots=True)
class ImageGenerationTraceRecord:
    """生图供应商调用追溯。"""

    trace_id: str
    job_id: str
    model_id: str
    model_name: str
    provider: str
    phase: str
    provider_request_id: str
    ok: bool
    elapsed_ms: float
    error_code: str
    error: str
    created_at: float

    def to_dict(self) -> dict:
        return asdict(self)


def json_object(value: str) -> dict[str, Any]:
    """读取数据库 JSON 字段；历史坏数据只降级为空对象，不影响任务查询。"""

    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}

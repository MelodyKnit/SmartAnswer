"""大模型配置与 LLM 运行时配置相关业务操作。"""

from __future__ import annotations

import json
import secrets
import time
from threading import RLock

from ...auth import AuthError
from ...platform.config import (
    LLM_RUNTIME_CONFIG_KEYS,
    LLM_RUNTIME_DEFAULTS,
    LLM_RUNTIME_SECRET_KEYS,
    SYSTEM_CONFIG_KEYS,
)
from ..management.records import LlmModelRecord
from .contracts import LlmConfigRepository


def default_llm_runtime_config() -> dict[str, str]:
    """返回 LLM 答题运行时配置默认值。"""
    return dict(LLM_RUNTIME_DEFAULTS)


def legacy_system_llm_keys() -> tuple[str, ...]:
    """旧版 system_config 中承载 LLM 答题配置的键。"""
    return (
        "llm_base_url",
        "llm_model",
        "llm_api_key",
        "llm_stream",
        "llm_fallback",
        "llm_explain",
        "web_search_provider",
        "search_proxy",
        "llm_proxy",
        "google_search_api_key",
        "google_search_cx",
        "baidu_search_api_key",
        "ai_cache_enabled",
        "ai_cache_min_confidence",
        "ai_cache_min_confirmations",
        "llm_cache_enabled",
        "llm_cache_min_confidence",
        "llm_cache_min_confirmations",
    )


def list_llm_models(
    repository: LlmConfigRepository,
    lock: RLock,
    *,
    reveal_secret: bool = False,
) -> list[dict]:
    """列出所有已配置模型。"""
    with lock:
        return [item.to_dict(reveal_secret=reveal_secret) for item in repository.list_llm_models()]


def get_llm_model(
    repository: LlmConfigRepository,
    lock: RLock,
    model_id: str,
    *,
    reveal_secret: bool = False,
) -> dict:
    """读取单个模型配置。"""
    with lock:
        record = repository.get_llm_model(model_id)
    if record is None:
        raise AuthError("MODEL_NOT_FOUND", "模型配置不存在", http_status=404)
    return record.to_dict(reveal_secret=reveal_secret)


def create_llm_model(
    repository: LlmConfigRepository,
    lock: RLock,
    *,
    name: str,
    base_url: str,
    model: str,
    api_key: str = "",
    role: str = "backup",
    priority: int = 100,
    stream: bool = True,
    max_completion_tokens: int = 700,
    timeout_seconds: float = 30.0,
    status: str = "active",
) -> dict:
    """新增一个大模型配置条目。"""
    clean_name = (name or "").strip()
    clean_base_url = (base_url or "").strip()
    clean_model = (model or "").strip()
    if not clean_name:
        raise AuthError("INVALID_INPUT", "请填写模型名称", http_status=400)
    if not clean_base_url or not clean_model:
        raise AuthError("INVALID_INPUT", "请填写接口地址与模型标识", http_status=400)
    normalized_role = role if role in {"primary", "backup", "disabled"} else "backup"
    now = time.time()
    record = LlmModelRecord(
        model_id="llm_" + secrets.token_hex(8),
        name=clean_name,
        base_url=clean_base_url,
        model=clean_model,
        api_key=(api_key or "").strip(),
        role=normalized_role,
        priority=int(priority),
        stream=bool(stream),
        max_completion_tokens=max(1, int(max_completion_tokens)),
        timeout_seconds=max(1.0, float(timeout_seconds)),
        status=status if status in {"active", "inactive"} else "active",
        created_at=now,
        updated_at=now,
    )
    with lock:
        saved = repository.save_llm_model(record)
    return saved.to_dict()


def update_llm_model(
    repository: LlmConfigRepository,
    lock: RLock,
    model_id: str,
    values: dict,
) -> dict:
    """更新模型配置。"""
    with lock:
        record = repository.get_llm_model(model_id)
        if record is None:
            raise AuthError("MODEL_NOT_FOUND", "模型配置不存在", http_status=404)
        if "name" in values and values["name"] is not None:
            record.name = str(values["name"]).strip() or record.name
        if "base_url" in values and values["base_url"] is not None:
            record.base_url = str(values["base_url"]).strip() or record.base_url
        if "model" in values and values["model"] is not None:
            record.model = str(values["model"]).strip() or record.model
        if values.get("api_key"):
            record.api_key = str(values["api_key"]).strip()
        if values.get("role") in {"primary", "backup", "disabled"}:
            record.role = str(values["role"])
        if "priority" in values and values["priority"] is not None:
            record.priority = int(values["priority"])
        if "stream" in values and values["stream"] is not None:
            record.stream = bool(values["stream"])
        if "max_completion_tokens" in values and values["max_completion_tokens"] is not None:
            record.max_completion_tokens = max(1, int(values["max_completion_tokens"]))
        if "timeout_seconds" in values and values["timeout_seconds"] is not None:
            record.timeout_seconds = max(1.0, float(values["timeout_seconds"]))
        if values.get("status") in {"active", "inactive"}:
            record.status = str(values["status"])
        record.updated_at = time.time()
        saved = repository.save_llm_model(record)
    return saved.to_dict()


def delete_llm_model(
    repository: LlmConfigRepository,
    lock: RLock,
    model_id: str,
) -> bool:
    """删除一个模型配置。"""
    with lock:
        removed = repository.delete_llm_model(model_id)
    if not removed:
        raise AuthError("MODEL_NOT_FOUND", "模型配置不存在", http_status=404)
    return True


def active_llm_models(
    repository: LlmConfigRepository,
    lock: RLock,
) -> list[LlmModelRecord]:
    """返回用于组装主备链的启用模型。"""
    with lock:
        records = repository.list_llm_models()
    return [r for r in records if r.status == "active" and r.role != "disabled"]


def get_llm_runtime_config(
    repository: LlmConfigRepository,
    lock: RLock,
    *,
    reveal_secret: bool = False,
) -> dict:
    """读取统一后的 LLM 答题运行时配置。"""
    with lock:
        raw = read_llm_runtime_config_raw(repository)
        # 兼容旧版运行时配置键，优先提升为新的 llm_cache_* 形态。
        if not str(raw.get("llm_cache_enabled") or "").strip():
            raw["llm_cache_enabled"] = str(raw.get("ai_cache_enabled") or "").strip()
        if not str(raw.get("llm_cache_min_confidence") or "").strip():
            raw["llm_cache_min_confidence"] = str(raw.get("ai_cache_min_confidence") or "").strip()
        if not str(raw.get("llm_cache_min_confirmations") or "").strip():
            raw["llm_cache_min_confirmations"] = str(
                raw.get("ai_cache_min_confirmations") or ""
            ).strip()
        payload: dict[str, str | bool] = {}
        for key, value in raw.items():
            if key == "web_search_configs" and not reveal_secret:
                payload[key] = sanitize_web_search_configs(value)
            elif key in LLM_RUNTIME_SECRET_KEYS and not reveal_secret:
                payload[f"{key}_configured"] = bool(str(value).strip())
            else:
                payload[key] = value
        payload.pop("ai_cache_enabled", None)
        payload.pop("ai_cache_min_confidence", None)
        payload.pop("ai_cache_min_confirmations", None)
        return payload


def set_llm_runtime_config(
    repository: LlmConfigRepository,
    lock: RLock,
    values: dict[str, object],
) -> dict:
    """更新统一后的 LLM 答题运行时配置。"""
    with lock:
        existing = read_llm_runtime_config_raw(repository)
        normalized: dict[str, str] = {}
        for key, value in values.items():
            if key not in LLM_RUNTIME_CONFIG_KEYS:
                raise AuthError("INVALID_INPUT", f"不支持的大模型配置项: {key}", http_status=400)
            if key == "web_search_configs":
                normalized[key] = normalize_web_search_configs(
                    value,
                    existing_value=str(existing.get("web_search_configs") or ""),
                )
            else:
                normalized[key] = "" if value is None else str(value).strip()
        repository.set_settings("llm_runtime_config", normalized)
    return get_llm_runtime_config(repository, lock)


def read_llm_runtime_config_raw(repository: LlmConfigRepository) -> dict[str, str]:
    """读取未脱敏的 LLM 运行时配置，供运行时内部组装 provider 使用。"""

    raw = default_llm_runtime_config()
    raw.update(
        repository.get_settings(
            "llm_runtime_config",
            keys=set(LLM_RUNTIME_CONFIG_KEYS),
        )
    )
    return raw


def normalize_web_search_configs(value: object, *, existing_value: str = "") -> str:
    """规范化联网搜索配置，并在编辑时保留已配置但未重新输入的密钥。"""

    incoming = parse_web_search_configs(value, strict=True)
    existing_by_id = {
        str(item.get("id") or "").strip(): item
        for item in parse_web_search_configs(existing_value, strict=False)
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    normalized: list[dict[str, object]] = []
    for item in incoming:
        item_id = str(item.get("id") or "").strip()
        api_key = str(item.get("api_key") or "").strip()
        if (
            not api_key
            and item_id
            and bool_from_payload(item.get("api_key_configured"))
            and item_id in existing_by_id
        ):
            api_key = str(existing_by_id[item_id].get("api_key") or "").strip()
        clean_item: dict[str, object] = {
            "id": item_id,
            "name": str(item.get("name") or "").strip(),
            "provider": str(item.get("provider") or "").strip().lower(),
            "search_engine": str(item.get("search_engine") or item.get("engine") or "").strip(),
            "api_key": api_key,
            "cx": str(item.get("cx") or "").strip(),
            "proxy_url": str(item.get("proxy_url") or "").strip(),
            "status": normalize_status(str(item.get("status") or "")),
            "api_key_configured": bool(api_key),
        }
        normalized.append(clean_item)
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def sanitize_web_search_configs(value: object) -> str:
    """返回给前端的联网搜索配置，不暴露嵌套 API Key。"""

    sanitized: list[dict[str, object]] = []
    for item in parse_web_search_configs(value, strict=False):
        clean_item = dict(item)
        api_key = str(clean_item.pop("api_key", "") or "").strip()
        clean_item["api_key_configured"] = bool(api_key) or bool_from_payload(
            clean_item.get("api_key_configured")
        )
        sanitized.append(clean_item)
    return json.dumps(sanitized, ensure_ascii=False, separators=(",", ":"))


def parse_web_search_configs(value: object, *, strict: bool) -> list[dict[str, object]]:
    """解析联网搜索配置 JSON。"""

    if value is None or value == "":
        return []
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            if strict:
                raise AuthError("INVALID_INPUT", "联网搜索配置不是有效 JSON", http_status=400) from exc
            return []
    else:
        decoded = value
    if not isinstance(decoded, list):
        if strict:
            raise AuthError("INVALID_INPUT", "联网搜索配置必须是数组", http_status=400)
        return []
    result: list[dict[str, object]] = []
    for item in decoded:
        if not isinstance(item, dict):
            if strict:
                raise AuthError("INVALID_INPUT", "联网搜索配置项必须是对象", http_status=400)
            continue
        result.append(item)
    return result


def bool_from_payload(value: object) -> bool:
    """按前端表单提交语义解析布尔值。"""

    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def normalize_status(value: str) -> str:
    """联网搜索配置只接受启用或停用两种状态。"""

    return value if value in {"active", "inactive"} else "active"


def migrate_legacy_llm_settings(
    repository: LlmConfigRepository,
    *,
    default_system_config: dict[str, str],
) -> None:
    """把旧 system_config 中的大模型相关字段迁移到统一配置域。"""
    import os

    env_base_url = os.getenv("STQB_LLM_BASE_URL", "").strip()
    env_model = os.getenv("STQB_LLM_MODEL", "").strip()
    env_api_key = os.getenv("STQB_LLM_API_KEY", "").strip()
    env_stream = os.getenv("STQB_LLM_STREAM", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
        "disabled",
    }
    env_max_tokens_str = os.getenv("STQB_LLM_MAX_COMPLETION_TOKENS", "700").strip()
    try:
        env_max_tokens = int(env_max_tokens_str)
    except ValueError:
        env_max_tokens = 700

    legacy_keys = set(legacy_system_llm_keys())
    current_system = repository.get_settings("system_config")
    legacy_values = {key: current_system.get(key, "") for key in legacy_keys}

    has_legacy_in_db = any(str(value).strip() for value in legacy_values.values())
    has_legacy_in_env = bool(env_base_url and env_model)
    if not has_legacy_in_db and not has_legacy_in_env:
        return

    existing_runtime = repository.get_settings(
        "llm_runtime_config",
        keys=set(LLM_RUNTIME_CONFIG_KEYS),
    )
    runtime_payload = default_llm_runtime_config()
    runtime_payload.update(existing_runtime)
    for key in LLM_RUNTIME_CONFIG_KEYS:
        if (
            not str(existing_runtime.get(key) or "").strip()
            and str(legacy_values.get(key) or "").strip()
        ):
            runtime_payload[key] = str(legacy_values[key]).strip()
    legacy_cache_key_map = {
        "llm_cache_enabled": "ai_cache_enabled",
        "llm_cache_min_confidence": "ai_cache_min_confidence",
        "llm_cache_min_confirmations": "ai_cache_min_confirmations",
    }
    for new_key, old_key in legacy_cache_key_map.items():
        if (
            not str(existing_runtime.get(new_key) or "").strip()
            and str(legacy_values.get(old_key) or "").strip()
        ):
            runtime_payload[new_key] = str(legacy_values[old_key]).strip()
    repository.replace_settings("llm_runtime_config", runtime_payload)

    if not repository.list_llm_models():
        base_url = env_base_url or str(legacy_values.get("llm_base_url") or "").strip()
        model = env_model or str(legacy_values.get("llm_model") or "").strip()
        if base_url and model:
            now = time.time()
            record = LlmModelRecord(
                model_id="llm_" + secrets.token_hex(8),
                name="默认模型",
                base_url=base_url,
                model=model,
                api_key=env_api_key or str(legacy_values.get("llm_api_key") or "").strip(),
                role="primary",
                priority=0,
                stream=(
                    env_stream
                    if env_base_url
                    else (
                        str(legacy_values.get("llm_stream") or "true").strip().lower()
                        not in {"0", "false", "no", "off", "disabled"}
                    )
                ),
                max_completion_tokens=env_max_tokens if env_base_url else 700,
                timeout_seconds=30.0,
                status="active",
                created_at=now,
                updated_at=now,
            )
            repository.save_llm_model(record)

    new_system_payload = dict(default_system_config)
    for key in SYSTEM_CONFIG_KEYS:
        if key in current_system and str(current_system[key]).strip():
            new_system_payload[key] = str(current_system[key]).strip()
    repository.replace_settings("system_config", new_system_payload)

"""OCS 配置与客户端包资源读取。"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

BASE_URL_PLACEHOLDER = "{{BASE_URL}}"
TOKEN_PLACEHOLDER = "{{TOKEN}}"
CONFIG_NAME_PLACEHOLDER = "{{CONFIG_NAME}}"


def load_ocs_import_template_payload() -> dict[str, Any]:
    """读取随 Python 包发布的 OCS 导入模板。"""

    resource = files("study_qb_assistant.adapters.ocs.resources").joinpath(
        "import-script-template.json"
    )
    with resource.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("OCS 导入模板必须是 JSON 对象")
    return payload


def load_ocs_client_script_source() -> str:
    """读取随 Python 包发布的 OCS 客户端桥接脚本。"""

    resource = files("study_qb_assistant.adapters.ocs.resources").joinpath(
        "client-bridge.user.js"
    )
    return resource.read_text(encoding="utf-8")


def build_ocs_config(
    base_url: str,
    *,
    platform_name: str,
    token_description: str = "",
    token_key_mask: str = "",
) -> list[dict[str, Any]]:
    """根据运行时平台与令牌信息构建 OCS 题库配置。"""

    payload = load_ocs_import_template_payload()
    normalized_base_url = base_url.rstrip("/")
    config_items = payload.get("config_items") or []
    config_name = build_ocs_config_name(
        platform_name,
        token_description=token_description,
        token_key_mask=token_key_mask,
    )
    return [
        replace_placeholders(dict(item), normalized_base_url, config_name)
        for item in config_items
    ]


def build_ocs_config_name(
    platform_name: str,
    *,
    token_description: str = "",
    token_key_mask: str = "",
) -> str:
    """生成 OCS 中可区分来源与 API Key 的题库名称。"""

    normalized_platform_name = normalize_display_text(platform_name)
    if not normalized_platform_name:
        raise ValueError("平台名称不能为空")
    normalized_description = normalize_display_text(token_description)
    if normalized_description:
        return f"{normalized_platform_name} · {normalized_description}"

    normalized_key_mask = normalize_display_text(token_key_mask)
    if normalized_key_mask:
        return f"{normalized_platform_name} · {normalized_key_mask[-4:]}"
    return normalized_platform_name


def render_ocs_client_script(base_url: str, *, token: str = TOKEN_PLACEHOLDER) -> str:
    """渲染默认服务地址和 API Key 的 OCS 客户端脚本。"""

    normalized_base_url = base_url.rstrip("/")
    script = load_ocs_client_script_source()
    script = script.replace(
        '    baseUrl: "http://127.0.0.1:8765",',
        f'    baseUrl: "{normalized_base_url}",',
    )
    return script.replace('    apiKey: "",', f'    apiKey: "{token}",')


def replace_placeholders(value: Any, base_url: str, config_name: str) -> Any:
    """递归替换 OCS 模板中的服务地址占位符。"""

    if isinstance(value, str):
        return (
            value.replace(BASE_URL_PLACEHOLDER, base_url)
            .replace(CONFIG_NAME_PLACEHOLDER, config_name)
        )
    if isinstance(value, list):
        return [replace_placeholders(item, base_url, config_name) for item in value]
    if isinstance(value, tuple):
        return tuple(replace_placeholders(item, base_url, config_name) for item in value)
    if isinstance(value, dict):
        return {
            str(key): replace_placeholders(item, base_url, config_name)
            for key, item in value.items()
        }
    return value


def normalize_display_text(value: object) -> str:
    """清理配置展示文本，避免控制字符影响 OCS 配置可读性。"""

    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())

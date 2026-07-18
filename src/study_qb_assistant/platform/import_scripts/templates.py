"""导入脚本模板目录。

本模块把可提交的导入脚本模板放在仓库内的 JSONL 文件中统一维护：

- 普通用户“复制导入脚本”读取这里的默认模板。
- 管理端“导入脚本”页面读取这里的模板目录与预览内容。

后续如需新增其它平台脚本，开发者只需补充 JSONL 模板记录，不需要再改业务代码。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from ...adapters.ocs.config import (
    load_ocs_client_script_source,
    load_ocs_import_template_payload,
)

PLACEHOLDER_BASE_URL = "{{BASE_URL}}"
PLACEHOLDER_TOKEN = "{{TOKEN}}"
PLACEHOLDER_CONFIG_JSON = "{{CONFIG_JSON}}"
CLIENT_SCRIPT_TEMPLATE_PATTERN = re.compile(r"^\{\{CLIENT_SCRIPT:([^}]+)\}\}$")


@dataclass(slots=True, frozen=True)
class ImportScriptTemplate:
    """单条导入脚本模板定义。"""

    template_id: str
    name: str
    target: str
    description: str
    config_items: tuple[dict[str, Any], ...]
    script_template: str
    tags: tuple[str, ...] = ()
    requires_token: bool = True
    is_default: bool = False

    def to_summary(self) -> dict[str, Any]:
        return {
            "script_id": self.template_id,
            "name": self.name,
            "target": self.target,
            "description": self.description,
            "requires_token": self.requires_token,
            "is_default": self.is_default,
            "tags": list(self.tags),
        }


def load_import_script_templates() -> list[ImportScriptTemplate]:
    """读取随 OCS 集成包发布的默认导入模板。"""

    return [template_from_dict(load_ocs_import_template_payload())]


def template_from_dict(payload: dict[str, Any]) -> ImportScriptTemplate:
    return ImportScriptTemplate(
        template_id=str(payload["template_id"]),
        name=str(payload.get("name") or ""),
        target=str(payload.get("target") or "ocs"),
        description=str(payload.get("description") or ""),
        config_items=tuple(dict(item) for item in (payload.get("config_items") or ())),
        script_template=str(payload.get("script_template") or ""),
        tags=tuple(str(t) for t in (payload.get("tags") or ())),
        requires_token=bool(payload.get("requires_token", True)),
        is_default=bool(payload.get("is_default", False)),
    )


def get_import_script_template(template_id: str | None = None) -> ImportScriptTemplate:
    templates = load_import_script_templates()
    if not templates:
        raise ValueError("未配置任何导入脚本模板")
    if template_id:
        for template in templates:
            if template.template_id == template_id:
                return template
        raise KeyError(template_id)
    else:
        for template in templates:
            if template.is_default:
                return template
    return templates[0]


def render_import_script(
    template: ImportScriptTemplate,
    base_url: str,
    *,
    config_name: str,
) -> dict[str, Any]:
    normalized_base_url = base_url.rstrip("/")
    config_items = [
        replace_template_placeholders(item, normalized_base_url, config_name)
        for item in template.config_items
    ]
    script_template = resolve_script_template_content(template.script_template)
    script_content = replace_string_placeholders(
        script_template,
        base_url=normalized_base_url,
        config_name=config_name,
        config_json=json.dumps(config_items, ensure_ascii=False, indent=2),
    )
    if script_content.lstrip().startswith("// ==UserScript=="):
        script_content = inject_client_script_defaults(
            script_content,
            base_url=normalized_base_url,
        )
    result = {}
    result.update(template.to_summary())
    result.update({"content": script_content, "ocs_config": config_items})
    return result


def resolve_script_template_content(script_template: str) -> str:
    """解析脚本模板正文，支持读取 OCS 包内桥接脚本。"""

    raw = str(script_template or "")
    match = CLIENT_SCRIPT_TEMPLATE_PATTERN.match(raw.strip())
    if not match:
        return raw
    filename = match.group(1).strip()
    if filename not in {"client-bridge.user.js", "sisu-ocs-client-bridge.user.js"}:
        raise ValueError(f"不支持的客户端脚本资源: {filename}")
    return load_ocs_client_script_source()


def inject_client_script_defaults(script_content: str, *, base_url: str) -> str:
    """把桥接脚本中的默认服务地址和占位密钥替换为平台当前值。"""

    rendered = script_content.replace(
        '    baseUrl: "http://127.0.0.1:8765",',
        f'    baseUrl: "{base_url}",',
    )
    rendered = rendered.replace(
        '    apiKey: "",',
        '    apiKey: "{{TOKEN}}",',
    )
    return rendered


def replace_template_placeholders(value: Any, base_url: str, config_name: str) -> Any:
    if isinstance(value, str):
        return replace_string_placeholders(value, base_url=base_url, config_name=config_name)
    elif isinstance(value, list):
        return [replace_template_placeholders(item, base_url, config_name) for item in value]
    elif isinstance(value, tuple):
        return tuple(replace_template_placeholders(item, base_url, config_name) for item in value)
    elif isinstance(value, dict):
        return {
            str(key): replace_template_placeholders(item, base_url, config_name)
            for key, item in value.items()
        }
    return value


def replace_string_placeholders(
    value: str,
    base_url: str,
    config_name: str,
    config_json: str | None = None,
) -> str:
    rendered = value.replace(PLACEHOLDER_BASE_URL, base_url)
    rendered = rendered.replace("{{CONFIG_NAME}}", config_name)
    if config_json is not None:
        rendered = rendered.replace(PLACEHOLDER_CONFIG_JSON, config_json)
    return rendered

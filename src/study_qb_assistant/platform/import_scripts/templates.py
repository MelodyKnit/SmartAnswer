"""后台客户端模板目录。

内置 OCS 配置模板来自 OCS 适配器资源；管理员创建的自定义模板由模板仓储维护。
普通用户复制 OCS 配置走 Token API，不经过这里的脚本模板渲染。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ...adapters.ocs.config import load_ocs_config_template_payload

PLACEHOLDER_BASE_URL = "{{BASE_URL}}"
PLACEHOLDER_TOKEN = "{{TOKEN}}"
PLACEHOLDER_CONFIG_JSON = "{{CONFIG_JSON}}"


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

    return [template_from_dict(load_ocs_config_template_payload())]


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
    script_content = replace_string_placeholders(
        template.script_template,
        base_url=normalized_base_url,
        config_name=config_name,
        config_json=json.dumps(config_items, ensure_ascii=False, indent=2),
    )
    result = {}
    result.update(template.to_summary())
    result.update({"content": script_content, "ocs_config": config_items})
    return result


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

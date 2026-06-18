"""导入脚本模板目录。

本模块把可提交的导入脚本模板放在仓库内的 JSONL 文件中统一维护：

- 普通用户“复制导入脚本”读取这里的默认模板。
- 管理端“导入脚本”页面读取这里的模板目录与预览内容。

后续如需新增其它平台脚本，开发者只需补充 JSONL 模板记录，不需要再改业务代码。
"""

from __future__ import annotations
import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

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
    template_path = files("study_qb_assistant.platform").joinpath("import_script_templates.jsonl")
    templates = []
    with template_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            templates.append(template_from_dict(payload))
    return templates


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


def render_import_script(template: ImportScriptTemplate, base_url: str) -> dict[str, Any]:
    normalized_base_url = base_url.rstrip("/")
    config_items = [
        replace_template_placeholders(item, normalized_base_url) for item in template.config_items
    ]
    script_content = replace_string_placeholders(
        template.script_template,
        base_url=normalized_base_url,
        config_json=json.dumps(config_items, ensure_ascii=False, indent=2),
    )
    result = {}
    result.update(template.to_summary())
    result.update({"content": script_content, "ocs_config": config_items})
    return result


def replace_template_placeholders(value: Any, base_url: str) -> Any:
    if isinstance(value, str):
        return replace_string_placeholders(value, base_url=base_url)
    elif isinstance(value, list):
        return [replace_template_placeholders(item, base_url) for item in value]
    elif isinstance(value, tuple):
        return tuple(replace_template_placeholders(item, base_url) for item in value)
    elif isinstance(value, dict):
        return {
            str(key): replace_template_placeholders(item, base_url) for key, item in value.items()
        }
    return value


def replace_string_placeholders(value: str, base_url: str, config_json: str | None = None) -> str:
    rendered = value.replace(PLACEHOLDER_BASE_URL, base_url)
    if config_json is not None:
        rendered = rendered.replace(PLACEHOLDER_CONFIG_JSON, config_json)
    return rendered

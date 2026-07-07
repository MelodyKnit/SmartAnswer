"""大模型提示词模板加载与渲染服务。"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

from ..config import get_global_config


@lru_cache(maxsize=1)
def prompt_environment() -> Environment:
    """构建严格变量校验的 Jinja 提示词模板环境。"""

    prompts_dir = get_global_config().prompts_dir
    return Environment(
        loader=FileSystemLoader(str(prompts_dir)),
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )


def render_prompt(template_name: str, **context: Any) -> str:
    """渲染指定提示词模板。

    Args:
        template_name: `configs/prompts` 下的模板文件名。
        **context: 模板变量。

    Returns:
        str: 渲染后的提示词文本。

    Raises:
        RuntimeError: 模板不存在或渲染失败时抛出明确错误。
    """

    try:
        template = prompt_environment().get_template(template_name)
        return template.render(**context).strip()
    except TemplateNotFound as exc:
        raise RuntimeError(f"prompt template not found: {template_name}") from exc
    except Exception as exc:
        raise RuntimeError(f"prompt template render failed: {template_name}: {exc}") from exc


def clear_prompt_cache() -> None:
    """清理提示词模板缓存，供测试或热更新场景使用。"""

    prompt_environment.cache_clear()

"""查询请求解析与清洗工具。"""

from __future__ import annotations

from typing import Any

from ..input_anomalies import (
    CHOICE_TYPES,
    is_image_data_url,
    has_placeholder_options,
    is_image_url,
    normalize_image_data_urls,
    normalize_image_urls,
)
from ..models import QuestionQuery
from .schemas import QueryPayload


def build_query_from_mapping(params: dict[str, list[str]]) -> QuestionQuery:
    """从类查询字符串字典构建标准题目查询对象。"""
    title = first_value(params, "title")
    question_type = first_value(params, "type") or "unknown"
    options = sanitize_query_options(
        title, question_type, split_options(first_value(params, "options"))
    )
    request_id = first_value(params, "request_id") or None
    image_urls = normalize_image_urls(split_raw_values(first_value(params, "image_urls")), (title,))
    return QuestionQuery(
        title=title,
        options=options,
        question_type=question_type,
        request_id=request_id,
        page_url=first_value(params, "page_url") or None,
        image_urls=image_urls,
        image_data_urls=normalize_image_data_urls(
            split_raw_values(first_value(params, "image_data_urls"))
        ),
    )


def build_query_from_payload(payload: QueryPayload | dict[str, Any]) -> QuestionQuery:
    """从 JSON 请求体构建标准题目查询对象。"""
    if isinstance(payload, QueryPayload):
        raw_options = payload.options
        question_type = payload.type or payload.question_type or "unknown"
        title = str(payload.title or "")
        return QuestionQuery(
            title=title,
            options=sanitize_query_options(
                title, str(question_type), options_from_raw(raw_options)
            ),
            question_type=str(question_type),
            request_id=payload.request_id,
            page_url=payload.page_url,
            image_urls=normalize_image_urls(payload.image_urls, (title,)),
            image_data_urls=normalize_image_data_urls(payload.image_data_urls),
            option_image_urls=normalize_option_image_urls(payload.option_image_urls),
            option_image_data_urls=normalize_option_image_data_urls(payload.option_image_data_urls),
        )
    raw_options = payload.get("options") or ()
    title = str(payload.get("title") or "")
    question_type = str(payload.get("type") or payload.get("question_type") or "unknown")
    return QuestionQuery(
        title=title,
        options=sanitize_query_options(title, question_type, options_from_raw(raw_options)),
        question_type=question_type,
        request_id=payload.get("request_id"),
        page_url=payload.get("page_url"),
        image_urls=normalize_image_urls(payload.get("image_urls") or (), (title,)),
        image_data_urls=normalize_image_data_urls(payload.get("image_data_urls") or ()),
        option_image_urls=normalize_option_image_urls(payload.get("option_image_urls") or {}),
        option_image_data_urls=normalize_option_image_data_urls(
            payload.get("option_image_data_urls") or {}
        ),
    )


def options_from_raw(raw_options: str | list[str] | tuple[str, ...] | Any) -> tuple[str, ...]:
    """把不同来源的选项参数统一规整为元组。"""
    if isinstance(raw_options, str):
        return split_options(raw_options)
    return tuple(str(value).strip() for value in raw_options or () if is_real_option(str(value)))


def first_value(params: dict[str, list[str]], key: str) -> str:
    """读取多值字典的第一个值。"""
    values = params.get(key) or [""]
    return values[0]


def split_options(value: str) -> tuple[str, ...]:
    """拆分 OCS 传来的选项文本，并过滤编辑器噪声。"""
    if not value:
        return ()
    parts = value.splitlines() if "\n" in value else value.split("#")
    return tuple(part.strip() for part in parts if is_real_option(part))


def split_raw_values(value: str) -> tuple[str, ...]:
    """按 OCS 常见分隔方式拆分普通字段，不套用选项过滤规则。"""

    if not value:
        return ()
    parts = value.splitlines() if "\n" in value else value.split("#")
    return tuple(part.strip() for part in parts if part.strip())


def is_real_option(value: str) -> bool:
    """判断字符串是否是真实选项，而不是编辑器脚本残片。"""
    stripped = value.strip()
    if not stripped:
        return False
    noisy_markers = (
        "window.",
        "ueditor",
        "geteditor",
        "loadeditoranswerd",
        "answercontentchange",
        "allowpaste",
        "addlistener",
        "beforepaste",
        "initialframe",
        "var ",
        "function",
        "点击上传",
    )
    lowered = stripped.lower()
    if stripped in {"}", "{", "});", ");", ");}", "};"}:
        return False
    if is_image_url(stripped):
        return False
    return not any(marker in lowered for marker in noisy_markers)


def sanitize_query_options(
    title: str, question_type: str, options: tuple[str, ...]
) -> tuple[str, ...]:
    """按题型清洗选项，避免填空题被错误选项污染。"""
    if is_completion_request(title, question_type):
        return ()
    if has_placeholder_options(options):
        return ()
    return options


def normalize_option_image_urls(raw_value: object) -> dict[str, str]:
    """标准化选项图片映射，只保留 A-Z 标签和可识别图片 URL。"""

    if not isinstance(raw_value, dict):
        return {}
    result: dict[str, str] = {}
    for key, value in raw_value.items():
        label = str(key or "").strip().upper()
        urls = normalize_image_urls((value,))
        if len(label) == 1 and "A" <= label <= "Z" and urls:
            result[label] = urls[0]
    return result


def normalize_option_image_data_urls(raw_value: object) -> dict[str, str]:
    """标准化选项图片 data URL 映射，只保留 A-Z 标签。"""

    if not isinstance(raw_value, dict):
        return {}
    result: dict[str, str] = {}
    for key, value in raw_value.items():
        label = str(key or "").strip().upper()
        text = str(value or "").strip()
        if len(label) == 1 and "A" <= label <= "Z" and is_image_data_url(text):
            result[label] = text
    return result


def is_completion_request(title: str, question_type: str) -> bool:
    """判断当前请求是否应按填空题处理。"""
    normalized_type = (question_type or "").strip().lower()
    stripped_title = (title or "").strip()
    if normalized_type in CHOICE_TYPES or stripped_title.startswith(("单选题", "多选题")):
        return False
    return (
        normalized_type in {"completion", "blank", "fill", "填空", "填空题"}
        or stripped_title.startswith("填空题")
        or "____" in stripped_title
        or "___" in stripped_title
    )

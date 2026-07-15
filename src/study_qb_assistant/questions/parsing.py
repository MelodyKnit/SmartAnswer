"""查询请求解析与清洗工具。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from study_qb_assistant.media.inputs import (
    is_image_data_url,
    is_image_url,
    normalize_image_data_urls,
    normalize_image_urls,
    strip_embedded_image_urls,
)
from .models import QuestionQuery
from .validation import CHOICE_TYPES, has_placeholder_options


def build_query_from_mapping(params: dict[str, list[str]]) -> QuestionQuery:
    """从类查询字符串字典构建标准题目查询对象。"""
    title = first_value(params, "title")
    question_type = first_value(params, "type") or "unknown"
    page_url = first_value(params, "page_url") or None
    image_urls = normalize_image_urls(split_raw_values(first_value(params, "image_urls")), (title,))
    image_data_urls = normalize_image_data_urls(
        split_raw_values(first_value(params, "image_data_urls"))
    )
    normalized_title = strip_embedded_image_urls(
        title,
        image_urls,
        image_data_urls,
    )
    options = sanitize_query_options(
        normalized_title, question_type, split_options(first_value(params, "options"))
    )
    request_id = first_value(params, "request_id") or None
    return QuestionQuery(
        title=normalized_title,
        options=options,
        question_type=question_type,
        request_id=request_id,
        page_url=page_url,
        image_capture_status=first_value(params, "image_capture_status"),
        image_capture_failures=safe_int(first_value(params, "image_capture_failures")),
        image_urls=image_urls,
        image_data_urls=image_data_urls,
    )


def build_query_from_payload(payload: Mapping[str, Any] | Any) -> QuestionQuery:
    """从 JSON 请求体构建标准题目查询对象。"""
    if not isinstance(payload, Mapping):
        model_dump = getattr(payload, "model_dump", None)
        if model_dump is None or not callable(model_dump):
            raise TypeError("query payload must be a mapping or support model_dump()")
        payload = model_dump()
    raw_options = payload.get("options") or ()
    title = str(payload.get("title") or "")
    question_type = str(payload.get("type") or payload.get("question_type") or "unknown")
    image_urls = normalize_image_urls(payload.get("image_urls") or (), (title,))
    image_data_urls = normalize_image_data_urls(payload.get("image_data_urls") or ())
    normalized_title = strip_embedded_image_urls(
        title,
        image_urls,
        image_data_urls,
    )
    return QuestionQuery(
        title=normalized_title,
        options=sanitize_query_options(
            normalized_title,
            question_type,
            options_from_raw(raw_options),
        ),
        question_type=question_type,
        request_id=payload.get("request_id"),
        page_url=payload.get("page_url"),
        image_capture_status=str(payload.get("image_capture_status") or ""),
        image_capture_failures=safe_int(payload.get("image_capture_failures")),
        image_urls=image_urls,
        image_data_urls=image_data_urls,
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


def safe_int(value: object) -> int:
    """安全解析整数，异常输入按 0 处理。"""

    try:
        return int(str(value or "0"))
    except (TypeError, ValueError):
        return 0


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

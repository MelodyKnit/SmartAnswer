"""查询请求解析与清洗工具。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
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


@dataclass(frozen=True, slots=True)
class ParsedPastedQuestion:
    """保存单输入框粘贴文本解析出的标准题目字段。"""

    title: str
    options: tuple[str, ...]
    inferred_question_type: str


class QueryInputError(ValueError):
    """表示查题请求在进入答题链路前存在可提示给用户的输入冲突。"""


OPTION_LINE_PATTERN = re.compile(
    r"^\s*(?:[（(]\s*([A-Z])\s*[）)]|([A-Z])\s*[.．、:：)）])\s*\S.*$",
    re.IGNORECASE,
)

QUESTION_TYPE_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("multiple", ("多选", "multiple-choice", "multiple choice", "multi-choice")),
    ("single", ("单选", "single-choice", "single choice")),
    ("judgement", ("判断", "true/false", "true false", "judgement", "judgment")),
    ("completion", ("填空", "fill-in", "fill in", "completion")),
)


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
    raw_text = str(payload.get("raw_text") or "").strip()
    if raw_text:
        ensure_raw_text_is_standalone(payload)
        parsed_question = parse_pasted_question_text(raw_text)
        raw_options = parsed_question.options
        title = parsed_question.title
        question_type = resolve_raw_text_question_type(payload, parsed_question.inferred_question_type)
    else:
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


def parse_pasted_question_text(raw_text: str) -> ParsedPastedQuestion:
    """解析在线搜题单输入框中的题干与末尾选择题选项块。

    只接受至少两条连续、标签严格递增的选项行，避免正文中偶然出现的
    字母编号被错误拆成选项。无法确认的文本完整保留为题干，由后续模型
    链路结合原文处理。
    """

    normalized_text = str(raw_text or "").strip()
    lines = normalized_text.splitlines()
    option_block = find_terminal_option_block(lines)
    if option_block is None:
        return ParsedPastedQuestion(
            title=normalized_text,
            options=(),
            inferred_question_type=infer_question_type(normalized_text),
        )

    start, end = option_block
    if not any(line.strip() for line in lines[:start]):
        return ParsedPastedQuestion(
            title=normalized_text,
            options=(),
            inferred_question_type=infer_question_type(normalized_text),
        )
    title = "\n".join(lines[:start]).strip()
    options = tuple(line.strip() for line in lines[start:end])
    return ParsedPastedQuestion(
        title=title,
        options=options,
        inferred_question_type=infer_question_type(title),
    )


def ensure_raw_text_is_standalone(payload: Mapping[str, Any]) -> None:
    """拒绝原始粘贴文本与结构化题目字段混用，避免请求语义不明确。"""

    if str(payload.get("title") or "").strip() or has_nonempty_raw_options(payload.get("options")):
        raise QueryInputError("raw_text 不能与 title 或 options 同时提交")


def has_nonempty_raw_options(raw_options: object) -> bool:
    """判断结构化选项字段是否携带非空值，不依赖后续选项清洗规则。"""

    if isinstance(raw_options, str):
        return bool(raw_options.strip())
    if isinstance(raw_options, (list, tuple)):
        return any(str(option or "").strip() for option in raw_options)
    return bool(str(raw_options or "").strip())


def resolve_raw_text_question_type(payload: Mapping[str, Any], inferred_type: str) -> str:
    """让显式题型覆盖自动识别；unknown 保持自动识别语义。"""

    explicit_type = str(payload.get("type") or payload.get("question_type") or "").strip()
    if explicit_type and explicit_type.lower() != "unknown":
        return explicit_type
    return inferred_type


def find_terminal_option_block(lines: list[str]) -> tuple[int, int] | None:
    """定位末尾连续的标准选项行，返回左闭右开区间。"""

    for start, line in enumerate(lines):
        previous_label = option_label_from_line(line)
        if previous_label is None:
            continue

        end = start + 1
        while end < len(lines):
            current_label = option_label_from_line(lines[end])
            if current_label is None or ord(current_label) != ord(previous_label) + 1:
                break
            previous_label = current_label
            end += 1

        if end - start < 2:
            continue
        if all(not line.strip() for line in lines[end:]):
            return start, end
    return None


def option_label_from_line(line: str) -> str | None:
    """读取一行标准选项开头的字母标签。"""

    match = OPTION_LINE_PATTERN.match(line)
    if match is None:
        return None
    return (match.group(1) or match.group(2) or "").upper() or None


def infer_question_type(title: str) -> str:
    """仅从明确题型标记推断题型，不以选项数量猜测。"""

    normalized_title = str(title or "").casefold()
    for question_type, markers in QUESTION_TYPE_MARKERS:
        if any(marker in normalized_title for marker in markers):
            return question_type
    return "unknown"


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

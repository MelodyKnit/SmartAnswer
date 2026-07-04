"""查题输入异常识别策略。

本模块只判断“传入服务端的题目上下文是否足够作答”，不负责 DOM 采集、
模型推理或题库检索。这样可以让 OCS、在线搜题和后续脚本增强共享同一套边界。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .models import ModelAnswer, QueryResult, QuestionQuery

CHOICE_TYPES = {"single", "multiple", "单选", "单选题", "多选", "多选题"}
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
INPUT_ANOMALY_MODE = "input_anomaly"
DATA_URL_PATTERN = re.compile(r"^data:image/[-+.\w]+;base64,[A-Za-z0-9+/=\s]+$", re.I)
EMBEDDED_IMAGE_URL_PATTERN = re.compile(
    r"https?://[^\s\u3000\"'<>]+?\.(?:png|jpg|jpeg|webp|gif|bmp)(?:\?[^\s\u3000\"'<>]*)?",
    re.I,
)


@dataclass(slots=True)
class InputAnomaly:
    """描述一次不能安全作答的输入异常。"""

    code: str
    message: str
    flags: tuple[str, ...]
    context: dict[str, object] = field(default_factory=dict)


def is_image_url(value: str) -> bool:
    """判断字符串是否像直接指向图片资源的 URL。"""

    text = str(value or "").strip()
    if not text:
        return False
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    path = parsed.path.lower()
    return path.endswith(IMAGE_EXTENSIONS)


def normalize_image_urls(*groups: object) -> tuple[str, ...]:
    """从多个输入来源提取去重后的图片 URL。"""

    urls: list[str] = []
    for group in groups:
        if isinstance(group, str):
            candidates = re.split(r"[\s,，]+", group)
        else:
            candidates = list(group or ())
        for candidate in candidates:
            text = str(candidate or "").strip()
            if is_image_url(text) and text not in urls:
                urls.append(text)
    return tuple(urls)


def is_image_data_url(value: str) -> bool:
    """判断字符串是否是图片 data URL。"""

    text = str(value or "").strip()
    if not text:
        return False
    return bool(DATA_URL_PATTERN.match(text))


def normalize_image_data_urls(*groups: object) -> tuple[str, ...]:
    """从多个输入来源提取去重后的图片 data URL。"""

    urls: list[str] = []
    for group in groups:
        if isinstance(group, str):
            candidates = (group,)
        else:
            candidates = list(group or ())
        for candidate in candidates:
            text = str(candidate or "").strip()
            if is_image_data_url(text) and text not in urls:
                urls.append(text)
    return tuple(urls)


def legacy_image_url_only(query: QuestionQuery) -> bool:
    """判断当前图片题是否仍停留在只传 URL 的旧链路。"""

    return bool(normalize_image_urls(query.image_urls, (query.title,))) and not bool(
        normalize_image_data_urls(
            query.image_data_urls,
            query.option_image_data_urls.values(),
        )
    )


def strip_embedded_image_urls(title: str, *groups: object) -> str:
    """移除题干中的裸露图片 URL，避免污染文本匹配与模型输入。"""

    raw = str(title or "").strip()
    if not raw:
        return ""
    cleaned = raw
    for url in normalize_image_urls((raw,), *groups):
        if cleaned != url:
            cleaned = cleaned.replace(url, " ")
    cleaned = EMBEDDED_IMAGE_URL_PATTERN.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"([\u4e00-\u9fff])\s+([\u4e00-\u9fff])", r"\1\2", cleaned)
    return cleaned or raw


def is_choice_query(query: QuestionQuery) -> bool:
    """判断题型是否属于必须依赖选项的客观选择题。"""

    normalized = (query.question_type or "").strip().lower()
    title = (query.title or "").strip()
    return normalized in CHOICE_TYPES or title.startswith(("单选题", "多选题"))


def is_placeholder_option(value: str) -> bool:
    """识别只有选项标签、没有实际选项文本的占位选项。"""

    text = str(value or "").strip()
    match = re.match(r"^([A-Z])[\s.．、:：-]*([A-Z])?$", text, re.I)
    if not match:
        return False
    left = match.group(1).upper()
    right = (match.group(2) or left).upper()
    return left == right


def has_placeholder_options(options: tuple[str, ...]) -> bool:
    """判断当前选项列表是否整体像 A/B/C/D 这类占位内容。"""

    if not options:
        return False
    return sum(1 for option in options if is_placeholder_option(option)) >= max(1, len(options) - 1)


def analyze_query_input(query: QuestionQuery) -> InputAnomaly | None:
    """识别进入答题流程前即可确定的输入异常。"""

    image_urls = normalize_image_urls(query.image_urls, (query.title,))
    flags: list[str] = []
    if is_image_url(query.title):
        flags.append("image_url_as_title")
    if image_urls and not query.image_urls:
        flags.append("image_urls_inferred")

    if not is_choice_query(query):
        return None

    placeholder_options = has_placeholder_options(query.options)
    if placeholder_options:
        flags.append("placeholder_options")
    has_real_options = bool(query.options) and not placeholder_options
    if has_real_options:
        return None

    if image_urls:
        # 图片题仍允许进入多模态/OCR 链路；只有图片不可读时再转为异常。
        return None
    if not choice_stem_requires_options(query.title):
        return None

    flags.append("missing_options_for_choice")
    return InputAnomaly(
        code="INPUT_MISSING_OPTIONS",
        message="题目缺少可匹配选项，无法安全作答",
        flags=tuple(dict.fromkeys(flags)),
        context={"options_count": len(query.options)},
    )


def choice_stem_requires_options(title: str) -> bool:
    """判断题干是否明确依赖外部选项，缺选项时不适合交给 AI 猜。"""

    text = str(title or "").strip()
    option_dependent_markers = (
        "以下哪个",
        "以下哪",
        "下列",
        "选项",
        "说法正确",
        "说法错误",
        "错误的是",
        "正确的是",
        "___",
        "____",
    )
    return any(marker in text for marker in option_dependent_markers) or bool(
        re.search(r"[（(]\s*[）)]", text)
    )


def model_answer_indicates_unreadable_image(query: QuestionQuery, answer: ModelAnswer) -> bool:
    """识别模型实际没有读到图片却返回了低置信度占位文本的情况。"""

    if not normalize_image_urls(query.image_urls, (query.title,)):
        return False
    combined = " ".join(
        value
        for value in (answer.candidate_answer, answer.answer_text, answer.explanation)
        if value
    ).casefold()
    unreadable_markers = (
        "can't access the image",
        "cannot access the image",
        "无法访问图片",
        "无法查看图片",
        "看不到图片",
        "不能确定正确选项",
    )
    return answer.confidence < 0.3 or any(marker in combined for marker in unreadable_markers)


def provider_error_indicates_unreadable_image(query: QuestionQuery, error: Exception) -> bool:
    """识别图片题在模型请求阶段就因图片不可读而失败的异常。"""

    if not normalize_image_urls(query.image_urls, (query.title,)):
        return False
    combined = str(error or "").casefold()
    unreadable_markers = (
        "can't access the image",
        "cannot access the image",
        "failed to download file",
        "error getting file type",
        "image unreadable",
        "无法访问图片",
        "无法查看图片",
        "看不到图片",
        "count_token_failed",
        "status code: 403",
    )
    return any(marker in combined for marker in unreadable_markers)


def result_from_input_anomaly(query: QuestionQuery, anomaly: InputAnomaly) -> QueryResult:
    """把输入异常转换为统一 QueryResult，供 API 与 usage log 共用。"""

    return QueryResult(
        ok=False,
        query=query,
        candidate_answer=None,
        answer_text=None,
        explanation=None,
        confidence=0.0,
        resolution_mode=INPUT_ANOMALY_MODE,
        review_required=True,
        sources=(
            {
                "source_name": "input-validator",
                "source_type": "input_anomaly",
                "source_id": anomaly.code,
                "source_url": None,
                "source_license": None,
                "score": 0.0,
            },
        ),
        error_code=anomaly.code,
        error_message=anomaly.message,
        debug={
            "provider": "input-validator",
            "input_flags": ",".join(anomaly.flags),
            **{key: str(value) for key, value in anomaly.context.items()},
        },
    )

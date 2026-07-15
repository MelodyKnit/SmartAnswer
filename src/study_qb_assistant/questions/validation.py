"""进入答题流程前的题目完整性校验。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from study_qb_assistant.media.inputs import is_image_url, normalize_image_urls
from .models import QuestionQuery

CHOICE_TYPES = {"single", "multiple", "单选", "单选题", "多选", "多选题"}


@dataclass(slots=True)
class InputAnomaly:
    """描述一次不能安全作答的输入异常。"""

    code: str
    message: str
    flags: tuple[str, ...]
    context: dict[str, object] = field(default_factory=dict)


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
    placeholder_count = sum(1 for option in options if is_placeholder_option(option))
    return placeholder_count >= max(1, len(options) - 1)


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
    if query.options and not placeholder_options:
        return None
    if image_urls or not choice_stem_requires_options(query.title):
        return None

    flags.append("missing_options_for_choice")
    return InputAnomaly(
        code="INPUT_MISSING_OPTIONS",
        message="题目缺少可匹配选项，无法安全作答",
        flags=tuple(dict.fromkeys(flags)),
        context={"options_count": len(query.options)},
    )


def choice_stem_requires_options(title: str) -> bool:
    """判断题干是否明确依赖外部选项。"""

    text = str(title or "").strip()
    markers = (
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
    return any(marker in text for marker in markers) or bool(re.search(r"[（(]\s*[）)]", text))

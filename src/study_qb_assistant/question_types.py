"""题型形态判断工具。"""

from __future__ import annotations

import re

from .models import QuestionQuery

COMPLETION_TYPES = {"completion", "blank", "fill", "填空", "填空题"}


def is_completion_query(query: QuestionQuery | None) -> bool:
    """判断查询是否属于填空/补全文本类题型。"""

    if query is None:
        return False
    normalized_type = (query.question_type or "").strip().lower()
    title = (query.title or "").strip()
    return normalized_type in COMPLETION_TYPES or title.startswith("填空题")


def has_blank_marker(title: str) -> bool:
    """识别 OCS/超星常见空位标记，避免把真正填空题误判为开放文本题。"""

    normalized = title.strip()
    if "___" in normalized or "＿＿" in normalized:
        return True
    return re.search(r"[【\[]\s*\d+\s*[】\]]\s*[_＿]*", normalized) is not None


def is_open_text_completion(query: QuestionQuery | None) -> bool:
    """判断 completion 是否更像开放文本题，而不是有明确空位的填空题。"""

    if query is None or query.options:
        return False
    return is_completion_query(query) and not has_blank_marker(query.title or "")

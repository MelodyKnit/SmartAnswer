"""题型形态判断工具。"""

from __future__ import annotations

import re

from study_qb_assistant.questions.models import QuestionQuery

COMPLETION_TYPES = {"completion", "blank", "fill", "填空", "填空题"}
JUDGEMENT_TYPES = {"judgement", "judge", "truefalse", "判断", "判断题"}
MULTIPLE_TYPES = {"multiple", "multi", "多选", "多选题"}


def is_completion_query(query: QuestionQuery | None) -> bool:
    """判断查询是否属于填空/补全文本类题型。"""

    if query is None:
        return False
    normalized_type = (query.question_type or "").strip().lower()
    title = (query.title or "").strip()
    return normalized_type in COMPLETION_TYPES or title.startswith("填空题")


def has_blank_marker(title: str) -> bool:
    """识别 OCS/超星常见空位标记，避免把真正填空题误判为开放文本题。"""

    return blank_count_hint(title) > 0


def blank_count_hint(title: str) -> int:
    """估算题干中的可回填空位数量。

    OCS 页面经常把填空题传成 `【1】____`、`____` 或空括号 `（）（）`。
    这里仅统计明确空位标记，避免把普通括号说明误判成多空题。
    """

    normalized = title.strip()
    numbered = re.findall(r"[【\[]\s*\d+\s*[】\]]\s*[_＿]*", normalized)
    if numbered:
        return len(numbered)
    empty_parentheses = re.findall(r"(?:\(\s*\)|（\s*）)", normalized)
    if empty_parentheses:
        return len(empty_parentheses)
    return len(re.findall(r"(?:_{2,}|＿{2,})", normalized))


def is_open_text_completion(query: QuestionQuery | None) -> bool:
    """判断 completion 是否更像开放文本题，而不是有明确空位的填空题。"""

    if query is None or query.options:
        return False
    return is_completion_query(query) and not has_blank_marker(query.title or "")

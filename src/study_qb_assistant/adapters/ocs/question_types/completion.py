"""OCS 填空题处理策略。"""

from __future__ import annotations

import json
import re

from ....logger import log_event
from study_qb_assistant.questions.models import QueryResult
from study_qb_assistant.questions.types import blank_count_hint, is_open_text_completion
from .base import BaseOcsQuestionTypeHandler, OcsFormattedAnswer


class CompletionOcsHandler(BaseOcsQuestionTypeHandler):
    """按 OCS 契约输出单空文本或多空 JSON 数组。"""

    canonical_type = "completion"
    aliases = frozenset({"completion", "blank", "fill", "fillblank", "填空", "填空题"})

    def matches(self, raw_type: str, result: QueryResult) -> bool:
        normalized = raw_type.strip().casefold()
        title = result.query.title.strip()
        return normalized in self.aliases or (
            normalized in {"", "unknown", "undefined"}
            and (title.startswith("填空题") or "___" in title)
        )

    def format_answer(self, result: QueryResult) -> OcsFormattedAnswer:
        if (
            is_open_text_completion(result.query)
            and result.answer_text
            and not looks_like_json_array(result.candidate_answer)
        ):
            return OcsFormattedAnswer(result.answer_text, "text")

        answer = result.candidate_answer or result.answer_text
        blanks = blank_count_hint(result.query.title)
        parts = completion_answer_parts(answer, blank_count=blanks)
        diagnostics: dict[str, object] = {
            "answer_parts_count": len(parts),
            "blank_count_hint": blanks,
        }
        if len(parts) > 1:
            if blanks and blanks != len(parts):
                log_event(
                    "ocs_completion_answer_count_mismatch",
                    {
                        "title": result.query.title,
                        "answer_parts_count": len(parts),
                        "blank_count_hint": blanks,
                    },
                )
            return OcsFormattedAnswer(
                json.dumps(parts, ensure_ascii=False),
                "json_array",
                diagnostics,
            )
        return OcsFormattedAnswer(answer, "text", diagnostics)


def looks_like_json_array(value: str | None) -> bool:
    """判断答案是否已经是 JSON 数组文本。"""

    text = (value or "").strip()
    return text.startswith("[") and text.endswith("]")


def completion_answer_parts(value: str | None, *, blank_count: int = 0) -> list[str]:
    """把填空答案拆成 OCS 多空可消费的答案片段。"""

    text = (value or "").strip()
    if not text:
        return []
    parsed_parts = json_array_parts(text)
    if parsed_parts:
        return parsed_parts
    if blank_count > 1:
        bracketed_parts = bracketed_completion_parts(text, blank_count=blank_count)
        if bracketed_parts:
            return bracketed_parts
    for separator in ("###", "===", "---", "#", "|", "；", ";"):
        if separator in text:
            parts = [part.strip() for part in text.split(separator) if part.strip()]
            if len(parts) > 1:
                return parts
    if blank_count > 1:
        words = [part.strip() for part in re.split(r"\s+", text) if part.strip()]
        if len(words) == blank_count and all(len(word) <= 40 for word in words):
            return [strip_answer_wrapper(word) for word in words]
    return [text]


def json_array_parts(value: str) -> list[str]:
    """解析 JSON 数组答案。"""

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def bracketed_completion_parts(value: str, *, blank_count: int) -> list[str]:
    """解析以中英文括号分隔的多空答案。"""

    groups = re.findall(r"\(([^()]*)\)|（([^（）]*)）", value)
    parts = [part.strip() for group in groups for part in group if part.strip()]
    return parts if len(parts) == blank_count else []


def strip_answer_wrapper(value: str) -> str:
    """移除单个答案外层的中英文括号。"""

    text = value.strip()
    matched = re.fullmatch(r"\(([^()]*)\)|（([^（）]*)）", text)
    if not matched:
        return text
    return next(part.strip() for part in matched.groups() if part is not None)

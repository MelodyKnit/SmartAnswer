"""OCS 未支持题型处理策略。"""

from __future__ import annotations

from study_qb_assistant.questions.models import QueryResult
from .base import BaseOcsQuestionTypeHandler, OcsFormattedAnswer


class UnsupportedOcsQuestionTypeHandler(BaseOcsQuestionTypeHandler):
    """保留未知题型原始答案，并明确标记当前未提供专用适配。"""

    canonical_type = "unsupported"
    aliases = frozenset()

    def matches(self, raw_type: str, result: QueryResult) -> bool:
        return True

    def format_answer(self, result: QueryResult) -> OcsFormattedAnswer:
        raw_type = result.query.question_type.strip() or "unknown"
        return OcsFormattedAnswer(
            result.candidate_answer or result.answer_text,
            "unsupported",
            {
                "ocs_type_supported": False,
                "ocs_raw_question_type": raw_type,
            },
        )

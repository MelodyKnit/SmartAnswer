"""OCS 单选题处理策略。"""

from __future__ import annotations

from study_qb_assistant.questions.models import QueryResult
from study_qb_assistant.questions.labels import canonicalize_label_answer
from .base import BaseOcsQuestionTypeHandler, OcsFormattedAnswer


class SingleChoiceOcsHandler(BaseOcsQuestionTypeHandler):
    """将单选答案格式化为标准选项标签。"""

    canonical_type = "single"
    aliases = frozenset({"single", "singlechoice", "single-choice", "单选", "单选题"})

    def matches(self, raw_type: str, result: QueryResult) -> bool:
        normalized = raw_type.strip().casefold()
        if normalized in self.aliases:
            return True
        if normalized not in {"", "unknown", "undefined"}:
            return False
        if result.query.title.strip().startswith("单选题"):
            return True
        labels = canonicalize_label_answer(result.query, result.candidate_answer)
        return bool(result.query.options and labels and "#" not in labels)

    def format_answer(self, result: QueryResult) -> OcsFormattedAnswer:
        labels = canonicalize_label_answer(result.query, result.candidate_answer)
        if labels:
            return OcsFormattedAnswer(labels, "option_labels")
        return OcsFormattedAnswer(result.candidate_answer or result.answer_text, "text")

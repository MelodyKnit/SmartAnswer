"""OCS 多选题处理策略。"""

from __future__ import annotations

from study_qb_assistant.questions.models import QueryResult
from study_qb_assistant.questions.labels import canonicalize_label_answer
from .base import BaseOcsQuestionTypeHandler, OcsFormattedAnswer


class MultipleChoiceOcsHandler(BaseOcsQuestionTypeHandler):
    """将多选答案规范为 OCS 可识别的升序标签串。"""

    canonical_type = "multiple"
    aliases = frozenset({"multiple", "multiplechoice", "multiple-choice", "多选", "多选题"})

    def matches(self, raw_type: str, result: QueryResult) -> bool:
        normalized = raw_type.strip().casefold()
        if normalized in self.aliases:
            return True
        if normalized not in {"", "unknown", "undefined"}:
            return False
        if result.query.title.strip().startswith("多选题"):
            return True
        labels = canonicalize_label_answer(result.query, result.candidate_answer)
        return bool(result.query.options and labels and "#" in labels)

    def format_answer(self, result: QueryResult) -> OcsFormattedAnswer:
        labels = canonicalize_label_answer(result.query, result.candidate_answer)
        if labels:
            return OcsFormattedAnswer(labels, "option_labels")
        return OcsFormattedAnswer(result.candidate_answer or result.answer_text, "text")

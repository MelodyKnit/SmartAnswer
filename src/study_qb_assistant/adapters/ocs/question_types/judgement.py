"""OCS 判断题处理策略。"""

from __future__ import annotations

from study_qb_assistant.questions.models import QueryResult
from .base import BaseOcsQuestionTypeHandler, OcsFormattedAnswer

TRUE_TEXTS = {"对", "正确", "true", "yes"}
FALSE_TEXTS = {"错", "错误", "false", "no"}


class JudgementOcsHandler(BaseOcsQuestionTypeHandler):
    """将判断题内部标签转换为页面可匹配的对错文本。"""

    canonical_type = "judgement"
    aliases = frozenset({"judgement", "judge", "truefalse", "true-false", "判断", "判断题"})

    def matches(self, raw_type: str, result: QueryResult) -> bool:
        normalized = raw_type.strip().casefold()
        if normalized in self.aliases:
            return True
        if normalized not in {"", "unknown", "undefined"}:
            return False
        answer_text = (result.answer_text or "").strip().casefold()
        return result.query.title.strip().startswith("判断题") or answer_text in (
            TRUE_TEXTS | FALSE_TEXTS
        )

    def format_answer(self, result: QueryResult) -> OcsFormattedAnswer:
        answer_text = (result.answer_text or "").strip().casefold()
        if answer_text in TRUE_TEXTS:
            return OcsFormattedAnswer("对", "judgement_text")
        if answer_text in FALSE_TEXTS:
            return OcsFormattedAnswer("错", "judgement_text")
        candidate = (result.candidate_answer or "").strip().upper()
        if candidate == "A":
            return OcsFormattedAnswer("对", "judgement_text")
        if candidate == "B":
            return OcsFormattedAnswer("错", "judgement_text")
        return OcsFormattedAnswer(result.candidate_answer or result.answer_text, "text")

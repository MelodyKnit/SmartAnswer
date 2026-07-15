"""AI 答案复用策略。

该模块只判断“AI 生成答案是否允许被后续自动复用”，不改变题目是否可以正常作答、
正常记录使用日志或正常写入题库管理。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from study_qb_assistant.questions.models import CanonicalQuestionRecord, QuestionQuery
from study_qb_assistant.questions.types import (
    has_blank_marker,
    is_completion_query,
    is_open_text_completion,
)

REUSE_POLICY_REUSABLE = "reusable"
REUSE_POLICY_NON_REUSABLE_OPEN_TEXT = "non_reusable_open_text"
NON_REUSABLE_STATUS = "non_reusable"

OPEN_TEXT_TAGS = ("open_text", "non_reusable")
OPEN_TEXT_LONG_ANSWER_MIN_LENGTH = 180
OPEN_TEXT_QUESTION_FORMS = {
    "open_text",
    "open_text_generation",
    "long_form_writing",
    "essay",
    "reflection",
    "report",
}

OPEN_TEXT_TITLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(心得|体会|感想|观后感|读后感)"),
    re.compile(r"(学习|实验|课程|培训|操作系统|Linux).{0,12}(总结|小结|报告)"),
    re.compile(r"(写一篇|撰写|完成|提交).{0,12}(作文|论文|报告|征文|演讲稿|发言稿|申请书|说明书)"),
    re.compile(r"(以.+为题|围绕.+写).{0,12}(作文|论文|报告|征文|演讲稿|发言稿)"),
    re.compile(r"(不少于|不低于|至少|大于|超过)\s*\d+\s*(字|词|字符)"),
    re.compile(r"\d+\s*(字|词|字符)\s*(以上|左右|以内)?"),
)


@dataclass(frozen=True, slots=True)
class AnswerReuseDecision:
    """一次题目答案复用判定的结果。"""

    policy: str
    reusable: bool
    reason: str
    status: str
    tags: tuple[str, ...] = ()


def decide_answer_reuse(
    query: QuestionQuery,
    *,
    answer_text: str | None = None,
    candidate_answer: str | None = None,
    reuse_policy: str | None = None,
    question_form: str | None = None,
    reuse_reason: str | None = None,
    reuse_confidence: float | None = None,
) -> AnswerReuseDecision:
    """判断某次 AI 答案是否允许进入自动复用链路。"""

    if query.options:
        return reusable_decision("objective_options_guard")
    if has_blank_marker(query.title or ""):
        return reusable_decision("explicit_blank_guard")
    model_decision = decision_from_model_policy(
        query,
        reuse_policy=reuse_policy,
        question_form=question_form,
        reuse_reason=reuse_reason,
        reuse_confidence=reuse_confidence,
    )
    if model_decision is not None:
        return model_decision
    if is_non_reusable_open_text_query(
        query, answer_text=answer_text, candidate_answer=candidate_answer
    ):
        return non_reusable_open_text_decision("fallback_open_text_signal")
    return reusable_decision("normal_question")


def is_non_reusable_open_text_query(
    query: QuestionQuery | None,
    *,
    answer_text: str | None = None,
    candidate_answer: str | None = None,
) -> bool:
    """识别心得、作文、总结等不适合复用的开放性生成题。"""

    if query is None or query.options:
        return False
    title = (query.title or "").strip()
    if not title:
        return False
    if has_blank_marker(title):
        return False
    if not is_completion_query(query):
        return False
    if title_has_open_text_signal(title):
        return True
    answer_body = answer_body_text(answer_text=answer_text, candidate_answer=candidate_answer)
    return is_open_text_completion(query) and len(answer_body) >= OPEN_TEXT_LONG_ANSWER_MIN_LENGTH


def title_has_open_text_signal(title: str) -> bool:
    """判断题干是否含有开放写作或长文本约束信号。"""

    compact = re.sub(r"\s+", "", title or "")
    return any(pattern.search(compact) for pattern in OPEN_TEXT_TITLE_PATTERNS)


def decision_from_model_policy(
    query: QuestionQuery,
    *,
    reuse_policy: str | None,
    question_form: str | None,
    reuse_reason: str | None,
    reuse_confidence: float | None,
) -> AnswerReuseDecision | None:
    """把模型返回的复用建议转成服务端决策，低可信建议交给兜底规则。"""

    if reuse_confidence is not None and reuse_confidence < 0.5:
        return None
    policy = compact_policy(reuse_policy)
    form = compact_policy(question_form)
    if policy == REUSE_POLICY_REUSABLE:
        return reusable_decision(reuse_reason or "model_reuse_policy")
    if (
        policy == REUSE_POLICY_NON_REUSABLE_OPEN_TEXT
        or form in OPEN_TEXT_QUESTION_FORMS
    ) and is_open_text_completion(query):
        return non_reusable_open_text_decision(reuse_reason or "model_reuse_policy")
    return None


def reusable_decision(reason: str) -> AnswerReuseDecision:
    """构造允许复用的策略结果。"""

    return AnswerReuseDecision(
        policy=REUSE_POLICY_REUSABLE,
        reusable=True,
        reason=reason,
        status="active",
    )


def non_reusable_open_text_decision(reason: str) -> AnswerReuseDecision:
    """构造开放性长文本不可复用的策略结果。"""

    return AnswerReuseDecision(
        policy=REUSE_POLICY_NON_REUSABLE_OPEN_TEXT,
        reusable=False,
        reason=reason,
        status=NON_REUSABLE_STATUS,
        tags=OPEN_TEXT_TAGS,
    )


def compact_policy(value: str | None) -> str:
    """标准化模型返回的策略或题目形态标识。"""

    return re.sub(r"\s+", "_", str(value or "").strip().casefold())


def record_should_be_indexable_by_reuse_policy(record: CanonicalQuestionRecord) -> bool:
    """判断题库记录是否允许进入本地/RAG 可复用召回集合。"""

    status = (
        record.metadata.get("status")
        or record.metadata.get("ai_status")
        or record.source_split
        or ""
    )
    if str(status).strip().casefold() == NON_REUSABLE_STATUS:
        return False
    if record.metadata.get("reuse_policy") == REUSE_POLICY_NON_REUSABLE_OPEN_TEXT:
        return False
    tags = {tag.casefold() for tag in record.tags}
    if "non_reusable" in tags or "open_text" in tags:
        return False
    query = QuestionQuery(
        title=record.title_raw,
        question_type=record.question_type,
        options=record.options_raw,
    )
    return not is_non_reusable_open_text_query(
        query,
        answer_text=record.metadata.get("ai_answer_text") or record.answer_raw,
        candidate_answer=record.answer_raw,
    )


def answer_body_text(*, answer_text: str | None, candidate_answer: str | None) -> str:
    """提取用于判断开放题长度的答案正文。"""

    return str(answer_text or candidate_answer or "").strip()

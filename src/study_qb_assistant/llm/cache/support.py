"""LLM 自动沉淀题库的辅助工具。"""

from __future__ import annotations

from ...models import CanonicalQuestionRecord, ModelAnswer, QuestionQuery
from ...option_labels import canonicalize_label_answer


def cache_record_key(record: CanonicalQuestionRecord, cache_key_builder) -> str:
    """根据题库记录构建缓存键。"""
    query = QuestionQuery(
        title=record.title_raw,
        options=record.options_raw,
        question_type=record.question_type,
    )
    return cache_key_builder(query)


def is_cacheable_model_answer(
    query: QuestionQuery,
    answer: ModelAnswer,
    min_confidence: float,
    answer_shape_is_valid,
) -> bool:
    """判断模型答案是否满足进入 LLM 自动沉淀题库的最低条件。"""
    if answer.confidence < min_confidence:
        return False
    if not answer.candidate_answer:
        return False
    return answer_shape_is_valid(query, answer.candidate_answer)


def answer_shape_is_valid(query: QuestionQuery, candidate_answer: str) -> bool:
    """检查候选答案的格式是否与题型和选项结构相符。"""
    candidate = candidate_answer.strip()
    if not candidate:
        return False
    if not query.options:
        return True
    return canonicalize_label_answer(query, candidate) is not None


def optional_string(value: object) -> str | None:
    """把对象安全转换为非空字符串。"""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def canonical_candidate_from_payload(payload: dict) -> str:
    """从原始载荷中恢复标准化后的候选答案。"""
    query = QuestionQuery(
        title=str(payload.get("title") or ""),
        question_type=str(payload.get("question_type") or "unknown"),
        options=tuple(str(option) for option in payload.get("options") or ()),
    )
    candidate = str(payload.get("candidate_answer") or "")
    return canonicalize_label_answer(query, candidate) or candidate


def float_value(value: object, *, default: float) -> float:
    """安全解析浮点数。"""
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def int_value(value: object, *, default: int) -> int:
    """安全解析整数。"""
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default

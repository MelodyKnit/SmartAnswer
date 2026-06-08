"""基于模型的课程题目答案后处理与修复规则。

此模块包含针对不同题型（单选、多选、填空、判断）进行模型答案修复、一致性验证
以及基于预设/配置规则匹配已知答案的函数和辅助工具。
"""

from __future__ import annotations

from ..models import ModelAnswer, QuestionQuery
from .rules import (
    compact_text,
    configured_completion_rules,
    configured_option_rules,
    is_completion_query,
    known_completion_answer,
    known_option_answer,
    load_rules_payload,
)
from .support import (
    answer_text_from_labels,
    answer_with_labels,
    extract_explicit_labels,
    is_judgement_query,
    judgement_answer,
    judgement_signal,
    known_explanation,
    label_for_answer_text,
    labels_for_answer_texts,
    labels_from_answer_text,
    normalize_label_group,
    repair_judgement_answer,
)


def direct_known_answer(query: QuestionQuery) -> ModelAnswer | None:
    """对于符合高信号、固定表述模式的课程问题，直接返回已知答案。

    Args:
        query: 问题查询对象。

    Returns:
        ModelAnswer | None: 命中的已知答案，若未命中则返回 None。
    """
    # 优先匹配填空题已知规则
    completion_answer = known_completion_answer(query)
    if completion_answer is not None:
        return ModelAnswer(
            completion_answer,
            completion_answer,
            known_explanation(completion_answer),
            0.99,
        )

    # 其次匹配选择题已知规则
    known_labels = known_option_answer(query, labels_for_answer_texts)
    if known_labels is not None:
        return answer_with_labels(
            query,
            ModelAnswer(None, None, None, 0.0),
            known_labels,
            confidence=0.99,
            explanation=known_explanation(answer_text_from_labels(query, known_labels) or known_labels),
        )

    return None


def repair_model_answer(query: QuestionQuery, answer: ModelAnswer) -> ModelAnswer:
    """修复置信度低或内部不一致的模型生成答案。

    Args:
        query: 问题查询对象。
        answer: 模型生成的答案对象。

    Returns:
        ModelAnswer: 修复或校正后的答案对象。
    """
    # 如果该问题能直接命中已知的高信号匹配规则，则直接采用
    direct_answer = direct_known_answer(query)
    if direct_answer is not None:
        return direct_answer

    # 对于选择题，如果解析（explanation）中显式写出了答案，但与 candidate_answer 不一致，进行校正
    if query.options:
        explicit_labels = extract_explicit_labels(answer.explanation or "", query)
        if explicit_labels and explicit_labels != answer.candidate_answer:
            return answer_with_labels(
                query,
                answer,
                explicit_labels,
                confidence=max(answer.confidence, 0.9),
                explanation=known_explanation(answer_text_from_labels(query, explicit_labels) or explicit_labels),
            )

    # 如果是判断题，进行特定规则的修复
    if is_judgement_query(query):
        return repair_judgement_answer(query, answer)

    if not query.options:
        return answer

    return answer


def is_cache_safe_answer(query: QuestionQuery, answer: ModelAnswer) -> bool:
    """检查模型答案的内部一致性，判断其是否安全且适合缓存。

    Args:
        query: 问题查询对象。
        answer: 模型生成的答案对象。

    Returns:
        bool: 若安全可缓存则返回 True，否则返回 False。
    """
    # 无候选答案时不可缓存
    if not answer.candidate_answer:
        return False
    # 非选择题，认为安全（没有选项映射关系）
    if not query.options:
        return True

    # 验证候选答案中的标签是否全都在合法的选项范围内
    labels = normalize_label_group(answer.candidate_answer, query)
    if not labels:
        return False

    # 若解析中显式提取的标签存在且与候选答案不一致，则不安全
    explicit_labels = extract_explicit_labels(answer.explanation or "", query)
    if explicit_labels and explicit_labels != labels:
        return False

    # 若通过答案文本提取的标签存在且与候选答案不一致，则不安全
    text_labels = labels_from_answer_text(query, answer.answer_text)
    if text_labels and text_labels != labels:
        return False

    return True


# 为兼容现有测试与局部旧调用，保留最薄私有别名层。
_configured_option_rules = configured_option_rules
_configured_completion_rules = configured_completion_rules
_load_rules_payload = load_rules_payload

"""答案质量模块的标签映射、判断题修复与解释辅助。"""

from __future__ import annotations

import re

from ..models import ModelAnswer, QuestionQuery
from ..option_labels import canonicalize_label_answer

LABELS = ("A", "B", "C", "D", "E", "F")


def is_judgement_query(query: QuestionQuery) -> bool:
    """判断当前查询是否为判断题。"""
    normalized_type = query.question_type.strip().lower()
    title = query.title.strip()
    return normalized_type in {
        "judgement",
        "judge",
        "truefalse",
        "判断",
        "判断题",
    } or title.startswith("判断题")


def repair_judgement_answer(query: QuestionQuery, answer: ModelAnswer) -> ModelAnswer:
    """对判断题答案做标准化修复。"""
    if query.options and answer.candidate_answer:
        labels = normalize_label_group(answer.candidate_answer, query)
        if labels:
            return answer_with_labels(query, answer, labels, confidence=answer.confidence)

    text_labels = labels_from_answer_text(query, answer.answer_text)
    if text_labels:
        return answer_with_labels(query, answer, text_labels, confidence=answer.confidence)

    explanation_signal = judgement_signal(answer.explanation)
    if explanation_signal:
        return judgement_answer(query, answer, explanation_signal)
    return answer


def judgement_answer(query: QuestionQuery, answer: ModelAnswer, text: str) -> ModelAnswer:
    """为判断题构造标准答案对象。"""
    label = label_for_answer_text(query, text) if query.options else None
    if label:
        return answer_with_labels(query, answer, label, confidence=answer.confidence)
    return ModelAnswer(text, text, answer.explanation, answer.confidence)


def answer_with_labels(
    query: QuestionQuery,
    answer: ModelAnswer,
    labels: str,
    *,
    confidence: float,
    explanation: str | None = None,
) -> ModelAnswer:
    """使用标签字符串重建标准答案对象。"""
    normalized_labels = canonicalize_label_answer(query, labels) or labels
    return ModelAnswer(
        candidate_answer=normalized_labels,
        answer_text=answer_text_from_labels(query, normalized_labels) or answer.answer_text,
        explanation=explanation or answer.explanation,
        confidence=min(max(confidence, 0.0), 1.0),
    )


def extract_explicit_labels(text: str, query: QuestionQuery) -> str | None:
    """从说明文本中提取显式声明的选项标签。"""
    if not text:
        return None
    patterns = (
        r"(?:标准答案|正确答案|答案|应选|故选|因此选|所以选|选择)[为是：:\s]*([A-F](?:[#、,，和及与\s]*[A-F])*)",
    )
    for pattern in patterns:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        if not matches:
            continue
        labels = normalize_label_group(matches[-1], query)
        if labels:
            return labels
    return None


def normalize_label_group(value: str, query: QuestionQuery) -> str | None:
    """标准化选项标签组。"""
    return canonicalize_label_answer(query, value)


def labels_from_answer_text(query: QuestionQuery, answer_text: str | None) -> str | None:
    """根据答案文本反向推导标签组。"""
    if not query.options or not answer_text:
        return None
    labels = normalize_label_group(answer_text, query)
    if labels:
        return labels
    parts = [part.strip() for part in re.split(r"[#;,，、；\n]+", answer_text) if part.strip()]
    if not parts:
        return None
    mapped: list[str] = []
    for part in parts:
        label = label_for_answer_text(query, part)
        if not label:
            return None
        mapped.append(label)
    return canonicalize_label_answer(query, "#".join(mapped))


def judgement_signal(text: str | None) -> str | None:
    """从解释文本中识别判断题的对错倾向。"""
    normalized = compact_text(text)
    if not normalized:
        return None
    true_patterns = ("表述正确", "说法正确", "题干正确", "判断为正确", "判断正确")
    false_patterns = ("表述错误", "说法错误", "题干错误", "判断为错误", "判断错误", "不正确")
    if any(pattern in normalized for pattern in false_patterns):
        return "错"
    if any(pattern in normalized for pattern in true_patterns):
        return "对"
    return None


def labels_for_answer_texts(query: QuestionQuery, answer_texts: tuple[str, ...]) -> str | None:
    """把多个答案文本映射为标签组。"""
    labels: list[str] = []
    for answer_text in answer_texts:
        label = label_for_answer_text(query, answer_text)
        if label is None:
            return None
        labels.append(label)
    return canonicalize_label_answer(query, "#".join(labels))


def label_for_answer_text(query: QuestionQuery, answer_text: str) -> str | None:
    """根据选项内容查找对应标签。"""
    answer_key = compact_text(answer_text)
    for label, option in zip(LABELS, query.options, strict=False):
        option_key = compact_text(strip_option_label(option))
        if option_key == answer_key or answer_key in option_key or option_key in answer_key:
            return label
    return None


def answer_text_from_labels(query: QuestionQuery, labels: str) -> str | None:
    """根据标签组反向拼接答案文本。"""
    option_map = {
        label: strip_option_label(option)
        for label, option in zip(LABELS, query.options, strict=False)
    }
    parts = [option_map.get(label) for label in labels.split("#")]
    texts = [part for part in parts if part]
    return "；".join(texts) if texts else None


def strip_option_label(option: str) -> str:
    """移除选项文本前缀，例如 `A.`。"""
    return re.sub(r"^\s*[A-Fa-f][\.、．:：]\s*", "", option).strip()


def compact_text(value: str | None) -> str:
    """清除空白并统一大小写，便于模糊匹配。"""
    return re.sub(r"\s+", "", value or "").casefold()


def known_explanation(answer_text: str) -> str:
    """生成已知规则命中的标准解释文本。"""
    return f"本地固定表述规则命中，答案为：{answer_text}。"

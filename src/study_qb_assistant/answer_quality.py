"""基于模型的课程题目答案后处理与修复规则。

此模块包含针对不同题型（单选、多选、填空、判断）进行模型答案修复、一致性验证
以及基于预设/配置规则匹配已知答案的函数和辅助工具。
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

from .models import ModelAnswer, QuestionQuery
from .option_labels import canonicalize_label_answer

# 选项的字母标签定义（支持最多6个选项）
_LABELS = ("A", "B", "C", "D", "E", "F")

# 内置的选项和填空题答案规则（静态空元组，由配置文件动态扩展）
_BUILTIN_OPTION_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = ()
_BUILTIN_COMPLETION_RULES: tuple[tuple[tuple[str, ...], str], ...] = ()


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
            _known_explanation(completion_answer),
            0.99,
        )

    # 其次匹配选择题已知规则
    known_labels = known_option_answer(query)
    if known_labels is not None:
        return _answer_with_labels(
            query,
            ModelAnswer(None, None, None, 0.0),
            known_labels,
            confidence=0.99,
            explanation=_known_explanation(_answer_text_from_labels(query, known_labels) or known_labels),
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
        explicit_labels = _extract_explicit_labels(answer.explanation or "", query)
        if explicit_labels and explicit_labels != answer.candidate_answer:
            return _answer_with_labels(
                query,
                answer,
                explicit_labels,
                confidence=max(answer.confidence, 0.9),
                explanation=_known_explanation(_answer_text_from_labels(query, explicit_labels) or explicit_labels),
            )

    # 如果是判断题，进行特定规则的修复
    if is_judgement_query(query):
        return _repair_judgement_answer(query, answer)

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
    labels = _normalize_label_group(answer.candidate_answer, query)
    if not labels:
        return False

    # 若解析中显式提取的标签存在且与候选答案不一致，则不安全
    explicit_labels = _extract_explicit_labels(answer.explanation or "", query)
    if explicit_labels and explicit_labels != labels:
        return False

    # 若通过答案文本提取的标签存在且与候选答案不一致，则不安全
    text_labels = _labels_from_answer_text(query, answer.answer_text)
    if text_labels and text_labels != labels:
        return False

    return True


def known_option_answer(query: QuestionQuery) -> str | None:
    """根据预设规则，为固定、高信号的选择题匹配选项标签答案。

    Args:
        query: 问题查询对象。

    Returns:
        str | None: 匹配到的选项标签组合（如 "A" 或 "A#B"），未匹配则返回 None。
    """
    if not query.options:
        return None
    # 将题干压缩用于匹配
    title_key = _compact(query.title)
    for title_needles, answer_texts in _iter_option_rules():
        # 如果预设规则中的所有关键词都出现在题干中，则尝试解析对应的选项标签
        if all(_compact(needle) in title_key for needle in title_needles):
            labels = _labels_for_answer_texts(query, answer_texts)
            if labels:
                return labels
    return None


def known_completion_answer(query: QuestionQuery) -> str | None:
    """根据预设规则，为固定的填空式问题返回确切的答案文本。

    Args:
        query: 问题查询对象。

    Returns:
        str | None: 匹配到的填空题答案文本，未匹配则返回 None。
    """
    if not is_completion_query(query):
        return None
    title_key = _compact(query.title)
    for title_needles, answer_text in _iter_completion_rules():
        # 如果预设规则中的所有关键词都出现在题干中，则返回规则定义的答案
        if all(_compact(needle) in title_key for needle in title_needles):
            return answer_text
    return None


def _iter_option_rules() -> tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]:
    """迭代合并内置选项规则与配置文件中的自定义选项规则。"""
    return _BUILTIN_OPTION_RULES + _configured_option_rules()


def _iter_completion_rules() -> tuple[tuple[tuple[str, ...], str], ...]:
    """迭代合并内置填空规则与配置文件中的自定义填空规则。"""
    return _BUILTIN_COMPLETION_RULES + _configured_completion_rules()


@lru_cache(maxsize=1)
def _configured_option_rules() -> tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]:
    """从配置文件中解析并获取选项类型的匹配规则（缓存结果）。"""
    payload = _load_rules_payload()
    rules: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    for item in payload.get("option_rules") or ():
        if not isinstance(item, dict):
            continue
        needles = _string_tuple(item.get("needles"))
        answers = _string_tuple(item.get("answers"))
        if needles and answers:
            rules.append((needles, answers))
    return tuple(rules)


@lru_cache(maxsize=1)
def _configured_completion_rules() -> tuple[tuple[tuple[str, ...], str], ...]:
    """从配置文件中解析并获取填空类型的匹配规则（缓存结果）。"""
    payload = _load_rules_payload()
    rules: list[tuple[tuple[str, ...], str]] = []
    for item in payload.get("completion_rules") or ():
        if not isinstance(item, dict):
            continue
        needles = _string_tuple(item.get("needles"))
        answer = str(item.get("answer") or "").strip()
        if needles and answer:
            rules.append((needles, answer))
    return tuple(rules)


@lru_cache(maxsize=1)
def _load_rules_payload() -> dict:
    """加载配置好的自定义规则 JSON 文件。"""
    raw_path = os.getenv("STQB_ANSWER_RULES_PATH", "").strip()
    if not raw_path:
        return {}
    path = Path(raw_path)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _string_tuple(value: object) -> tuple[str, ...]:
    """辅助方法：将输入对象转换为清理后的字符串元组。"""
    if not isinstance(value, list):
        return ()
    return tuple(text for text in (str(item).strip() for item in value) if text)


def is_completion_query(query: QuestionQuery) -> bool:
    """判断当前查询是否为填空题（即使输入中带有干扰性选项描述）。

    Args:
        query: 问题查询对象。

    Returns:
        bool: 是否为填空题。
    """
    normalized_type = query.question_type.strip().lower()
    return (
        normalized_type in {"completion", "blank", "fill", "填空", "填空题"}
        or query.title.strip().startswith("填空题")
        or "____" in query.title
    )


def is_judgement_query(query: QuestionQuery) -> bool:
    """判断当前查询是否为判断题。

    Args:
        query: 问题查询对象。

    Returns:
        bool: 是否为判断题。
    """
    normalized_type = query.question_type.strip().lower()
    title = query.title.strip()
    return normalized_type in {"judgement", "judge", "truefalse", "判断", "判断题"} or title.startswith("判断题")


def _repair_judgement_answer(query: QuestionQuery, answer: ModelAnswer) -> ModelAnswer:
    """对判断题的答案和置信度进行校验与修复。"""
    # 1. 尝试从已有的 candidate_answer 中提取并校验选项
    if query.options and answer.candidate_answer:
        labels = _normalize_label_group(answer.candidate_answer, query)
        if labels:
            return _answer_with_labels(query, answer, labels, confidence=answer.confidence)

    # 2. 尝试从已有的 answer_text 中提取并校验选项
    text_labels = _labels_from_answer_text(query, answer.answer_text)
    if text_labels:
        return _answer_with_labels(query, answer, text_labels, confidence=answer.confidence)

    # 3. 尝试从解析文本中识别出 "对" / "错" 等信号来确认答案
    explanation_signal = _judgement_signal(answer.explanation)
    if explanation_signal:
        return _judgement_answer(query, answer, explanation_signal)
    return answer


def _judgement_answer(query: QuestionQuery, answer: ModelAnswer, text: str) -> ModelAnswer:
    """为判断题组装标准的 ModelAnswer 响应。"""
    label = _label_for_answer_text(query, text) if query.options else None
    if label:
        return _answer_with_labels(query, answer, label, confidence=answer.confidence)
    return ModelAnswer(text, text, answer.explanation, answer.confidence)


def _answer_with_labels(
    query: QuestionQuery,
    answer: ModelAnswer,
    labels: str,
    *,
    confidence: float,
    explanation: str | None = None,
) -> ModelAnswer:
    """根据给定的选项标签，为选择题或判断题构造标准 ModelAnswer 对象。"""
    normalized_labels = canonicalize_label_answer(query, labels) or labels
    return ModelAnswer(
        candidate_answer=normalized_labels,
        answer_text=_answer_text_from_labels(query, normalized_labels) or answer.answer_text,
        explanation=explanation or answer.explanation,
        confidence=min(max(confidence, 0.0), 1.0),
    )


def _extract_explicit_labels(text: str, query: QuestionQuery) -> str | None:
    """从给定的说明或解析文本中，提取明确声明的选项字母（例如“答案是A”）。"""
    if not text:
        return None
    # 匹配文本中诸如“正确答案为A”、“应选A、B”、“答案是A”等典型表述
    # 组 1 将提取如 A、B 或 A#B 等格式
    patterns = (
        r"(?:标准答案|正确答案|答案|应选|故选|因此选|所以选|选择)[为是：:\s]*([A-F](?:[#、,，和及与\s]*[A-F])*)",
    )
    for pattern in patterns:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        if not matches:
            continue
        # 取最后一个匹配到的选项声明，进行标准化
        labels = _normalize_label_group(matches[-1], query)
        if labels:
            return labels
    return None


def _normalize_label_group(value: str, query: QuestionQuery) -> str | None:
    """标准化选项标签字符串，将提取到的选项字母去重并使用 '#' 连接。"""
    return canonicalize_label_answer(query, value)


def _labels_from_answer_text(query: QuestionQuery, answer_text: str | None) -> str | None:
    """根据选项内容，从文本答案中反向映射出其对应的字母标签组合（如“北京”映射为“A”）。"""
    if not query.options or not answer_text:
        return None
    # 如果它本身就已经是合法的标签组合（例如 "A" 或 "A#B"），则直接返回
    labels = _normalize_label_group(answer_text, query)
    if labels:
        return labels
    # 按常见的分隔符对文本答案进行切分，以便对应多选题的多个文本选项
    parts = [
        part.strip()
        for part in re.split(r"[#;,，、；\n]+", answer_text)
        if part.strip()
    ]
    if not parts:
        return None
    mapped: list[str] = []
    for part in parts:
        label = _label_for_answer_text(query, part)
        if not label:
            return None
        mapped.append(label)
    return canonicalize_label_answer(query, "#".join(mapped))


def _judgement_signal(text: str | None) -> str | None:
    """从解析文本中检索判断题的对错表意倾向。"""
    normalized = _compact(text)
    if not normalized:
        return None
    true_patterns = ("表述正确", "说法正确", "题干正确", "判断为正确", "判断正确")
    false_patterns = ("表述错误", "说法错误", "题干错误", "判断为错误", "判断错误", "不正确")
    if any(pattern in normalized for pattern in false_patterns):
        return "错"
    if any(pattern in normalized for pattern in true_patterns):
        return "对"
    return None


def _labels_for_answer_texts(query: QuestionQuery, answer_texts: tuple[str, ...]) -> str | None:
    """将包含多个具体选项文本的元组映射为用 '#' 连接的字母标签组。"""
    labels: list[str] = []
    for answer_text in answer_texts:
        label = _label_for_answer_text(query, answer_text)
        if label is None:
            return None
        labels.append(label)
    return canonicalize_label_answer(query, "#".join(labels))


def _label_for_answer_text(query: QuestionQuery, answer_text: str) -> str | None:
    """查找与给定选项文本内容完全相符或最相似 of 选项，并返回其字母标签。"""
    answer_key = _compact(answer_text)
    for label, option in zip(_LABELS, query.options, strict=False):
        # 去掉选项本身可能包含的前缀（如 "A."）后再压缩字符进行比对
        option_key = _compact(_strip_option_label(option))
        if option_key == answer_key or answer_key in option_key or option_key in answer_key:
            return label
    return None


def _answer_text_from_labels(query: QuestionQuery, labels: str) -> str | None:
    """根据 '#' 连接的字母标签字符串，拼装出对应的选项中文文本。"""
    option_map = {
        label: _strip_option_label(option)
        for label, option in zip(_LABELS, query.options, strict=False)
    }
    parts = [option_map.get(label) for label in labels.split("#")]
    texts = [part for part in parts if part]
    return "；".join(texts) if texts else None


def _strip_option_label(option: str) -> str:
    """移除选项文本的字母前缀，例如 "A. 北京" -> "北京"。"""
    return re.sub(r"^\s*[A-Fa-f][\.、．:：]\s*", "", option).strip()


def _compact(value: str | None) -> str:
    """清除字符串中所有的空白字符并转换为小写，以便做更鲁棒的非精确匹配。"""
    return re.sub(r"\s+", "", value or "").casefold()


def _known_explanation(answer_text: str) -> str:
    """生成应用已知预设规则时的标准答案解析文本。"""
    return f"本地固定表述规则命中，答案为：{answer_text}。"

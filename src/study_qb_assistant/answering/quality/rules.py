"""答案质量模块的规则加载与已知答案匹配。"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from study_qb_assistant.questions.models import QuestionQuery

BUILTIN_OPTION_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = ()
BUILTIN_COMPLETION_RULES: tuple[tuple[tuple[str, ...], str], ...] = ()


def compact_text(value: str | None) -> str:
    """清除空白并统一大小写，便于模糊包含匹配。"""
    import re

    return re.sub(r"\s+", "", value or "").casefold()


def is_completion_query(query: QuestionQuery) -> bool:
    """判断当前查询是否属于填空题。"""
    normalized_type = query.question_type.strip().lower()
    return (
        normalized_type in {"completion", "blank", "fill", "填空", "填空题"}
        or query.title.strip().startswith("填空题")
        or "____" in query.title
    )


def known_option_answer(
    query: QuestionQuery,
    labels_for_answer_texts,
) -> str | None:
    """根据高信号规则匹配选择题标准标签答案。"""
    if not query.options:
        return None
    title_key = compact_text(query.title)
    for title_needles, answer_texts in iter_option_rules():
        if all(compact_text(needle) in title_key for needle in title_needles):
            labels = labels_for_answer_texts(query, answer_texts)
            if labels:
                return labels
    return None


def known_completion_answer(query: QuestionQuery) -> str | None:
    """根据高信号规则匹配填空题标准答案文本。"""
    if not is_completion_query(query):
        return None
    title_key = compact_text(query.title)
    for title_needles, answer_text in iter_completion_rules():
        if all(compact_text(needle) in title_key for needle in title_needles):
            return answer_text
    return None


def iter_option_rules() -> tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]:
    """迭代内置与外部配置合并后的选择题规则。"""
    return BUILTIN_OPTION_RULES + configured_option_rules()


def iter_completion_rules() -> tuple[tuple[tuple[str, ...], str], ...]:
    """迭代内置与外部配置合并后的填空题规则。"""
    return BUILTIN_COMPLETION_RULES + configured_completion_rules()


@lru_cache(maxsize=1)
def configured_option_rules() -> tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]:
    """从外部 JSON 规则文件中读取选择题规则。"""
    payload = load_rules_payload()
    rules: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    for item in payload.get("option_rules") or ():
        if not isinstance(item, dict):
            continue
        needles = string_tuple(item.get("needles"))
        answers = string_tuple(item.get("answers"))
        if needles and answers:
            rules.append((needles, answers))
    return tuple(rules)


@lru_cache(maxsize=1)
def configured_completion_rules() -> tuple[tuple[tuple[str, ...], str], ...]:
    """从外部 JSON 规则文件中读取填空题规则。"""
    payload = load_rules_payload()
    rules: list[tuple[tuple[str, ...], str]] = []
    for item in payload.get("completion_rules") or ():
        if not isinstance(item, dict):
            continue
        needles = string_tuple(item.get("needles"))
        answer = str(item.get("answer") or "").strip()
        if needles and answer:
            rules.append((needles, answer))
    return tuple(rules)


@lru_cache(maxsize=1)
def load_rules_payload() -> dict:
    """加载外部答案规则配置文件。"""
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


def string_tuple(value: object) -> tuple[str, ...]:
    """把 JSON 数组值规整为非空字符串元组。"""
    if not isinstance(value, list):
        return ()
    return tuple(text for text in (str(item).strip() for item in value) if text)

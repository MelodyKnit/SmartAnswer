"""面向本地学习服务的 OCS 风格响应适配器。

该模块负责将内部的 QueryResult 对象格式化为符合 OCS 规范的 JSON 响应。
"""

from __future__ import annotations

import json
import re

from ...logger import log_event
from ...models import QueryResult
from ...option_labels import canonicalize_label_answer
from ...question_types import blank_count_hint, is_completion_query, is_open_text_completion
from .config import build_ocs_config

_JUDGEMENT_TRUE_LABELS = {"A"}
_JUDGEMENT_FALSE_LABELS = {"B"}
_JUDGEMENT_TRUE_TEXTS = {"对", "正确", "true", "yes"}
_JUDGEMENT_FALSE_TEXTS = {"错", "错误", "false", "no"}

__all__ = ["build_ocs_config", "to_ocs_low_confidence_response", "to_ocs_response"]


def to_ocs_response(result: QueryResult) -> dict:
    """将内部查询结果转换为 OCS 风格的 JSON 载荷。

    参数:
        result: QueryResult 实例，表示内部的查询处理结果。

    返回:
        dict: 符合 OCS API 规范的响应数据字典。
    """

    # 如果查询未成功（例如服务出错或请求发生异常），返回错误状态响应 (code=1)
    if not result.ok:
        return {
            "code": 1,
            "message": result.error_message or "query failed",
            "data": {
                "question": result.query.title,
                "answer": None,
                "ai": {
                    "review_required": True,
                    "confidence": result.confidence,
                    "resolution_mode": result.resolution_mode,
                    "error_code": result.error_code,
                    "input_flags": [
                        flag
                        for flag in str(result.debug.get("input_flags", "")).split(",")
                        if flag
                    ],
                },
            },
        }

    # 查询成功，返回状态码 0 以及匹配到的候选答案、详细文本与解析信息。
    # OCS 判断题页面通常没有 A/B 可匹配选项，因此仅在判断题中把内部标签转换为“对/错”文本。
    answer, answer_diagnostics = _ocs_answer_with_diagnostics(result)
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "question": result.query.title,
            "answer": answer,
            "answer_raw": result.candidate_answer,
            "answer_text": result.answer_text,
            "explanation": result.explanation,
            "ai": {
                "review_required": result.review_required,
                "confidence": result.confidence,
                "resolution_mode": result.resolution_mode,
                "sources": list(result.sources),
                **answer_diagnostics,
            },
        },
    }


def to_ocs_low_confidence_response(result: QueryResult, *, threshold: float) -> dict:
    """构造 API Key 策略拒绝低置信度作答时的 OCS 响应。"""

    return {
        "code": 1,
        "message": "低信任度答案未作答",
        "data": {
            "question": result.query.title,
            "answer": None,
            "answer_raw": result.candidate_answer,
            "answer_text": result.answer_text,
            "explanation": result.explanation,
            "ai": {
                "review_required": True,
                "confidence": result.confidence,
                "min_answer_confidence": threshold,
                "resolution_mode": result.resolution_mode,
                "error_code": "LOW_CONFIDENCE_ANSWER",
                "sources": list(result.sources),
            },
        },
    }


def _ocs_answer_with_diagnostics(result: QueryResult) -> tuple[str | None, dict[str, object]]:
    """返回 OCS 可消费答案及最小诊断信息。"""

    if not _is_judgement_result(result):
        return _non_judgement_ocs_answer(result)
    normalized_text = _normalize_judgement_text(result.answer_text)
    if normalized_text is not None:
        return normalized_text, {}
    candidate = (result.candidate_answer or "").strip().upper()
    if candidate in _JUDGEMENT_TRUE_LABELS:
        return "对", {}
    if candidate in _JUDGEMENT_FALSE_LABELS:
        return "错", {}
    return result.candidate_answer, {}


def _non_judgement_ocs_answer(result: QueryResult) -> tuple[str | None, dict[str, object]]:
    """处理选择题和填空题在 OCS 中需要的答案形态。"""

    if not is_completion_query(result.query):
        labels = canonicalize_label_answer(result.query, result.candidate_answer)
        if labels:
            return labels, {"ocs_answer_shape": "option_labels"}
        return result.candidate_answer or result.answer_text, {}
    if (
        is_open_text_completion(result.query)
        and result.answer_text
        and not _looks_like_json_array(result.candidate_answer)
    ):
        return result.answer_text, {"ocs_answer_shape": "text"}

    answer = result.candidate_answer or result.answer_text
    blanks = blank_count_hint(result.query.title)
    parts = _completion_answer_parts(answer, blank_count_hint=blanks)
    diagnostics: dict[str, object] = {
        "answer_parts_count": len(parts),
        "blank_count_hint": blanks,
        "ocs_answer_shape": "text",
    }
    if len(parts) > 1:
        diagnostics["ocs_answer_shape"] = "json_array"
        blank_count = int(diagnostics["blank_count_hint"])
        if blank_count and blank_count != len(parts):
            log_event(
                "ocs_completion_answer_count_mismatch",
                {
                    "title": result.query.title,
                    "answer_parts_count": len(parts),
                    "blank_count_hint": blank_count,
                },
            )
        return json.dumps(parts, ensure_ascii=False), diagnostics
    return answer, diagnostics


def _is_judgement_result(result: QueryResult) -> bool:
    question_type = result.query.question_type.strip().lower()
    title = result.query.title.strip()
    return question_type in {
        "judgement",
        "judge",
        "truefalse",
        "判断",
        "判断题",
    } or title.startswith("判断题")


def _normalize_judgement_text(value: str | None) -> str | None:
    normalized = (value or "").strip().casefold()
    if normalized in _JUDGEMENT_TRUE_TEXTS:
        return "对"
    if normalized in _JUDGEMENT_FALSE_TEXTS:
        return "错"
    return None


def _looks_like_json_array(value: str | None) -> bool:
    text = (value or "").strip()
    return text.startswith("[") and text.endswith("]")


def _completion_answer_parts(value: str | None, *, blank_count_hint: int = 0) -> list[str]:
    """把填空答案拆成 OCS 多空可消费的答案片段。"""

    text = (value or "").strip()
    if not text:
        return []
    parsed_parts = _json_array_parts(text)
    if parsed_parts:
        return parsed_parts
    if blank_count_hint > 1:
        bracketed_parts = _bracketed_completion_parts(text, blank_count_hint=blank_count_hint)
        if bracketed_parts:
            return bracketed_parts
    for separator in ("###", "===", "---", "#", "|", "；", ";"):
        if separator in text:
            parts = [part.strip() for part in text.split(separator) if part.strip()]
            if len(parts) > 1:
                return parts
    if blank_count_hint > 1:
        words = [part.strip() for part in re.split(r"\s+", text) if part.strip()]
        if len(words) == blank_count_hint and all(len(word) <= 40 for word in words):
            return [_strip_answer_wrapper(word) for word in words]
    return [text]


def _json_array_parts(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _bracketed_completion_parts(value: str, *, blank_count_hint: int) -> list[str]:
    groups = re.findall(r"\(([^()]*)\)|（([^（）]*)）", value)
    parts = [part.strip() for group in groups for part in group if part.strip()]
    return parts if len(parts) == blank_count_hint else []


def _strip_answer_wrapper(value: str) -> str:
    text = value.strip()
    matched = re.fullmatch(r"\(([^()]*)\)|（([^（）]*)）", text)
    if not matched:
        return text
    return next(part.strip() for part in matched.groups() if part is not None)

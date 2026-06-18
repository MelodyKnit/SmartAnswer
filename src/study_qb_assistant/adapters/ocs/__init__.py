"""面向本地学习服务的 OCS 风格响应适配器。

该模块负责将内部的 QueryResult 对象格式化为符合 OCS 规范的 JSON 响应。
"""

from __future__ import annotations

from ...models import QueryResult
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
                },
            },
        }

    # 查询成功，返回状态码 0 以及匹配到的候选答案、详细文本与解析信息。
    # OCS 判断题页面通常没有 A/B 可匹配选项，因此仅在判断题中把内部标签转换为“对/错”文本。
    answer = _ocs_answer(result)
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


def _ocs_answer(result: QueryResult) -> str | None:
    """Return the answer shape OCS can click on the current page."""
    if not _is_judgement_result(result):
        return result.candidate_answer or result.answer_text
    normalized_text = _normalize_judgement_text(result.answer_text)
    if normalized_text is not None:
        return normalized_text
    candidate = (result.candidate_answer or "").strip().upper()
    if candidate in _JUDGEMENT_TRUE_LABELS:
        return "对"
    if candidate in _JUDGEMENT_FALSE_LABELS:
        return "错"
    return result.candidate_answer


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

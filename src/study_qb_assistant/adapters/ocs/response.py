"""内部查询结果到 OCS 响应契约的适配。"""

from __future__ import annotations

from study_qb_assistant.questions.models import QueryResult
from .registry import OcsQuestionTypeRegistry
from .images import restore_ocs_image_numbers

DEFAULT_QUESTION_TYPE_REGISTRY = OcsQuestionTypeRegistry.with_defaults()


def to_ocs_response(
    result: QueryResult,
    *,
    registry: OcsQuestionTypeRegistry | None = None,
) -> dict[str, object]:
    """将内部查询结果转换为 OCS 风格响应。"""

    if not result.ok:
        return {
            "code": 1,
            "message": result.error_message or "query failed",
            "data": {
                "question": restore_ocs_image_numbers(result.query.title, result.query),
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

    handler = (registry or DEFAULT_QUESTION_TYPE_REGISTRY).resolve(
        result.query.question_type,
        result,
    )
    formatted = handler.format_answer(result)
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "question": restore_ocs_image_numbers(result.query.title, result.query),
            "answer": restore_ocs_image_numbers(formatted.answer, result.query),
            "answer_raw": restore_ocs_image_numbers(result.candidate_answer, result.query),
            "answer_text": restore_ocs_image_numbers(result.answer_text, result.query),
            "explanation": restore_ocs_image_numbers(result.explanation, result.query),
            "ai": {
                "review_required": result.review_required,
                "confidence": result.confidence,
                "resolution_mode": result.resolution_mode,
                "sources": list(result.sources),
                "ocs_question_type": handler.canonical_type,
                **formatted.diagnostic_payload(),
            },
        },
    }


def to_ocs_low_confidence_response(result: QueryResult, *, threshold: float) -> dict[str, object]:
    """构造 API Key 策略拒绝低置信度作答时的 OCS 响应。"""

    return {
        "code": 1,
        "message": "低信任度答案未作答",
        "data": {
            "question": restore_ocs_image_numbers(result.query.title, result.query),
            "answer": None,
            "answer_raw": restore_ocs_image_numbers(result.candidate_answer, result.query),
            "answer_text": restore_ocs_image_numbers(result.answer_text, result.query),
            "explanation": restore_ocs_image_numbers(result.explanation, result.query),
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

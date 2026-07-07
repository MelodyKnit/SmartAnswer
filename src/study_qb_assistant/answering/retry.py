"""AI/联网增强答题异常重试执行器。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..answer_quality import repair_model_answer
from ..logger import log_event
from ..models import ModelAnswer, QuestionQuery
from .policies import has_unhydrated_image_context

if TYPE_CHECKING:
    from .service import AnswerService


def retry_model_answer(service: AnswerService, query: QuestionQuery) -> tuple[ModelAnswer, int]:
    """在 AI/联网增强答题链路异常时按配置次数重试。"""

    assert service.model_provider is not None
    max_attempts = max(1, service.answer_retry_times + 1)
    last_error: Exception | None = None
    attempts = 0

    # 从包入口读取，保留 tests/外部对 study_qb_assistant.answering.build_model_query 的 patch 能力。
    from . import build_model_query

    model_query = build_model_query(query)
    if has_unhydrated_image_context(model_query):
        error = RuntimeError("image unreadable: no local image payload available")
        setattr(error, "stqb_retry_attempts", 1)
        raise error
    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        try:
            answer = service.model_provider.answer(model_query)
            return repair_model_answer(answer.source_query or model_query, answer), attempt
        except Exception as exc:
            last_error = exc
            if attempt >= max_attempts:
                break
            log_event(
                "answer_retry",
                {
                    "request_id": model_query.request_id,
                    "title": model_query.title,
                    "provider": service.model_provider.provider_name,
                    "attempt": attempt,
                    "max_retries": service.answer_retry_times,
                    "error": str(exc),
                },
            )
    assert last_error is not None
    setattr(last_error, "stqb_retry_attempts", attempts)
    raise last_error

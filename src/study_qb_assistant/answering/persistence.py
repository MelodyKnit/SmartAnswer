"""AI 答案沉淀到题库记录的持久化封装。"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from study_qb_assistant.media.inputs import normalize_image_urls
from ..llm.cache import CachedLlmAnswer, cache_key
from ..llm.cache.support import cache_candidate_for_answer
from study_qb_assistant.questions.models import CanonicalQuestionRecord, ModelAnswer, QuestionQuery

if TYPE_CHECKING:
    from .service import AnswerService


def persist_model_answer_record(
    service: AnswerService,
    query: QuestionQuery,
    answer: ModelAnswer,
    *,
    status: str,
    reuse_policy: str = "reusable",
    reuse_tags: tuple[str, ...] = (),
    original_query: QuestionQuery | None = None,
) -> CanonicalQuestionRecord | None:
    """把结构化 AI 答案写入题库仓储，并按状态决定后续是否可命中。"""

    repository = service.question_repository
    if repository is None:
        return None
    candidate = cache_candidate_for_answer(query, answer) or str(answer.answer_text or "").strip()
    if not candidate:
        return None
    now = time.time()
    entry = CachedLlmAnswer(
        key=cache_key(query),
        title=query.title,
        question_type=query.question_type,
        options=query.options,
        candidate_answer=candidate,
        answer_text=answer.answer_text,
        explanation=answer.explanation,
        confidence=max(0.0, min(answer.confidence, 1.0)),
        confirmations=1,
        conflicts=0,
        status=status,
        provider_name=service.model_provider.provider_name if service.model_provider else "unknown",
        created_at=now,
        updated_at=now,
    )
    record = entry.to_record()
    if reuse_tags or reuse_policy != "reusable" or original_query is not None:
        payload = record.to_dict()
        metadata = dict(record.metadata)
        metadata["reuse_policy"] = reuse_policy
        metadata["status"] = status
        if original_query is not None:
            image_urls = normalize_image_urls(
                original_query.image_urls,
                (original_query.title,),
                original_query.option_image_urls.values(),
            )
            if image_urls:
                metadata["source_image_urls"] = "#".join(image_urls)
        if answer.question_form:
            metadata["question_form"] = answer.question_form
        if answer.reuse_reason:
            metadata["reuse_reason"] = answer.reuse_reason
        if answer.reuse_confidence is not None:
            metadata["reuse_confidence"] = str(answer.reuse_confidence)
        payload["metadata"] = metadata
        payload["tags"] = tuple(dict.fromkeys((*record.tags, *reuse_tags)))
        record = CanonicalQuestionRecord.from_dict(payload)
    try:
        repository.save_question_record(record)
    except Exception:
        return None
    return record

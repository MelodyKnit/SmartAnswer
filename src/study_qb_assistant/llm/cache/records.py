"""LLM 自动沉淀题库的记录模型。"""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass

from ...models import CanonicalQuestionRecord, QuestionQuery
from ...option_labels import canonicalize_label_answer


@dataclass(slots=True)
class CachedLlmAnswer:
    """存储单个标准化问题形式的 AI 答案元数据。"""

    key: str
    title: str
    question_type: str
    options: tuple[str, ...]
    candidate_answer: str
    answer_text: str | None
    explanation: str | None
    confidence: float
    confirmations: int
    conflicts: int
    status: str
    provider_name: str
    created_at: float
    updated_at: float

    @classmethod
    def from_dict(
        cls,
        payload: dict,
        *,
        canonical_candidate_from_payload,
        optional_string,
        float_value,
        int_value,
    ) -> "CachedLlmAnswer":
        """从字典数据中还原缓存答案对象。"""
        return cls(
            key=str(payload["key"]),
            title=str(payload.get("title") or ""),
            question_type=str(payload.get("question_type") or "unknown"),
            options=tuple(str(option) for option in payload.get("options") or ()),
            candidate_answer=canonical_candidate_from_payload(payload),
            answer_text=optional_string(payload.get("answer_text")),
            explanation=optional_string(payload.get("explanation")),
            confidence=float(payload.get("confidence") or 0.0),
            confirmations=int(payload.get("confirmations") or 0),
            conflicts=int(payload.get("conflicts") or 0),
            status=str(payload.get("status") or "pending"),
            provider_name=str(payload.get("provider_name") or "unknown"),
            created_at=float(payload.get("created_at") or time.time()),
            updated_at=float(payload.get("updated_at") or time.time()),
        )

    def to_dict(self) -> dict:
        """将缓存答案序列化为稳定的 JSON 字典。"""
        payload = asdict(self)
        payload["options"] = list(self.options)
        return payload

    @classmethod
    def from_record(
        cls,
        record: CanonicalQuestionRecord,
        *,
        record_cache_key,
        optional_string,
        float_value,
        int_value,
    ) -> "CachedLlmAnswer":
        """从统一题库记录还原 LLM 沉淀状态。"""
        metadata = record.metadata
        query = QuestionQuery(
            title=record.title_raw,
            question_type=record.question_type,
            options=record.options_raw,
        )
        return cls(
            key=metadata.get("ai_cache_key") or record_cache_key(record),
            title=record.title_raw,
            question_type=record.question_type,
            options=record.options_raw,
            candidate_answer=canonicalize_label_answer(query, record.answer_raw or "")
            or (record.answer_raw or ""),
            answer_text=optional_string(metadata.get("ai_answer_text")),
            explanation=record.explanation,
            confidence=float_value(metadata.get("ai_confidence"), default=0.0),
            confirmations=int_value(metadata.get("ai_confirmations"), default=0),
            conflicts=int_value(metadata.get("ai_conflicts"), default=0),
            status=metadata.get("ai_status") or record.source_split or "pending",
            provider_name=metadata.get("ai_provider_name") or "unknown",
            created_at=float_value(metadata.get("ai_created_at"), default=time.time()),
            updated_at=float_value(metadata.get("ai_updated_at"), default=time.time()),
        )

    def to_record(self) -> CanonicalQuestionRecord:
        """把 LLM 沉淀答案写成统一题库记录。"""
        record_id = f"ai:{hashlib.sha256(self.key.encode('utf-8')).hexdigest()[:24]}"
        metadata = {
            "record_origin": "ai_generated",
            "ai_cache_key": self.key,
            "ai_status": self.status,
            "ai_confirmations": str(self.confirmations),
            "ai_conflicts": str(self.conflicts),
            "ai_confidence": str(self.confidence),
            "ai_provider_name": self.provider_name,
            "ai_created_at": str(self.created_at),
            "ai_updated_at": str(self.updated_at),
        }
        if self.answer_text:
            metadata["ai_answer_text"] = self.answer_text
        return CanonicalQuestionRecord(
            question_id=record_id,
            title_raw=self.title,
            question_type=self.question_type,
            options_raw=self.options,
            answer_raw=self.candidate_answer,
            explanation=self.explanation,
            subject="ai-generated",
            chapter=None,
            tags=(
                "ai_generated",
                "auto_learned",
                f"status:{self.status}",
                f"provider:{self.provider_name}",
            ),
            source_name="AIGenerated",
            source_url="",
            source_license="user-local-ai-generated",
            source_split=self.status,
            source_record_path="data/normalized/ai-learned.jsonl",
            metadata=metadata,
        )

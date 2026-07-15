"""使用记录模型。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass


@dataclass(slots=True)
class UsageLogRecord:
    """单次查题使用记录。"""

    log_id: str
    user_id: str
    username: str
    token_id: str | None
    title: str
    question_type: str
    resolution_mode: str
    answer: str | None
    confidence: float
    points_cost: int
    provider: str
    elapsed_ms: float
    created_at: float
    request_id: str = ""
    question_id: str | None = None
    source_name: str = ""
    source_type: str = ""
    source_id: str = ""
    source_url: str = ""
    context_json: str = "{}"
    token_description: str = ""
    token_key_mask: str = ""
    token_label: str = ""

    def to_dict(self) -> dict:
        return {
            "log_id": self.log_id,
            "user_id": self.user_id,
            "username": self.username,
            "token_id": self.token_id,
            "token_description": self.token_description,
            "token_key_mask": self.token_key_mask,
            "token_label": self.token_label,
            "title": self.title,
            "question_type": self.question_type,
            "resolution_mode": self.resolution_mode,
            "answer": self.answer,
            "confidence": self.confidence,
            "points_cost": self.points_cost,
            "provider": self.provider,
            "elapsed_ms": self.elapsed_ms,
            "created_at": self.created_at,
            "request_id": self.request_id,
            "question_id": self.question_id,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "source_url": self.source_url,
            "context_json": self.context_json,
            "context": _json_object(self.context_json),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "UsageLogRecord":
        return cls(
            log_id=str(payload["log_id"]),
            user_id=str(payload["user_id"]),
            username=str(payload["username"]),
            token_id=(str(payload["token_id"]) if payload.get("token_id") else None),
            title=str(payload.get("title") or ""),
            question_type=str(payload.get("question_type") or "unknown"),
            resolution_mode=str(payload.get("resolution_mode") or ""),
            answer=(str(payload["answer"]) if payload.get("answer") is not None else None),
            confidence=float(payload.get("confidence") or 0.0),
            points_cost=int(payload.get("points_cost") or 0),
            provider=str(payload.get("provider") or ""),
            elapsed_ms=float(payload.get("elapsed_ms") or 0.0),
            created_at=float(payload.get("created_at") or time.time()),
            request_id=str(payload.get("request_id") or ""),
            question_id=(str(payload["question_id"]) if payload.get("question_id") else None),
            source_name=str(payload.get("source_name") or ""),
            source_type=str(payload.get("source_type") or ""),
            source_id=str(payload.get("source_id") or ""),
            source_url=str(payload.get("source_url") or ""),
            context_json=str(payload.get("context_json") or "{}"),
            token_description=str(payload.get("token_description") or ""),
            token_key_mask=str(payload.get("token_key_mask") or ""),
            token_label=str(payload.get("token_label") or ""),
        )

def _json_object(value: str) -> dict:
    """安全解析 JSON 对象，坏数据按空对象处理。"""

    try:
        payload = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}

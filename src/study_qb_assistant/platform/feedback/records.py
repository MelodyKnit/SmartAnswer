"""用户反馈记录。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass


@dataclass(slots=True)
class FeedbackRecord:
    """用户错题反馈记录。"""

    feedback_id: str
    user_id: str
    username: str
    usage_log_id: str | None
    title: str
    content: str
    image_urls: tuple[str, ...]
    status: str
    created_at: float
    category: str = "answer"
    admin_note: str = ""
    corrected_answer: str = ""
    reward_points: int = 0
    handled_by: str = ""
    handled_at: float = 0.0
    question_id: str | None = None
    question_title: str = ""
    question_type: str = ""
    answer_snapshot: str | None = None
    resolution_mode: str = ""
    confidence: float = 0.0
    request_id: str = ""
    source_name: str = ""
    source_type: str = ""
    source_id: str = ""
    source_url: str = ""
    context_json: str = "{}"

    def to_dict(self) -> dict:
        try:
            context = json.loads(self.context_json or "{}")
        except json.JSONDecodeError:
            context = {}
        return {
            "feedback_id": self.feedback_id,
            "user_id": self.user_id,
            "username": self.username,
            "usage_log_id": self.usage_log_id,
            "title": self.title,
            "content": self.content,
            "image_urls": list(self.image_urls),
            "status": self.status,
            "created_at": self.created_at,
            "category": self.category,
            "admin_note": self.admin_note,
            "corrected_answer": self.corrected_answer,
            "reward_points": self.reward_points,
            "handled_by": self.handled_by,
            "handled_at": self.handled_at,
            "question_id": self.question_id,
            "question_title": self.question_title,
            "question_type": self.question_type,
            "answer_snapshot": self.answer_snapshot,
            "resolution_mode": self.resolution_mode,
            "confidence": self.confidence,
            "request_id": self.request_id,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "source_url": self.source_url,
            "context": context,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "FeedbackRecord":
        return cls(
            feedback_id=str(payload["feedback_id"]),
            user_id=str(payload["user_id"]),
            username=str(payload["username"]),
            usage_log_id=(str(payload["usage_log_id"]) if payload.get("usage_log_id") else None),
            title=str(payload.get("title") or ""),
            content=str(payload.get("content") or ""),
            image_urls=tuple(str(url) for url in payload.get("image_urls") or ()),
            status=str(payload.get("status") or "open"),
            created_at=float(payload.get("created_at") or time.time()),
            category=str(payload.get("category") or "answer"),
            admin_note=str(payload.get("admin_note") or ""),
            corrected_answer=str(payload.get("corrected_answer") or ""),
            reward_points=int(payload.get("reward_points") or 0),
            handled_by=str(payload.get("handled_by") or ""),
            handled_at=float(payload.get("handled_at") or 0.0),
            question_id=(str(payload["question_id"]) if payload.get("question_id") else None),
            question_title=str(payload.get("question_title") or ""),
            question_type=str(payload.get("question_type") or ""),
            answer_snapshot=(
                str(payload["answer_snapshot"]) if payload.get("answer_snapshot") is not None else None
            ),
            resolution_mode=str(payload.get("resolution_mode") or ""),
            confidence=float(payload.get("confidence") or 0.0),
            request_id=str(payload.get("request_id") or ""),
            source_name=str(payload.get("source_name") or ""),
            source_type=str(payload.get("source_type") or ""),
            source_id=str(payload.get("source_id") or ""),
            source_url=str(payload.get("source_url") or ""),
            context_json=str(payload.get("context_json") or "{}"),
        )

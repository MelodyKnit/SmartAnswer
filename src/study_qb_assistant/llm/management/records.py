"""大模型配置与调用追溯记录。"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(slots=True)
class LlmModelRecord:
    """大模型接入配置记录。"""

    model_id: str
    name: str
    base_url: str
    model: str
    api_key: str
    role: str
    priority: int
    stream: bool
    max_completion_tokens: int
    timeout_seconds: float
    status: str
    created_at: float
    updated_at: float

    def to_dict(self, *, reveal_secret: bool = False) -> dict:
        """转换为前端可消费的字典，默认隐藏 API Key。"""

        return {
            "model_id": self.model_id,
            "name": self.name,
            "base_url": self.base_url,
            "model": self.model,
            "api_key": self.api_key if reveal_secret else ("******" if self.api_key else ""),
            "api_key_configured": bool(self.api_key),
            "role": self.role,
            "priority": self.priority,
            "stream": self.stream,
            "max_completion_tokens": self.max_completion_tokens,
            "timeout_seconds": self.timeout_seconds,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

@dataclass(slots=True)
class LlmCallTraceRecord:
    """大模型调用追溯记录。"""

    trace_id: str
    request_id: str
    phase: str
    model_id: str
    model_name: str
    base_url: str
    provider: str
    question_title: str
    prompt: str
    evidence: str
    response_text: str
    candidate_answer: str | None
    confidence: float
    ok: bool
    error: str
    elapsed_ms: float
    created_at: float

    def to_dict(self) -> dict:
        """转换为前端调用追溯字典。"""

        try:
            evidence = json.loads(self.evidence or "[]")
        except json.JSONDecodeError:
            evidence = []
        if not isinstance(evidence, list):
            evidence = []
        return {
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "phase": self.phase,
            "model_id": self.model_id,
            "model_name": self.model_name,
            "base_url": self.base_url,
            "provider": self.provider,
            "question_title": self.question_title,
            "prompt": self.prompt,
            "evidence": evidence,
            "response_text": self.response_text,
            "candidate_answer": self.candidate_answer,
            "confidence": self.confidence,
            "ok": self.ok,
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
            "created_at": self.created_at,
        }

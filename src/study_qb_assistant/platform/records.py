"""平台领域持久化记录模型。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass


@dataclass(slots=True)
class ApiTokenRecord:
    """用户 API 令牌的持久化记录。"""

    token_id: str
    user_id: str
    key_hash: str
    key_mask: str
    description: str
    status: str
    created_at: float
    last_used_at: float = 0.0
    usage_count: int = 0
    quota_used: int = 0
    quota_limit: int = -1
    reject_low_confidence: bool = False
    min_answer_confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "token_id": self.token_id,
            "user_id": self.user_id,
            "key_hash": self.key_hash,
            "key_mask": self.key_mask,
            "description": self.description,
            "status": self.status,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
            "usage_count": self.usage_count,
            "quota_used": self.quota_used,
            "quota_limit": self.quota_limit,
            "reject_low_confidence": self.reject_low_confidence,
            "min_answer_confidence": self.min_answer_confidence,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "ApiTokenRecord":
        return cls(
            token_id=str(payload["token_id"]),
            user_id=str(payload["user_id"]),
            key_hash=str(payload["key_hash"]),
            key_mask=str(payload["key_mask"]),
            description=str(payload.get("description") or ""),
            status=str(payload.get("status") or "active"),
            created_at=float(payload.get("created_at") or time.time()),
            last_used_at=float(payload.get("last_used_at") or 0.0),
            usage_count=int(payload.get("usage_count") or 0),
            quota_used=int(payload.get("quota_used", payload.get("usage_count", 0)) or 0),
            quota_limit=int(payload.get("quota_limit", -1)),
            reject_low_confidence=bool(payload.get("reject_low_confidence") or False),
            min_answer_confidence=float(payload.get("min_answer_confidence") or 0.0),
        )


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

    def to_dict(self) -> dict:
        return {
            "log_id": self.log_id,
            "user_id": self.user_id,
            "username": self.username,
            "token_id": self.token_id,
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
        )


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


@dataclass(slots=True)
class RedeemCodeRecord:
    """兑换码记录。"""

    code_id: str
    code: str
    kind: str
    points: int
    max_uses: int
    used_uses: int
    status: str
    created_by: str
    created_at: float
    expires_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "code_id": self.code_id,
            "code": self.code,
            "kind": self.kind,
            "points": self.points,
            "max_uses": self.max_uses,
            "used_uses": self.used_uses,
            "status": self.status,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "RedeemCodeRecord":
        return cls(
            code_id=str(payload["code_id"]),
            code=str(payload["code"]),
            kind=str(payload.get("kind") or "points"),
            points=int(payload.get("points") or 0),
            max_uses=int(payload.get("max_uses") or 1),
            used_uses=int(payload.get("used_uses") or 0),
            status=str(payload.get("status") or "active"),
            created_by=str(payload.get("created_by") or ""),
            created_at=float(payload.get("created_at") or time.time()),
            expires_at=float(payload.get("expires_at") or 0.0),
        )


@dataclass(slots=True)
class WalletOrderRecord:
    """钱包订单与权益变更流水。"""

    order_id: str
    user_id: str
    username: str
    kind: str
    points_delta: int
    source: str
    source_id: str | None
    status: str
    created_by: str
    created_at: float

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "user_id": self.user_id,
            "username": self.username,
            "kind": self.kind,
            "points_delta": self.points_delta,
            "source": self.source,
            "source_id": self.source_id,
            "status": self.status,
            "created_by": self.created_by,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "WalletOrderRecord":
        return cls(
            order_id=str(payload["order_id"]),
            user_id=str(payload["user_id"]),
            username=str(payload["username"]),
            kind=str(payload.get("kind") or "points"),
            points_delta=int(payload.get("points_delta") or 0),
            source=str(payload.get("source") or ""),
            source_id=(str(payload["source_id"]) if payload.get("source_id") else None),
            status=str(payload.get("status") or "completed"),
            created_by=str(payload.get("created_by") or ""),
            created_at=float(payload.get("created_at") or time.time()),
        )


@dataclass(slots=True)
class NotificationRecord:
    """消息中心通知记录。"""

    notification_id: str
    user_id: str | None
    level: str
    category: str
    title: str
    content: str
    read: bool
    created_at: float

    def to_dict(self) -> dict:
        return {
            "notification_id": self.notification_id,
            "user_id": self.user_id,
            "level": self.level,
            "category": self.category,
            "title": self.title,
            "content": self.content,
            "read": self.read,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "NotificationRecord":
        return cls(
            notification_id=str(payload["notification_id"]),
            user_id=(str(payload["user_id"]) if payload.get("user_id") else None),
            level=str(payload.get("level") or "info"),
            category=str(payload.get("category") or "system"),
            title=str(payload.get("title") or ""),
            content=str(payload.get("content") or ""),
            read=bool(payload.get("read") or False),
            created_at=float(payload.get("created_at") or time.time()),
        )


@dataclass(slots=True)
class ImportScriptRecord:
    """导入脚本记录。"""

    script_id: str
    name: str
    integration_id: str | None
    token_id: str | None
    target: str
    content: str
    status: str
    created_at: float
    updated_at: float
    description: str = ""
    requires_token: bool = True
    tags: tuple[str, ...] = ()
    builtin: bool = False
    is_default: bool = False
    ocs_config: tuple[dict, ...] = ()

    def to_dict(self) -> dict:
        return {
            "script_id": self.script_id,
            "name": self.name,
            "integration_id": self.integration_id,
            "token_id": self.token_id,
            "target": self.target,
            "content": self.content,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "description": self.description,
            "requires_token": self.requires_token,
            "tags": list(self.tags),
            "builtin": self.builtin,
            "is_default": self.is_default,
            "ocs_config": list(self.ocs_config),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "ImportScriptRecord":
        return cls(
            script_id=str(payload["script_id"]),
            name=str(payload.get("name") or ""),
            integration_id=(
                str(payload["integration_id"]) if payload.get("integration_id") else None
            ),
            token_id=(str(payload["token_id"]) if payload.get("token_id") else None),
            target=str(payload.get("target") or "ocs"),
            content=str(payload.get("content") or ""),
            status=str(payload.get("status") or "active"),
            created_at=float(payload.get("created_at") or time.time()),
            updated_at=float(payload.get("updated_at") or time.time()),
            description=str(payload.get("description") or ""),
            requires_token=bool(payload.get("requires_token", True)),
            tags=tuple(str(item) for item in payload.get("tags") or ()),
            builtin=bool(payload.get("builtin", False)),
            is_default=bool(payload.get("is_default", False)),
            ocs_config=tuple(dict(item) for item in payload.get("ocs_config") or ()),
        )


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


@dataclass(slots=True)
class RolePermissionRecord:
    """角色权限矩阵记录。"""

    role_id: str
    permissions: tuple[str, ...]
    updated_at: float

    def to_dict(self) -> dict:
        return {
            "role_id": self.role_id,
            "permissions": list(self.permissions),
            "updated_at": self.updated_at,
        }

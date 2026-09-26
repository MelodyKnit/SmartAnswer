"""API 令牌记录。"""

from __future__ import annotations

import time
from dataclasses import dataclass


def normalize_token_status(value: object) -> str:
    """规范化 API Key 状态，同时保留不可逆的历史吊销状态。"""

    status = str("active" if value is None else value).strip().lower()
    return status if status in {"active", "disabled", "revoked"} else "disabled"


@dataclass(slots=True)
class ApiTokenRecord:
    """用户 API 令牌的持久化记录。"""

    token_id: str
    user_id: str
    key_hash: str
    key_mask: str
    token_raw: str = ""
    description: str = ""
    status: str = "active"
    created_at: float = 0.0
    last_used_at: float = 0.0
    usage_count: int = 0
    quota_used: int = 0
    quota_limit: int = -1
    reject_low_confidence: bool = False
    min_answer_confidence: float = 0.0
    bind_client: bool = False
    bound_client_id: str = ""

    def to_dict(self) -> dict:
        return {
            "token_id": self.token_id,
            "user_id": self.user_id,
            "key_hash": self.key_hash,
            "key_mask": self.key_mask,
            "description": self.description,
            "status": normalize_token_status(self.status),
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
            "usage_count": self.usage_count,
            "quota_used": self.quota_used,
            "quota_limit": self.quota_limit,
            "reject_low_confidence": self.reject_low_confidence,
            "min_answer_confidence": self.min_answer_confidence,
            "bind_client": self.bind_client,
            "is_bound": bool(self.bind_client and self.bound_client_id),
            "is_recoverable": bool(self.token_raw),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "ApiTokenRecord":
        return cls(
            token_id=str(payload["token_id"]),
            user_id=str(payload["user_id"]),
            key_hash=str(payload["key_hash"]),
            key_mask=str(payload["key_mask"]),
            token_raw=str(payload.get("token_raw", "") or ""),
            description=str(payload.get("description", "") or ""),
            status=normalize_token_status(payload.get("status", "active")),
            created_at=float(payload.get("created_at") or time.time()),
            last_used_at=float(payload.get("last_used_at", 0.0) or 0.0),
            usage_count=int(payload.get("usage_count", 0) or 0),
            quota_used=int(payload.get("quota_used", 0) or 0),
            quota_limit=int(payload.get("quota_limit", -1) if payload.get("quota_limit") is not None else -1),
            reject_low_confidence=bool(payload.get("reject_low_confidence", False)),
            min_answer_confidence=float(payload.get("min_answer_confidence", 0.0) or 0.0),
            bind_client=bool(payload.get("bind_client", False)),
            bound_client_id=str(payload.get("bound_client_id", "") or ""),
        )

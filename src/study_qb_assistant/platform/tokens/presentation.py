"""API 令牌安全展示与摘要工具。"""

from __future__ import annotations

import hashlib

from .records import ApiTokenRecord


def hash_token(token: str) -> str:
    """生成用于 Bearer 查询的 SHA-256 索引。"""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def mask_token(token: str) -> str:
    """对令牌做掩码，避免前端重复看到完整密钥。"""

    if len(token) <= 12:
        return token
    return token[:10] + "..." + token[-4:]


def public_token_dict(token: ApiTokenRecord) -> dict:
    """生成不包含原始令牌的公开令牌摘要。"""

    return {
        "token_id": token.token_id,
        "user_id": token.user_id,
        "key_mask": token.key_mask,
        "description": token.description,
        "status": token.status,
        "created_at": token.created_at,
        "last_used_at": token.last_used_at,
        "usage_count": token.usage_count,
        "quota_limit": token.quota_limit,
        "quota_used": token.quota_used,
        "reject_low_confidence": token.reject_low_confidence,
        "min_answer_confidence": token.min_answer_confidence,
        "is_recoverable": bool(token.token_raw),
    }

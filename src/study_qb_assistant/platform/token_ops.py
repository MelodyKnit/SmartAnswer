"""平台令牌相关业务辅助。"""

from __future__ import annotations

import secrets
import time

from ..auth import AuthError
from .records import ApiTokenRecord
from .storage import hash_token, mask_token, public_token_dict


def create_token_entry(
    *,
    tokens: dict[str, ApiTokenRecord],
    token_lookup: dict[str, str],
    user_id: str,
    description: str,
) -> tuple[str, dict]:
    """创建新的 API 令牌并写入状态集合。"""
    raw = "sk_stqb_" + secrets.token_urlsafe(24)
    token = ApiTokenRecord(
        token_id=secrets.token_hex(12),
        user_id=user_id,
        key_hash=hash_token(raw),
        key_mask=mask_token(raw),
        description=description.strip(),
        status="active",
        created_at=time.time(),
    )
    tokens[token.token_id] = token
    token_lookup[token.key_hash] = token.token_id
    return raw, public_token_dict(token)


def list_token_entries(tokens: dict[str, ApiTokenRecord], *, user_id: str) -> list[dict]:
    """列出指定用户的全部 API 令牌。"""
    return [public_token_dict(token) for token in tokens.values() if token.user_id == user_id]


def revoke_token_entry(
    tokens: dict[str, ApiTokenRecord],
    *,
    user_id: str,
    token_id: str,
) -> dict:
    """吊销用户自己的 API 令牌。"""
    token = tokens.get(token_id)
    if token is None or token.user_id != user_id:
        raise AuthError("TOKEN_NOT_FOUND", "令牌不存在", http_status=404)
    token.status = "revoked"
    return public_token_dict(token)


def resolve_token_entry(
    tokens: dict[str, ApiTokenRecord],
    token_lookup: dict[str, str],
    *,
    raw_token: str | None,
) -> dict | None:
    """解析原始 Bearer 令牌，并更新使用时间。"""
    if not raw_token:
        return None
    token_id = token_lookup.get(hash_token(raw_token))
    if not token_id:
        return None
    token = tokens.get(token_id)
    if token is None or token.status != "active":
        return None
    token.last_used_at = time.time()
    token.usage_count += 1
    return public_token_dict(token)

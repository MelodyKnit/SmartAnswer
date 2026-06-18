"""平台状态的落盘与恢复辅助。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .config import SYSTEM_CONFIG_KEYS
from .records import (
    ApiTokenRecord,
    FeedbackRecord,
    RedeemCodeRecord,
    UsageLogRecord,
    WalletOrderRecord,
)


def hash_token(token: str) -> str:
    """对原始令牌做 SHA-256 摘要，避免明文落盘。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def mask_token(token: str) -> str:
    """对令牌做掩码，避免前端看到完整密钥。"""
    if len(token) <= 12:
        return token
    return token[:10] + "..." + token[-4:]


def public_token_dict(token: ApiTokenRecord) -> dict:
    """生成对前端安全可见的令牌信息。"""
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
        "quota_used": token.usage_count,
        "reject_low_confidence": token.reject_low_confidence,
        "min_answer_confidence": token.min_answer_confidence,
    }


def load_platform_state(
    path: Path,
    *,
    tokens: dict[str, ApiTokenRecord],
    token_lookup: dict[str, str],
    usage_logs: list[UsageLogRecord],
    feedbacks: list[FeedbackRecord],
    redeem_codes: dict[str, RedeemCodeRecord],
    wallet_orders: list[WalletOrderRecord],
    billing: dict[str, int],
    system_config: dict[str, str],
) -> None:
    """从 JSON 文件恢复平台状态。"""
    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return
    for item in payload.get("tokens") or ():
        token = ApiTokenRecord.from_dict(item)
        tokens[token.token_id] = token
        token_lookup[token.key_hash] = token.token_id
    for item in payload.get("usage_logs") or ():
        usage_logs.append(UsageLogRecord.from_dict(item))
    for item in payload.get("feedbacks") or ():
        feedbacks.append(FeedbackRecord.from_dict(item))
    for item in payload.get("redeem_codes") or ():
        redeem = RedeemCodeRecord.from_dict(item)
        redeem_codes[redeem.code_id] = redeem
    for item in payload.get("wallet_orders") or ():
        wallet_orders.append(WalletOrderRecord.from_dict(item))
    loaded_billing = payload.get("billing") if isinstance(payload, dict) else None
    if isinstance(loaded_billing, dict):
        for key in billing:
            if key in loaded_billing:
                billing[key] = max(0, int(loaded_billing[key]))
    loaded_system_config = payload.get("system_config") if isinstance(payload, dict) else None
    if isinstance(loaded_system_config, dict):
        for key in SYSTEM_CONFIG_KEYS:
            if key in loaded_system_config:
                system_config[key] = str(loaded_system_config[key] or "").strip()


def save_platform_state(
    path: Path,
    *,
    tokens: dict[str, ApiTokenRecord],
    usage_logs: list[UsageLogRecord],
    feedbacks: list[FeedbackRecord],
    redeem_codes: dict[str, RedeemCodeRecord],
    wallet_orders: list[WalletOrderRecord],
    billing: dict[str, int],
    system_config: dict[str, str],
) -> None:
    """以原子写方式保存平台状态。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    payload = {
        "version": 1,
        "tokens": [token.to_dict() for token in tokens.values()],
        "usage_logs": [log.to_dict() for log in usage_logs],
        "feedbacks": [fb.to_dict() for fb in feedbacks],
        "redeem_codes": [code.to_dict() for code in redeem_codes.values()],
        "wallet_orders": [order.to_dict() for order in wallet_orders],
        "billing": billing,
        "system_config": system_config,
    }
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    tmp_path.replace(path)

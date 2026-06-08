"""鉴权基础安全工具。"""

from __future__ import annotations

import hashlib
import re

PBKDF2_ALGO = "sha256"
PBKDF2_ITERATIONS = 200_000
SALT_BYTES = 16

USERNAME_RE = re.compile(r"^[A-Za-z0-9_\-一-龥]{3,32}$")
MIN_PASSWORD_LEN = 8

SESSION_TTL_DEFAULT = 12 * 3600
SESSION_TTL_REMEMBER = 30 * 24 * 3600
RESET_TOKEN_TTL = 30 * 60

THROTTLE_MAX_FAILURES = 5
THROTTLE_WINDOW = 5 * 60
THROTTLE_LOCK = 10 * 60


def hash_password(password: str, salt_hex: str) -> str:
    """用 PBKDF2-HMAC-SHA256 计算密码哈希。"""
    derived = hashlib.pbkdf2_hmac(
        PBKDF2_ALGO,
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        PBKDF2_ITERATIONS,
    )
    return derived.hex()


def hash_token(token: str) -> str:
    """对令牌做 SHA-256 摘要，避免明文令牌落盘。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

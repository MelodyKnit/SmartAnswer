"""鉴权领域的数据记录模型。"""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass


@dataclass(slots=True)
class UserRecord:
    """单个用户的持久化记录。"""

    user_id: str
    username: str
    role: str
    status: str
    salt: str
    password_hash: str
    email: str | None
    points: int
    created_at: float
    invite_code: str = ""
    invited_by: str = ""
    reset_token_hash: str | None = None
    reset_expires_at: float = 0.0
    unlimited_expires_at: float = 0.0

    @property
    def is_unlimited(self) -> bool:
        """检查用户当前是否在无限使用天数有效期内。"""
        return self.unlimited_expires_at > time.time()

    def to_dict(self) -> dict:
        """转换为可写入 JSON 的字典。"""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
            "status": self.status,
            "salt": self.salt,
            "password_hash": self.password_hash,
            "email": self.email,
            "points": self.points,
            "created_at": self.created_at,
            "invite_code": self.invite_code,
            "invited_by": self.invited_by,
            "reset_token_hash": self.reset_token_hash,
            "reset_expires_at": self.reset_expires_at,
            "unlimited_expires_at": self.unlimited_expires_at,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "UserRecord":
        """从磁盘字典恢复用户记录。"""
        return cls(
            user_id=str(payload.get("user_id") or secrets.token_hex(16)),
            username=str(payload["username"]),
            role=str(payload.get("role") or "user"),
            status=str(payload.get("status") or "active"),
            salt=str(payload["salt"]),
            password_hash=str(payload["password_hash"]),
            email=(str(payload["email"]) if payload.get("email") else None),
            points=int(payload.get("points") or int(os.getenv("STQB_DEFAULT_USER_POINTS", "100"))),
            created_at=float(payload.get("created_at") or time.time()),
            invite_code=str(payload.get("invite_code") or ""),
            invited_by=str(payload.get("invited_by") or ""),
            reset_token_hash=(
                str(payload["reset_token_hash"]) if payload.get("reset_token_hash") else None
            ),
            reset_expires_at=float(payload.get("reset_expires_at") or 0.0),
            unlimited_expires_at=float(payload.get("unlimited_expires_at") or payload.get("vip_expires_at") or 0.0),
        )


@dataclass(slots=True)
class SessionRecord:
    """内存中的会话记录。"""

    username: str
    role: str
    expires_at: float


@dataclass(slots=True)
class EmailVerificationCodeRecord:
    """邮箱验证码持久化记录，只保存哈希和审计必要字段。"""

    code_id: str
    email: str
    purpose: str
    code_hash: str
    expires_at: float
    attempts: int
    send_ip_hash: str
    created_at: float
    consumed_at: float = 0.0

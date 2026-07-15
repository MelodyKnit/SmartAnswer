"""API 令牌领域服务。"""

from __future__ import annotations

import secrets
import time

from ...auth import AuthError
from ..base import PlatformDomainService
from ..import_scripts.templates import get_import_script_template, render_import_script
from .records import ApiTokenRecord
from .presentation import hash_token, mask_token, public_token_dict


class TokenService(PlatformDomainService):
    """TokenService 领域实现。"""

    def create_token(
        self,
        *,
        user_id: str,
        description: str = "",
        quota_limit: int = -1,
        reject_low_confidence: bool = False,
        min_answer_confidence: float = 0.0,
    ) -> tuple[str, dict]:
        """为指定用户创建新的 API 令牌。"""
        with self.lock:
            raw = "sk_stqb_" + secrets.token_urlsafe(24)
            record = ApiTokenRecord(
                token_id=secrets.token_hex(12),
                user_id=user_id,
                key_hash=hash_token(raw),
                key_mask=mask_token(raw),
                description=description.strip(),
                status="active",
                created_at=time.time(),
                quota_limit=int(quota_limit),
                reject_low_confidence=bool(reject_low_confidence),
                min_answer_confidence=normalized_confidence(min_answer_confidence),
            )
            self.repository.save_token(record)
            return raw, public_token_dict(record)

    def list_tokens(self, *, user_id: str) -> list[dict]:
        """列出指定用户的全部 API 令牌。"""
        with self.lock:
            return [
                public_token_dict(token) for token in self.repository.list_tokens(user_id=user_id)
            ]

    def token_import_script(
        self,
        *,
        user_id: str,
        base_url: str,
        token_id: str | None = None,
        template_id: str | None = None,
    ) -> dict:
        """为普通用户即时生成导入脚本和 OCS 题库配置。"""
        tokens = [
            token
            for token in self.repository.list_tokens(user_id=user_id)
            if token.status == "active"
        ]
        if not tokens:
            raise AuthError("TOKEN_REQUIRED", "请先创建密钥", http_status=404)
        if token_id is None and len(tokens) > 1:
            return {
                "mode": "select_token",
                "token_options": [public_token_dict(token) for token in tokens],
            }
        selected = (
            tokens[0]
            if token_id is None
            else next((token for token in tokens if token.token_id == token_id), None)
        )
        if selected is None:
            raise AuthError("TOKEN_NOT_FOUND", "令牌不存在", http_status=404)
        template = get_import_script_template(template_id)
        rendered = render_import_script(template, base_url)
        return {
            "mode": "direct",
            "token_id": selected.token_id,
            "token_option": public_token_dict(selected),
            "script": rendered["content"],
            "ocs_config": rendered["ocs_config"],
            "template_id": template.template_id,
            "requires_local_secret": True,
        }

    def revoke_token(self, *, user_id: str, token_id: str) -> dict:
        """吊销用户自己的 API 令牌。"""
        with self.lock:
            token = self.repository.get_token(token_id)
            if token is None or token.user_id != user_id:
                raise AuthError("TOKEN_NOT_FOUND", "令牌不存在", http_status=404)
            token.status = "revoked"
            self.repository.save_token(token)
            return public_token_dict(token)

    def update_token(
        self,
        *,
        user_id: str,
        token_id: str,
        description: str = "",
        quota_limit: int = -1,
        reject_low_confidence: bool = False,
        min_answer_confidence: float = 0.0,
    ) -> dict:
        """更新用户自己的 API 令牌配置。"""
        with self.lock:
            token = self.repository.get_token(token_id)
            if token is None or token.user_id != user_id:
                raise AuthError("TOKEN_NOT_FOUND", "令牌不存在", http_status=404)
            token.description = description.strip()
            token.quota_limit = int(quota_limit)
            token.reject_low_confidence = bool(reject_low_confidence)
            token.min_answer_confidence = normalized_confidence(min_answer_confidence)
            self.repository.save_token(token)
            return public_token_dict(token)

    def delete_token(self, *, user_id: str, token_id: str) -> None:
        """删除用户自己的 API 令牌。"""
        with self.lock:
            token = self.repository.get_token(token_id)
            if token is None or token.user_id != user_id:
                raise AuthError("TOKEN_NOT_FOUND", "令牌不存在", http_status=404)
            self.repository.delete_token(token_id)

    def resolve_token(self, raw_token: str | None) -> dict | None:
        """解析原始 Bearer 令牌，并校验当前剩余额度。"""
        with self.lock:
            if not raw_token:
                return None
            token = self.repository.find_token_by_hash(hash_token(raw_token))
            if token is None or token.status != "active":
                return None
            if token.quota_limit >= 0 and token.quota_used >= token.quota_limit:
                raise AuthError("TOKEN_QUOTA_EXCEEDED", "API Key 调用额度已用完", http_status=401)
            return public_token_dict(token)


def normalized_confidence(value: object) -> float:
    """把令牌置信度阈值归一化到 0 到 1。"""

    try:
        return min(max(float(str(value or "0")), 0.0), 1.0)
    except (TypeError, ValueError):
        return 0.0

"""平台业务服务。"""

from __future__ import annotations

import json
import secrets
import time
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock
from zoneinfo import ZoneInfo

from ..auth import AuthError
from ..logger import log_path
from ..llm.config import service as llm_config_service
from ..storage.platform_repository import SqlAlchemyPlatformRepository
from .config import (
    LLM_RUNTIME_CONFIG_KEYS,
    LLM_RUNTIME_ENV_MAP,
    SYSTEM_CONFIG_DEFAULTS,
    SYSTEM_CONFIG_ENV_MAP,
    SYSTEM_CONFIG_BOOLEAN_KEYS,
    SYSTEM_CONFIG_KEYS,
    SYSTEM_CONFIG_SECRET_KEYS,
)
from .records import (
    ApiTokenRecord,
    FeedbackRecord,
    ImportScriptRecord,
    LlmCallTraceRecord,
    NotificationRecord,
    RedeemCodeRecord,
    RolePermissionRecord,
    UsageLogRecord,
    WalletOrderRecord,
)
from .import_script_catalog import (
    get_import_script_template,
    load_import_script_templates,
    render_import_script,
)
from .storage import hash_token, mask_token, public_token_dict
from .wallet_ops import wallet_summary_payload


DEFAULT_ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "superadmin": (
        "dashboard:all",
        "users:write",
        "roles:read",
        "roles:write",
        "system:read",
        "system:write",
        "billing:read",
        "billing:write",
        "wallet:changes:read",
        "wallet:changes:write",
        "import-scripts:read",
        "import-scripts:write",
        "questions:read",
        "questions:write",
        "llm:read",
        "llm:write",
    ),
    "admin": (
        "dashboard:all",
        "users:write",
        "roles:read",
        "billing:read",
        "wallet:changes:read",
        "wallet:changes:write",
        "import-scripts:read",
        "import-scripts:write",
        "questions:read",
        "questions:write",
        "llm:read",
    ),
    "user": ("dashboard:self", "tokens:self", "feedback:self"),
}

LOCAL_TIMEZONE = ZoneInfo("Asia/Shanghai")


class PlatformService:
    """平台领域服务，负责令牌、计费、日志、反馈、钱包与系统配置。"""

    def __init__(self, path: str | Path) -> None:
        """初始化平台状态服务。

        Args:
            path: 数据库路径、数据库 URL，或兼容的旧 JSON 路径。
        """
        self.path = Path(path) if not isinstance(path, Path) and "://" not in str(path) else path
        self._lock = RLock()
        self.repository = SqlAlchemyPlatformRepository(path)

    @staticmethod
    def default_system_config() -> dict[str, str]:
        """返回平台系统配置默认值。"""

        return dict(SYSTEM_CONFIG_DEFAULTS)

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
        with self._lock:
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
        with self._lock:
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
        with self._lock:
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
        with self._lock:
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
        with self._lock:
            token = self.repository.get_token(token_id)
            if token is None or token.user_id != user_id:
                raise AuthError("TOKEN_NOT_FOUND", "令牌不存在", http_status=404)
            self.repository.delete_token(token_id)

    def resolve_token(self, raw_token: str | None) -> dict | None:
        """解析原始 Bearer 令牌，并校验当前剩余额度。"""
        with self._lock:
            if not raw_token:
                return None
            token = self.repository.find_token_by_hash(hash_token(raw_token))
            if token is None or token.status != "active":
                return None
            if token.quota_limit >= 0 and token.quota_used >= token.quota_limit:
                raise AuthError("TOKEN_QUOTA_EXCEEDED", "API Key 调用额度已用完", http_status=401)
            return public_token_dict(token)

    def get_billing(self) -> dict:
        """读取当前积分计费配置。"""
        with self._lock:
            defaults = {"local_hit": 1, "web_search": 2, "llm_fallback": 3}
            stored = self.repository.get_settings("billing", keys=set(defaults.keys()))
            return {key: max(0, int(stored.get(key, default))) for key, default in defaults.items()}

    def set_billing(self, values: dict[str, int]) -> dict:
        """更新积分计费配置。"""
        current = self.get_billing()
        for key, value in values.items():
            if key not in current:
                raise AuthError("INVALID_INPUT", f"不支持的积分项目: {key}", http_status=400)
            current[key] = max(0, int(value))
        with self._lock:
            self.repository.replace_settings(
                "billing", {key: str(value) for key, value in current.items()}
            )
        return current

    def calculate_points_cost(self, resolution_mode: str) -> int:
        """根据查题命中方式计算本次调用的积分消耗。"""
        billing = self.get_billing()
        if resolution_mode == "llm_fallback":
            return billing["llm_fallback"]
        if resolution_mode in {"exact_match", "fuzzy_match", "known_rule", "ai_cache"}:
            return billing["local_hit"]
        return billing["web_search"]

    def system_points_value(self, key: str) -> int:
        """读取非负整数型积分策略配置。"""

        if key not in SYSTEM_CONFIG_KEYS:
            raise AuthError("INVALID_INPUT", f"不支持的系统配置项: {key}", http_status=400)
        raw = self.repository.get_settings("system_config", keys={key})
        value = raw.get(key, SYSTEM_CONFIG_DEFAULTS.get(key, "0"))
        try:
            return max(0, int(str(value or "0").strip() or "0"))
        except ValueError as exc:
            raise AuthError("INVALID_INPUT", f"{key} 必须为非负整数", http_status=400) from exc

    def get_default_user_points(self) -> int:
        """返回新注册用户初始积分。"""

        return self.system_points_value("default_user_points")

    def get_invite_bonus(self) -> int:
        """返回注册邀请码奖励积分。"""

        return self.system_points_value("invite_bonus_points")

    def is_registration_enabled(self) -> bool:
        """返回公开注册入口是否启用。"""

        raw = self.get_system_config().get("registration_enabled", "true")
        return str(raw).strip().lower() not in {"0", "false", "no", "off", "disabled"}

    def get_points_policy(self) -> dict[str, int]:
        """返回前端表单需要展示或预填的积分策略。"""

        return {
            "default_user_points": self.get_default_user_points(),
            "invite_bonus_points": self.get_invite_bonus(),
            "manual_grant_default_points": self.system_points_value(
                "manual_grant_default_points"
            ),
            "redeem_code_default_points": self.system_points_value(
                "redeem_code_default_points"
            ),
        }

    def wallet_summary(self, *, user_id: str, username: str, points: int) -> dict:
        """汇总用户钱包积分状态。"""

        with self._lock:
            return wallet_summary_payload(
                user_id=user_id,
                username=username,
                points=points,
            )

    def record_usage(
        self,
        *,
        user_id: str,
        username: str,
        token_id: str | None,
        title: str,
        question_type: str,
        resolution_mode: str,
        answer: str | None,
        confidence: float,
        provider: str,
        points_cost: int,
        elapsed_ms: float = 0.0,
        request_id: str = "",
    ) -> dict:
        """记录一次查题调用的审计日志。"""
        record = UsageLogRecord(
            log_id=secrets.token_hex(12),
            user_id=user_id,
            username=username,
            token_id=token_id,
            title=title,
            question_type=question_type,
            resolution_mode=resolution_mode,
            answer=answer,
            confidence=confidence,
            points_cost=points_cost,
            provider=(provider or "unknown").strip() or "unknown",
            elapsed_ms=elapsed_ms,
            created_at=time.time(),
            request_id=request_id.strip(),
        )
        with self._lock:
            self.repository.commit_usage_transaction(
                record,
                token_id=token_id,
                points_cost=points_cost,
            )
        return record.to_dict()

    def list_usage_logs(
        self,
        *,
        username: str | None = None,
        token_id: str = "",
        keyword: str = "",
        limit: int = 100,
        offset: int = 0,
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> list[dict]:
        """按用户与关键词筛选使用日志。"""
        with self._lock:
            return [
                item.to_dict()
                for item in self.repository.list_usage_logs(
                    username=username,
                    token_id=token_id,
                    keyword=keyword,
                    limit=limit,
                    offset=offset,
                    start_time=start_time,
                    end_time=end_time,
                )
            ]

    def count_usage_logs(
        self,
        *,
        username: str | None = None,
        token_id: str = "",
        keyword: str = "",
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> int:
        """统计使用日志数量。"""
        with self._lock:
            return self.repository.count_usage_logs(
                username=username,
                token_id=token_id,
                keyword=keyword,
                start_time=start_time,
                end_time=end_time,
            )

    def usage_scope(self, *, username: str, role: str, scope: str = "self") -> tuple[str, str | None]:
        """归一化统计范围，并返回仓储层需要的用户过滤器。"""

        requested_scope = (scope or "").strip().lower()
        if not requested_scope:
            requested_scope = "global" if role in {"admin", "superadmin"} else "self"
        if requested_scope == "global" and role in {"admin", "superadmin"}:
            return "global", None
        return "self", username

    def usage_overview(
        self,
        *,
        username: str,
        role: str,
        scope: str,
        start_time: float,
        end_time: float,
    ) -> dict[str, float | str]:
        """返回当前口径下的概览统计。"""

        effective_scope, username_filter = self.usage_scope(
            username=username,
            role=role,
            scope=scope,
        )
        with self._lock:
            metrics = self.repository.usage_overview(
                username=username_filter,
                start_time=start_time,
                end_time=end_time,
            )
        return {"scope": effective_scope, **metrics}

    def usage_distribution(
        self,
        field: str,
        *,
        username: str,
        role: str,
        scope: str,
        start_time: float,
        end_time: float,
        limit: int | None = None,
    ) -> list[tuple[str, int]]:
        """返回指定统计口径下的分布聚合。"""

        _effective_scope, username_filter = self.usage_scope(
            username=username,
            role=role,
            scope=scope,
        )
        with self._lock:
            return self.repository.usage_counts_by_field(
                field,
                username=username_filter,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
            )

    def create_feedback(
        self,
        *,
        user_id: str,
        username: str,
        usage_log_id: str | None,
        title: str,
        content: str,
        image_urls: tuple[str, ...],
        category: str = "answer",
    ) -> dict:
        """创建一条错题反馈记录。"""
        record = FeedbackRecord(
            feedback_id=secrets.token_hex(12),
            user_id=user_id,
            username=username,
            usage_log_id=usage_log_id,
            title=title,
            content=content.strip(),
            image_urls=tuple(url.strip() for url in image_urls if url.strip()),
            status="open",
            created_at=time.time(),
            category=category or "answer",
        )
        with self._lock:
            self.repository.save_feedback(record)
        return record.to_dict()

    def list_feedbacks(
        self,
        *,
        username: str | None = None,
        status: str = "",
        category: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """按用户过滤反馈列表。"""
        with self._lock:
            records = [
                item.to_dict()
                for item in self.repository.list_feedbacks(
                    username=username,
                    limit=max(1, min(int(limit) + max(0, int(offset)), 5000)),
                )
            ]
        if status:
            records = [item for item in records if item.get("status") == status]
        if category:
            records = [item for item in records if item.get("category") == category]
        return records[max(0, int(offset)) : max(0, int(offset)) + max(1, int(limit))]

    def count_feedbacks(
        self,
        *,
        username: str | None = None,
        status: str = "",
        category: str = "",
    ) -> int:
        """统计反馈数量。"""

        return len(
            self.list_feedbacks(
                username=username,
                status=status,
                category=category,
                limit=5000,
            )
        )

    def resolve_feedback(
        self,
        feedback_id: str,
        *,
        handled_by: str,
        status: str = "resolved",
        admin_note: str = "",
        corrected_answer: str = "",
        reward_points: int = 0,
    ) -> tuple[dict, int]:
        """处理用户反馈并返回奖励积分。

        奖励积分按反馈记录中的累计奖励值补差额，避免管理员重复保存时重复发放。
        """
        normalized_status = (status or "resolved").strip().lower()
        if normalized_status not in {"open", "processing", "resolved", "rejected"}:
            raise AuthError("INVALID_FEEDBACK_STATUS", "反馈状态不合法", http_status=400)
        normalized_reward_points = max(0, int(reward_points))
        now = time.time()
        with self._lock:
            existing = self.repository.get_feedback(feedback_id)
            if existing is None:
                raise AuthError("FEEDBACK_NOT_FOUND", "反馈不存在", http_status=404)
            stored_reward_points = (
                max(existing.reward_points, normalized_reward_points)
                if normalized_status == "resolved"
                else existing.reward_points
            )
            record = self.repository.update_feedback_resolution(
                feedback_id,
                status=normalized_status,
                admin_note=admin_note.strip(),
                corrected_answer=corrected_answer.strip(),
                reward_points=stored_reward_points,
                handled_by=handled_by,
                handled_at=now,
            )
            if record is None:
                raise AuthError("FEEDBACK_NOT_FOUND", "反馈不存在", http_status=404)
        granted = (
            max(0, record.reward_points - existing.reward_points)
            if normalized_status == "resolved"
            else 0
        )
        return record.to_dict(), granted

    def create_notification(
        self,
        *,
        user_id: str | None,
        level: str,
        category: str,
        title: str,
        content: str,
    ) -> dict:
        """创建一条消息中心通知。"""
        record = NotificationRecord(
            notification_id=secrets.token_hex(12),
            user_id=user_id,
            level=level or "info",
            category=category or "system",
            title=title,
            content=content,
            read=False,
            created_at=time.time(),
        )
        with self._lock:
            self.repository.save_notification(record)
        return record.to_dict()

    def list_notifications(
        self, *, user_id: str | None = None, status: str = "", limit: int = 20
    ) -> list[dict]:
        """列出消息中心通知。"""
        with self._lock:
            return [
                item.to_dict()
                for item in self.repository.list_notifications(
                    user_id=user_id, status=status, limit=limit
                )
            ]

    def mark_notification_read(
        self,
        notification_id: str,
        *,
        user_id: str | None = None,
        read: bool = True,
    ) -> dict:
        """标记单条消息的已读状态。"""
        with self._lock:
            record = self.repository.get_notification(notification_id)
            if record is None:
                raise AuthError("NOTIFICATION_NOT_FOUND", "消息不存在", http_status=404)
            if record.user_id not in {None, user_id}:
                raise AuthError("NOTIFICATION_FORBIDDEN", "无权操作该消息", http_status=403)
            record.read = bool(read)
            self.repository.save_notification(record)
            return record.to_dict()

    def mark_all_notifications_read(self, *, user_id: str | None = None) -> int:
        """批量标记消息为已读。"""
        count = 0
        with self._lock:
            for record in self.repository.list_notifications(
                user_id=user_id, status="unread", limit=500
            ):
                record.read = True
                self.repository.save_notification(record)
                count += 1
        return count

    def create_redeem_code(
        self,
        *,
        created_by: str,
        kind: str,
        points: int = 0,
        max_uses: int = 1,
        expires_at: float = 0.0,
    ) -> dict:
        """创建积分兑换码。"""

        if kind != "points":
            raise AuthError("INVALID_INPUT", "兑换码类型仅支持 points", http_status=400)
        record = RedeemCodeRecord(
            code_id=secrets.token_hex(12),
            code="rc_" + secrets.token_urlsafe(10),
            kind="points",
            points=max(0, int(points)),
            max_uses=max(1, int(max_uses)),
            used_uses=0,
            status="active",
            created_by=created_by,
            created_at=time.time(),
            expires_at=max(0.0, float(expires_at)),
        )
        with self._lock:
            self.repository.save_redeem_code(record)
        return record.to_dict()

    def list_redeem_codes(self) -> list[dict]:
        """列出全部兑换码。"""
        with self._lock:
            return [item.to_dict() for item in self.repository.list_redeem_codes()]

    def grant_wallet(
        self,
        *,
        user_id: str,
        username: str,
        created_by: str,
        kind: str,
        points: int = 0,
        source: str = "manual_credit",
        source_id: str | None = None,
    ) -> dict:
        """手动发放积分，并写入钱包流水。"""

        if kind != "points":
            raise AuthError("INVALID_INPUT", "钱包类型仅支持 points", http_status=400)
        with self._lock:
            order = WalletOrderRecord(
                order_id=secrets.token_hex(12),
                user_id=user_id,
                username=username,
                kind="points",
                points_delta=max(0, int(points)),
                source=source,
                source_id=source_id,
                status="completed",
                created_by=created_by,
                created_at=time.time(),
            )
            self.repository.save_wallet_order(order)
            return order.to_dict()

    def redeem_code(
        self,
        *,
        code: str,
        user_id: str,
        username: str,
        created_by: str,
    ) -> dict:
        """核销兑换码，并转换成标准钱包流水。"""
        with self._lock:
            redeem = self.repository.find_redeem_code_by_code((code or "").strip())
            if redeem is None:
                raise AuthError("REDEEM_CODE_NOT_FOUND", "兑换码不存在", http_status=404)
            now = time.time()
            if redeem.status != "active":
                raise AuthError("REDEEM_CODE_DISABLED", "兑换码不可用", http_status=400)
            if redeem.expires_at and redeem.expires_at < now:
                redeem.status = "expired"
                self.repository.save_redeem_code(redeem)
                raise AuthError("REDEEM_CODE_EXPIRED", "兑换码已过期", http_status=400)
            if redeem.used_uses >= redeem.max_uses:
                redeem.status = "exhausted"
                self.repository.save_redeem_code(redeem)
                raise AuthError("REDEEM_CODE_EXHAUSTED", "兑换码已用完", http_status=400)
            redeem.used_uses += 1
            if redeem.used_uses >= redeem.max_uses:
                redeem.status = "exhausted"
            self.repository.save_redeem_code(redeem)
            return self.grant_wallet(
                user_id=user_id,
                username=username,
                created_by=created_by,
                kind=redeem.kind,
                points=redeem.points,
                source="redeem_code",
                source_id=redeem.code_id,
            )

    def list_wallet_orders(
        self,
        *,
        username: str | None = None,
        kind: str = "",
        source: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """按用户过滤钱包流水。"""
        with self._lock:
            return [
                item.to_dict()
                for item in self.repository.list_wallet_orders(
                    username=username,
                    kind=kind,
                    source=source,
                    limit=limit,
                    offset=offset,
                )
            ]

    def list_wallet_changes(
        self,
        *,
        username: str | None = None,
        kind: str = "",
        source: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """列出钱包变更流水，供管理端分页查看。"""

        return self.list_wallet_orders(
            username=username,
            kind=kind,
            source=source,
            limit=limit,
            offset=offset,
        )

    def count_wallet_orders(
        self,
        *,
        username: str | None = None,
        kind: str = "",
        source: str = "",
    ) -> int:
        """统计钱包流水数量。"""

        return len(
            self.list_wallet_orders(
                username=username,
                kind=kind,
                source=source,
                limit=5000,
            )
        )

    def list_import_scripts(self) -> list[dict]:
        """列出全部导入脚本。"""
        builtin_scripts = []
        for template in load_import_script_templates():
            item = render_import_script(template, "")
            item["builtin"] = True
            item["status"] = "active"
            item["created_at"] = 0
            item["updated_at"] = 0
            builtin_scripts.append(item)
        with self._lock:
            custom_scripts = [item.to_dict() for item in self.repository.list_import_scripts()]
        return [*builtin_scripts, *custom_scripts]

    def get_import_script(self, script_id: str, *, base_url: str = "") -> dict | None:
        """读取单个导入脚本。"""
        try:
            template = get_import_script_template(script_id)
        except KeyError:
            template = None
        if template is not None:
            payload = render_import_script(template, base_url)
            payload["builtin"] = True
            payload["status"] = "active"
            payload["created_at"] = 0
            payload["updated_at"] = 0
            return payload
        with self._lock:
            record = self.repository.get_import_script(script_id)
            if record is None:
                return None
            payload = record.to_dict()
            if base_url:
                payload["base_url"] = base_url
            return payload

    def create_import_script(
        self,
        *,
        name: str,
        target: str,
        content: str = "",
        description: str = "",
        script_template: str = "",
        config_items: tuple[dict, ...] | list[dict] = (),
        requires_token: bool = True,
        tags: tuple[str, ...] | list[str] = (),
        is_default: bool = False,
        status: str = "active",
        created_by: str = "",
    ) -> dict:
        """创建并保存导入脚本模板。"""
        now = time.time()
        script_content = content or script_template
        record = ImportScriptRecord(
            script_id=secrets.token_hex(12),
            name=(name or "导入脚本").strip(),
            integration_id=None,
            token_id=None,
            target=(target or "ocs").strip(),
            content=script_content,
            status=(status or "active").strip(),
            created_at=now,
            updated_at=now,
            description=description.strip(),
            requires_token=bool(requires_token),
            tags=tuple(str(item).strip() for item in tags if str(item).strip()),
            builtin=False,
            is_default=bool(is_default),
            ocs_config=tuple(dict(item) for item in config_items),
        )
        with self._lock:
            self.repository.save_import_script(record)
        return record.to_dict()

    def generate_import_script(
        self,
        *,
        name: str,
        token_id: str | None,
        target: str,
        include_test_snippet: bool,
    ) -> dict:
        """生成并保存导入脚本。"""
        token = self.repository.get_token(token_id) if token_id else None
        content_lines = [
            f"// {name or '导入脚本'}",
            f"// target: {target}",
        ]
        if token is not None:
            content_lines.append(f"const tokenId = '{token.token_id}';")
            content_lines.append(f"// token: {token.key_mask}")
        content_lines.append("export const config = { enabled: true };")
        if include_test_snippet:
            content_lines.append(
                "export function testConnection() { return Promise.resolve(true); }"
            )
        content = "\n".join(content_lines)
        now = time.time()
        record = ImportScriptRecord(
            script_id=secrets.token_hex(12),
            name=(name or "导入脚本").strip(),
            integration_id=None,
            token_id=token_id,
            target=(target or "ocs").strip(),
            content=content,
            status="active",
            created_at=now,
            updated_at=now,
            description=f"{name or '导入脚本'} 自动生成模板",
            requires_token=True,
            tags=("generated", target or "ocs"),
            builtin=False,
            is_default=False,
        )
        with self._lock:
            self.repository.save_import_script(record)
        return record.to_dict()

    def delete_import_script(self, script_id: str) -> bool:
        """删除导入脚本。"""
        try:
            get_import_script_template(script_id)
        except KeyError:
            pass
        else:
            raise AuthError("BUILTIN_SCRIPT_READONLY", "内置导入脚本不能删除", http_status=400)
        with self._lock:
            removed = self.repository.delete_import_script(script_id)
        if not removed:
            raise AuthError("SCRIPT_NOT_FOUND", "导入脚本不存在", http_status=404)
        return True

    def list_llm_models(self, *, reveal_secret: bool = False) -> list[dict]:
        """列出所有大模型配置。"""

        return llm_config_service.list_llm_models(
            self.repository,
            self._lock,
            reveal_secret=reveal_secret,
        )

    def get_llm_model(self, model_id: str, *, reveal_secret: bool = False) -> dict:
        """读取单个大模型配置。"""

        return llm_config_service.get_llm_model(
            self.repository,
            self._lock,
            model_id,
            reveal_secret=reveal_secret,
        )

    def create_llm_model(
        self,
        *,
        name: str,
        base_url: str,
        model: str,
        api_key: str = "",
        role: str = "backup",
        priority: int = 100,
        stream: bool = True,
        max_completion_tokens: int = 700,
        timeout_seconds: float = 30.0,
        status: str = "active",
    ) -> dict:
        """新增大模型配置。"""

        return llm_config_service.create_llm_model(
            self.repository,
            self._lock,
            name=name,
            base_url=base_url,
            model=model,
            api_key=api_key,
            role=role,
            priority=priority,
            stream=stream,
            max_completion_tokens=max_completion_tokens,
            timeout_seconds=timeout_seconds,
            status=status,
        )

    def update_llm_model(self, model_id: str, values: dict) -> dict:
        """更新大模型配置。"""

        return llm_config_service.update_llm_model(
            self.repository,
            self._lock,
            model_id,
            values,
        )

    def delete_llm_model(self, model_id: str) -> bool:
        """删除大模型配置。"""

        return llm_config_service.delete_llm_model(self.repository, self._lock, model_id)

    def active_llm_models(self):
        """返回可参与主备链的大模型配置。"""

        return llm_config_service.active_llm_models(self.repository, self._lock)

    def test_llm_model(self, model_id: str) -> dict:
        """测试指定大模型配置的连通性与接口解析。"""
        from ..llm.providers.openai_compatible import OpenAICompatibleProvider
        from ..models import QuestionQuery

        model_dict = self.get_llm_model(model_id, reveal_secret=True)
        provider = OpenAICompatibleProvider(
            base_url=model_dict["base_url"],
            model=model_dict["model"],
            api_key=model_dict["api_key"] or None,
            stream=model_dict["stream"],
            max_completion_tokens=model_dict["max_completion_tokens"],
            timeout_seconds=model_dict["timeout_seconds"],
            model_id=model_id,
            display_name=model_dict["name"],
        )

        query = QuestionQuery(
            title="请验证接口，这道题的答案是: A。此为系统连通性测试，请输出: A",
            options=("A", "B"),
            question_type="single",
        )

        t0 = time.time()
        try:
            res = provider.answer(query)
            elapsed = (time.time() - t0) * 1000
            return {
                "ok": True,
                "elapsed_ms": elapsed,
                "candidate_answer": res.candidate_answer,
                "answer_text": res.answer_text,
                "explanation": res.explanation,
                "confidence": res.confidence,
            }
        except Exception as exc:
            elapsed = (time.time() - t0) * 1000
            return {
                "ok": False,
                "elapsed_ms": elapsed,
                "error": str(exc),
            }

    def save_llm_call_trace(self, payload: dict) -> None:
        """落库一条 LLM 调用追溯，失败不影响答题主流程。"""

        try:
            record = LlmCallTraceRecord(
                trace_id=str(payload.get("trace_id") or secrets.token_hex(12)),
                request_id=str(payload.get("request_id") or ""),
                phase=str(payload.get("phase") or ""),
                model_id=str(payload.get("model_id") or payload.get("model_name") or ""),
                model_name=str(payload.get("model_name") or payload.get("model_id") or ""),
                base_url=str(payload.get("base_url") or ""),
                provider=str(payload.get("provider") or ""),
                question_title=str(payload.get("question_title") or ""),
                prompt=str(payload.get("prompt") or payload.get("question_title") or ""),
                evidence=json.dumps(payload.get("evidence") or [], ensure_ascii=False),
                response_text=str(payload.get("response_text") or payload.get("response") or ""),
                candidate_answer=(
                    str(payload["candidate_answer"]) if payload.get("candidate_answer") else None
                ),
                confidence=float(payload.get("confidence") or 0.0),
                ok=bool(payload.get("ok", True)),
                error=str(payload.get("error") or ""),
                elapsed_ms=float(payload.get("elapsed_ms") or payload.get("latency_ms") or 0.0),
                created_at=float(payload.get("created_at") or time.time()),
            )
            self.repository.save_llm_call_trace(record)
        except Exception:
            return

    def list_llm_call_traces(
        self,
        *,
        request_id: str = "",
        model_id: str = "",
        phase: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """按条件分页读取 LLM 调用追溯。"""

        with self._lock:
            return [
                item.to_dict()
                for item in self.repository.list_llm_call_traces(
                    request_id=request_id,
                    model_id=model_id,
                    phase=phase,
                    limit=limit,
                    offset=offset,
                )
            ]

    def count_llm_call_traces(
        self,
        *,
        request_id: str = "",
        model_id: str = "",
        phase: str = "",
    ) -> int:
        """统计 LLM 调用追溯数量。"""

        with self._lock:
            return self.repository.count_llm_call_traces(
                request_id=request_id,
                model_id=model_id,
                phase=phase,
            )

    def llm_call_stats(self) -> list[dict]:
        """按模型聚合 LLM 调用统计。"""

        with self._lock:
            return self.repository.llm_call_stats()

    def project_update_status(self, *, refresh_remote: bool = False) -> dict:
        """返回项目更新状态。

        为避免在 Web 请求里执行不透明的远程 Git 操作，当前只提供安全状态占位。
        """

        return {
            "available": False,
            "refresh_remote": bool(refresh_remote),
            "current_version": "local",
            "latest_version": "local",
            "message": "当前部署未配置在线更新源，请通过代码仓库和部署流程更新。",
        }

    def apply_project_update(self) -> dict:
        """拒绝在运行时直接执行项目更新。"""

        raise AuthError(
            "PROJECT_UPDATE_UNCONFIGURED",
            "当前部署未配置安全的在线更新流程",
            http_status=400,
        )

    def list_role_permissions(self) -> list[dict]:
        """列出角色权限矩阵。"""
        with self._lock:
            existing = {item.role_id: item for item in self.repository.get_role_permissions()}
            result: list[RolePermissionRecord] = []
            allowed = self.allowed_role_permissions()
            for role_id, permissions in DEFAULT_ROLE_PERMISSIONS.items():
                record = existing.get(
                    role_id,
                    RolePermissionRecord(
                        role_id=role_id, permissions=permissions, updated_at=0.0
                    ),
                )
                result.append(
                    RolePermissionRecord(
                        role_id=record.role_id,
                        permissions=tuple(item for item in record.permissions if item in allowed),
                        updated_at=record.updated_at,
                    )
                )
            return [item.to_dict() for item in result]

    @staticmethod
    def allowed_role_permissions() -> set[str]:
        """返回当前系统真实生效的权限白名单。"""

        return {item for values in DEFAULT_ROLE_PERMISSIONS.values() for item in values}

    def get_role_permissions(self, role_id: str) -> dict:
        """读取单个角色的权限矩阵。"""
        items = {item["role_id"]: item for item in self.list_role_permissions()}
        record = items.get(role_id)
        if record is None:
            raise AuthError("ROLE_NOT_FOUND", "角色不存在", http_status=404)
        return record

    def role_permissions(self, role_id: str) -> set[str]:
        """返回指定角色的权限集合。"""

        record = self.get_role_permissions(role_id)
        return set(record.get("permissions") or ())

    def set_role_permissions(self, role_id: str, permissions: tuple[str, ...]) -> dict:
        """更新角色权限矩阵。"""
        if role_id not in DEFAULT_ROLE_PERMISSIONS:
            raise AuthError("ROLE_NOT_FOUND", "角色不存在", http_status=404)
        normalized = tuple(str(item).strip() for item in permissions if str(item).strip())
        invalid = sorted(set(normalized) - self.allowed_role_permissions())
        if invalid:
            raise AuthError(
                "INVALID_PERMISSION",
                f"权限项不存在: {', '.join(invalid)}",
                http_status=400,
            )
        with self._lock:
            self.repository.set_role_permissions(
                role_id,
                normalized,
                time.time(),
            )
        return self.get_role_permissions(role_id)

    def dashboard_rankings(
        self,
        *,
        days: int = 1,
        limit: int = 10,
        dimension: str = "provider",
        username: str,
        role: str = "user",
        scope: str = "self",
    ) -> list[dict]:
        """构造工作台排行统计。"""
        start_time, end_time = recent_day_range(days)
        normalized_dimension = normalize_ranking_dimension(dimension)
        rows = self.usage_distribution(
            normalized_dimension,
            username=username,
            role=role,
            scope=scope,
            start_time=start_time,
            end_time=end_time,
            limit=max(1, min(limit, 50)),
        )
        return [
            {"rank": index + 1, "label": label, "count": count}
            for index, (label, count) in enumerate(rows)
        ]

    def dashboard_workbench(
        self,
        *,
        user_id: str,
        username: str,
        points: int,
        role: str = "user",
        scope: str = "self",
    ) -> dict:
        """构造工作台首页聚合数据。"""
        today_start, today_end = current_local_day_range()
        effective_scope, _ = self.usage_scope(username=username, role=role, scope=scope)
        overview = self.usage_overview(
            username=username,
            role=role,
            scope=effective_scope,
            start_time=today_start,
            end_time=today_end,
        )
        total_count = int(overview["total_count"])
        success_rate = (
            100.0
            if total_count == 0
            else round(float(overview["success_count"]) / total_count * 100, 1)
        )
        avg_response = round(float(overview["avg_elapsed_ms"]) / 1000, 2) if total_count else 0.0
        distribution = {
            key: value
            for key, value in self.usage_distribution(
                "question_type",
                username=username,
                role=role,
                scope=effective_scope,
                start_time=today_start,
                end_time=today_end,
            )
        }
        notifications = self.list_notifications(user_id=user_id, limit=5)
        wallet = self.wallet_summary(user_id=user_id, username=username, points=points)
        is_admin = role in {"admin", "superadmin"}
        ranking_preview = self.dashboard_rankings(
            days=1,
            limit=5,
            dimension="provider",
            username=username,
            role=role,
            scope=effective_scope,
        )
        quick_actions = (
            [
                {
                    "key": "create_api_key",
                    "label": "创建API Key",
                    "path": "/tokens",
                    "action": "navigate",
                    "requires_role": "user",
                },
                {
                    "key": "copy_import_script",
                    "label": "复制导入脚本",
                    "path": "/tokens",
                    "action": "copy_import_script",
                    "requires_role": "user",
                },
                {
                    "key": "interface_status",
                    "label": "接口状态",
                    "path": "/status",
                    "action": "navigate",
                    "requires_role": "user",
                },
                {
                    "key": "usage_logs",
                    "label": "使用记录",
                    "path": "/usage-logs",
                    "action": "navigate",
                    "requires_role": "user",
                },
                {
                    "key": "wallet",
                    "label": "我的钱包",
                    "path": "/wallet",
                    "action": "navigate",
                    "requires_role": "user",
                },
            ]
            if not is_admin
            else [
                {
                    "key": "create_api_key",
                    "label": "创建API Key",
                    "path": "/tokens",
                    "action": "navigate",
                    "requires_role": "user",
                },
                {
                    "key": "generate_script",
                    "label": "生成导入脚本",
                    "path": "/import-scripts",
                    "action": "navigate",
                    "requires_role": "admin",
                },
                {
                    "key": "interface_status",
                    "label": "接口状态",
                    "path": "/status",
                    "action": "navigate",
                    "requires_role": "user",
                },
            ]
        )
        return {
            "scope": effective_scope,
            "hero": {
                "title": "答题接入平台 全新上线",
                "subtitle": "更稳定的接口服务，更便捷的接入体验，助力平台高效接入答题能力",
                "badges": ["高可用保障", "快速接入", "安全合规"],
            },
            "quick_actions": quick_actions,
            "overview": {
                "today_calls": total_count,
                "success_rate": success_rate,
                "avg_response_seconds": avg_response,
                "remaining_points": wallet["points"],
            },
            "trend": {"days": 7, "items": self._usage_trend(username, role, effective_scope, 7)},
            "question_distribution": distribution,
            "ranking_preview": ranking_preview,
            "notifications_preview": notifications,
            "service_status": self._dashboard_service_status(),
        }

    def dashboard_summary(
        self,
        *,
        username: str,
        role: str,
        scope: str,
        days: int = 30,
    ) -> dict:
        """返回工作台摘要统计。"""

        start_time, end_time = recent_day_range(days)
        overview = self.usage_overview(
            username=username,
            role=role,
            scope=scope,
            start_time=start_time,
            end_time=end_time,
        )
        effective_scope = str(overview["scope"])
        return {
            "scope": effective_scope,
            "days": max(1, min(days, 365)),
            "points_used": int(overview["points_used"]),
            "query_count": int(overview["total_count"]),
            "resolution_modes": {
                key: value
                for key, value in self.usage_distribution(
                    "resolution_mode",
                    username=username,
                    role=role,
                    scope=effective_scope,
                    start_time=start_time,
                    end_time=end_time,
                )
            },
            "trend": self._usage_summary_trend(username, role, effective_scope, days),
        }

    def usage_audit(self, date_text: str = "") -> dict:
        """返回指定自然日的调用对账结果。"""

        date_label, start_time, end_time = local_day_range_from_text(date_text)
        with self._lock:
            usage_log_count = self.repository.count_usage_logs(
                start_time=start_time,
                end_time=end_time,
            )
            resolution_modes = {
                key: value
                for key, value in self.repository.usage_counts_by_field(
                    "resolution_mode",
                    start_time=start_time,
                    end_time=end_time,
                )
            }
            token_totals = self.repository.token_counter_totals()
        query_event_count, malformed_lines = count_query_events_for_date(date_label)
        gaps = [
            "api_tokens 仅保留累计 usage_count/quota_used，无法直接还原指定自然日的独立 token 日计数。"
        ]
        return {
            "date": date_label,
            "timezone": "Asia/Shanghai",
            "evidence_status": "partial",
            "gaps": gaps,
            "usage_logs": {
                "count": usage_log_count,
                "resolution_modes": resolution_modes,
            },
            "api_tokens": {
                **token_totals,
                "daily_count_available": False,
            },
            "runtime_logs": {
                "query_event_count": query_event_count,
                "malformed_line_count": malformed_lines,
            },
            "diff": {
                "usage_logs_vs_runtime_queries": usage_log_count - query_event_count,
            },
        }

    def _usage_trend(self, username: str, role: str, scope: str, days: int) -> list[dict]:
        effective_scope, username_filter = self.usage_scope(
            username=username,
            role=role,
            scope=scope,
        )
        del effective_scope
        items: list[dict] = []
        for label, start_time, end_time in day_windows(days):
            with self._lock:
                count = self.repository.count_usage_logs(
                    username=username_filter,
                    start_time=start_time,
                    end_time=end_time,
                )
            items.append({"date": label[5:], "count": count})
        return items

    def _usage_summary_trend(self, username: str, role: str, scope: str, days: int) -> list[dict]:
        effective_scope, username_filter = self.usage_scope(
            username=username,
            role=role,
            scope=scope,
        )
        del effective_scope
        items: list[dict] = []
        for label, start_time, end_time in day_windows(days):
            with self._lock:
                overview = self.repository.usage_overview(
                    username=username_filter,
                    start_time=start_time,
                    end_time=end_time,
                )
            items.append(
                {
                    "date": label,
                    "query_count": int(overview["total_count"]),
                    "points_used": int(overview["points_used"]),
                }
            )
        return items

    def _dashboard_service_status(self) -> dict[str, str]:
        """返回工作台服务状态摘要。"""

        runtime_config = self.get_llm_runtime_config()
        active_models = self.active_llm_models()
        primary_model = next((item for item in active_models if item.role == "primary"), None)
        first_model = primary_model or (active_models[0] if active_models else None)
        return {
            "api": "ok",
            "search_provider": str(runtime_config.get("web_search_provider") or ""),
            "llm_model": first_model.model if first_model else "",
        }

    def get_system_config(self) -> dict:
        """读取系统运行配置，并对敏感项只暴露是否已配置。"""
        with self._lock:
            raw = {key: SYSTEM_CONFIG_DEFAULTS.get(key, "") for key in SYSTEM_CONFIG_KEYS}
            raw.update(self.repository.get_settings("system_config", keys=set(SYSTEM_CONFIG_KEYS)))
            payload: dict[str, str | bool] = {}
            for key, value in raw.items():
                if key in SYSTEM_CONFIG_SECRET_KEYS:
                    payload[f"{key}_configured"] = bool(str(value).strip())
                else:
                    payload[key] = value
            return payload

    def get_llm_runtime_config(self, *, reveal_secret: bool = False) -> dict:
        """读取统一后的 LLM 答题运行时配置。"""

        llm_config_service.migrate_legacy_llm_settings(
            self.repository,
            default_system_config=self.default_system_config(),
        )
        return llm_config_service.get_llm_runtime_config(
            self.repository,
            self._lock,
            reveal_secret=reveal_secret,
        )

    def set_llm_runtime_config(self, values: dict[str, object]) -> dict:
        """更新统一后的 LLM 答题运行时配置。"""

        llm_config_service.migrate_legacy_llm_settings(
            self.repository,
            default_system_config=self.default_system_config(),
        )
        return llm_config_service.set_llm_runtime_config(
            self.repository,
            self._lock,
            values,
        )

    def llm_runtime_env(self) -> dict[str, str]:
        """把统一后的 LLM 答题配置转换为环境变量。"""

        raw = self.repository.get_settings(
            "llm_runtime_config",
            keys=set(LLM_RUNTIME_CONFIG_KEYS),
        )
        return {
            env_key: str(raw.get(config_key) or "").strip()
            for config_key, env_key in LLM_RUNTIME_ENV_MAP.items()
            if str(raw.get(config_key) or "").strip()
        }

    def set_system_config(self, values: dict[str, object]) -> dict:
        """更新系统运行配置。"""
        normalized: dict[str, str] = {}
        for key, value in values.items():
            if key not in SYSTEM_CONFIG_KEYS:
                raise AuthError("INVALID_INPUT", f"不支持的系统配置项: {key}", http_status=400)
            text = "" if value is None else str(value).strip()
            if key in SYSTEM_CONFIG_BOOLEAN_KEYS:
                text = (
                    "false" if text.lower() in {"0", "false", "no", "off", "disabled"} else "true"
                )
            elif key.endswith("_points") or key == "answer_retry_times":
                try:
                    parsed = max(0, int(text or "0"))
                except ValueError as exc:
                    raise AuthError(
                        "INVALID_INPUT", f"{key} 必须为非负整数", http_status=400
                    ) from exc
                if key == "answer_retry_times":
                    parsed = min(parsed, 10)
                text = str(parsed)
            normalized[key] = text
        with self._lock:
            self.repository.set_settings("system_config", normalized)
        return self.get_system_config()

    def runtime_env(self) -> dict[str, str]:
        """把平台配置转换为运行时环境变量映射。"""
        raw = self.repository.get_settings("system_config", keys=set(SYSTEM_CONFIG_KEYS))
        env = {
            env_key: str(raw.get(config_key) or "").strip()
            for config_key, env_key in SYSTEM_CONFIG_ENV_MAP.items()
            if str(raw.get(config_key) or "").strip()
        }
        env.update(self.llm_runtime_env())
        return env


def normalize_ranking_dimension(value: str) -> str:
    """把排行维度收敛到受支持集合。"""

    normalized = (value or "provider").strip().lower()
    if normalized in {"provider", "question_type", "username"}:
        return normalized
    return "provider"


def local_day_range_from_text(date_text: str = "") -> tuple[str, float, float]:
    """把日期文本转换为上海时区自然日范围。"""

    if date_text.strip():
        target = datetime.strptime(date_text.strip(), "%Y-%m-%d").replace(tzinfo=LOCAL_TIMEZONE)
    else:
        now = datetime.now(LOCAL_TIMEZONE)
        target = datetime(now.year, now.month, now.day, tzinfo=LOCAL_TIMEZONE)
    start = datetime(target.year, target.month, target.day, tzinfo=LOCAL_TIMEZONE)
    end = start + timedelta(days=1)
    return start.strftime("%Y-%m-%d"), start.timestamp(), end.timestamp()


def local_day_window_from_dates(
    start_date: str = "",
    end_date: str = "",
) -> tuple[float | None, float | None]:
    """把日期区间文本转换为上海时区自然日的闭开区间。"""

    normalized_start = start_date.strip()
    normalized_end = end_date.strip()
    start_time: float | None = None
    end_time: float | None = None
    start_label = ""
    end_label = ""

    if normalized_start:
        start_label, start_time, _ignored = local_day_range_from_text(normalized_start)
    if normalized_end:
        end_label, _ignored, end_time = local_day_range_from_text(normalized_end)

    if start_time is not None and end_time is not None and start_label > end_label:
        raise ValueError("start_date must be on or before end_date")
    return start_time, end_time


def current_local_day_range() -> tuple[float, float]:
    """返回当前上海自然日的时间戳范围。"""

    _, start_time, end_time = local_day_range_from_text("")
    return start_time, end_time


def recent_day_range(days: int) -> tuple[float, float]:
    """返回最近 N 个自然日的范围，包含今天。"""

    normalized_days = max(1, min(int(days), 365))
    today_label, _today_start, today_end = local_day_range_from_text("")
    start_day = (
        datetime.strptime(today_label, "%Y-%m-%d").replace(tzinfo=LOCAL_TIMEZONE)
        - timedelta(days=normalized_days - 1)
    )
    return start_day.timestamp(), today_end


def day_windows(days: int) -> list[tuple[str, float, float]]:
    """返回最近 N 个自然日的标签和边界。"""

    normalized_days = max(1, min(int(days), 365))
    start_time, _end_time = recent_day_range(normalized_days)
    start_day = datetime.fromtimestamp(start_time, LOCAL_TIMEZONE)
    windows: list[tuple[str, float, float]] = []
    for offset in range(normalized_days):
        day_start = start_day + timedelta(days=offset)
        day_end = day_start + timedelta(days=1)
        windows.append((day_start.strftime("%Y-%m-%d"), day_start.timestamp(), day_end.timestamp()))
    return windows


def count_query_events_for_date(date_label: str) -> tuple[int, int]:
    """统计运行日志中指定自然日的 query 事件数量。"""

    path = log_path()
    if not path.exists():
        return 0, 0
    query_count = 0
    malformed_lines = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                malformed_lines += 1
                if f'"ts": "{date_label}' in line and '"event": "query"' in line:
                    query_count += 1
                continue
            if str(payload.get("ts") or "")[:10] != date_label:
                continue
            if str(payload.get("event") or "") == "query":
                query_count += 1
    return query_count, malformed_lines


def normalized_confidence(value: object) -> float:
    """把用户配置的置信度阈值归一化到 0 到 1。"""

    try:
        return min(max(float(str(value or "0")), 0.0), 1.0)
    except (TypeError, ValueError):
        return 0.0

"""平台业务服务。"""

from __future__ import annotations

import json
import math
import secrets
import time
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from ..auth import AuthError
from ..auth.email_verification import normalize_email, smtp_settings_from_config
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
    AnnouncementRecord,
    ApiTokenRecord,
    FeedbackRecord,
    ImportScriptRecord,
    NotificationReadReceiptRecord,
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
from .llm_service import PlatformLlmService


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
        "announcements:read",
        "announcements:write",
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
        "announcements:read",
        "announcements:write",
    ),
    "user": ("dashboard:self", "tokens:self", "feedback:self"),
}

LOCAL_TIMEZONE = ZoneInfo("Asia/Shanghai")
ANNOUNCEMENT_LEVELS = {"info", "success", "warning", "danger"}
ANNOUNCEMENT_AUDIENCES = {"all", "user", "admin", "superadmin"}
ANNOUNCEMENT_STATUSES = {"draft", "published", "archived"}


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
        self.llm_service = PlatformLlmService(self.repository, self._lock)

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
        if resolution_mode == "input_anomaly":
            return 0
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

    def is_email_verification_enabled(self) -> bool:
        """返回注册邮箱验证是否启用。"""

        raw = self.get_system_config().get("email_verification_enabled", "false")
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
        question_id: str | None = None,
        source_name: str = "",
        source_type: str = "",
        source_id: str = "",
        source_url: str = "",
        context_json: str = "{}",
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
            question_id=question_id,
            source_name=source_name.strip(),
            source_type=source_type.strip(),
            source_id=source_id.strip(),
            source_url=source_url.strip(),
            context_json=context_json,
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
        usage_record = None
        if usage_log_id:
            with self._lock:
                usage_record = self.repository.get_usage_log(usage_log_id)
            if usage_record and usage_record.user_id != user_id:
                usage_record = None
        question_title = usage_record.title if usage_record else ""
        answer_snapshot = usage_record.answer if usage_record else None
        context: dict[str, object] = {
            "usage_log_id": usage_log_id or "",
            "submitted_title": title.strip(),
            "submitted_content": content.strip(),
        }
        if usage_record:
            context.update(
                {
                    "username": str(usage_record.username),
                    "question_title": str(usage_record.title),
                    "question_type": str(usage_record.question_type),
                    "answer_snapshot": str(usage_record.answer or ""),
                    "resolution_mode": str(usage_record.resolution_mode),
                    "confidence": float(usage_record.confidence or 0.0),
                    "request_id": str(usage_record.request_id),
                    "source_name": str(usage_record.source_name),
                    "source_type": str(usage_record.source_type),
                    "source_id": str(usage_record.source_id),
                    "source_url": str(usage_record.source_url),
                }
            )
        record = FeedbackRecord(
            feedback_id=secrets.token_hex(12),
            user_id=user_id,
            username=username,
            usage_log_id=usage_log_id,
            title=title.strip() or ("题目反馈" if usage_record else "反馈"),
            content=content.strip(),
            image_urls=tuple(url.strip() for url in image_urls if url.strip()),
            status="open",
            created_at=time.time(),
            category=category or "answer",
            question_id=usage_record.question_id if usage_record else None,
            question_title=question_title,
            question_type=usage_record.question_type if usage_record else "",
            answer_snapshot=answer_snapshot,
            resolution_mode=usage_record.resolution_mode if usage_record else "",
            confidence=usage_record.confidence if usage_record else 0.0,
            request_id=usage_record.request_id if usage_record else "",
            source_name=usage_record.source_name if usage_record else "",
            source_type=usage_record.source_type if usage_record else "",
            source_id=usage_record.source_id if usage_record else "",
            source_url=usage_record.source_url if usage_record else "",
            context_json=json.dumps(context, ensure_ascii=False, sort_keys=True),
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

    def notification_center(
        self,
        *,
        user_id: str,
        role: str,
        status: str = "",
        source: str = "",
        limit: int = 20,
    ) -> dict:
        """聚合当前用户可见的公告和消息通知。"""

        normalized_limit = max(1, min(int(limit or 20), 100))
        normalized_source = (source or "").strip()
        if normalized_source not in {"", "announcement", "notification"}:
            raise AuthError("INVALID_SOURCE", "通知来源无效", http_status=400)
        normalized_status = (status or "").strip()
        if normalized_status not in {"", "read", "unread"}:
            raise AuthError("INVALID_STATUS", "通知状态无效", http_status=400)

        with self._lock:
            items = self.build_notification_center_items(
                user_id=user_id,
                role=role,
                source=normalized_source,
                limit=500,
            )

        unread_count = sum(1 for item in items if not item["read"])
        if normalized_status == "read":
            items = [item for item in items if item["read"]]
        elif normalized_status == "unread":
            items = [item for item in items if not item["read"]]
        return {
            "items": items[:normalized_limit],
            "unread_count": unread_count,
            "total": len(items),
        }

    def mark_notification_center_item_read(
        self,
        *,
        user_id: str,
        role: str,
        source: str,
        item_id: str,
    ) -> dict:
        """按通知中心来源标记单条公告或消息为已读。"""

        normalized_source = (source or "").strip()
        with self._lock:
            if normalized_source == "announcement":
                announcement_record = self.repository.get_announcement(item_id)
                now = time.time()
                if announcement_record is None or not self.announcement_visible_for_role(
                    announcement_record, role=role, now=now
                ):
                    raise AuthError("ANNOUNCEMENT_NOT_FOUND", "公告不存在", http_status=404)
                self.repository.save_notification_read_receipt(
                    NotificationReadReceiptRecord(
                        user_id=user_id,
                        source="announcement",
                        item_id=announcement_record.announcement_id,
                        item_updated_at=announcement_record.updated_at,
                        read_at=now,
                    )
                )
            elif normalized_source == "notification":
                notification_record = self.repository.get_notification(item_id)
                if notification_record is None:
                    raise AuthError("NOTIFICATION_NOT_FOUND", "消息不存在", http_status=404)
                if notification_record.user_id not in {None, user_id}:
                    raise AuthError("NOTIFICATION_FORBIDDEN", "无权操作该消息", http_status=403)
                if notification_record.user_id is None:
                    self.repository.save_notification_read_receipt(
                        NotificationReadReceiptRecord(
                            user_id=user_id,
                            source="notification",
                            item_id=notification_record.notification_id,
                            item_updated_at=notification_record.created_at,
                            read_at=time.time(),
                        )
                    )
                else:
                    notification_record.read = True
                    self.repository.save_notification(notification_record)
            else:
                raise AuthError("INVALID_SOURCE", "通知来源无效", http_status=400)

            items = self.build_notification_center_items(
                user_id=user_id,
                role=role,
                source=normalized_source,
                limit=100,
            )
        for item in items:
            if item["source"] == normalized_source and item["item_id"] == item_id:
                return item
        raise AuthError("NOTIFICATION_CENTER_ITEM_NOT_FOUND", "通知不存在", http_status=404)

    def mark_all_notification_center_read(self, *, user_id: str, role: str) -> int:
        """批量标记通知中心的可见未读内容。"""

        with self._lock:
            items = self.build_notification_center_items(
                user_id=user_id,
                role=role,
                source="",
                limit=500,
            )
            unread_items = [item for item in items if not item["read"]]
            for item in unread_items:
                if item["source"] == "announcement":
                    self.repository.save_notification_read_receipt(
                        NotificationReadReceiptRecord(
                            user_id=user_id,
                            source="announcement",
                            item_id=item["item_id"],
                            item_updated_at=float(item["updated_at"] or 0.0),
                            read_at=time.time(),
                        )
                    )
                else:
                    record = self.repository.get_notification(str(item["item_id"]))
                    if record is None:
                        continue
                    if record.user_id is None:
                        self.repository.save_notification_read_receipt(
                            NotificationReadReceiptRecord(
                                user_id=user_id,
                                source="notification",
                                item_id=record.notification_id,
                                item_updated_at=record.created_at,
                                read_at=time.time(),
                            )
                        )
                    else:
                        record.read = True
                        self.repository.save_notification(record)
        return len(unread_items)

    def build_notification_center_items(
        self, *, user_id: str, role: str, source: str, limit: int
    ) -> list[dict]:
        """构建通知中心统一列表，保持公告和通知各自的存储语义。"""

        items: list[dict] = []
        keys: list[tuple[str, str]] = []
        notification_records: list[NotificationRecord] = []
        announcement_records: list[AnnouncementRecord] = []
        if source in {"", "notification"}:
            notification_records = self.repository.list_notifications(
                user_id=user_id, limit=max(1, min(limit, 500))
            )
            keys.extend(("notification", item.notification_id) for item in notification_records)
        if source in {"", "announcement"}:
            announcement_records = self.repository.list_active_announcements(
                role=role, now=time.time(), limit=max(1, min(limit, 500))
            )
            keys.extend(("announcement", item.announcement_id) for item in announcement_records)

        receipts = self.repository.list_notification_read_receipts(
            user_id=user_id,
            keys=tuple(keys),
        )

        for notification_record in notification_records:
            item_updated_at = float(notification_record.created_at or 0.0)
            receipt = receipts.get(("notification", notification_record.notification_id))
            read = bool(notification_record.read) if notification_record.user_id else self.receipt_covers(
                receipt, item_updated_at
            )
            items.append(
                {
                    "item_id": notification_record.notification_id,
                    "source": "notification",
                    "level": notification_record.level,
                    "category": notification_record.category,
                    "title": notification_record.title,
                    "content": notification_record.content,
                    "read": read,
                    "pinned": False,
                    "created_at": item_updated_at,
                    "updated_at": item_updated_at,
                    "expires_at": 0.0,
                }
            )

        for announcement_record in announcement_records:
            item_updated_at = float(announcement_record.updated_at or 0.0)
            receipt = receipts.get(("announcement", announcement_record.announcement_id))
            created_at = float(
                announcement_record.published_at
                or announcement_record.updated_at
                or announcement_record.created_at
            )
            items.append(
                {
                    "item_id": announcement_record.announcement_id,
                    "source": "announcement",
                    "level": announcement_record.level,
                    "category": "announcement",
                    "title": announcement_record.title,
                    "content": announcement_record.content,
                    "read": self.receipt_covers(receipt, item_updated_at),
                    "pinned": bool(announcement_record.pinned),
                    "created_at": created_at,
                    "updated_at": item_updated_at,
                    "expires_at": float(announcement_record.ends_at or 0.0),
                }
            )

        items.sort(key=lambda item: (not item["pinned"], -float(item["created_at"] or 0.0)))
        return items[: max(1, min(limit, 500))]

    @staticmethod
    def receipt_covers(
        receipt: NotificationReadReceiptRecord | None, item_updated_at: float
    ) -> bool:
        return bool(receipt and receipt.item_updated_at >= item_updated_at)

    @staticmethod
    def announcement_visible_for_role(
        record: AnnouncementRecord, *, role: str, now: float
    ) -> bool:
        return (
            record.status == "published"
            and record.audience in {"all", role}
            and (record.starts_at <= 0 or record.starts_at <= now)
            and (record.ends_at <= 0 or record.ends_at > now)
        )

    def create_announcement(
        self,
        *,
        title: str,
        content: str,
        level: str = "info",
        audience: str = "all",
        status: str = "draft",
        pinned: bool = False,
        starts_at: float = 0.0,
        ends_at: float = 0.0,
        created_by: str = "",
    ) -> dict:
        """创建系统公告。"""

        now = time.time()
        normalized = self._normalize_announcement_payload(
            title=title,
            content=content,
            level=level,
            audience=audience,
            status=status,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        record = AnnouncementRecord(
            announcement_id=secrets.token_hex(12),
            title=normalized["title"],
            content=normalized["content"],
            level=normalized["level"],
            audience=normalized["audience"],
            status=normalized["status"],
            pinned=bool(pinned),
            starts_at=normalized["starts_at"],
            ends_at=normalized["ends_at"],
            created_by=created_by,
            created_at=now,
            updated_at=now,
            published_at=now if normalized["status"] == "published" else 0.0,
        )
        with self._lock:
            return self.repository.save_announcement(record).to_dict()

    def update_announcement(
        self,
        announcement_id: str,
        *,
        title: str | None = None,
        content: str | None = None,
        level: str | None = None,
        audience: str | None = None,
        status: str | None = None,
        pinned: bool | None = None,
        starts_at: float | None = None,
        ends_at: float | None = None,
    ) -> dict:
        """更新系统公告。"""

        with self._lock:
            record = self.repository.get_announcement(announcement_id)
            if record is None:
                raise AuthError("ANNOUNCEMENT_NOT_FOUND", "公告不存在", http_status=404)
            normalized = self._normalize_announcement_payload(
                title=record.title if title is None else title,
                content=record.content if content is None else content,
                level=record.level if level is None else level,
                audience=record.audience if audience is None else audience,
                status=record.status if status is None else status,
                starts_at=record.starts_at if starts_at is None else starts_at,
                ends_at=record.ends_at if ends_at is None else ends_at,
            )
            published_at = record.published_at
            if normalized["status"] == "published" and published_at <= 0:
                published_at = time.time()
            updated = AnnouncementRecord(
                announcement_id=record.announcement_id,
                title=normalized["title"],
                content=normalized["content"],
                level=normalized["level"],
                audience=normalized["audience"],
                status=normalized["status"],
                pinned=record.pinned if pinned is None else bool(pinned),
                starts_at=normalized["starts_at"],
                ends_at=normalized["ends_at"],
                created_by=record.created_by,
                created_at=record.created_at,
                updated_at=time.time(),
                published_at=published_at,
            )
            return self.repository.save_announcement(updated).to_dict()

    def archive_announcement(self, announcement_id: str) -> dict:
        """归档公告，不物理删除。"""

        return self.update_announcement(announcement_id, status="archived")

    def list_announcements(
        self,
        *,
        keyword: str = "",
        status: str = "",
        level: str = "",
        audience: str = "",
        page: int = 1,
        limit: int = 20,
    ) -> dict:
        """读取公告管理列表。"""

        normalized_limit = max(1, min(int(limit or 20), 100))
        normalized_page = max(1, int(page or 1))
        offset = (normalized_page - 1) * normalized_limit
        with self._lock:
            items = self.repository.list_announcements(
                keyword=keyword,
                status=status,
                level=level,
                audience=audience,
                limit=normalized_limit,
                offset=offset,
            )
            total = self.repository.count_announcements(
                keyword=keyword,
                status=status,
                level=level,
                audience=audience,
            )
        return {
            "announcements": [item.to_dict() for item in items],
            "total": total,
            "page": normalized_page,
            "limit": normalized_limit,
        }

    def list_active_announcements(self, *, role: str, limit: int = 10) -> list[dict]:
        """读取当前角色可见的有效公告。"""

        with self._lock:
            records = self.repository.list_active_announcements(
                role=role,
                now=time.time(),
                limit=limit,
            )
        return [record.to_dict() for record in records]

    def create_redeem_code(
        self,
        *,
        created_by: str,
        kind: str,
        points: int = 0,
        max_uses: int = 1,
        expires_at: float = 0.0,
        code: str | None = None,
        count: int = 1,
    ) -> dict:
        """创建积分兑换码。"""

        if kind != "points":
            raise AuthError("INVALID_INPUT", "兑换码类型仅支持 points", http_status=400)
        if count < 1 or count > 1000:
            raise AuthError("INVALID_INPUT", "批量创建兑换码的数量必须在 1 到 1000 之间", http_status=400)
        if code and count > 1:
            raise AuthError("INVALID_INPUT", "批量创建不支持指定特定兑换码文字", http_status=400)

        now = time.time()
        expires_at_value = float(expires_at or 0.0)
        if not math.isfinite(expires_at_value):
            raise AuthError("INVALID_INPUT", "兑换码有效期必须是有效时间戳", http_status=400)
        if expires_at_value < 0:
            raise AuthError("INVALID_INPUT", "兑换码有效期不能为负数", http_status=400)
        if expires_at_value and expires_at_value <= now:
            raise AuthError("INVALID_INPUT", "兑换码有效期必须晚于当前时间", http_status=400)

        if code:
            code = code.strip()
            if len(code) < 3 or len(code) > 64:
                raise AuthError("INVALID_INPUT", "自定义兑换码长度必须在 3 到 64 之间", http_status=400)
            import re
            if not re.match(r"^[a-zA-Z0-9_\-]+$", code):
                raise AuthError("INVALID_INPUT", "自定义兑换码只能包含字母、数字、下划线和连字符", http_status=400)

        created_records = []
        with self._lock:
            if code:
                if self.repository.find_redeem_code_by_code(code):
                    raise AuthError("INVALID_INPUT", f"兑换码 {code} 已存在", http_status=400)

            for _ in range(count):
                actual_code = code if code else "rc_" + secrets.token_urlsafe(10)
                if not code:
                    while self.repository.find_redeem_code_by_code(actual_code):
                        actual_code = "rc_" + secrets.token_urlsafe(10)

                record = RedeemCodeRecord(
                    code_id=secrets.token_hex(12),
                    code=actual_code,
                    kind="points",
                    points=max(0, int(points)),
                    max_uses=max(1, int(max_uses)),
                    used_uses=0,
                    status="active",
                    created_by=created_by,
                    created_at=now,
                    expires_at=expires_at_value,
                )
                self.repository.save_redeem_code(record)
                created_records.append(record)

        return created_records[-1].to_dict()

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

        return self.llm_service.list_models(reveal_secret=reveal_secret)

    def get_llm_model(self, model_id: str, *, reveal_secret: bool = False) -> dict:
        """读取单个大模型配置。"""

        return self.llm_service.get_model(model_id, reveal_secret=reveal_secret)

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

        return self.llm_service.create_model(
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

        return self.llm_service.update_model(model_id, values)

    def delete_llm_model(self, model_id: str) -> bool:
        """删除大模型配置。"""

        return self.llm_service.delete_model(model_id)

    def active_llm_models(self):
        """返回可参与主备链的大模型配置。"""

        return self.llm_service.active_models()

    def test_llm_model(self, model_id: str) -> dict:
        """测试指定大模型配置的连通性与接口解析。"""
        return self.llm_service.test_model(model_id)

    def save_llm_call_trace(self, payload: dict) -> None:
        """落库一条 LLM 调用追溯，失败不影响答题主流程。"""

        self.llm_service.save_call_trace(payload)

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

        return self.llm_service.list_call_traces(
            request_id=request_id,
            model_id=model_id,
            phase=phase,
            limit=limit,
            offset=offset,
        )

    def count_llm_call_traces(
        self,
        *,
        request_id: str = "",
        model_id: str = "",
        phase: str = "",
    ) -> int:
        """统计 LLM 调用追溯数量。"""

        return self.llm_service.count_call_traces(
            request_id=request_id,
            model_id=model_id,
            phase=phase,
        )

    def llm_call_stats(self) -> list[dict]:
        """按模型聚合 LLM 调用统计。"""

        return self.llm_service.call_stats()

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

    @staticmethod
    def _normalize_announcement_payload(
        *,
        title: str,
        content: str,
        level: str,
        audience: str,
        status: str,
        starts_at: float,
        ends_at: float,
    ) -> dict:
        """校验并规范化公告输入。"""

        normalized_title = (title or "").strip()
        normalized_content = (content or "").strip()
        if not normalized_title:
            raise AuthError("INVALID_INPUT", "请填写公告标题", http_status=400)
        if len(normalized_title) > 120:
            raise AuthError("INVALID_INPUT", "公告标题不能超过 120 个字符", http_status=400)
        if not normalized_content:
            raise AuthError("INVALID_INPUT", "请填写公告内容", http_status=400)
        if len(normalized_content) > 3000:
            raise AuthError("INVALID_INPUT", "公告内容不能超过 3000 个字符", http_status=400)

        normalized_level = (level or "info").strip()
        normalized_audience = (audience or "all").strip()
        normalized_status = (status or "draft").strip()
        if normalized_level not in ANNOUNCEMENT_LEVELS:
            raise AuthError("INVALID_INPUT", "公告等级不支持", http_status=400)
        if normalized_audience not in ANNOUNCEMENT_AUDIENCES:
            raise AuthError("INVALID_INPUT", "公告投放范围不支持", http_status=400)
        if normalized_status not in ANNOUNCEMENT_STATUSES:
            raise AuthError("INVALID_INPUT", "公告状态不支持", http_status=400)

        normalized_starts_at = max(0.0, float(starts_at or 0.0))
        normalized_ends_at = max(0.0, float(ends_at or 0.0))
        if normalized_starts_at > 0 and normalized_ends_at > 0:
            if normalized_ends_at <= normalized_starts_at:
                raise AuthError("INVALID_INPUT", "结束时间必须晚于开始时间", http_status=400)
        return {
            "title": normalized_title,
            "content": normalized_content,
            "level": normalized_level,
            "audience": normalized_audience,
            "status": normalized_status,
            "starts_at": normalized_starts_at,
            "ends_at": normalized_ends_at,
        }

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
        site_title = self.get_site_config()["site_title"]
        return {
            "scope": effective_scope,
            "hero": {
                "title": f"{site_title} 全新上线",
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

    def get_system_config(self, *, reveal_secret: bool = False) -> dict:
        """读取系统运行配置；默认对敏感项只暴露是否已配置。"""
        with self._lock:
            raw = {key: SYSTEM_CONFIG_DEFAULTS.get(key, "") for key in SYSTEM_CONFIG_KEYS}
            raw.update(self.repository.get_settings("system_config", keys=set(SYSTEM_CONFIG_KEYS)))
            payload: dict[str, str | bool] = {}
            for key, value in raw.items():
                if key in SYSTEM_CONFIG_SECRET_KEYS and not reveal_secret:
                    payload[f"{key}_configured"] = bool(str(value).strip())
                else:
                    payload[key] = value
            return payload

    def get_site_config(self) -> dict[str, object]:
        """读取可公开暴露给登录页和前端初始化使用的站点品牌配置。"""

        config = self.get_system_config()
        title = str(config.get("site_title") or SYSTEM_CONFIG_DEFAULTS["site_title"]).strip()
        raw_logo_url = str(config.get("site_logo_url") or "").strip()
        try:
            logo_url = normalize_site_logo_url(raw_logo_url)
        except AuthError:
            logo_url = ""

        site_logo_urls: dict[str, str] = {}
        if logo_url.startswith("/media/brand/"):
            import re

            match = re.match(r"^/media/brand/logo_([a-z]+)\.png(\?t=\d+)?$", logo_url)
            if match:
                t_suffix = match.group(2) or ""
                for size_key in ("original", "lg", "md", "sm"):
                    site_logo_urls[size_key] = f"/media/brand/logo_{size_key}.png{t_suffix}"

        if not site_logo_urls:
            for size_key in ("original", "lg", "md", "sm"):
                site_logo_urls[size_key] = logo_url

        return {
            "site_title": title or SYSTEM_CONFIG_DEFAULTS["site_title"],
            "site_logo_url": logo_url,
            "site_logo_urls": site_logo_urls,
        }

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
            if key in SYSTEM_CONFIG_SECRET_KEYS and not text:
                continue
            if key == "site_title":
                text = text or SYSTEM_CONFIG_DEFAULTS["site_title"]
                if len(text) > 40:
                    raise AuthError("INVALID_INPUT", "网站标题不能超过 40 个字符", http_status=400)
            elif key == "site_logo_url":
                text = normalize_site_logo_url(text)
            elif key == "smtp_security":
                text = text.lower() or SYSTEM_CONFIG_DEFAULTS["smtp_security"]
                if text not in {"ssl", "starttls", "none"}:
                    raise AuthError(
                        "INVALID_INPUT", "SMTP 加密方式必须为 ssl、starttls 或 none", http_status=400
                    )
            elif key == "smtp_port":
                try:
                    parsed_port = int(text or SYSTEM_CONFIG_DEFAULTS["smtp_port"])
                except ValueError as exc:
                    raise AuthError("INVALID_INPUT", "SMTP 端口必须为有效整数", http_status=400) from exc
                if parsed_port < 1 or parsed_port > 65535:
                    raise AuthError("INVALID_INPUT", "SMTP 端口必须在 1 到 65535 之间", http_status=400)
                text = str(parsed_port)
            elif key in {
                "email_code_ttl_minutes",
                "email_code_cooldown_seconds",
                "email_code_daily_limit",
                "email_code_ip_hourly_limit",
                "email_code_max_attempts",
            }:
                text = normalize_email_code_policy_value(key, text)
            elif key == "smtp_from_email" and text:
                text = normalize_email(text)
            elif key == "smtp_from_name":
                text = text or SYSTEM_CONFIG_DEFAULTS["smtp_from_name"]
                if any(ch in text for ch in "\r\n"):
                    raise AuthError("INVALID_INPUT", "发件人名称格式不正确", http_status=400)
                if len(text) > 40:
                    raise AuthError("INVALID_INPUT", "发件人名称不能超过 40 个字符", http_status=400)
            elif key in SYSTEM_CONFIG_BOOLEAN_KEYS:
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
            current = {key: SYSTEM_CONFIG_DEFAULTS.get(key, "") for key in SYSTEM_CONFIG_KEYS}
            current.update(self.repository.get_settings("system_config", keys=set(SYSTEM_CONFIG_KEYS)))
            candidate = {**current, **normalized}
            if str(candidate.get("email_verification_enabled") or "").lower() == "true":
                host = str(candidate.get("smtp_host") or "").strip()
                from_email = str(candidate.get("smtp_from_email") or "").strip()
                username = str(candidate.get("smtp_username") or "").strip()
                password = str(candidate.get("smtp_password") or "").strip()

                if not host or not from_email or not username:
                    raise AuthError("INVALID_INPUT", "启用的邮箱验证码注册前，请先完整配置 SMTP 服务（宿主机、用户名与发件邮箱）", http_status=400)

                is_pwd_configured = bool(current.get("smtp_password_configured")) or bool(current.get("smtp_password"))
                if not password and not is_pwd_configured:
                    raise AuthError("INVALID_INPUT", "启用的邮箱验证码注册前，请先输入 SMTP 密码", http_status=400)

                smtp_settings_from_config(candidate)
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


def normalize_site_logo_url(value: str) -> str:
    """校验站点 Logo 地址，只允许空值、站内绝对路径或 HTTP(S) URL。"""

    text = (value or "").strip()
    if not text:
        return ""
    if len(text) > 2048:
        raise AuthError("INVALID_INPUT", "Logo 地址不能超过 2048 个字符", http_status=400)
    if text.startswith("/"):
        if text.startswith("/media/brand/"):
            return text
        if text.startswith("//") or any(ch.isspace() for ch in text):
            raise AuthError("INVALID_INPUT", "Logo 地址格式不正确", http_status=400)
        return text
    parsed = urlparse(text)
    if (
        parsed.scheme in {"http", "https"}
        and parsed.netloc
        and not any(ch.isspace() for ch in text)
    ):
        return text
    raise AuthError("INVALID_INPUT", "Logo 地址仅支持站内路径或 http/https URL", http_status=400)


def normalize_email_code_policy_value(key: str, value: str) -> str:
    """校验邮箱验证码策略数值，避免误配置拖垮注册入口。"""

    bounds = {
        "email_code_ttl_minutes": (1, 60),
        "email_code_cooldown_seconds": (0, 3600),
        "email_code_daily_limit": (1, 100),
        "email_code_ip_hourly_limit": (1, 500),
        "email_code_max_attempts": (1, 20),
    }
    minimum, maximum = bounds[key]
    try:
        parsed = int(value or SYSTEM_CONFIG_DEFAULTS[key])
    except ValueError as exc:
        raise AuthError("INVALID_INPUT", f"{key} 必须为整数", http_status=400) from exc
    if parsed < minimum or parsed > maximum:
        raise AuthError(
            "INVALID_INPUT",
            f"{key} 必须在 {minimum} 到 {maximum} 之间",
            http_status=400,
        )
    return str(parsed)


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
            if local_date_from_log_timestamp(str(payload.get("ts") or "")) != date_label:
                continue
            if str(payload.get("event") or "") == "query":
                query_count += 1
    return query_count, malformed_lines


def local_date_from_log_timestamp(value: str) -> str:
    """把运行日志 UTC/带时区时间戳转换成上海自然日标签。"""

    timestamp = value.strip()
    if not timestamp:
        return ""
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return timestamp[:10]
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_TIMEZONE)
    return parsed.astimezone(LOCAL_TIMEZONE).strftime("%Y-%m-%d")


def normalized_confidence(value: object) -> float:
    """把用户配置的置信度阈值归一化到 0 到 1。"""

    try:
        return min(max(float(str(value or "0")), 0.0), 1.0)
    except (TypeError, ValueError):
        return 0.0

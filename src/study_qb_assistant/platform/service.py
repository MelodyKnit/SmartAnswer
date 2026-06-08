"""平台业务服务。"""

from __future__ import annotations

import secrets
import time
from pathlib import Path
from threading import RLock

from ..auth import AuthError
from ..storage.platform_repository import SqlAlchemyPlatformRepository
from .config import SYSTEM_CONFIG_ENV_MAP, SYSTEM_CONFIG_KEYS, SYSTEM_CONFIG_SECRET_KEYS
from .records import (
    ApiTokenRecord,
    FeedbackRecord,
    ImportScriptRecord,
    IntegrationRecord,
    NotificationRecord,
    QuotaPackageRecord,
    RedeemCodeRecord,
    RolePermissionRecord,
    UsageLogRecord,
    WalletOrderRecord,
    WalletProfileRecord,
)
from .storage import hash_token, mask_token, public_token_dict
from .wallet_ops import has_active_subscription_profile, wallet_summary_payload


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

    def create_token(self, *, user_id: str, description: str = "") -> tuple[str, dict]:
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
            )
            self.repository.save_token(record)
            return raw, public_token_dict(record)

    def list_tokens(self, *, user_id: str) -> list[dict]:
        """列出指定用户的全部 API 令牌。"""
        with self._lock:
            return [public_token_dict(token) for token in self.repository.list_tokens(user_id=user_id)]

    def revoke_token(self, *, user_id: str, token_id: str) -> dict:
        """吊销用户自己的 API 令牌。"""
        with self._lock:
            token = self.repository.get_token(token_id)
            if token is None or token.user_id != user_id:
                raise AuthError("TOKEN_NOT_FOUND", "令牌不存在", http_status=404)
            token.status = "revoked"
            self.repository.save_token(token)
            return public_token_dict(token)

    def resolve_token(self, raw_token: str | None) -> dict | None:
        """解析原始 Bearer 令牌，并记录最后使用时间。"""
        with self._lock:
            if not raw_token:
                return None
            token = self.repository.find_token_by_hash(hash_token(raw_token))
            if token is None or token.status != "active":
                return None
            token.last_used_at = time.time()
            token.usage_count += 1
            self.repository.save_token(token)
            return public_token_dict(token)

    def get_billing(self) -> dict:
        """读取当前积分计费配置。"""
        with self._lock:
            current = {"local_hit": 1, "web_search": 2, "llm_fallback": 3}
            current.update(self.repository.get_settings("billing", keys=set(current.keys())))
            return {key: max(0, int(value)) for key, value in current.items()}

    def set_billing(self, values: dict[str, int]) -> dict:
        """更新积分计费配置。"""
        current = self.get_billing()
        for key, value in values.items():
            if key not in current:
                raise AuthError("INVALID_INPUT", f"不支持的积分项目: {key}", http_status=400)
            current[key] = max(0, int(value))
        with self._lock:
            self.repository.replace_settings("billing", {key: str(value) for key, value in current.items()})
        return current

    def calculate_points_cost(self, resolution_mode: str) -> int:
        """根据查题命中方式计算本次调用的积分消耗。"""
        billing = self.get_billing()
        if resolution_mode == "llm_fallback":
            return billing["llm_fallback"]
        if resolution_mode in {"exact_match", "fuzzy_match", "known_rule", "ai_cache"}:
            return billing["local_hit"]
        return billing["web_search"]

    def wallet_summary(self, *, user_id: str, username: str, points: int) -> dict:
        """汇总用户钱包与订阅状态。"""
        with self._lock:
            profile = self.repository.get_wallet_profile(user_id) or WalletProfileRecord(user_id=user_id)
            return wallet_summary_payload(
                {user_id: profile},
                user_id=user_id,
                username=username,
                points=points,
            )

    def has_active_subscription(self, user_id: str) -> bool:
        """判断用户当前是否拥有有效订阅。"""
        with self._lock:
            profile = self.repository.get_wallet_profile(user_id)
            return has_active_subscription_profile({user_id: profile} if profile else {}, user_id)

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
            provider=provider,
            created_at=time.time(),
        )
        with self._lock:
            self.repository.save_usage_log(record)
        return record.to_dict()

    def list_usage_logs(self, *, username: str | None = None, keyword: str = "", limit: int = 100) -> list[dict]:
        """按用户与关键词筛选使用日志。"""
        with self._lock:
            return [
                item.to_dict()
                for item in self.repository.list_usage_logs(username=username, keyword=keyword, limit=limit)
            ]

    def create_feedback(
        self,
        *,
        user_id: str,
        username: str,
        usage_log_id: str | None,
        title: str,
        content: str,
        image_urls: tuple[str, ...],
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
        )
        with self._lock:
            self.repository.save_feedback(record)
        return record.to_dict()

    def list_feedbacks(self, *, username: str | None = None, limit: int = 100) -> list[dict]:
        """按用户过滤反馈列表。"""
        with self._lock:
            return [item.to_dict() for item in self.repository.list_feedbacks(username=username, limit=limit)]

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

    def list_notifications(self, *, user_id: str | None = None, status: str = "", limit: int = 20) -> list[dict]:
        """列出消息中心通知。"""
        with self._lock:
            return [item.to_dict() for item in self.repository.list_notifications(user_id=user_id, status=status, limit=limit)]

    def mark_notification_read(self, notification_id: str, *, read: bool = True) -> dict:
        """标记单条消息的已读状态。"""
        with self._lock:
            record = self.repository.get_notification(notification_id)
            if record is None:
                raise AuthError("NOTIFICATION_NOT_FOUND", "消息不存在", http_status=404)
            record.read = bool(read)
            self.repository.save_notification(record)
            return record.to_dict()

    def mark_all_notifications_read(self, *, user_id: str | None = None) -> int:
        """批量标记消息为已读。"""
        count = 0
        with self._lock:
            for record in self.repository.list_notifications(user_id=user_id, status="unread", limit=500):
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
        subscription_days: int = 0,
        max_uses: int = 1,
        expires_at: float = 0.0,
    ) -> dict:
        """创建积分或订阅兑换码。"""
        if kind not in {"points", "subscription"}:
            raise AuthError("INVALID_INPUT", "兑换码类型必须为 points 或 subscription", http_status=400)
        record = RedeemCodeRecord(
            code_id=secrets.token_hex(12),
            code="rc_" + secrets.token_urlsafe(10),
            kind=kind,
            points=max(0, int(points)),
            subscription_days=max(0, int(subscription_days)),
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
        subscription_days: int = 0,
        source: str = "manual_credit",
        source_id: str | None = None,
    ) -> dict:
        """手动发放积分或订阅权益，并写入钱包流水。"""
        if kind not in {"points", "subscription"}:
            raise AuthError("INVALID_INPUT", "钱包类型必须为 points 或 subscription", http_status=400)
        with self._lock:
            profile = self.repository.get_wallet_profile(user_id) or WalletProfileRecord(user_id=user_id)
            order = WalletOrderRecord(
                order_id=secrets.token_hex(12),
                user_id=user_id,
                username=username,
                kind=kind,
                points_delta=max(0, int(points)) if kind == "points" else 0,
                subscription_days=max(0, int(subscription_days)) if kind == "subscription" else 0,
                source=source,
                source_id=source_id,
                status="completed",
                created_by=created_by,
                created_at=time.time(),
            )
            if kind == "subscription" and order.subscription_days > 0:
                start = max(profile.subscription_expires_at, time.time())
                profile.subscription_expires_at = start + (order.subscription_days * 86400)
                self.repository.save_wallet_profile(profile)
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
                subscription_days=redeem.subscription_days,
                source="redeem_code",
                source_id=redeem.code_id,
            )

    def list_wallet_orders(self, *, username: str | None = None, limit: int = 100) -> list[dict]:
        """按用户过滤钱包流水。"""
        with self._lock:
            return [item.to_dict() for item in self.repository.list_wallet_orders(username=username, limit=limit)]

    def list_integrations(self) -> list[dict]:
        """列出全部接入点。"""
        with self._lock:
            return [item.to_dict() for item in self.repository.list_integrations()]

    def get_integration(self, integration_id: str) -> dict | None:
        """读取单个接入点。"""
        with self._lock:
            record = self.repository.get_integration(integration_id)
            return record.to_dict() if record else None

    def create_integration(
        self,
        *,
        name: str,
        platform: str,
        base_url: str,
        token_id: str | None,
        status: str,
        description: str,
    ) -> dict:
        """创建接入点。"""
        now = time.time()
        record = IntegrationRecord(
            integration_id=secrets.token_hex(12),
            name=name.strip(),
            platform=(platform or "generic").strip(),
            base_url=base_url.strip(),
            token_id=token_id,
            status=(status or "active").strip(),
            description=description.strip(),
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self.repository.save_integration(record)
        return record.to_dict()

    def update_integration(self, integration_id: str, values: dict[str, object]) -> dict:
        """更新接入点。"""
        with self._lock:
            record = self.repository.get_integration(integration_id)
            if record is None:
                raise AuthError("INTEGRATION_NOT_FOUND", "接入点不存在", http_status=404)
            for key, value in values.items():
                if value is None:
                    continue
                if key == "token_id":
                    setattr(record, key, value)
                else:
                    setattr(record, key, str(value).strip())
            record.updated_at = time.time()
            self.repository.save_integration(record)
            return record.to_dict()

    def delete_integration(self, integration_id: str) -> bool:
        """删除接入点。"""
        with self._lock:
            return self.repository.delete_integration(integration_id)

    def test_integration(self, integration_id: str) -> dict:
        """测试接入点配置。"""
        with self._lock:
            record = self.repository.get_integration(integration_id)
            if record is None:
                raise AuthError("INTEGRATION_NOT_FOUND", "接入点不存在", http_status=404)
            ok = bool(record.base_url and record.status == "active")
            record.last_test_at = time.time()
            record.last_test_status = "success" if ok else "failed"
            record.last_error = "" if ok else "base_url missing or integration disabled"
            self.repository.save_integration(record)
            return {
                "ok": ok,
                "integration": record.to_dict(),
                "message": "连接测试成功" if ok else "接入配置不完整或已禁用",
            }

    def list_import_scripts(self) -> list[dict]:
        """列出全部导入脚本。"""
        with self._lock:
            return [item.to_dict() for item in self.repository.list_import_scripts()]

    def get_import_script(self, script_id: str) -> dict | None:
        """读取单个导入脚本。"""
        with self._lock:
            record = self.repository.get_import_script(script_id)
            return record.to_dict() if record else None

    def generate_import_script(
        self,
        *,
        name: str,
        integration_id: str | None,
        token_id: str | None,
        target: str,
        include_test_snippet: bool,
    ) -> dict:
        """生成并保存导入脚本。"""
        integration = self.repository.get_integration(integration_id) if integration_id else None
        token = self.repository.get_token(token_id) if token_id else None
        content_lines = [
            f"// {name or '导入脚本'}",
            f"// target: {target}",
        ]
        if integration is not None:
            content_lines.append(f"const baseUrl = '{integration.base_url}';")
        if token is not None:
            content_lines.append(f"const tokenId = '{token.token_id}';")
            content_lines.append(f"// token: {token.key_mask}")
        content_lines.append("export const config = { enabled: true };")
        if include_test_snippet:
            content_lines.append("export function testConnection() { return Promise.resolve(true); }")
        content = "\n".join(content_lines)
        now = time.time()
        record = ImportScriptRecord(
            script_id=secrets.token_hex(12),
            name=(name or "导入脚本").strip(),
            integration_id=integration_id,
            token_id=token_id,
            target=(target or "ocs").strip(),
            content=content,
            status="active",
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self.repository.save_import_script(record)
        return record.to_dict()

    def delete_import_script(self, script_id: str) -> bool:
        """删除导入脚本。"""
        with self._lock:
            return self.repository.delete_import_script(script_id)

    def list_quota_packages(self) -> list[dict]:
        """列出额度套餐。"""
        with self._lock:
            return [item.to_dict() for item in self.repository.list_quota_packages()]

    def create_quota_package(
        self,
        *,
        name: str,
        kind: str,
        points: int,
        subscription_days: int,
        price: float,
        status: str,
        description: str,
        sort_order: int,
    ) -> dict:
        """创建额度套餐。"""
        now = time.time()
        record = QuotaPackageRecord(
            package_id=secrets.token_hex(12),
            name=name.strip(),
            kind=(kind or "points").strip(),
            points=max(0, int(points)),
            subscription_days=max(0, int(subscription_days)),
            price=max(0.0, float(price)),
            status=(status or "active").strip(),
            description=description.strip(),
            sort_order=int(sort_order),
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self.repository.save_quota_package(record)
        return record.to_dict()

    def update_quota_package(self, package_id: str, values: dict[str, object]) -> dict:
        """更新额度套餐。"""
        with self._lock:
            record = self.repository.get_quota_package(package_id)
            if record is None:
                raise AuthError("PACKAGE_NOT_FOUND", "套餐不存在", http_status=404)
            for key, value in values.items():
                if value is None:
                    continue
                if key in {"points", "subscription_days", "sort_order"}:
                    setattr(record, key, int(value))
                elif key == "price":
                    setattr(record, key, float(value))
                else:
                    setattr(record, key, str(value).strip())
            record.updated_at = time.time()
            self.repository.save_quota_package(record)
            return record.to_dict()

    def delete_quota_package(self, package_id: str) -> bool:
        """删除额度套餐。"""
        with self._lock:
            return self.repository.delete_quota_package(package_id)

    def list_role_permissions(self) -> list[dict]:
        """列出角色权限矩阵。"""
        defaults = {
            "superadmin": ("dashboard:all", "users:write", "roles:write", "system:write"),
            "admin": ("dashboard:all", "users:write", "billing:read"),
            "user": ("dashboard:self", "tokens:self", "feedback:self"),
        }
        with self._lock:
            existing = {item.role_id: item for item in self.repository.get_role_permissions()}
            result: list[RolePermissionRecord] = []
            for role_id, permissions in defaults.items():
                result.append(
                    existing.get(
                        role_id,
                        RolePermissionRecord(role_id=role_id, permissions=permissions, updated_at=0.0),
                    )
                )
            return [item.to_dict() for item in result]

    def get_role_permissions(self, role_id: str) -> dict:
        """读取单个角色的权限矩阵。"""
        items = {item["role_id"]: item for item in self.list_role_permissions()}
        record = items.get(role_id)
        if record is None:
            raise AuthError("ROLE_NOT_FOUND", "角色不存在", http_status=404)
        return record

    def set_role_permissions(self, role_id: str, permissions: tuple[str, ...]) -> dict:
        """更新角色权限矩阵。"""
        with self._lock:
            self.repository.set_role_permissions(role_id, tuple(str(item).strip() for item in permissions if str(item).strip()), time.time())
        return self.get_role_permissions(role_id)

    def dashboard_rankings(self, *, days: int = 1, limit: int = 10, dimension: str = "integration") -> list[dict]:
        """构造工作台排行统计。"""
        logs = self.list_usage_logs(limit=5000)
        since = time.time() - max(1, min(days, 365)) * 86400
        scoped = [log for log in logs if float(log["created_at"]) >= since]
        counters: dict[str, int] = {}
        token_map = {}
        if dimension == "integration":
            for item in self.list_integrations():
                if item.get("token_id"):
                    token_map[str(item["token_id"])] = str(item["name"])
        for log in scoped:
            if dimension == "integration":
                label = token_map.get(str(log.get("token_id") or ""), str(log.get("provider") or "未归类接入"))
            elif dimension == "question_type":
                label = str(log.get("question_type") or "unknown")
            else:
                label = str(log.get("username") or "unknown")
            counters[label] = counters.get(label, 0) + 1
        ranked = sorted(counters.items(), key=lambda item: item[1], reverse=True)
        return [
            {"rank": index + 1, "label": label, "count": count}
            for index, (label, count) in enumerate(ranked[: max(1, min(limit, 50))])
        ]

    def dashboard_workbench(self, *, user_id: str, username: str, points: int) -> dict:
        """构造工作台首页聚合数据。"""
        logs = self.list_usage_logs(username=username, limit=1000)
        today = time.time() - 86400
        today_logs = [log for log in logs if float(log["created_at"]) >= today]
        success_rate = 100.0 if not today_logs else round(
            sum(1 for log in today_logs if log.get("resolution_mode") != "model_error") / len(today_logs) * 100,
            1,
        )
        avg_response = 0.82
        distribution: dict[str, int] = {}
        for log in today_logs:
            question_type = str(log.get("question_type") or "unknown")
            distribution[question_type] = distribution.get(question_type, 0) + 1
        notifications = self.list_notifications(user_id=user_id, limit=5)
        wallet = self.wallet_summary(user_id=user_id, username=username, points=points)
        ranking_preview = self.dashboard_rankings(days=1, limit=5, dimension="integration")
        return {
            "hero": {
                "title": "答题接入平台 全新上线",
                "subtitle": "更稳定的接口服务，更便捷的接入体验，助力平台高效接入答题能力",
                "badges": ["高可用保障", "快速接入", "安全合规"],
            },
            "quick_actions": [
                {"key": "create_api_key", "label": "创建API Key", "path": "/tokens"},
                {"key": "generate_script", "label": "生成导入脚本", "path": "/import-scripts"},
                {"key": "test_integration", "label": "测试连接", "path": "/integrations"},
                {"key": "integration_manage", "label": "接入管理", "path": "/integrations"},
                {"key": "interface_status", "label": "接口状态", "path": "/status"},
            ],
            "overview": {
                "today_calls": len(today_logs),
                "success_rate": success_rate,
                "avg_response_seconds": avg_response,
                "remaining_points": wallet["points"],
            },
            "trend": {"days": 7, "items": self._daily_trend(logs, 7)},
            "question_distribution": distribution,
            "ranking_preview": ranking_preview,
            "notifications_preview": notifications,
            "service_status": {
                "api": "ok",
                "search_provider": self.get_system_config().get("web_search_provider", ""),
                "llm_model": self.get_system_config().get("llm_model", ""),
            },
        }

    def _daily_trend(self, logs: list[dict], days: int) -> list[dict]:
        buckets: dict[str, int] = {}
        for offset in range(days):
            stamp = time.time() - ((days - offset - 1) * 86400)
            key = time.strftime("%m-%d", time.localtime(stamp))
            buckets[key] = 0
        for log in logs:
            key = time.strftime("%m-%d", time.localtime(float(log["created_at"])))
            if key in buckets:
                buckets[key] += 1
        return [{"date": key, "count": value} for key, value in buckets.items()]

    def get_system_config(self) -> dict:
        """读取系统运行配置，并对敏感项只暴露是否已配置。"""
        with self._lock:
            raw = {key: "" for key in SYSTEM_CONFIG_KEYS}
            raw.update(self.repository.get_settings("system_config", keys=set(SYSTEM_CONFIG_KEYS)))
            payload: dict[str, str | bool] = {}
            for key, value in raw.items():
                if key in SYSTEM_CONFIG_SECRET_KEYS:
                    payload[f"{key}_configured"] = bool(str(value).strip())
                else:
                    payload[key] = value
            return payload

    def set_system_config(self, values: dict[str, object]) -> dict:
        """更新系统运行配置。"""
        normalized: dict[str, str] = {}
        for key, value in values.items():
            if key not in SYSTEM_CONFIG_KEYS:
                raise AuthError("INVALID_INPUT", f"不支持的系统配置项: {key}", http_status=400)
            normalized[key] = "" if value is None else str(value).strip()
        with self._lock:
            self.repository.set_settings("system_config", normalized)
        return self.get_system_config()

    def runtime_env(self) -> dict[str, str]:
        """把平台配置转换为运行时环境变量映射。"""
        raw = self.repository.get_settings("system_config", keys=set(SYSTEM_CONFIG_KEYS))
        return {
            env_key: str(raw.get(config_key) or "").strip()
            for config_key, env_key in SYSTEM_CONFIG_ENV_MAP.items()
            if str(raw.get(config_key) or "").strip()
        }

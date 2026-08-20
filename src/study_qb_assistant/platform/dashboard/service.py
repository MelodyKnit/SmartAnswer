"""工作台聚合服务。"""

from __future__ import annotations

from collections.abc import Sequence

from ...llm.management import LlmManagementService
from ..notifications import NotificationService
from ..settings import SettingsService
from ..usage import UsageService
from ..usage.time_ranges import current_local_day_range, recent_day_range
from ..wallet import WalletService


class DashboardService:
    """聚合工作台所需的跨领域只读数据。"""

    def __init__(
        self,
        *,
        usage: UsageService,
        notifications: NotificationService,
        wallet: WalletService,
        settings: SettingsService,
        llm: LlmManagementService,
    ) -> None:
        self.usage = usage
        self.notifications = notifications
        self.wallet = wallet
        self.settings = settings
        self.llm = llm

    def dashboard_rankings(
        self,
        *,
        days: int = 1,
        limit: int = 10,
        dimension: str = "provider",
        username: str,
        role: str = "user",
        scope: str = "self",
        permissions: set[str] | None = None,
    ) -> list[dict]:
        """构造工作台排行统计。"""
        start_time, end_time = recent_day_range(days)
        normalized_dimension = normalize_ranking_dimension(dimension)
        rows = self.usage.usage_distribution(
            normalized_dimension,
            username=username,
            role=role,
            scope=scope,
            can_view_global=can_view_global(role, permissions),
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
        unlimited_expires_at: float = 0.0,
        role: str = "user",
        scope: str = "self",
        permissions: set[str] | None = None,
    ) -> dict:
        """构造工作台首页聚合数据。"""
        today_start, today_end = current_local_day_range()
        can_view_all = can_view_global(role, permissions)
        effective_scope, _ = self.usage.usage_scope(
            username=username,
            role=role,
            scope=scope,
            can_view_global=can_view_all,
        )
        overview = self.usage.usage_overview(
            username=username,
            role=role,
            scope=effective_scope,
            start_time=today_start,
            end_time=today_end,
            can_view_global=can_view_all,
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
            for key, value in self.usage.usage_distribution(
                "question_type",
                username=username,
                role=role,
                scope=effective_scope,
                start_time=today_start,
                end_time=today_end,
                can_view_global=can_view_all,
            )
        }
        notifications = self.notifications.list_notifications(user_id=user_id, limit=5)
        wallet = self.wallet.wallet_summary(
            user_id=user_id,
            username=username,
            points=points,
            unlimited_expires_at=unlimited_expires_at,
        )
        ranking_preview = self.dashboard_rankings(
            days=1,
            limit=5,
            dimension="provider",
            username=username,
            role=role,
            scope=effective_scope,
            permissions=permissions,
        )
        quick_actions = [
            {
                "key": "create_api_key",
                "label": "创建 API Key",
                "path": "/tokens",
                "action": "navigate",
                "requires_permissions": ["tokens:self"],
            },
            {
                "key": "copy_import_script",
                "label": "复制导入脚本",
                "path": "/tokens",
                "action": "copy_import_script",
                "requires_permissions": ["tokens:self"],
            },
            {
                "key": "interface_status",
                "label": "接口状态",
                "path": "/status",
                "action": "navigate",
                "requires_permissions": [],
            },
            {
                "key": "usage_logs",
                "label": "使用记录",
                "path": "/usage-logs",
                "action": "navigate",
                "requires_permissions": [],
            },
            {
                "key": "wallet",
                "label": "我的钱包",
                "path": "/wallet",
                "action": "navigate",
                "requires_permissions": [],
            },
            {
                "key": "generate_script",
                "label": "生成导入脚本",
                "path": "/import-scripts",
                "action": "navigate",
                "requires_permissions": ["import-scripts:read"],
            },
        ]
        quick_actions = [
            action
            for action in quick_actions
            if has_permissions(role, permissions, action["requires_permissions"])
        ]
        site_title = self.settings.get_site_config()["site_title"]
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
            "trend": {
                "days": 7,
                "items": self.usage.usage_trend(
                    username,
                    role,
                    effective_scope,
                    7,
                    can_view_global=can_view_all,
                ),
            },
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
        permissions: set[str] | None = None,
    ) -> dict:
        """返回工作台摘要统计。"""

        start_time, end_time = recent_day_range(days)
        overview = self.usage.usage_overview(
            username=username,
            role=role,
            scope=scope,
            start_time=start_time,
            end_time=end_time,
            can_view_global=can_view_global(role, permissions),
        )
        effective_scope = str(overview["scope"])
        return {
            "scope": effective_scope,
            "days": max(1, min(days, 365)),
            "points_used": int(overview["points_used"]),
            "query_count": int(overview["total_count"]),
            "resolution_modes": {
                key: value
                for key, value in self.usage.usage_distribution(
                    "resolution_mode",
                    username=username,
                    role=role,
                    scope=effective_scope,
                    start_time=start_time,
                    end_time=end_time,
                    can_view_global=can_view_global(role, permissions),
                )
            },
            "trend": self.usage.usage_summary_trend(
                username,
                role,
                effective_scope,
                days,
                can_view_global=can_view_global(role, permissions),
            ),
        }

    def _dashboard_service_status(self) -> dict[str, str]:
        """返回工作台服务状态摘要。"""

        runtime_config = self.settings.get_llm_runtime_config()
        active_models = self.llm.active_models()
        primary_model = next((item for item in active_models if item.role == "primary"), None)
        first_model = primary_model or (active_models[0] if active_models else None)
        return {
            "api": "ok",
            "search_provider": str(runtime_config.get("web_search_provider") or ""),
            "llm_model": first_model.model if first_model else "",
        }


def normalize_ranking_dimension(value: str) -> str:
    """把排行维度收敛到受支持集合。"""

    normalized = (value or "provider").strip().lower()
    if normalized in {"provider", "question_type", "username"}:
        return normalized
    return "provider"


def can_view_global(role: str, permissions: set[str] | None) -> bool:
    """判断当前角色是否可读取全站看板统计。"""

    if permissions is None:
        return role == "superadmin"
    return role == "superadmin" or "dashboard:all" in set(permissions or ())


def has_permissions(role: str, permissions: set[str] | None, required: Sequence[str]) -> bool:
    """判断工作台快捷项所需权限，超级管理员始终可见。"""

    if role == "superadmin":
        return True
    if permissions is None:
        return False
    return set(required).issubset(set(permissions))

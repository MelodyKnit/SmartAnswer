"""使用记录与统计服务。"""

from __future__ import annotations

import secrets
import time

from ..base import PlatformDomainService
from .records import UsageLogRecord
from .time_ranges import count_query_events_for_date, day_windows, local_day_range_from_text


class UsageService(PlatformDomainService):
    """UsageService 领域实现。"""

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
        with self.lock:
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
        with self.lock:
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
        with self.lock:
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
        with self.lock:
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
        with self.lock:
            return self.repository.usage_counts_by_field(
                field,
                username=username_filter,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
            )

    def usage_audit(self, date_text: str = "") -> dict:
        """返回指定自然日的调用对账结果。"""

        date_label, start_time, end_time = local_day_range_from_text(date_text)
        with self.lock:
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

    def usage_trend(self, username: str, role: str, scope: str, days: int) -> list[dict]:
        effective_scope, username_filter = self.usage_scope(
            username=username,
            role=role,
            scope=scope,
        )
        del effective_scope
        items: list[dict] = []
        for label, start_time, end_time in day_windows(days):
            with self.lock:
                count = self.repository.count_usage_logs(
                    username=username_filter,
                    start_time=start_time,
                    end_time=end_time,
                )
            items.append({"date": label[5:], "count": count})
        return items

    def usage_summary_trend(
        self, username: str, role: str, scope: str, days: int
    ) -> list[dict]:
        effective_scope, username_filter = self.usage_scope(
            username=username,
            role=role,
            scope=scope,
        )
        del effective_scope
        items: list[dict] = []
        for label, start_time, end_time in day_windows(days):
            with self.lock:
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

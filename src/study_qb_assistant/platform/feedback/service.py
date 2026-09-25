"""用户反馈服务。"""

from __future__ import annotations

import json
import secrets
import time
from threading import RLock
from typing import Any

from ...auth import AuthError
from ..base import PlatformDomainService
from ..usage.time_ranges import recent_day_range
from .errors import FeedbackOperationError
from .records import FeedbackRecord, FeedbackResolution


class FeedbackService(PlatformDomainService):
    """FeedbackService 领域实现。"""

    def __init__(self, repository: Any, usage_repository: Any, lock: RLock) -> None:
        super().__init__(repository, lock)
        self.usage_repository = usage_repository

    def create_feedback(
        self,
        *,
        user_id: str,
        username: str,
        usage_log_id: str | None,
        usage_log_ids: tuple[str, ...] = (),
        title: str,
        content: str,
        image_urls: tuple[str, ...],
        category: str = "answer",
    ) -> dict:
        """创建反馈，并在同一事务中保存所有选中的答题记录关联。"""
        normalized_category = _normalize_feedback_category(category)
        selected_ids = _normalize_usage_ids(usage_log_id, usage_log_ids)
        if normalized_category == "answer" and selected_ids:
            normalized_category = "wrong_answer"
        usage_records: list[Any] = []
        if selected_ids:
            with self.lock:
                records_by_id = self.usage_repository.get_usage_logs_by_ids(selected_ids)
            missing_ids = [item for item in selected_ids if item not in records_by_id]
            if missing_ids:
                raise FeedbackOperationError(
                    "FEEDBACK_USAGE_NOT_FOUND",
                    "存在不存在的答题记录，请刷新后重新选择",
                    http_status=400,
                )
            usage_records = [records_by_id[item] for item in selected_ids]
            if any(record.user_id != user_id for record in usage_records):
                raise FeedbackOperationError(
                    "FEEDBACK_USAGE_FORBIDDEN",
                    "只能关联自己的答题记录",
                    http_status=403,
                )
        elif normalized_category == "wrong_answer":
            raise FeedbackOperationError(
                "FEEDBACK_USAGE_REQUIRED",
                "答题问题至少选择一条答题记录",
                http_status=400,
            )

        usage_record = usage_records[0] if usage_records else None
        question_title = usage_record.title if usage_record else ""
        answer_snapshot = usage_record.answer if usage_record else None
        related_questions = [_usage_relation(record) for record in usage_records]
        context: dict[str, object] = {
            "usage_log_id": usage_record.log_id if usage_record else "",
            "usage_log_ids": selected_ids,
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
            # Keep the legacy scalar association populated for callers that only
            # understand usage_log_id, even when the new multi-select payload was used.
            usage_log_id=usage_record.log_id if usage_record else usage_log_id,
            title=title.strip() or ("题目反馈" if usage_record else "反馈"),
            content=content.strip(),
            image_urls=tuple(url.strip() for url in image_urls if url.strip()),
            status="open",
            created_at=time.time(),
            category=normalized_category,
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
            related_questions=related_questions,
        )
        with self.lock:
            self.repository.save_feedback(record)
        return record.to_dict()

    def answer_record_options(
        self,
        *,
        user_id: str,
        keyword: str = "",
        days: int = 1,
        deduplicate: bool = False,
        question_id: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """返回当前用户可关联的答题记录，不暴露跨用户使用日志字段。"""

        normalized_days = int(days)
        if normalized_days < 0:
            raise FeedbackOperationError("INVALID_DATE_RANGE", "历史范围不能为负数", http_status=400)
        start_time, end_time = recent_day_range(normalized_days) if normalized_days else (None, None)
        normalized_question_id = question_id.strip()
        limit = max(1, min(int(limit), 100))
        offset = max(0, int(offset))
        if normalized_question_id:
            with self.lock:
                records = self.usage_repository.list_usage_logs(
                    user_id=user_id,
                    question_id=normalized_question_id,
                    keyword=keyword.strip(),
                    limit=limit,
                    offset=offset,
                    start_time=start_time,
                    end_time=end_time,
                )
                total = self.usage_repository.count_usage_logs(
                    user_id=user_id,
                    question_id=normalized_question_id,
                    keyword=keyword.strip(),
                    start_time=start_time,
                    end_time=end_time,
                )
            return {
                "records": [_feedback_usage_option(record) for record in records],
                "groups": [],
                "total": total,
                "page": offset // limit + 1,
                "limit": limit,
                "deduplicated": bool(deduplicate),
            }

        if not deduplicate:
            with self.lock:
                records = self.usage_repository.list_usage_logs(
                    user_id=user_id,
                    keyword=keyword.strip(),
                    limit=limit,
                    offset=offset,
                    start_time=start_time,
                    end_time=end_time,
                )
                total = self.usage_repository.count_usage_logs(
                    user_id=user_id,
                    keyword=keyword.strip(),
                    start_time=start_time,
                    end_time=end_time,
                )
            return {
                "records": [_feedback_usage_option(record) for record in records],
                "groups": [],
                "total": total,
                "page": offset // limit + 1,
                "limit": limit,
                "deduplicated": False,
            }

        with self.lock:
            groups = self.usage_repository.list_question_groups(
                user_id=user_id,
                keyword=keyword.strip(),
                start_time=start_time,
                end_time=end_time,
                limit=limit,
                offset=offset,
            )
            total = self.usage_repository.count_question_groups(
                user_id=user_id,
                keyword=keyword.strip(),
                start_time=start_time,
                end_time=end_time,
            )
            question_ids = [str(group["question_id"]) for group in groups if group["question_id"]]
            latest_by_question = self.usage_repository.latest_usage_logs_for_question_ids(
                user_id=user_id,
                question_ids=question_ids,
                keyword=keyword.strip(),
                start_time=start_time,
                end_time=end_time,
            )
            unlinked_ids = [
                str(group["group_key"])
                for group in groups
                if not group["question_id"]
            ]
            latest_unlinked = self.usage_repository.get_usage_logs_by_ids(
                unlinked_ids,
                user_id=user_id,
            )
        payload_groups: list[dict] = []
        for group in groups:
            latest = (
                latest_by_question.get(str(group["question_id"]))
                if group["question_id"]
                else latest_unlinked.get(str(group["group_key"]))
            )
            if latest is None:
                continue
            payload_groups.append(
                {
                    "group_key": group["group_key"],
                    "question_id": group["question_id"],
                    "title": latest.title,
                    "question_type": latest.question_type,
                    "attempt_count": group["attempt_count"],
                    "latest": _feedback_usage_option(latest),
                }
            )
        return {
            "records": [],
            "groups": payload_groups,
            "total": total,
            "page": offset // limit + 1,
            "limit": limit,
            "deduplicated": True,
        }

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
        with self.lock:
            records = self._hydrate_feedback_records(
                self.repository.list_feedbacks(
                    username=username,
                    limit=max(1, min(int(limit) + max(0, int(offset)), 5000)),
                )
            )
            payloads = [item.to_dict() for item in records]
        if status:
            payloads = [item for item in payloads if item.get("status") == status]
        if category:
            normalized_category = _normalize_feedback_category_filter(category)
            payloads = [
                item
                for item in payloads
                if item.get("category") in normalized_category
            ]
        start = max(0, int(offset))
        return payloads[start : start + max(1, int(limit))]

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
    ) -> FeedbackResolution:
        """处理用户反馈并返回奖励积分。

        奖励积分按反馈记录中的累计奖励值补差额，避免管理员重复保存时重复发放。
        """
        normalized_status = (status or "resolved").strip().lower()
        if normalized_status not in {"open", "processing", "resolved", "rejected"}:
            raise AuthError("INVALID_FEEDBACK_STATUS", "反馈状态不合法", http_status=400)
        normalized_reward_points = max(0, int(reward_points))
        now = time.time()
        with self.lock:
            try:
                record, granted, changed_fields = self.repository.resolve_feedback_with_reward(
                    feedback_id,
                    status=normalized_status,
                    admin_note=admin_note.strip(),
                    corrected_answer=corrected_answer.strip(),
                    reward_points=normalized_reward_points,
                    handled_by=handled_by,
                    handled_at=now,
                    reward_order_id=secrets.token_hex(12),
                )
            except FeedbackOperationError as exc:
                raise feedback_auth_error(exc) from exc
            record = self._hydrate_feedback_records([record])[0]
        return FeedbackResolution(
            feedback=record.to_dict(),
            granted_points=granted,
            changed_fields=changed_fields,
        )

    def _hydrate_feedback_records(
        self, records: list[FeedbackRecord]
    ) -> list[FeedbackRecord]:
        """用关联的使用记录补齐旧反馈缺失的题目快照。

        早期反馈只保存了 usage_log_id，读取时回填可以修复历史数据的展示和定位，
        同时避免一次反馈列表产生 N+1 次数据库查询。
        """

        usage_ids: list[str] = []
        for record in records:
            context = _json_object(record.context_json)
            usage_id = str(record.usage_log_id or context.get("usage_log_id") or "").strip()
            if usage_id and not record.usage_log_id:
                record.usage_log_id = usage_id
            usage_ids.append(usage_id)

        batch_reader = getattr(self.usage_repository, "get_usage_logs_by_ids", None)
        if callable(batch_reader):
            usage_records = batch_reader(usage_ids)
        else:
            usage_records = {}
            for usage_id in dict.fromkeys(usage_ids):
                if usage_id:
                    usage_record = self.usage_repository.get_usage_log(usage_id)
                    if usage_record is not None:
                        usage_records[usage_id] = usage_record

        return [
            self._hydrate_feedback_record(
                record,
                usage_records.get(str(record.usage_log_id or "")),
            )
            for record in records
        ]

    @staticmethod
    def _hydrate_feedback_record(
        record: FeedbackRecord,
        usage_record: Any | None,
    ) -> FeedbackRecord:
        if usage_record is None or usage_record.user_id != record.user_id:
            return record

        existing_context = _json_object(record.context_json)
        usage_context = _json_object(usage_record.context_json)
        merged_context = dict(usage_context)
        for key, value in existing_context.items():
            if _has_context_value(value) or key not in merged_context:
                merged_context[key] = value

        if not record.question_id and usage_record.question_id:
            record.question_id = usage_record.question_id
        if not record.question_title.strip() and usage_record.title:
            record.question_title = usage_record.title
        if not record.question_type.strip() and usage_record.question_type:
            record.question_type = usage_record.question_type
        if not _has_context_value(record.answer_snapshot) and _has_context_value(
            usage_record.answer
        ):
            record.answer_snapshot = usage_record.answer
        if not record.resolution_mode.strip() and usage_record.resolution_mode:
            record.resolution_mode = usage_record.resolution_mode
        if record.confidence <= 0 and usage_record.confidence > 0:
            record.confidence = usage_record.confidence
        if not record.related_questions:
            record.related_questions = [_usage_relation(usage_record)]
        for field in ("request_id", "source_name", "source_type", "source_id", "source_url"):
            if not str(getattr(record, field) or "").strip() and str(
                getattr(usage_record, field) or ""
            ).strip():
                setattr(record, field, getattr(usage_record, field))

        canonical_values = {
            "usage_log_id": record.usage_log_id or usage_record.log_id,
            "question_id": record.question_id,
            "question_title": record.question_title,
            "question_type": record.question_type,
            "answer_snapshot": record.answer_snapshot,
            "resolution_mode": record.resolution_mode,
            "confidence": record.confidence,
            "request_id": record.request_id,
            "source_name": record.source_name,
            "source_type": record.source_type,
            "source_id": record.source_id,
            "source_url": record.source_url,
        }
        for key, value in canonical_values.items():
            if _has_context_value(value) or key not in merged_context:
                merged_context[key] = value
        record.context_json = json.dumps(merged_context, ensure_ascii=False, sort_keys=True)
        return record


def feedback_auth_error(exc: FeedbackOperationError) -> AuthError:
    """将仓储层反馈异常转换为统一业务错误。"""

    return AuthError(exc.code, exc.message, http_status=exc.http_status)


def _json_object(value: object) -> dict[str, object]:
    """安全解析上下文对象，历史坏数据按空对象处理。"""

    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str):
        return {}
    try:
        payload = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _has_context_value(value: object) -> bool:
    """判断上下文字段是否包含可用值，保留 0 和 False。"""

    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return value not in ([], {})


def _normalize_feedback_category(value: str) -> str:
    raw = (value or "answer").strip().lower()
    aliases = {
        "wrong_answer": "wrong_answer",
        "answer_problem": "wrong_answer",
        "suggestion": "suggestion",
        "feature_suggestion": "suggestion",
        "other": "other",
        "system": "other",
        # 保留旧普通反馈类别，避免历史客户端提交无题目反馈时中断。
        "answer": "answer",
    }
    normalized = aliases.get(raw)
    if normalized is None:
        raise FeedbackOperationError("INVALID_FEEDBACK_CATEGORY", "反馈类型不合法", http_status=400)
    return normalized


def _normalize_feedback_category_filter(value: str) -> set[str]:
    """Map new and historical filter values to the categories stored in feedbacks."""

    raw = (value or "").strip().lower()
    aliases = {
        "wrong_answer": {"wrong_answer", "answer_problem", "answer"},
        "suggestion": {"suggestion", "feature_suggestion"},
        "other": {"other", "system"},
        "answer_problem": {"wrong_answer", "answer_problem", "answer"},
        "answer": {"wrong_answer", "answer_problem", "answer"},
        "feature_suggestion": {"suggestion", "feature_suggestion"},
        "system": {"other", "system"},
    }
    return aliases.get(raw, {raw})


def _normalize_usage_ids(primary: str | None, values: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in (primary, *values):
        item = str(value or "").strip()
        if item and item not in normalized:
            normalized.append(item)
    return tuple(normalized)


def _usage_relation(record: Any) -> dict:
    return {
        "usage_log_id": record.log_id,
        "question_id": record.question_id,
        "question_title": record.title,
        "question_type": record.question_type,
        "answer_snapshot": record.answer,
        "resolution_mode": record.resolution_mode,
        "confidence": float(record.confidence or 0.0),
        "request_id": record.request_id,
        "source_name": record.source_name,
        "source_type": record.source_type,
        "source_id": record.source_id,
        "source_url": record.source_url,
        "created_at": float(record.created_at or 0.0),
    }


def _feedback_usage_option(record: Any) -> dict:
    """返回选择器所需的最小答题记录字段，不泄露请求 IP 或完整上下文。"""

    return {
        "log_id": record.log_id,
        "question_id": record.question_id,
        "title": record.title,
        "question_type": record.question_type,
        "answer": record.answer,
        "resolution_mode": record.resolution_mode,
        "confidence": float(record.confidence or 0.0),
        "created_at": float(record.created_at or 0.0),
        "points_cost": int(record.points_cost or 0),
        "provider": record.provider,
        "source_name": record.source_name,
    }

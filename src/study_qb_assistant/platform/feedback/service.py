"""用户反馈服务。"""

from __future__ import annotations

import json
import secrets
import time
from threading import RLock
from typing import Any

from ...auth import AuthError
from ..base import PlatformDomainService
from .errors import FeedbackOperationError
from .records import FeedbackRecord


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
        title: str,
        content: str,
        image_urls: tuple[str, ...],
        category: str = "answer",
    ) -> dict:
        """创建一条错题反馈记录。"""
        usage_record = None
        if usage_log_id:
            with self.lock:
                usage_record = self.usage_repository.get_usage_log(usage_log_id)
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
        with self.lock:
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
        with self.lock:
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
        with self.lock:
            try:
                record, granted = self.repository.resolve_feedback_with_reward(
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
        return record.to_dict(), granted


def feedback_auth_error(exc: FeedbackOperationError) -> AuthError:
    """将仓储层反馈异常转换为统一业务错误。"""

    return AuthError(exc.code, exc.message, http_status=exc.http_status)

"""用户反馈仓储。"""

from __future__ import annotations

import json

from sqlalchemy import select

from ...platform.feedback.errors import FeedbackOperationError
from ...platform.feedback.records import FeedbackRecord
from ..orm import FeedbackEntity, UserEntity, WalletOrderEntity
from .base import SqlAlchemyRepository


class FeedbackRepository(SqlAlchemyRepository):
    """FeedbackRepository 实现。"""

    def save_feedback(self, record: FeedbackRecord) -> None:
        with self.session_factory() as session:
            entity = FeedbackEntity(
                feedback_id=record.feedback_id,
                user_id=record.user_id,
                username=record.username,
                usage_log_id=record.usage_log_id,
                title=record.title,
                content=record.content,
                image_urls=json.dumps(list(record.image_urls), ensure_ascii=False),
                category=record.category,
                status=record.status,
                admin_note=record.admin_note,
                corrected_answer=record.corrected_answer,
                reward_points=record.reward_points,
                handled_by=record.handled_by,
                handled_at=record.handled_at,
                created_at=record.created_at,
                question_id=record.question_id,
                question_title=record.question_title,
                question_type=record.question_type,
                answer_snapshot=record.answer_snapshot,
                resolution_mode=record.resolution_mode,
                confidence=record.confidence,
                request_id=record.request_id,
                source_name=record.source_name,
                source_type=record.source_type,
                source_id=record.source_id,
                source_url=record.source_url,
                context_json=record.context_json,
            )
            session.add(entity)
            session.commit()

    def list_feedbacks(
        self, *, username: str | None = None, limit: int = 100
    ) -> list[FeedbackRecord]:
        with self.session_factory() as session:
            stmt = select(FeedbackEntity).order_by(FeedbackEntity.created_at.desc())
            if username:
                stmt = stmt.where(FeedbackEntity.username == username)
            entities = session.scalars(stmt.limit(max(1, min(limit, 500)))).all()
            return [self._feedback_record(entity) for entity in entities]

    def get_feedback(self, feedback_id: str) -> FeedbackRecord | None:
        """读取单条反馈记录。"""
        with self.session_factory() as session:
            entity = session.scalar(
                select(FeedbackEntity).where(FeedbackEntity.feedback_id == feedback_id)
            )
            return self._feedback_record(entity) if entity else None

    def update_feedback_status(self, feedback_id: str, status: str) -> FeedbackRecord | None:
        """更新反馈处理状态。"""
        with self.session_factory() as session:
            entity = session.scalar(
                select(FeedbackEntity).where(FeedbackEntity.feedback_id == feedback_id)
            )
            if entity is None:
                return None
            entity.status = status
            session.commit()
            return self._feedback_record(entity)

    def resolve_feedback_with_reward(
        self,
        feedback_id: str,
        *,
        status: str,
        admin_note: str,
        corrected_answer: str,
        reward_points: int,
        handled_by: str,
        handled_at: float,
        reward_order_id: str,
    ) -> tuple[FeedbackRecord, int, tuple[str, ...]]:
        """原子更新反馈处理结果、奖励积分和钱包流水。"""

        with self.session_factory() as session:
            try:
                entity = session.scalar(
                    select(FeedbackEntity)
                    .where(FeedbackEntity.feedback_id == feedback_id)
                    .with_for_update()
                )
                if entity is None:
                    raise FeedbackOperationError(
                        "FEEDBACK_NOT_FOUND", "反馈不存在", http_status=404
                    )

                previous_values = {
                    "status": entity.status,
                    "admin_note": entity.admin_note,
                    "corrected_answer": entity.corrected_answer,
                    "reward_points": int(entity.reward_points or 0),
                }
                previous_reward = max(0, int(entity.reward_points or 0))
                stored_reward = (
                    max(previous_reward, max(0, int(reward_points)))
                    if status == "resolved"
                    else previous_reward
                )
                granted_points = (
                    max(0, stored_reward - previous_reward) if status == "resolved" else 0
                )

                entity.status = status
                entity.admin_note = admin_note
                entity.corrected_answer = corrected_answer
                entity.reward_points = stored_reward
                entity.handled_by = handled_by
                entity.handled_at = handled_at

                if granted_points > 0:
                    user = session.scalar(
                        select(UserEntity)
                        .where(UserEntity.user_id == entity.user_id)
                        .with_for_update()
                    )
                    if user is None or user.username != entity.username:
                        raise FeedbackOperationError(
                            "USER_NOT_FOUND", "反馈提交用户不存在", http_status=404
                        )
                    user.points = int(user.points or 0) + granted_points
                    session.add(
                        WalletOrderEntity(
                            order_id=reward_order_id,
                            user_id=entity.user_id,
                            username=entity.username,
                            kind="points",
                            points_delta=granted_points,
                            days_delta=0,
                            source="feedback_reward",
                            source_id=entity.feedback_id,
                            status="completed",
                            created_by=handled_by,
                            created_at=handled_at,
                        )
                    )
                session.commit()
            except Exception:
                session.rollback()
                raise
            record = self._feedback_record(entity)
            current_values = {
                "status": record.status,
                "admin_note": record.admin_note,
                "corrected_answer": record.corrected_answer,
                "reward_points": record.reward_points,
            }
            changed_fields = tuple(
                field
                for field in previous_values
                if previous_values[field] != current_values[field]
            )
            return record, granted_points, changed_fields

    def _feedback_record(self, entity: FeedbackEntity) -> FeedbackRecord:
        image_urls = tuple(json.loads(entity.image_urls or "[]"))
        return FeedbackRecord(
            feedback_id=entity.feedback_id,
            user_id=entity.user_id,
            username=entity.username,
            usage_log_id=entity.usage_log_id,
            title=entity.title,
            content=entity.content,
            image_urls=image_urls,
            status=entity.status,
            created_at=entity.created_at,
            category=entity.category,
            admin_note=entity.admin_note,
            corrected_answer=entity.corrected_answer,
            reward_points=entity.reward_points,
            handled_by=entity.handled_by,
            handled_at=entity.handled_at,
            question_id=(
                str(getattr(entity, "question_id", "") or "")
                if getattr(entity, "question_id", None)
                else None
            ),
            question_title=str(getattr(entity, "question_title", "") or ""),
            question_type=str(getattr(entity, "question_type", "") or ""),
            answer_snapshot=(
                str(getattr(entity, "answer_snapshot", ""))
                if getattr(entity, "answer_snapshot", None) is not None
                else None
            ),
            resolution_mode=str(getattr(entity, "resolution_mode", "") or ""),
            confidence=float(getattr(entity, "confidence", 0.0) or 0.0),
            request_id=str(getattr(entity, "request_id", "") or ""),
            source_name=str(getattr(entity, "source_name", "") or ""),
            source_type=str(getattr(entity, "source_type", "") or ""),
            source_id=str(getattr(entity, "source_id", "") or ""),
            source_url=str(getattr(entity, "source_url", "") or ""),
            context_json=str(getattr(entity, "context_json", "{}") or "{}"),
        )

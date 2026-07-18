"""使用记录与计费原子事务仓储。"""

from __future__ import annotations

from sqlalchemy import case, func, select

from ...auth import AuthError
from ...platform.usage.records import UsageLogRecord
from ..orm import ApiTokenEntity, UserEntity, UsageLogEntity
from .base import SqlAlchemyRepository


class UsageRepository(SqlAlchemyRepository):
    """UsageRepository 实现。"""

    def save_usage_log(self, record: UsageLogRecord) -> None:
        with self.session_factory() as session:
            entity = UsageLogEntity(
                log_id=record.log_id,
                user_id=record.user_id,
                username=record.username,
                token_id=record.token_id,
                title=record.title,
                question_type=record.question_type,
                resolution_mode=record.resolution_mode,
                answer=record.answer,
                confidence=record.confidence,
                points_cost=record.points_cost,
                provider=record.provider,
                elapsed_ms=record.elapsed_ms,
                created_at=record.created_at,
                request_id=record.request_id,
                client_ip=record.client_ip,
                question_id=record.question_id,
                source_name=record.source_name,
                source_type=record.source_type,
                source_id=record.source_id,
                source_url=record.source_url,
                context_json=record.context_json,
            )
            session.add(entity)
            session.commit()

    def save_usage_log_and_update_token(
        self,
        record: UsageLogRecord,
        *,
        token_id: str | None = None,
    ) -> None:
        """在同一事务内写入使用日志并同步更新令牌计数。"""

        with self.session_factory() as session:
            entity = UsageLogEntity(
                log_id=record.log_id,
                user_id=record.user_id,
                username=record.username,
                token_id=record.token_id,
                title=record.title,
                question_type=record.question_type,
                resolution_mode=record.resolution_mode,
                answer=record.answer,
                confidence=record.confidence,
                points_cost=record.points_cost,
                provider=record.provider,
                elapsed_ms=record.elapsed_ms,
                created_at=record.created_at,
                request_id=record.request_id,
                client_ip=record.client_ip,
                question_id=record.question_id,
                source_name=record.source_name,
                source_type=record.source_type,
                source_id=record.source_id,
                source_url=record.source_url,
                context_json=record.context_json,
            )
            session.add(entity)
            if token_id:
                token_entity = session.scalar(
                    select(ApiTokenEntity).where(ApiTokenEntity.token_id == token_id)
                )
                if token_entity is not None:
                    token_entity.last_used_at = record.created_at
                    token_entity.usage_count = int(token_entity.usage_count or 0) + 1
                    token_entity.quota_used = int(token_entity.quota_used or 0) + 1
            session.commit()

    def commit_usage_transaction(
        self,
        record: UsageLogRecord,
        *,
        token_id: str | None = None,
        points_cost: int = 0,
    ) -> None:
        """在单事务内完成额度校验、积分扣减、令牌计数与 usage log 落库。"""

        with self.session_factory() as session:
            token_entity: ApiTokenEntity | None = None
            if token_id:
                token_entity = session.scalar(
                    select(ApiTokenEntity).where(ApiTokenEntity.token_id == token_id)
                )
                if token_entity is None or token_entity.status != "active":
                    raise AuthError("UNAUTHORIZED", "请提供有效 API Key", http_status=401)
                quota_limit = int(getattr(token_entity, "quota_limit", -1) or -1)
                quota_used = int(getattr(token_entity, "quota_used", 0) or 0)
                if quota_limit >= 0 and quota_used + 1 > quota_limit:
                    raise AuthError(
                        "TOKEN_QUOTA_EXCEEDED",
                        "API Key 调用额度已用完",
                        http_status=401,
                    )

            user_entity = session.scalar(
                select(UserEntity).where(UserEntity.user_id == record.user_id)
            )
            if user_entity is None:
                raise AuthError("USER_NOT_FOUND", "用户不存在", http_status=404)

            normalized_points = max(0, int(points_cost))
            if normalized_points > 0:
                current_points = int(user_entity.points or 0)
                if current_points >= normalized_points:
                    user_entity.points = current_points - normalized_points
                else:
                    normalized_points = 0
            record.points_cost = normalized_points

            entity = UsageLogEntity(
                log_id=record.log_id,
                user_id=record.user_id,
                username=record.username,
                token_id=record.token_id,
                title=record.title,
                question_type=record.question_type,
                resolution_mode=record.resolution_mode,
                answer=record.answer,
                confidence=record.confidence,
                points_cost=record.points_cost,
                provider=record.provider,
                elapsed_ms=record.elapsed_ms,
                created_at=record.created_at,
                request_id=record.request_id,
                client_ip=record.client_ip,
                question_id=record.question_id,
                source_name=record.source_name,
                source_type=record.source_type,
                source_id=record.source_id,
                source_url=record.source_url,
                context_json=record.context_json,
            )
            session.add(entity)
            if token_entity is not None:
                token_entity.last_used_at = record.created_at
                token_entity.usage_count = int(token_entity.usage_count or 0) + 1
                token_entity.quota_used = int(token_entity.quota_used or 0) + 1
            session.commit()

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
    ) -> list[UsageLogRecord]:
        with self.session_factory() as session:
            stmt = select(UsageLogEntity).order_by(UsageLogEntity.created_at.desc())
            stmt = self._apply_usage_log_filters(
                stmt,
                username=username,
                token_id=token_id,
                keyword=keyword,
                start_time=start_time,
                end_time=end_time,
            )
            stmt = stmt.outerjoin(ApiTokenEntity, UsageLogEntity.token_id == ApiTokenEntity.token_id)
            rows = session.execute(
                stmt.with_only_columns(UsageLogEntity, ApiTokenEntity)
                .offset(max(0, int(offset)))
                .limit(max(1, min(limit, 5000)))
            ).all()
            return [
                self._usage_log_record(log_entity, token_entity)
                for log_entity, token_entity in rows
            ]

    def get_usage_log(self, log_id: str) -> UsageLogRecord | None:
        """按日志 ID 读取单条使用记录。"""

        with self.session_factory() as session:
            row = session.execute(
                select(UsageLogEntity, ApiTokenEntity)
                .outerjoin(ApiTokenEntity, UsageLogEntity.token_id == ApiTokenEntity.token_id)
                .where(UsageLogEntity.log_id == log_id)
            ).first()
            return self._usage_log_record(row[0], row[1]) if row else None

    def count_usage_logs(
        self,
        *,
        username: str | None = None,
        token_id: str = "",
        keyword: str = "",
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> int:
        with self.session_factory() as session:
            stmt = select(func.count(UsageLogEntity.id))
            stmt = self._apply_usage_log_filters(
                stmt,
                username=username,
                token_id=token_id,
                keyword=keyword,
                start_time=start_time,
                end_time=end_time,
            )
            return int(session.scalar(stmt) or 0)

    def usage_overview(
        self,
        *,
        username: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> dict[str, float]:
        """聚合指定范围内的调用概览。"""

        with self.session_factory() as session:
            stmt = select(
                func.count(UsageLogEntity.id),
                func.sum(
                    case((UsageLogEntity.resolution_mode != "model_error", 1), else_=0)
                ),
                func.avg(
                    case((UsageLogEntity.elapsed_ms > 0, UsageLogEntity.elapsed_ms), else_=None)
                ),
                func.sum(UsageLogEntity.points_cost),
            )
            stmt = self._apply_usage_log_filters(
                stmt,
                username=username,
                start_time=start_time,
                end_time=end_time,
            )
            total_count, success_count, avg_elapsed_ms, points_used = session.execute(stmt).one()
        return {
            "total_count": float(total_count or 0),
            "success_count": float(success_count or 0),
            "avg_elapsed_ms": float(avg_elapsed_ms or 0.0),
            "points_used": float(points_used or 0),
        }

    def usage_counts_by_field(
        self,
        field: str,
        *,
        username: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        limit: int | None = None,
    ) -> list[tuple[str, int]]:
        """按指定字段聚合使用日志数量。"""

        column_map = {
            "provider": UsageLogEntity.provider,
            "question_type": UsageLogEntity.question_type,
            "username": UsageLogEntity.username,
            "resolution_mode": UsageLogEntity.resolution_mode,
        }
        column = column_map.get(field)
        if column is None:
            return []
        with self.session_factory() as session:
            stmt = select(column, func.count(UsageLogEntity.id))
            stmt = self._apply_usage_log_filters(
                stmt,
                username=username,
                start_time=start_time,
                end_time=end_time,
            )
            stmt = stmt.group_by(column).order_by(func.count(UsageLogEntity.id).desc(), column.asc())
            if limit is not None:
                stmt = stmt.limit(max(1, min(int(limit), 100)))
            rows = session.execute(stmt).all()
        return [(str(value or "unknown"), int(count or 0)) for value, count in rows]

    def token_counter_totals(self) -> dict[str, int]:
        """读取 API Key 累计计数总览。"""

        with self.session_factory() as session:
            usage_count, quota_used = session.execute(
                select(
                    func.sum(ApiTokenEntity.usage_count),
                    func.sum(ApiTokenEntity.quota_used),
                )
            ).one()
        return {
            "usage_count_total": int(usage_count or 0),
            "quota_used_total": int(quota_used or 0),
        }

    def _apply_usage_log_filters(
        self,
        stmt,
        *,
        username: str | None = None,
        token_id: str = "",
        keyword: str = "",
        start_time: float | None = None,
        end_time: float | None = None,
    ):
        if username:
            stmt = stmt.where(UsageLogEntity.username == username)
        if token_id:
            stmt = stmt.where(UsageLogEntity.token_id == token_id)
        if keyword:
            stmt = stmt.where(UsageLogEntity.title.contains(keyword))
        if start_time is not None:
            stmt = stmt.where(UsageLogEntity.created_at >= start_time)
        if end_time is not None:
            stmt = stmt.where(UsageLogEntity.created_at < end_time)
        return stmt

    def _usage_log_record(
        self,
        entity: UsageLogEntity,
        token_entity: ApiTokenEntity | None = None,
    ) -> UsageLogRecord:
        token_description, token_key_mask, token_label = self._usage_log_token_display(
            entity.token_id,
            token_entity,
        )
        return UsageLogRecord(
            log_id=entity.log_id,
            user_id=entity.user_id,
            username=entity.username,
            token_id=entity.token_id,
            token_description=token_description,
            token_key_mask=token_key_mask,
            token_label=token_label,
            title=entity.title,
            question_type=entity.question_type,
            resolution_mode=entity.resolution_mode,
            answer=entity.answer,
            confidence=entity.confidence,
            points_cost=entity.points_cost,
            provider=entity.provider,
            elapsed_ms=float(getattr(entity, "elapsed_ms", 0.0) or 0.0),
            created_at=entity.created_at,
            request_id=str(getattr(entity, "request_id", "") or ""),
            client_ip=str(getattr(entity, "client_ip", "") or ""),
            question_id=(
                str(getattr(entity, "question_id", "") or "")
                if getattr(entity, "question_id", None)
                else None
            ),
            source_name=str(getattr(entity, "source_name", "") or ""),
            source_type=str(getattr(entity, "source_type", "") or ""),
            source_id=str(getattr(entity, "source_id", "") or ""),
            source_url=str(getattr(entity, "source_url", "") or ""),
            context_json=str(getattr(entity, "context_json", "{}") or "{}"),
        )

    def _usage_log_token_display(
        self,
        token_id: str | None,
        token_entity: ApiTokenEntity | None,
    ) -> tuple[str, str, str]:
        """生成使用记录里可安全展示的 API Key 标识。"""

        if not token_id:
            return "", "", ""
        if token_entity is None:
            return "", "", self._compact_identifier(token_id)

        description = str(getattr(token_entity, "description", "") or "").strip()
        key_mask = str(getattr(token_entity, "key_mask", "") or "").strip()
        label = description or key_mask or self._compact_identifier(token_id)
        return description, key_mask, label

    @staticmethod
    def _compact_identifier(value: str) -> str:
        """把缺失令牌记录里的 ID 压缩成便于排查且不抢眼的短标识。"""

        text = str(value or "").strip()
        if len(text) <= 12:
            return text
        return f"{text[:8]}...{text[-4:]}"

"""平台数据的 SQLAlchemy 仓储。"""

from __future__ import annotations

import json

from sqlalchemy import delete, select

from ..platform.records import (
    ApiTokenRecord,
    FeedbackRecord,
    ImportScriptRecord,
    LlmCallTraceRecord,
    LlmModelRecord,
    NotificationRecord,
    RedeemCodeRecord,
    RolePermissionRecord,
    UsageLogRecord,
    WalletOrderRecord,
)
from .database import get_session_factory
from . import llm_repository
from .orm import (
    ApiTokenEntity,
    FeedbackEntity,
    ImportScriptEntity,
    NotificationEntity,
    RedeemCodeEntity,
    SettingEntity,
    UsageLogEntity,
    WalletOrderEntity,
)


class SqlAlchemyPlatformRepository:
    """平台状态仓储。"""

    def __init__(self, path_or_url) -> None:
        self.session_factory = get_session_factory(path_or_url)

    def save_token(self, record: ApiTokenRecord) -> None:
        with self.session_factory() as session:
            entity = session.scalar(
                select(ApiTokenEntity).where(ApiTokenEntity.token_id == record.token_id)
            )
            if entity is None:
                entity = ApiTokenEntity(token_id=record.token_id, key_hash=record.key_hash)
                session.add(entity)
            self._apply_token(entity, record)
            session.commit()

    def list_tokens(self, *, user_id: str) -> list[ApiTokenRecord]:
        with self.session_factory() as session:
            entities = session.scalars(
                select(ApiTokenEntity).where(ApiTokenEntity.user_id == user_id)
            ).all()
            return [self._token_record(entity) for entity in entities]

    def delete_token(self, token_id: str) -> bool:
        """删除指定 API Key 记录。"""
        with self.session_factory() as session:
            entity = session.scalar(
                select(ApiTokenEntity).where(ApiTokenEntity.token_id == token_id)
            )
            if entity is None:
                return False
            session.delete(entity)
            session.commit()
            return True

    def find_token_by_hash(self, key_hash: str) -> ApiTokenRecord | None:
        with self.session_factory() as session:
            entity = session.scalar(
                select(ApiTokenEntity).where(ApiTokenEntity.key_hash == key_hash)
            )
            return self._token_record(entity) if entity else None

    def get_token(self, token_id: str) -> ApiTokenRecord | None:
        with self.session_factory() as session:
            entity = session.scalar(
                select(ApiTokenEntity).where(ApiTokenEntity.token_id == token_id)
            )
            return self._token_record(entity) if entity else None

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
            )
            session.add(entity)
            session.commit()

    def list_usage_logs(
        self,
        *,
        username: str | None = None,
        token_id: str = "",
        keyword: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[UsageLogRecord]:
        with self.session_factory() as session:
            stmt = select(UsageLogEntity).order_by(UsageLogEntity.created_at.desc())
            if username:
                stmt = stmt.where(UsageLogEntity.username == username)
            if token_id:
                stmt = stmt.where(UsageLogEntity.token_id == token_id)
            if keyword:
                stmt = stmt.where(UsageLogEntity.title.contains(keyword))
            entities = session.scalars(
                stmt.offset(max(0, int(offset))).limit(max(1, min(limit, 500)))
            ).all()
            return [self._usage_log_record(entity) for entity in entities]

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

    def update_feedback_resolution(
        self,
        feedback_id: str,
        *,
        status: str,
        admin_note: str,
        corrected_answer: str,
        reward_points: int,
        handled_by: str,
        handled_at: float,
    ) -> FeedbackRecord | None:
        """更新反馈处理结果。"""
        with self.session_factory() as session:
            entity = session.scalar(
                select(FeedbackEntity).where(FeedbackEntity.feedback_id == feedback_id)
            )
            if entity is None:
                return None
            entity.status = status
            entity.admin_note = admin_note
            entity.corrected_answer = corrected_answer
            entity.reward_points = max(0, int(reward_points))
            entity.handled_by = handled_by
            entity.handled_at = handled_at
            session.commit()
            return self._feedback_record(entity)

    def save_redeem_code(self, record: RedeemCodeRecord) -> None:
        with self.session_factory() as session:
            entity = session.scalar(
                select(RedeemCodeEntity).where(RedeemCodeEntity.code_id == record.code_id)
            )
            if entity is None:
                entity = RedeemCodeEntity(code_id=record.code_id, code=record.code)
                session.add(entity)
            self._apply_redeem_code(entity, record)
            session.commit()

    def list_redeem_codes(self) -> list[RedeemCodeRecord]:
        with self.session_factory() as session:
            entities = session.scalars(
                select(RedeemCodeEntity).order_by(RedeemCodeEntity.created_at.desc())
            ).all()
            return [self._redeem_code_record(entity) for entity in entities]

    def find_redeem_code_by_code(self, code: str) -> RedeemCodeRecord | None:
        with self.session_factory() as session:
            entity = session.scalar(select(RedeemCodeEntity).where(RedeemCodeEntity.code == code))
            return self._redeem_code_record(entity) if entity else None

    def save_wallet_order(self, record: WalletOrderRecord) -> None:
        with self.session_factory() as session:
            entity = WalletOrderEntity(
                order_id=record.order_id,
                user_id=record.user_id,
                username=record.username,
                kind=record.kind,
                points_delta=record.points_delta,
                source=record.source,
                source_id=record.source_id,
                status=record.status,
                created_by=record.created_by,
                created_at=record.created_at,
            )
            session.add(entity)
            session.commit()

    def list_wallet_orders(
        self,
        *,
        username: str | None = None,
        kind: str = "",
        source: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[WalletOrderRecord]:
        with self.session_factory() as session:
            stmt = select(WalletOrderEntity).order_by(WalletOrderEntity.created_at.desc())
            if username:
                stmt = stmt.where(WalletOrderEntity.username == username)
            if kind:
                stmt = stmt.where(WalletOrderEntity.kind == kind)
            if source:
                stmt = stmt.where(WalletOrderEntity.source == source)
            entities = session.scalars(
                stmt.offset(max(0, int(offset))).limit(max(1, min(limit, 500)))
            ).all()
            return [self._wallet_order_record(entity) for entity in entities]

    def get_settings(self, scope: str, *, keys: set[str] | None = None) -> dict[str, str]:
        with self.session_factory() as session:
            stmt = select(SettingEntity).where(SettingEntity.scope == scope)
            if keys:
                stmt = stmt.where(SettingEntity.key.in_(keys))
            entities = session.scalars(stmt).all()
            return {entity.key: entity.value for entity in entities}

    def set_settings(self, scope: str, values: dict[str, str]) -> None:
        with self.session_factory() as session:
            for key, value in values.items():
                entity = session.scalar(
                    select(SettingEntity).where(
                        SettingEntity.scope == scope, SettingEntity.key == key
                    )
                )
                if entity is None:
                    entity = SettingEntity(scope=scope, key=key, value=value)
                    session.add(entity)
                else:
                    entity.value = value
            session.commit()

    def replace_settings(self, scope: str, values: dict[str, str]) -> None:
        with self.session_factory() as session:
            session.execute(delete(SettingEntity).where(SettingEntity.scope == scope))
            for key, value in values.items():
                session.add(SettingEntity(scope=scope, key=key, value=value))
            session.commit()

    def save_notification(self, record: NotificationRecord) -> None:
        with self.session_factory() as session:
            entity = session.scalar(
                select(NotificationEntity).where(
                    NotificationEntity.notification_id == record.notification_id
                )
            )
            if entity is None:
                entity = NotificationEntity(notification_id=record.notification_id)
                session.add(entity)
            entity.user_id = record.user_id
            entity.level = record.level
            entity.category = record.category
            entity.title = record.title
            entity.content = record.content
            entity.read = 1 if record.read else 0
            entity.created_at = record.created_at
            session.commit()

    def list_notifications(
        self, *, user_id: str | None = None, status: str = "", limit: int = 100
    ) -> list[NotificationRecord]:
        with self.session_factory() as session:
            stmt = select(NotificationEntity).order_by(NotificationEntity.created_at.desc())
            if user_id:
                stmt = stmt.where(
                    (NotificationEntity.user_id == user_id) | (NotificationEntity.user_id.is_(None))
                )
            if status == "read":
                stmt = stmt.where(NotificationEntity.read == 1)
            elif status == "unread":
                stmt = stmt.where(NotificationEntity.read == 0)
            entities = session.scalars(stmt.limit(max(1, min(limit, 500)))).all()
            return [self._notification_record(entity) for entity in entities]

    def get_notification(self, notification_id: str) -> NotificationRecord | None:
        with self.session_factory() as session:
            entity = session.scalar(
                select(NotificationEntity).where(
                    NotificationEntity.notification_id == notification_id
                )
            )
            return self._notification_record(entity) if entity else None

    def save_import_script(self, record: ImportScriptRecord) -> None:
        with self.session_factory() as session:
            entity = session.scalar(
                select(ImportScriptEntity).where(ImportScriptEntity.script_id == record.script_id)
            )
            if entity is None:
                entity = ImportScriptEntity(script_id=record.script_id)
                session.add(entity)
            self._apply_import_script(entity, record)
            session.commit()

    def list_import_scripts(self) -> list[ImportScriptRecord]:
        with self.session_factory() as session:
            entities = session.scalars(
                select(ImportScriptEntity).order_by(ImportScriptEntity.created_at.desc())
            ).all()
            return [self._import_script_record(entity) for entity in entities]

    def get_import_script(self, script_id: str) -> ImportScriptRecord | None:
        with self.session_factory() as session:
            entity = session.scalar(
                select(ImportScriptEntity).where(ImportScriptEntity.script_id == script_id)
            )
            return self._import_script_record(entity) if entity else None

    def delete_import_script(self, script_id: str) -> bool:
        with self.session_factory() as session:
            entity = session.scalar(
                select(ImportScriptEntity).where(ImportScriptEntity.script_id == script_id)
            )
            if entity is None:
                return False
            session.delete(entity)
            session.commit()
            return True

    def list_llm_models(self) -> list[LlmModelRecord]:
        """读取所有大模型配置。"""

        return llm_repository.list_llm_models(self.session_factory)

    def get_llm_model(self, model_id: str) -> LlmModelRecord | None:
        """读取单个大模型配置。"""

        return llm_repository.get_llm_model(self.session_factory, model_id)

    def save_llm_model(self, record: LlmModelRecord) -> LlmModelRecord:
        """新增或更新大模型配置。"""

        return llm_repository.save_llm_model(self.session_factory, record)

    def delete_llm_model(self, model_id: str) -> bool:
        """删除大模型配置。"""

        return llm_repository.delete_llm_model(self.session_factory, model_id)

    def save_llm_call_trace(self, record: LlmCallTraceRecord) -> None:
        """保存大模型调用追溯。"""

        llm_repository.save_llm_call_trace(self.session_factory, record)

    def list_llm_call_traces(
        self,
        *,
        request_id: str = "",
        model_id: str = "",
        phase: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[LlmCallTraceRecord]:
        """分页读取大模型调用追溯。"""

        return llm_repository.list_llm_call_traces(
            self.session_factory,
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
        """统计大模型调用追溯数量。"""

        return llm_repository.count_llm_call_traces(
            self.session_factory,
            request_id=request_id,
            model_id=model_id,
            phase=phase,
        )

    def llm_call_stats(self) -> list[dict]:
        """汇总大模型调用追溯统计。"""

        return llm_repository.llm_call_stats(self.session_factory)

    def get_role_permissions(self) -> list[RolePermissionRecord]:
        raw = self.get_settings("role_permissions")
        result: list[RolePermissionRecord] = []
        for role_id, payload in raw.items():
            try:
                decoded = json.loads(payload)
            except json.JSONDecodeError:
                decoded = {"permissions": [], "updated_at": 0.0}
            result.append(
                RolePermissionRecord(
                    role_id=role_id,
                    permissions=tuple(str(item) for item in decoded.get("permissions") or ()),
                    updated_at=float(decoded.get("updated_at") or 0.0),
                )
            )
        return result

    def set_role_permissions(
        self, role_id: str, permissions: tuple[str, ...], updated_at: float
    ) -> None:
        payload = json.dumps(
            {"permissions": list(permissions), "updated_at": updated_at}, ensure_ascii=False
        )
        self.set_settings("role_permissions", {role_id: payload})

    def _apply_token(self, entity: ApiTokenEntity, record: ApiTokenRecord) -> None:
        entity.token_id = record.token_id
        entity.user_id = record.user_id
        entity.key_hash = record.key_hash
        entity.key_mask = record.key_mask
        entity.description = record.description
        entity.status = record.status
        entity.created_at = record.created_at
        entity.last_used_at = record.last_used_at
        entity.usage_count = record.usage_count
        entity.quota_limit = record.quota_limit
        entity.reject_low_confidence = 1 if record.reject_low_confidence else 0
        entity.min_answer_confidence = record.min_answer_confidence

    def _token_record(self, entity: ApiTokenEntity) -> ApiTokenRecord:
        return ApiTokenRecord(
            token_id=entity.token_id,
            user_id=entity.user_id,
            key_hash=entity.key_hash,
            key_mask=entity.key_mask,
            description=entity.description,
            status=entity.status,
            created_at=entity.created_at,
            last_used_at=entity.last_used_at,
            usage_count=entity.usage_count,
            quota_limit=getattr(entity, "quota_limit", -1),
            reject_low_confidence=bool(getattr(entity, "reject_low_confidence", 0)),
            min_answer_confidence=float(
                getattr(entity, "min_answer_confidence", 0.0) or 0.0
            ),
        )

    def _usage_log_record(self, entity: UsageLogEntity) -> UsageLogRecord:
        return UsageLogRecord(
            log_id=entity.log_id,
            user_id=entity.user_id,
            username=entity.username,
            token_id=entity.token_id,
            title=entity.title,
            question_type=entity.question_type,
            resolution_mode=entity.resolution_mode,
            answer=entity.answer,
            confidence=entity.confidence,
            points_cost=entity.points_cost,
            provider=entity.provider,
            elapsed_ms=float(getattr(entity, "elapsed_ms", 0.0) or 0.0),
            created_at=entity.created_at,
        )

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
        )

    def _apply_redeem_code(self, entity: RedeemCodeEntity, record: RedeemCodeRecord) -> None:
        entity.code_id = record.code_id
        entity.code = record.code
        entity.kind = record.kind
        entity.points = record.points
        entity.max_uses = record.max_uses
        entity.used_uses = record.used_uses
        entity.status = record.status
        entity.created_by = record.created_by
        entity.created_at = record.created_at
        entity.expires_at = record.expires_at

    def _redeem_code_record(self, entity: RedeemCodeEntity) -> RedeemCodeRecord:
        return RedeemCodeRecord(
            code_id=entity.code_id,
            code=entity.code,
            kind=entity.kind,
            points=entity.points,
            max_uses=entity.max_uses,
            used_uses=entity.used_uses,
            status=entity.status,
            created_by=entity.created_by,
            created_at=entity.created_at,
            expires_at=entity.expires_at,
        )

    def _wallet_order_record(self, entity: WalletOrderEntity) -> WalletOrderRecord:
        return WalletOrderRecord(
            order_id=entity.order_id,
            user_id=entity.user_id,
            username=entity.username,
            kind=entity.kind,
            points_delta=entity.points_delta,
            source=entity.source,
            source_id=entity.source_id,
            status=entity.status,
            created_by=entity.created_by,
            created_at=entity.created_at,
        )

    def _notification_record(self, entity: NotificationEntity) -> NotificationRecord:
        return NotificationRecord(
            notification_id=entity.notification_id,
            user_id=entity.user_id,
            level=entity.level,
            category=entity.category,
            title=entity.title,
            content=entity.content,
            read=bool(entity.read),
            created_at=entity.created_at,
        )

    def _apply_import_script(self, entity: ImportScriptEntity, record: ImportScriptRecord) -> None:
        entity.script_id = record.script_id
        entity.name = record.name
        entity.integration_id = record.integration_id
        entity.token_id = record.token_id
        entity.target = record.target
        entity.content = record.content
        entity.status = record.status
        entity.created_at = record.created_at
        entity.updated_at = record.updated_at
        entity.description = record.description
        entity.requires_token = 1 if record.requires_token else 0
        entity.tags = json.dumps(list(record.tags), ensure_ascii=False)
        entity.builtin = 1 if record.builtin else 0
        entity.is_default = 1 if record.is_default else 0
        entity.ocs_config = json.dumps(list(record.ocs_config), ensure_ascii=False)

    def _import_script_record(self, entity: ImportScriptEntity) -> ImportScriptRecord:
        return ImportScriptRecord(
            script_id=entity.script_id,
            name=entity.name,
            integration_id=entity.integration_id,
            token_id=entity.token_id,
            target=entity.target,
            content=entity.content,
            status=entity.status,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            description=getattr(entity, "description", "") or "",
            requires_token=bool(getattr(entity, "requires_token", 1)),
            tags=tuple(json.loads(getattr(entity, "tags", "[]") or "[]")),
            builtin=bool(getattr(entity, "builtin", 0)),
            is_default=bool(getattr(entity, "is_default", 0)),
            ocs_config=tuple(json.loads(getattr(entity, "ocs_config", "[]") or "[]")),
        )

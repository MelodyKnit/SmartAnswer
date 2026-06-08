"""平台数据的 SQLAlchemy 仓储。"""

from __future__ import annotations

import json

from sqlalchemy import delete, select

from ..platform.records import (
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
from .database import get_session_factory
from .orm import (
    ApiTokenEntity,
    FeedbackEntity,
    ImportScriptEntity,
    IntegrationEntity,
    NotificationEntity,
    QuotaPackageEntity,
    RedeemCodeEntity,
    SettingEntity,
    UsageLogEntity,
    WalletOrderEntity,
    WalletProfileEntity,
)


class SqlAlchemyPlatformRepository:
    """平台状态仓储。"""

    def __init__(self, path_or_url) -> None:
        self.session_factory = get_session_factory(path_or_url)

    def save_token(self, record: ApiTokenRecord) -> None:
        with self.session_factory() as session:
            entity = session.scalar(select(ApiTokenEntity).where(ApiTokenEntity.token_id == record.token_id))
            if entity is None:
                entity = ApiTokenEntity(token_id=record.token_id, key_hash=record.key_hash)
                session.add(entity)
            self._apply_token(entity, record)
            session.commit()

    def list_tokens(self, *, user_id: str) -> list[ApiTokenRecord]:
        with self.session_factory() as session:
            entities = session.scalars(select(ApiTokenEntity).where(ApiTokenEntity.user_id == user_id)).all()
            return [self._token_record(entity) for entity in entities]

    def find_token_by_hash(self, key_hash: str) -> ApiTokenRecord | None:
        with self.session_factory() as session:
            entity = session.scalar(select(ApiTokenEntity).where(ApiTokenEntity.key_hash == key_hash))
            return self._token_record(entity) if entity else None

    def get_token(self, token_id: str) -> ApiTokenRecord | None:
        with self.session_factory() as session:
            entity = session.scalar(select(ApiTokenEntity).where(ApiTokenEntity.token_id == token_id))
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
                created_at=record.created_at,
            )
            session.add(entity)
            session.commit()

    def list_usage_logs(self, *, username: str | None = None, keyword: str = "", limit: int = 100) -> list[UsageLogRecord]:
        with self.session_factory() as session:
            stmt = select(UsageLogEntity).order_by(UsageLogEntity.created_at.desc())
            if username:
                stmt = stmt.where(UsageLogEntity.username == username)
            if keyword:
                stmt = stmt.where(UsageLogEntity.title.contains(keyword))
            entities = session.scalars(stmt.limit(max(1, min(limit, 500)))).all()
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
                status=record.status,
                created_at=record.created_at,
            )
            session.add(entity)
            session.commit()

    def list_feedbacks(self, *, username: str | None = None, limit: int = 100) -> list[FeedbackRecord]:
        with self.session_factory() as session:
            stmt = select(FeedbackEntity).order_by(FeedbackEntity.created_at.desc())
            if username:
                stmt = stmt.where(FeedbackEntity.username == username)
            entities = session.scalars(stmt.limit(max(1, min(limit, 500)))).all()
            return [self._feedback_record(entity) for entity in entities]

    def get_wallet_profile(self, user_id: str) -> WalletProfileRecord | None:
        with self.session_factory() as session:
            entity = session.scalar(select(WalletProfileEntity).where(WalletProfileEntity.user_id == user_id))
            return self._wallet_profile_record(entity) if entity else None

    def save_wallet_profile(self, record: WalletProfileRecord) -> None:
        with self.session_factory() as session:
            entity = session.scalar(select(WalletProfileEntity).where(WalletProfileEntity.user_id == record.user_id))
            if entity is None:
                entity = WalletProfileEntity(user_id=record.user_id)
                session.add(entity)
            entity.subscription_expires_at = record.subscription_expires_at
            session.commit()

    def save_redeem_code(self, record: RedeemCodeRecord) -> None:
        with self.session_factory() as session:
            entity = session.scalar(select(RedeemCodeEntity).where(RedeemCodeEntity.code_id == record.code_id))
            if entity is None:
                entity = RedeemCodeEntity(code_id=record.code_id, code=record.code)
                session.add(entity)
            self._apply_redeem_code(entity, record)
            session.commit()

    def list_redeem_codes(self) -> list[RedeemCodeRecord]:
        with self.session_factory() as session:
            entities = session.scalars(select(RedeemCodeEntity).order_by(RedeemCodeEntity.created_at.desc())).all()
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
                subscription_days=record.subscription_days,
                source=record.source,
                source_id=record.source_id,
                status=record.status,
                created_by=record.created_by,
                created_at=record.created_at,
            )
            session.add(entity)
            session.commit()

    def list_wallet_orders(self, *, username: str | None = None, limit: int = 100) -> list[WalletOrderRecord]:
        with self.session_factory() as session:
            stmt = select(WalletOrderEntity).order_by(WalletOrderEntity.created_at.desc())
            if username:
                stmt = stmt.where(WalletOrderEntity.username == username)
            entities = session.scalars(stmt.limit(max(1, min(limit, 500)))).all()
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
                    select(SettingEntity).where(SettingEntity.scope == scope, SettingEntity.key == key)
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
            entity = session.scalar(select(NotificationEntity).where(NotificationEntity.notification_id == record.notification_id))
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

    def list_notifications(self, *, user_id: str | None = None, status: str = "", limit: int = 100) -> list[NotificationRecord]:
        with self.session_factory() as session:
            stmt = select(NotificationEntity).order_by(NotificationEntity.created_at.desc())
            if user_id:
                stmt = stmt.where((NotificationEntity.user_id == user_id) | (NotificationEntity.user_id.is_(None)))
            if status == "read":
                stmt = stmt.where(NotificationEntity.read == 1)
            elif status == "unread":
                stmt = stmt.where(NotificationEntity.read == 0)
            entities = session.scalars(stmt.limit(max(1, min(limit, 500)))).all()
            return [self._notification_record(entity) for entity in entities]

    def get_notification(self, notification_id: str) -> NotificationRecord | None:
        with self.session_factory() as session:
            entity = session.scalar(select(NotificationEntity).where(NotificationEntity.notification_id == notification_id))
            return self._notification_record(entity) if entity else None

    def save_integration(self, record: IntegrationRecord) -> None:
        with self.session_factory() as session:
            entity = session.scalar(select(IntegrationEntity).where(IntegrationEntity.integration_id == record.integration_id))
            if entity is None:
                entity = IntegrationEntity(integration_id=record.integration_id)
                session.add(entity)
            self._apply_integration(entity, record)
            session.commit()

    def list_integrations(self) -> list[IntegrationRecord]:
        with self.session_factory() as session:
            entities = session.scalars(select(IntegrationEntity).order_by(IntegrationEntity.created_at.desc())).all()
            return [self._integration_record(entity) for entity in entities]

    def get_integration(self, integration_id: str) -> IntegrationRecord | None:
        with self.session_factory() as session:
            entity = session.scalar(select(IntegrationEntity).where(IntegrationEntity.integration_id == integration_id))
            return self._integration_record(entity) if entity else None

    def delete_integration(self, integration_id: str) -> bool:
        with self.session_factory() as session:
            entity = session.scalar(select(IntegrationEntity).where(IntegrationEntity.integration_id == integration_id))
            if entity is None:
                return False
            session.delete(entity)
            session.commit()
            return True

    def save_import_script(self, record: ImportScriptRecord) -> None:
        with self.session_factory() as session:
            entity = session.scalar(select(ImportScriptEntity).where(ImportScriptEntity.script_id == record.script_id))
            if entity is None:
                entity = ImportScriptEntity(script_id=record.script_id)
                session.add(entity)
            self._apply_import_script(entity, record)
            session.commit()

    def list_import_scripts(self) -> list[ImportScriptRecord]:
        with self.session_factory() as session:
            entities = session.scalars(select(ImportScriptEntity).order_by(ImportScriptEntity.created_at.desc())).all()
            return [self._import_script_record(entity) for entity in entities]

    def get_import_script(self, script_id: str) -> ImportScriptRecord | None:
        with self.session_factory() as session:
            entity = session.scalar(select(ImportScriptEntity).where(ImportScriptEntity.script_id == script_id))
            return self._import_script_record(entity) if entity else None

    def delete_import_script(self, script_id: str) -> bool:
        with self.session_factory() as session:
            entity = session.scalar(select(ImportScriptEntity).where(ImportScriptEntity.script_id == script_id))
            if entity is None:
                return False
            session.delete(entity)
            session.commit()
            return True

    def save_quota_package(self, record: QuotaPackageRecord) -> None:
        with self.session_factory() as session:
            entity = session.scalar(select(QuotaPackageEntity).where(QuotaPackageEntity.package_id == record.package_id))
            if entity is None:
                entity = QuotaPackageEntity(package_id=record.package_id)
                session.add(entity)
            self._apply_quota_package(entity, record)
            session.commit()

    def list_quota_packages(self) -> list[QuotaPackageRecord]:
        with self.session_factory() as session:
            entities = session.scalars(
                select(QuotaPackageEntity).order_by(QuotaPackageEntity.sort_order.asc(), QuotaPackageEntity.created_at.desc())
            ).all()
            return [self._quota_package_record(entity) for entity in entities]

    def get_quota_package(self, package_id: str) -> QuotaPackageRecord | None:
        with self.session_factory() as session:
            entity = session.scalar(select(QuotaPackageEntity).where(QuotaPackageEntity.package_id == package_id))
            return self._quota_package_record(entity) if entity else None

    def delete_quota_package(self, package_id: str) -> bool:
        with self.session_factory() as session:
            entity = session.scalar(select(QuotaPackageEntity).where(QuotaPackageEntity.package_id == package_id))
            if entity is None:
                return False
            session.delete(entity)
            session.commit()
            return True

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

    def set_role_permissions(self, role_id: str, permissions: tuple[str, ...], updated_at: float) -> None:
        payload = json.dumps({"permissions": list(permissions), "updated_at": updated_at}, ensure_ascii=False)
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
        )

    def _wallet_profile_record(self, entity: WalletProfileEntity) -> WalletProfileRecord:
        return WalletProfileRecord(
            user_id=entity.user_id,
            subscription_expires_at=entity.subscription_expires_at,
        )

    def _apply_redeem_code(self, entity: RedeemCodeEntity, record: RedeemCodeRecord) -> None:
        entity.code_id = record.code_id
        entity.code = record.code
        entity.kind = record.kind
        entity.points = record.points
        entity.subscription_days = record.subscription_days
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
            subscription_days=entity.subscription_days,
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
            subscription_days=entity.subscription_days,
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

    def _apply_integration(self, entity: IntegrationEntity, record: IntegrationRecord) -> None:
        entity.integration_id = record.integration_id
        entity.name = record.name
        entity.platform = record.platform
        entity.base_url = record.base_url
        entity.token_id = record.token_id
        entity.status = record.status
        entity.description = record.description
        entity.created_at = record.created_at
        entity.updated_at = record.updated_at
        entity.last_test_at = record.last_test_at
        entity.last_test_status = record.last_test_status
        entity.last_error = record.last_error

    def _integration_record(self, entity: IntegrationEntity) -> IntegrationRecord:
        return IntegrationRecord(
            integration_id=entity.integration_id,
            name=entity.name,
            platform=entity.platform,
            base_url=entity.base_url,
            token_id=entity.token_id,
            status=entity.status,
            description=entity.description,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            last_test_at=entity.last_test_at,
            last_test_status=entity.last_test_status,
            last_error=entity.last_error,
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
        )

    def _apply_quota_package(self, entity: QuotaPackageEntity, record: QuotaPackageRecord) -> None:
        entity.package_id = record.package_id
        entity.name = record.name
        entity.kind = record.kind
        entity.points = record.points
        entity.subscription_days = record.subscription_days
        entity.price = record.price
        entity.status = record.status
        entity.description = record.description
        entity.sort_order = record.sort_order
        entity.created_at = record.created_at
        entity.updated_at = record.updated_at

    def _quota_package_record(self, entity: QuotaPackageEntity) -> QuotaPackageRecord:
        return QuotaPackageRecord(
            package_id=entity.package_id,
            name=entity.name,
            kind=entity.kind,
            points=entity.points,
            subscription_days=entity.subscription_days,
            price=entity.price,
            status=entity.status,
            description=entity.description,
            sort_order=entity.sort_order,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

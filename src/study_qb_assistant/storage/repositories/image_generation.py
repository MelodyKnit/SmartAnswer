"""文本生图模型、任务、资产与积分预扣的 SQLAlchemy 仓储。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult

from ...platform.image_generation.records import (
    ImageGenerationAssetRecord,
    ImageGenerationJobRecord,
    ImageGenerationModelRecord,
    ImageGenerationTraceRecord,
)
from ..orm import (
    ImageGenerationAssetEntity,
    ImageGenerationJobEntity,
    ImageGenerationModelEntity,
    ImageGenerationTraceEntity,
    UserEntity,
    WalletOrderEntity,
)
from .base import SqlAlchemyRepository


ACTIVE_JOB_STATUSES = frozenset({"queued", "running"})
TERMINAL_JOB_STATUSES = frozenset(
    {"succeeded", "failed", "rejected", "cancelled", "deleted"}
)


class ImageGenerationRepositoryError(RuntimeError):
    """仓储层可以安全映射为 API 错误的业务异常。"""

    def __init__(self, code: str, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


class ImageGenerationRepository(SqlAlchemyRepository):
    """处理生图业务需要的原子数据库状态变更。"""

    def list_models(self) -> list[ImageGenerationModelRecord]:
        """按更新时间倒序列出生图模型。"""

        with self.session_factory() as session:
            entities = session.scalars(
                select(ImageGenerationModelEntity).order_by(
                    ImageGenerationModelEntity.updated_at.desc()
                )
            ).all()
            return [image_model_record(entity) for entity in entities]

    def get_model(self, model_id: str) -> ImageGenerationModelRecord | None:
        """读取单个生图模型。"""

        with self.session_factory() as session:
            entity = session.scalar(
                select(ImageGenerationModelEntity).where(
                    ImageGenerationModelEntity.model_id == model_id
                )
            )
            return image_model_record(entity) if entity else None

    def get_active_model(self) -> ImageGenerationModelRecord | None:
        """读取当前唯一启用的生图模型；旧异常数据按最近更新优先。"""

        with self.session_factory() as session:
            entity = session.scalar(
                select(ImageGenerationModelEntity)
                .where(ImageGenerationModelEntity.status == "active")
                .order_by(ImageGenerationModelEntity.updated_at.desc())
                .limit(1)
            )
            return image_model_record(entity) if entity else None

    def save_model(self, record: ImageGenerationModelRecord) -> ImageGenerationModelRecord:
        """新增或更新生图模型配置。"""

        with self.session_factory() as session:
            entity = session.scalar(
                select(ImageGenerationModelEntity).where(
                    ImageGenerationModelEntity.model_id == record.model_id
                )
            )
            if entity is None:
                entity = ImageGenerationModelEntity(model_id=record.model_id)
                session.add(entity)
                entity.created_at = record.created_at
            entity.name = record.name
            entity.provider = record.provider
            entity.base_url = record.base_url
            entity.model = record.model
            entity.api_key = record.api_key
            entity.timeout_seconds = record.timeout_seconds
            entity.status = record.status
            entity.capabilities = record.capabilities
            entity.protocol_config = record.protocol_config
            entity.updated_at = record.updated_at
            if record.status == "active":
                # 首版仅支持单模型执行，启用当前模型时自动停用其它模型，避免任务被隐式分流。
                session.execute(
                    update(ImageGenerationModelEntity)
                    .where(ImageGenerationModelEntity.model_id != record.model_id)
                    .where(ImageGenerationModelEntity.status == "active")
                    .values(status="inactive", updated_at=record.updated_at)
                )
            session.commit()
            return image_model_record(entity)

    def delete_model(self, model_id: str) -> bool:
        """删除未被排队或运行任务引用的模型。"""

        with self.session_factory() as session:
            entity = session.scalar(
                select(ImageGenerationModelEntity).where(
                    ImageGenerationModelEntity.model_id == model_id
                )
            )
            if entity is None:
                return False
            active_job = session.scalar(
                select(ImageGenerationJobEntity.job_id)
                .where(ImageGenerationJobEntity.model_id == model_id)
                .where(ImageGenerationJobEntity.status.in_(ACTIVE_JOB_STATUSES))
                .limit(1)
            )
            if active_job:
                raise ImageGenerationRepositoryError(
                    "MODEL_IN_USE", "该生图模型仍有正在执行的任务", http_status=409
                )
            session.delete(entity)
            session.commit()
            return True

    def create_job_with_reservation(
        self,
        record: ImageGenerationJobRecord,
        *,
        active_limit: int,
        daily_limit: int,
    ) -> tuple[ImageGenerationJobRecord, bool]:
        """原子创建任务与积分预扣，重复幂等键返回原任务。"""

        with self.session_factory() as session:
            # 先对用户行做无副作用更新以串行化同一用户的提交。PostgreSQL 会持有行锁，
            # SQLite 会持有写锁，因此后续的幂等、限额与扣费检查看到的是同一份最新状态。
            locked = cast(
                CursorResult[Any],
                session.execute(
                    update(UserEntity)
                    .where(UserEntity.user_id == record.user_id)
                    .where(UserEntity.status == "active")
                    .values(points=UserEntity.points)
                ),
            )
            if locked.rowcount != 1:
                raise ImageGenerationRepositoryError("USER_NOT_FOUND", "用户不存在", http_status=404)

            existing = session.scalar(
                select(ImageGenerationJobEntity).where(
                    ImageGenerationJobEntity.user_id == record.user_id,
                    ImageGenerationJobEntity.idempotency_key == record.idempotency_key,
                )
            )
            if existing is not None:
                return image_job_record(existing), False

            active_count = int(
                session.scalar(
                    select(func.count()).select_from(ImageGenerationJobEntity).where(
                        ImageGenerationJobEntity.user_id == record.user_id,
                        ImageGenerationJobEntity.status.in_(ACTIVE_JOB_STATUSES),
                    )
                )
                or 0
            )
            if active_count >= active_limit:
                raise ImageGenerationRepositoryError(
                    "IMAGE_GENERATION_CONCURRENCY_LIMIT",
                    "当前仍有正在处理的生图任务，请等待完成后再试",
                    http_status=429,
                )
            if daily_limit > 0:
                today_start = datetime.now(UTC).replace(
                    hour=0, minute=0, second=0, microsecond=0
                ).timestamp()
                daily_count = int(
                    session.scalar(
                        select(func.count()).select_from(ImageGenerationJobEntity).where(
                            ImageGenerationJobEntity.user_id == record.user_id,
                            ImageGenerationJobEntity.created_at >= today_start,
                        )
                    )
                    or 0
                )
                if daily_count >= daily_limit:
                    raise ImageGenerationRepositoryError(
                        "IMAGE_GENERATION_DAILY_LIMIT",
                        "已达到今日生图次数上限",
                        http_status=429,
                    )

            user = session.scalar(select(UserEntity).where(UserEntity.user_id == record.user_id))
            if user is None:
                raise ImageGenerationRepositoryError("USER_NOT_FOUND", "用户不存在", http_status=404)
            if int(user.points or 0) < record.points_cost:
                raise ImageGenerationRepositoryError(
                    "INSUFFICIENT_POINTS", "积分不足，无法生成图片", http_status=400
                )
            user.points = int(user.points or 0) - record.points_cost
            order = WalletOrderEntity(
                order_id=record.reservation_order_id,
                user_id=record.user_id,
                username=record.username,
                kind="points",
                points_delta=-record.points_cost,
                source="image_generation",
                source_id=record.job_id,
                status="reserved",
                created_by=record.username,
                created_at=record.created_at,
            )
            entity = image_job_entity(record)
            session.add(order)
            session.add(entity)
            session.commit()
            return image_job_record(entity), True

    def claim_next_job(self, now: float) -> ImageGenerationJobRecord | None:
        """原子领取一条排队任务，避免多个工作器重复提交供应商。"""

        with self.session_factory() as session:
            job_id = session.scalar(
                select(ImageGenerationJobEntity.job_id)
                .where(ImageGenerationJobEntity.status == "queued")
                .order_by(ImageGenerationJobEntity.created_at.asc())
                .limit(1)
            )
            if job_id is None:
                return None
            claimed = cast(
                CursorResult[Any],
                session.execute(
                    update(ImageGenerationJobEntity)
                    .where(ImageGenerationJobEntity.job_id == job_id)
                    .where(ImageGenerationJobEntity.status == "queued")
                    .values(status="running", started_at=now, updated_at=now)
                ),
            )
            if claimed.rowcount != 1:
                session.rollback()
                return None
            session.commit()
            entity = session.scalar(
                select(ImageGenerationJobEntity).where(
                    ImageGenerationJobEntity.job_id == job_id
                )
            )
            if entity is None:
                return None
            return image_job_record(entity)

    def complete_job(
        self,
        job_id: str,
        asset: ImageGenerationAssetRecord,
        *,
        completed_at: float,
    ) -> ImageGenerationJobRecord:
        """标记成功、落库资产并确认已预扣积分。"""

        with self.session_factory() as session:
            job = self._get_job_entity(session, job_id, lock=True)
            if job.status != "running":
                raise ImageGenerationRepositoryError("JOB_NOT_RUNNING", "生图任务状态已变化", http_status=409)
            order = session.scalar(
                select(WalletOrderEntity).where(
                    WalletOrderEntity.order_id == job.reservation_order_id
                )
            )
            if order is not None and order.status == "reserved":
                order.status = "completed"
            session.add(image_asset_entity(asset))
            job.status = "succeeded"
            job.completed_at = completed_at
            job.updated_at = completed_at
            job.error_code = ""
            job.error_message = ""
            session.commit()
            return image_job_record(job)

    def fail_job_and_refund(
        self,
        job_id: str,
        *,
        status: str,
        error_code: str,
        error_message: str,
        completed_at: float,
        expected_status: str | None = None,
    ) -> ImageGenerationJobRecord:
        """将失败、拒绝或取消任务原子标记并归还尚未确认的预扣积分。"""

        if status not in {"failed", "rejected", "cancelled"}:
            raise ValueError(f"unsupported refundable job status: {status}")
        with self.session_factory() as session:
            # 结算前锁定任务行，确保并发恢复或取消最多创建一笔退款流水。
            job = self._get_job_entity(session, job_id, lock=True)
            if expected_status is not None and job.status != expected_status:
                if job.status == "running":
                    raise ImageGenerationRepositoryError(
                        "JOB_RUNNING", "生图任务正在执行，暂不能取消", http_status=409
                    )
                raise ImageGenerationRepositoryError(
                    "JOB_NOT_QUEUED", "生图任务已不在排队状态", http_status=409
                )
            if job.status in TERMINAL_JOB_STATUSES:
                return image_job_record(job)
            order = session.scalar(
                select(WalletOrderEntity).where(
                    WalletOrderEntity.order_id == job.reservation_order_id
                )
            )
            if order is not None and order.status == "reserved":
                user = session.scalar(
                    select(UserEntity).where(UserEntity.user_id == job.user_id)
                )
                if user is not None:
                    user.points = int(user.points or 0) + int(job.points_cost or 0)
                order.status = "refunded"
                session.add(
                    WalletOrderEntity(
                        order_id=f"refund_{job.job_id}",
                        user_id=job.user_id,
                        username=job.username,
                        kind="points",
                        points_delta=int(job.points_cost or 0),
                        source="image_generation_refund",
                        source_id=job.job_id,
                        status="completed",
                        created_by="system",
                        created_at=completed_at,
                    )
                )
            job.status = status
            job.error_code = error_code[:64]
            job.error_message = error_message[:2000]
            job.completed_at = completed_at
            job.updated_at = completed_at
            session.commit()
            return image_job_record(job)

    def get_job(self, job_id: str) -> ImageGenerationJobRecord | None:
        """读取单个任务。"""

        with self.session_factory() as session:
            entity = session.scalar(
                select(ImageGenerationJobEntity).where(ImageGenerationJobEntity.job_id == job_id)
            )
            return image_job_record(entity) if entity else None

    def list_jobs(
        self,
        *,
        user_id: str | None = None,
        status: str = "",
        limit: int = 30,
        offset: int = 0,
    ) -> list[ImageGenerationJobRecord]:
        """分页列出任务，管理员可省略 user_id 审计全量。"""

        with self.session_factory() as session:
            statement = select(ImageGenerationJobEntity).order_by(
                ImageGenerationJobEntity.created_at.desc()
            )
            if user_id:
                statement = statement.where(ImageGenerationJobEntity.user_id == user_id)
            if status:
                statement = statement.where(ImageGenerationJobEntity.status == status)
            entities = session.scalars(
                statement.offset(max(0, offset)).limit(max(1, min(limit, 100)))
            ).all()
            return [image_job_record(entity) for entity in entities]

    def count_jobs(self, *, user_id: str | None = None, status: str = "") -> int:
        """统计生图任务数量。"""

        with self.session_factory() as session:
            statement = select(func.count()).select_from(ImageGenerationJobEntity)
            if user_id:
                statement = statement.where(ImageGenerationJobEntity.user_id == user_id)
            if status:
                statement = statement.where(ImageGenerationJobEntity.status == status)
            return int(session.scalar(statement) or 0)

    def list_assets(self, job_id: str) -> list[ImageGenerationAssetRecord]:
        """读取任务仍可访问的输出资产。"""

        with self.session_factory() as session:
            entities = session.scalars(
                select(ImageGenerationAssetEntity)
                .where(ImageGenerationAssetEntity.job_id == job_id)
                .where(ImageGenerationAssetEntity.deleted_at <= 0)
                .order_by(ImageGenerationAssetEntity.created_at.asc())
            ).all()
            return [image_asset_record(entity) for entity in entities]

    def get_asset(self, job_id: str, asset_id: str) -> ImageGenerationAssetRecord | None:
        """读取某任务下单个未删除资产。"""

        with self.session_factory() as session:
            entity = session.scalar(
                select(ImageGenerationAssetEntity)
                .where(ImageGenerationAssetEntity.job_id == job_id)
                .where(ImageGenerationAssetEntity.asset_id == asset_id)
                .where(ImageGenerationAssetEntity.deleted_at <= 0)
            )
            return image_asset_record(entity) if entity else None

    def delete_job(self, job_id: str, *, now: float) -> tuple[ImageGenerationJobRecord, list[str]]:
        """软删除终态任务并返回待清理的资产文件键。"""

        with self.session_factory() as session:
            job = self._get_job_entity(session, job_id, lock=True)
            if job.status == "running":
                raise ImageGenerationRepositoryError(
                    "JOB_RUNNING", "生图任务正在执行，暂不能删除", http_status=409
                )
            if job.status == "queued":
                raise ImageGenerationRepositoryError(
                    "JOB_QUEUED", "请先取消排队中的生图任务", http_status=409
                )
            assets = session.scalars(
                select(ImageGenerationAssetEntity)
                .where(ImageGenerationAssetEntity.job_id == job_id)
                .where(ImageGenerationAssetEntity.deleted_at <= 0)
            ).all()
            keys = [asset.storage_key for asset in assets]
            for asset in assets:
                asset.deleted_at = now
            if job.status != "deleted":
                job.status = "deleted"
                job.updated_at = now
            session.commit()
            return image_job_record(job), keys

    def stale_running_job_ids(self, *, before: float) -> list[str]:
        """返回应用中断后未结算的过期运行任务。"""

        with self.session_factory() as session:
            return list(
                session.scalars(
                    select(ImageGenerationJobEntity.job_id)
                    .where(ImageGenerationJobEntity.status == "running")
                    .where(ImageGenerationJobEntity.started_at > 0)
                    .where(ImageGenerationJobEntity.started_at <= before)
                ).all()
            )

    def expired_job_assets(self, *, before: float) -> list[ImageGenerationAssetRecord]:
        """软删除超过保留期的成功任务资产并返回待删除文件。"""

        with self.session_factory() as session:
            job_ids = session.scalars(
                select(ImageGenerationJobEntity.job_id)
                .where(ImageGenerationJobEntity.status == "succeeded")
                .where(ImageGenerationJobEntity.expires_at > 0)
                .where(ImageGenerationJobEntity.expires_at <= before)
            ).all()
            if not job_ids:
                return []
            assets = session.scalars(
                select(ImageGenerationAssetEntity)
                .where(ImageGenerationAssetEntity.job_id.in_(job_ids))
                .where(ImageGenerationAssetEntity.deleted_at <= 0)
            ).all()
            for asset in assets:
                asset.deleted_at = before
            for job_id in job_ids:
                job = self._get_job_entity(session, job_id)
                job.status = "deleted"
                job.updated_at = before
            session.commit()
            return [image_asset_record(asset) for asset in assets]

    def save_trace(self, record: ImageGenerationTraceRecord) -> None:
        """写入一条不含提示词或密钥的供应商调用追溯。"""

        with self.session_factory() as session:
            session.add(
                ImageGenerationTraceEntity(
                    trace_id=record.trace_id,
                    job_id=record.job_id,
                    model_id=record.model_id,
                    model_name=record.model_name,
                    provider=record.provider,
                    phase=record.phase,
                    provider_request_id=record.provider_request_id,
                    ok=1 if record.ok else 0,
                    elapsed_ms=record.elapsed_ms,
                    error_code=record.error_code,
                    error=record.error[:2000],
                    created_at=record.created_at,
                )
            )
            session.commit()

    def list_traces(
        self,
        *,
        job_id: str = "",
        model_id: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[ImageGenerationTraceRecord]:
        """分页读取生图调用追溯。"""

        with self.session_factory() as session:
            statement = select(ImageGenerationTraceEntity).order_by(
                ImageGenerationTraceEntity.created_at.desc()
            )
            if job_id:
                statement = statement.where(ImageGenerationTraceEntity.job_id == job_id)
            if model_id:
                statement = statement.where(ImageGenerationTraceEntity.model_id == model_id)
            entities = session.scalars(
                statement.offset(max(0, offset)).limit(max(1, min(limit, 500)))
            ).all()
            return [image_trace_record(entity) for entity in entities]

    def count_traces(self, *, job_id: str = "", model_id: str = "") -> int:
        """统计调用追溯数量。"""

        with self.session_factory() as session:
            statement = select(func.count()).select_from(ImageGenerationTraceEntity)
            if job_id:
                statement = statement.where(ImageGenerationTraceEntity.job_id == job_id)
            if model_id:
                statement = statement.where(ImageGenerationTraceEntity.model_id == model_id)
            return int(session.scalar(statement) or 0)

    def stats(self) -> dict[str, int | float]:
        """返回管理端所需的任务与平均耗时摘要。"""

        with self.session_factory() as session:
            total = int(session.scalar(select(func.count()).select_from(ImageGenerationJobEntity)) or 0)
            rows = session.execute(
                select(ImageGenerationJobEntity.status, func.count())
                .group_by(ImageGenerationJobEntity.status)
            ).all()
            counts = {str(status): int(count) for status, count in rows}
            avg_elapsed = float(
                session.scalar(
                    select(func.avg(ImageGenerationTraceEntity.elapsed_ms)).where(
                        ImageGenerationTraceEntity.phase == "generate"
                    )
                )
                or 0.0
            )
            return {
                "total_jobs": total,
                "queued_jobs": counts.get("queued", 0),
                "running_jobs": counts.get("running", 0),
                "succeeded_jobs": counts.get("succeeded", 0),
                "failed_jobs": counts.get("failed", 0),
                "rejected_jobs": counts.get("rejected", 0),
                "cancelled_jobs": counts.get("cancelled", 0),
                "deleted_jobs": counts.get("deleted", 0),
                "avg_elapsed_ms": round(avg_elapsed, 2),
            }

    @staticmethod
    def _get_job_entity(
        session, job_id: str, *, lock: bool = False
    ) -> ImageGenerationJobEntity:
        """读取必需存在的任务 ORM 实体，状态转换时可请求行锁。"""

        statement = select(ImageGenerationJobEntity).where(
            ImageGenerationJobEntity.job_id == job_id
        )
        if lock:
            statement = statement.with_for_update()
        job = session.scalar(statement)
        if job is None:
            raise ImageGenerationRepositoryError("JOB_NOT_FOUND", "生图任务不存在", http_status=404)
        return job


def image_model_record(entity: ImageGenerationModelEntity) -> ImageGenerationModelRecord:
    """将模型 ORM 实体转换为领域记录。"""

    return ImageGenerationModelRecord(
        model_id=entity.model_id,
        name=entity.name or "",
        provider=entity.provider or "openai-images",
        base_url=entity.base_url or "",
        model=entity.model or "",
        api_key=entity.api_key or "",
        timeout_seconds=float(entity.timeout_seconds or 60.0),
        status=entity.status or "active",
        capabilities=entity.capabilities or "text-to-image,1024x1024",
        created_at=float(entity.created_at or 0.0),
        updated_at=float(entity.updated_at or 0.0),
        protocol_config=getattr(entity, "protocol_config", "{}") or "{}",
    )


def image_job_entity(record: ImageGenerationJobRecord) -> ImageGenerationJobEntity:
    """从领域记录构建新任务 ORM 实体。"""

    return ImageGenerationJobEntity(
        job_id=record.job_id,
        user_id=record.user_id,
        username=record.username,
        prompt=record.prompt,
        size=record.size,
        output_options=record.output_options,
        model_id=record.model_id,
        model_name=record.model_name,
        model_snapshot=record.model_snapshot,
        status=record.status,
        points_cost=record.points_cost,
        reservation_order_id=record.reservation_order_id,
        idempotency_key=record.idempotency_key,
        error_code=record.error_code,
        error_message=record.error_message,
        created_at=record.created_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
        updated_at=record.updated_at,
        expires_at=record.expires_at,
    )


def image_job_record(entity: ImageGenerationJobEntity) -> ImageGenerationJobRecord:
    """将任务 ORM 实体转换为领域记录。"""

    return ImageGenerationJobRecord(
        job_id=entity.job_id,
        user_id=entity.user_id,
        username=entity.username,
        prompt=entity.prompt or "",
        size=entity.size or "1024x1024",
        output_options=getattr(entity, "output_options", "{}") or "{}",
        model_id=entity.model_id or "",
        model_name=entity.model_name or "",
        model_snapshot=entity.model_snapshot or "{}",
        status=entity.status or "queued",
        points_cost=int(entity.points_cost or 0),
        reservation_order_id=entity.reservation_order_id or "",
        idempotency_key=entity.idempotency_key or "",
        error_code=entity.error_code or "",
        error_message=entity.error_message or "",
        created_at=float(entity.created_at or 0.0),
        started_at=float(entity.started_at or 0.0),
        completed_at=float(entity.completed_at or 0.0),
        updated_at=float(entity.updated_at or 0.0),
        expires_at=float(entity.expires_at or 0.0),
    )


def image_asset_entity(record: ImageGenerationAssetRecord) -> ImageGenerationAssetEntity:
    """从领域记录构建新资产 ORM 实体。"""

    return ImageGenerationAssetEntity(
        asset_id=record.asset_id,
        job_id=record.job_id,
        storage_key=record.storage_key,
        content_hash=record.content_hash,
        mime_type=record.mime_type,
        width=record.width,
        height=record.height,
        byte_size=record.byte_size,
        created_at=record.created_at,
        deleted_at=record.deleted_at,
    )


def image_asset_record(entity: ImageGenerationAssetEntity) -> ImageGenerationAssetRecord:
    """将资产 ORM 实体转换为领域记录。"""

    return ImageGenerationAssetRecord(
        asset_id=entity.asset_id,
        job_id=entity.job_id,
        storage_key=entity.storage_key,
        content_hash=entity.content_hash,
        mime_type=entity.mime_type or "image/png",
        width=int(entity.width or 0),
        height=int(entity.height or 0),
        byte_size=int(entity.byte_size or 0),
        created_at=float(entity.created_at or 0.0),
        deleted_at=float(entity.deleted_at or 0.0),
    )


def image_trace_record(entity: ImageGenerationTraceEntity) -> ImageGenerationTraceRecord:
    """将调用追溯 ORM 实体转换为领域记录。"""

    return ImageGenerationTraceRecord(
        trace_id=entity.trace_id,
        job_id=entity.job_id,
        model_id=entity.model_id,
        model_name=entity.model_name or "",
        provider=entity.provider or "",
        phase=entity.phase or "generate",
        provider_request_id=entity.provider_request_id or "",
        ok=bool(entity.ok),
        elapsed_ms=float(entity.elapsed_ms or 0.0),
        error_code=entity.error_code or "",
        error=entity.error or "",
        created_at=float(entity.created_at or 0.0),
    )

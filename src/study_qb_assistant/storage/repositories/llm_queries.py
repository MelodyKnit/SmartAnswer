"""大模型配置与调用追溯的 SQLAlchemy 持久化辅助。"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...llm.management.records import (
    LlmCallTraceRecord,
    LlmModelNotFoundError,
    LlmModelRecord,
    PrimaryModelRequiredError,
)
from ..orm import LlmCallTraceEntity, LlmModelEntity, SettingEntity


def list_llm_models(session_factory) -> list[LlmModelRecord]:
    """读取所有已配置模型，按角色与优先级排序。"""
    role_rank = {"primary": 0, "backup": 1, "disabled": 2}
    with session_factory() as session:
        entities = session.scalars(select(LlmModelEntity)).all()
        records = [llm_model_record(entity) for entity in entities]
    records.sort(
        key=lambda r: (
            role_rank.get(r.role, 3),
            r.priority if r.role == "backup" else 0,
            r.created_at,
            r.model_id,
        )
    )
    return records


def normalize_llm_model_roles(session_factory) -> None:
    """修复旧配置的重复主用、无主用及停用角色，保留原有停用效果。"""
    with session_factory() as session:
        _lock_model_configuration(session)
        entities = session.scalars(select(LlmModelEntity)).all()
        if not entities:
            return
        changed = False
        for entity in entities:
            if entity.role == "disabled":
                entity.role = "backup"
                entity.status = "inactive"
                changed = True
        primaries = [entity for entity in entities if entity.role == "primary"]
        candidates = primaries or entities
        primary = min(
            candidates,
            key=lambda entity: (
                0 if entity.status == "active" else 1,
                int(entity.priority if entity.priority is not None else 100),
                float(entity.created_at or 0.0),
                entity.model_id,
            ),
        )
        for entity in entities:
            role = "primary" if entity is primary else "backup"
            if entity.role != role:
                entity.role = role
                changed = True
        if changed:
            session.commit()


def get_llm_model(session_factory, model_id: str) -> LlmModelRecord | None:
    """读取单个模型配置。"""
    with session_factory() as session:
        entity = session.scalar(select(LlmModelEntity).where(LlmModelEntity.model_id == model_id))
        return llm_model_record(entity) if entity else None


def save_llm_model(
    session_factory, record: LlmModelRecord, *, update_fields: set[str] | None = None
) -> LlmModelRecord:
    """原子保存角色；指定 update_fields 时只更新已有模型的请求字段。"""
    with session_factory() as session:
        _lock_model_configuration(session)
        entities = session.scalars(select(LlmModelEntity)).all()
        entity = next((item for item in entities if item.model_id == record.model_id), None)
        if update_fields is not None and entity is None:
            raise LlmModelNotFoundError(record.model_id)
        was_primary = entity is not None and entity.role == "primary"
        role = "backup" if record.role == "disabled" else record.role
        if entity is not None and update_fields is not None and "role" not in update_fields:
            # 仅编辑其他字段时，采用锁内的最新角色，不恢复服务层读到的旧主用。
            role = entity.role
        if role == "primary":
            for other in entities:
                if other.model_id != record.model_id and other.role == "primary":
                    other.role = "backup"
                    other.updated_at = record.updated_at
        elif was_primary:
            replacement = _best_backup(
                item for item in entities if item.model_id != record.model_id
            )
            if replacement is not None:
                replacement.role = "primary"
                replacement.updated_at = record.updated_at
            else:
                raise PrimaryModelRequiredError("唯一模型不能改为备用")
        elif not any(
            item.role == "primary" and item.model_id != record.model_id
            for item in entities
        ):
            role = "primary"

        if entity is None:
            entity = LlmModelEntity(model_id=record.model_id)
            session.add(entity)
            entity.created_at = record.created_at
        values = {
            "name": record.name,
            "base_url": record.base_url,
            "model": record.model,
            "api_key": record.api_key,
            "priority": record.priority,
            "stream": 1 if record.stream else 0,
            "max_completion_tokens": record.max_completion_tokens,
            "timeout_seconds": record.timeout_seconds,
            "status": record.status,
        }
        for field, value in values.items():
            if update_fields is None or field in update_fields:
                setattr(entity, field, value)
        entity.role = role
        entity.updated_at = record.updated_at
        session.commit()
        return llm_model_record(entity)


def delete_llm_model(session_factory, model_id: str) -> bool:
    """删除一个模型配置。"""
    with session_factory() as session:
        _lock_model_configuration(session)
        entities = session.scalars(select(LlmModelEntity)).all()
        entity = next((item for item in entities if item.model_id == model_id), None)
        if entity is None:
            return False
        was_primary = entity.role == "primary"
        session.delete(entity)
        if was_primary:
            replacement = _best_backup(item for item in entities if item.model_id != model_id)
            if replacement is not None:
                replacement.role = "primary"
        session.commit()
        return True


def _best_backup(entities: Iterable[LlmModelEntity]) -> LlmModelEntity | None:
    candidates = [entity for entity in entities if entity.role != "primary"]
    return min(
        candidates,
        key=lambda entity: (
            0 if entity.status == "active" else 1,
            int(entity.priority if entity.priority is not None else 100),
            float(entity.created_at or 0.0),
            entity.model_id,
        ),
        default=None,
    )


def _lock_model_configuration(session: Session) -> None:
    """串行化主用角色写入，覆盖不同进程及空模型表的并发创建。"""
    if session.get_bind().dialect.name == "sqlite":
        # 必须在读取模型之前获取写锁，避免两个事务同时认为自己是唯一主用。
        session.execute(text("BEGIN IMMEDIATE"))
        return
    statement = select(SettingEntity).where(
        SettingEntity.scope == "llm_model_management",
        SettingEntity.key == "write_lock",
    ).with_for_update()
    if session.scalar(statement) is None:
        # 利用既有 settings 唯一约束建立固定锁行，无需新增表或修改表结构。
        try:
            with session.begin_nested():
                session.add(SettingEntity(scope="llm_model_management", key="write_lock", value=""))
                session.flush()
        except IntegrityError:
            # 另一事务抢先建立锁行；重新读取并等待它提交。
            pass
        session.scalar(statement)


def llm_model_record(entity: LlmModelEntity) -> LlmModelRecord:
    """把模型配置 ORM 实体转换为记录对象。"""
    return LlmModelRecord(
        model_id=entity.model_id,
        name=entity.name,
        base_url=entity.base_url,
        model=entity.model,
        api_key=entity.api_key or "",
        role=entity.role or "backup",
        priority=int(entity.priority if entity.priority is not None else 100),
        stream=bool(entity.stream),
        max_completion_tokens=int(entity.max_completion_tokens or 700),
        timeout_seconds=float(entity.timeout_seconds or 30.0),
        status=entity.status or "active",
        created_at=float(entity.created_at or 0.0),
        updated_at=float(entity.updated_at or 0.0),
    )


def save_llm_call_trace(session_factory, record: LlmCallTraceRecord) -> None:
    """落库一条大模型/联网检索调用追溯。"""
    with session_factory() as session:
        entity = LlmCallTraceEntity(
            trace_id=record.trace_id,
            request_id=record.request_id,
            phase=record.phase,
            model_id=record.model_id,
            model_name=record.model_name,
            base_url=record.base_url,
            provider=record.provider,
            question_title=record.question_title,
            prompt=record.prompt,
            evidence=record.evidence,
            response_text=record.response_text,
            candidate_answer=record.candidate_answer,
            confidence=record.confidence,
            ok=1 if record.ok else 0,
            error=record.error,
            elapsed_ms=record.elapsed_ms,
            created_at=record.created_at,
        )
        session.add(entity)
        session.commit()


def list_llm_call_traces(
    session_factory,
    *,
    request_id: str = "",
    model_id: str = "",
    phase: str = "",
    limit: int = 100,
    offset: int = 0,
) -> list[LlmCallTraceRecord]:
    """按关联 ID / 模型 / 阶段筛选调用追溯。"""
    with session_factory() as session:
        stmt = select(LlmCallTraceEntity).order_by(LlmCallTraceEntity.created_at.desc())
        if request_id:
            stmt = stmt.where(LlmCallTraceEntity.request_id == request_id)
        if model_id:
            stmt = stmt.where(LlmCallTraceEntity.model_id == model_id)
        if phase:
            stmt = stmt.where(LlmCallTraceEntity.phase == phase)
        stmt = stmt.offset(max(0, offset)).limit(max(1, min(limit, 500)))
        entities = session.scalars(stmt).all()
        return [llm_call_trace_record(entity) for entity in entities]


def count_llm_call_traces(
    session_factory,
    *,
    request_id: str = "",
    model_id: str = "",
    phase: str = "",
) -> int:
    """统计符合条件的调用追溯总数。"""
    with session_factory() as session:
        stmt = select(func.count()).select_from(LlmCallTraceEntity)
        if request_id:
            stmt = stmt.where(LlmCallTraceEntity.request_id == request_id)
        if model_id:
            stmt = stmt.where(LlmCallTraceEntity.model_id == model_id)
        if phase:
            stmt = stmt.where(LlmCallTraceEntity.phase == phase)
        return int(session.scalar(stmt) or 0)


def llm_call_stats(session_factory) -> list[dict]:
    """按模型聚合调用次数、成功/失败次数与平均耗时。"""
    with session_factory() as session:
        rows = session.execute(
            select(
                LlmCallTraceEntity.model_id,
                LlmCallTraceEntity.model_name,
                func.count().label("total"),
                func.sum(LlmCallTraceEntity.ok).label("ok_count"),
                func.avg(LlmCallTraceEntity.elapsed_ms).label("avg_elapsed_ms"),
            )
            .where(LlmCallTraceEntity.phase != "web_search")
            .where(LlmCallTraceEntity.phase != "failover")
            .group_by(LlmCallTraceEntity.model_id, LlmCallTraceEntity.model_name)
        ).all()
    stats: list[dict] = []
    for row in rows:
        total = int(row.total or 0)
        ok_count = int(row.ok_count or 0)
        stats.append(
            {
                "model_id": row.model_id or "",
                "model_name": row.model_name or "",
                "total_calls": total,
                "ok_calls": ok_count,
                "error_calls": total - ok_count,
                "avg_elapsed_ms": round(float(row.avg_elapsed_ms or 0.0), 2),
            }
        )
    stats.sort(key=lambda item: item["total_calls"], reverse=True)
    return stats


def llm_call_trace_record(entity: LlmCallTraceEntity) -> LlmCallTraceRecord:
    """把调用追溯 ORM 实体转换为记录对象。"""
    return LlmCallTraceRecord(
        trace_id=entity.trace_id,
        request_id=entity.request_id or "",
        phase=entity.phase or "",
        model_id=entity.model_id or "",
        model_name=entity.model_name or "",
        base_url=entity.base_url or "",
        provider=entity.provider or "",
        question_title=entity.question_title or "",
        prompt=entity.prompt or "",
        evidence=entity.evidence or "[]",
        response_text=entity.response_text or "",
        candidate_answer=entity.candidate_answer,
        confidence=float(entity.confidence or 0.0),
        ok=bool(entity.ok),
        error=entity.error or "",
        elapsed_ms=float(entity.elapsed_ms or 0.0),
        created_at=float(entity.created_at or 0.0),
    )

"""大模型配置与调用追溯的 SQLAlchemy 持久化辅助。"""

from __future__ import annotations

from sqlalchemy import func, select

from ..platform.records import LlmCallTraceRecord, LlmModelRecord
from .orm import LlmCallTraceEntity, LlmModelEntity


def list_llm_models(session_factory) -> list[LlmModelRecord]:
    """读取所有已配置模型，按角色与优先级排序。"""
    role_rank = {"primary": 0, "backup": 1, "disabled": 2}
    with session_factory() as session:
        entities = session.scalars(select(LlmModelEntity)).all()
        records = [llm_model_record(entity) for entity in entities]
    records.sort(key=lambda r: (role_rank.get(r.role, 3), r.priority, r.created_at))
    return records


def get_llm_model(session_factory, model_id: str) -> LlmModelRecord | None:
    """读取单个模型配置。"""
    with session_factory() as session:
        entity = session.scalar(select(LlmModelEntity).where(LlmModelEntity.model_id == model_id))
        return llm_model_record(entity) if entity else None


def save_llm_model(session_factory, record: LlmModelRecord) -> LlmModelRecord:
    """新增或更新一个模型配置。"""
    with session_factory() as session:
        entity = session.scalar(
            select(LlmModelEntity).where(LlmModelEntity.model_id == record.model_id)
        )
        if entity is None:
            entity = LlmModelEntity(model_id=record.model_id)
            session.add(entity)
            entity.created_at = record.created_at
        entity.name = record.name
        entity.base_url = record.base_url
        entity.model = record.model
        entity.api_key = record.api_key
        entity.role = record.role
        entity.priority = record.priority
        entity.stream = 1 if record.stream else 0
        entity.max_completion_tokens = record.max_completion_tokens
        entity.timeout_seconds = record.timeout_seconds
        entity.status = record.status
        entity.updated_at = record.updated_at
        session.commit()
        return llm_model_record(entity)


def delete_llm_model(session_factory, model_id: str) -> bool:
    """删除一个模型配置。"""
    with session_factory() as session:
        entity = session.scalar(select(LlmModelEntity).where(LlmModelEntity.model_id == model_id))
        if entity is None:
            return False
        session.delete(entity)
        session.commit()
        return True


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

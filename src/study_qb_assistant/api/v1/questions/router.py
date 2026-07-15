"""题库管理接口。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ....answering import AnswerService
from ....questions.models import CanonicalQuestionRecord
from ....platform.usage.time_ranges import local_day_window_from_dates
from ....storage.repositories.questions import question_record_is_indexable, question_record_status
from ...dependencies import get_lookup_service, get_question_repository
from ...security import require_permissions, require_roles
from .schemas import QuestionUpdatePayload


def build_question_router() -> APIRouter:
    """构建当前业务域路由。"""

    router = APIRouter()

    @router.get("/questions")
    def questions_list(
        request: Request,
        page: int = 1,
        limit: int = 20,
        keyword: str | None = None,
        question_id: str | None = None,
        type: str | None = None,
        source: str | None = None,
        status: str | None = None,
        updated_start_date: str | None = None,
        updated_end_date: str | None = None,
    ) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"questions:read"})
        if denied:
            return denied
        repository = get_question_repository(request)
        updated_start_time, updated_end_time = question_updated_window(
            updated_start_date or "", updated_end_date or ""
        )
        total = repository.count_questions(
            question_id=question_id or "",
            keyword=keyword or "",
            question_type=type or "",
            source_name=source or "",
            status=status or "",
            is_active=True,
            updated_start_time=updated_start_time,
            updated_end_time=updated_end_time,
        )
        paginated = repository.list_question_records(
            question_id=question_id or "",
            keyword=keyword or "",
            question_type=type or "",
            source_name=source or "",
            status=status or "",
            is_active=True,
            updated_start_time=updated_start_time,
            updated_end_time=updated_end_time,
            limit=limit,
            offset=max(0, (page - 1) * limit),
        )
        questions = [r.to_dict() for r in paginated]
        all_types = repository.question_types()
        all_sources = repository.source_names()

        return JSONResponse(
            {
                "ok": True,
                "total": total,
                "page": page,
                "limit": limit,
                "questions": questions,
                "all_types": all_types,
                "all_sources": all_sources,
            }
        )

    @router.patch("/questions/{question_id}")
    def question_update(
        request: Request,
        question_id: str,
        payload: QuestionUpdatePayload,
    ) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"questions:write"})
        if denied:
            return denied

        repository = get_question_repository(request)
        target_record = repository.get_question_record(question_id)
        if target_record is None:
            return JSONResponse(
                {"ok": False, "error": {"code": "QUESTION_NOT_FOUND", "message": "题目不存在"}},
                status_code=404,
            )

        updates: dict[str, object] = {}
        if payload.title_raw is not None:
            updates["title_raw"] = payload.title_raw
        if payload.question_type is not None:
            updates["question_type"] = payload.question_type
        if payload.options_raw is not None:
            updates["options_raw"] = tuple(payload.options_raw)
        if payload.answer_raw is not None:
            updates["answer_raw"] = payload.answer_raw
        if payload.explanation is not None:
            updates["explanation"] = payload.explanation
        if payload.subject is not None:
            updates["subject"] = payload.subject
        if payload.tags is not None:
            updates["tags"] = tuple(payload.tags)

        if payload.status is not None:
            updates["metadata"] = {
                **dict(target_record.metadata),
                "status": payload.status.strip() or question_record_status(target_record),
            }
            updates["source_split"] = payload.status.strip() or target_record.source_split
        updated_record = updated_question_record(target_record, updates)
        try:
            repository.save_question_record(updated_record)
        except Exception as exc:
            return JSONResponse(
                {"ok": False, "error": {"code": "QUESTION_PERSIST_FAILED", "message": str(exc)}},
                status_code=500,
            )
        lookup = get_lookup_service(request)
        index = lookup.index if isinstance(lookup, AnswerService) else lookup
        if question_record_is_indexable(updated_record):
            index.add_or_replace(updated_record)
        else:
            index.remove(question_id)

        return JSONResponse({"ok": True, "question": updated_record.to_dict()})

    @router.delete("/questions/{question_id}")
    def question_delete(request: Request, question_id: str) -> JSONResponse:
        """软删除题库记录，并从当前运行时索引移除。"""

        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"questions:write"})
        if denied:
            return denied

        repository = get_question_repository(request)
        try:
            deleted_record = repository.soft_delete_question_record(question_id)
        except Exception as exc:
            return JSONResponse(
                {"ok": False, "error": {"code": "QUESTION_DELETE_FAILED", "message": str(exc)}},
                status_code=500,
            )
        if deleted_record is None:
            return JSONResponse(
                {"ok": False, "error": {"code": "QUESTION_NOT_FOUND", "message": "题目不存在"}},
                status_code=404,
            )

        lookup = get_lookup_service(request)
        index = lookup.index if isinstance(lookup, AnswerService) else lookup
        index.remove(question_id)
        return JSONResponse({"ok": True, "question_id": question_id, "status": "deleted"})

    @router.post("/questions/reindex")
    def questions_reindex(request: Request) -> JSONResponse:
        """按数据库中的可信题库记录重建当前进程内存索引。"""

        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"questions:write"})
        if denied:
            return denied
        repository = get_question_repository(request)
        records = repository.list_indexable_records()
        lookup = get_lookup_service(request)
        index = lookup.index if isinstance(lookup, AnswerService) else lookup
        index.replace_records(tuple(records))
        return JSONResponse({"ok": True, "indexed_count": len(records)})

    return router


def updated_question_record(
    record: CanonicalQuestionRecord, values: dict[str, object]
) -> CanonicalQuestionRecord:
    """基于已有题库记录生成更新后的不可变记录。"""

    payload = record.to_dict()
    for key in {
        "title_raw",
        "question_type",
        "answer_raw",
        "explanation",
        "subject",
        "chapter",
        "source_split",
    }:
        if key in values:
            payload[key] = values[key]
    if "options_raw" in values:
        payload["options_raw"] = string_list(values["options_raw"])
    if "tags" in values:
        payload["tags"] = string_list(values["tags"])
    if "metadata" in values and isinstance(values["metadata"], dict):
        payload["metadata"] = {str(k): str(v) for k, v in values["metadata"].items()}
    return CanonicalQuestionRecord.from_dict(payload)

def string_list(value: object) -> list[str]:
    """把接口传入的列表型字段安全规范为字符串列表。"""
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return []

def question_updated_window(
    updated_start_date: str, updated_end_date: str
) -> tuple[float | None, float | None]:
    """把题库修改日期筛选转换为时间窗口；非法日期忽略筛选。"""

    try:
        return local_day_window_from_dates(updated_start_date, updated_end_date)
    except ValueError:
        return None, None

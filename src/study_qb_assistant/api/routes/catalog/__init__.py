"""平台目录与角色权限相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ....answering import AnswerService
from ....auth import AuthError
from ....models import CanonicalQuestionRecord
from ....storage.question_repository import question_record_status, question_status_is_indexable
from ...context import (
    auth_error_response,
    get_lookup_service,
    get_platform_service,
    get_question_repository,
    require_permissions,
    require_roles,
)
from ...schemas import QuestionUpdatePayload, RolePermissionPayload


def build_catalog_router() -> APIRouter:
    """构建目录与权限域路由。"""
    router = APIRouter()

    # --- 角色与权限 ---
    @router.get("/roles")
    def roles(request: Request) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"roles:read"})
        if denied:
            return denied
        platform = get_platform_service(request)
        return JSONResponse({"ok": True, "roles": platform.list_role_permissions()})

    @router.get("/roles/{role_id}/permissions")
    def role_permissions(request: Request, role_id: str) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"roles:read"})
        if denied:
            return denied
        platform = get_platform_service(request)
        try:
            item = platform.get_role_permissions(role_id)
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "role": item})

    @router.put("/roles/{role_id}/permissions")
    def role_permissions_update(
        request: Request, role_id: str, payload: RolePermissionPayload
    ) -> JSONResponse:
        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"roles:write"})
        if denied:
            return denied
        platform = get_platform_service(request)
        try:
            item = platform.set_role_permissions(role_id, tuple(payload.permissions))
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "role": item})

    # --- 题库题目管理 ---
    @router.get("/questions")
    def questions_list(
        request: Request,
        page: int = 1,
        limit: int = 20,
        keyword: str | None = None,
        type: str | None = None,
        source: str | None = None,
        status: str | None = None,
    ) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"questions:read"})
        if denied:
            return denied
        repository = get_question_repository(request)
        total = repository.count_questions(
            keyword=keyword or "",
            question_type=type or "",
            source_name=source or "",
            status=status or "",
            is_active=True,
        )
        paginated = repository.list_question_records(
            keyword=keyword or "",
            question_type=type or "",
            source_name=source or "",
            status=status or "",
            is_active=True,
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
        if question_status_is_indexable(question_record_status(updated_record)):
            index.add_or_replace(updated_record)
        else:
            index.remove(question_id)

        return JSONResponse({"ok": True, "question": updated_record.to_dict()})

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
        payload["options_raw"] = list(values["options_raw"])
    if "tags" in values:
        payload["tags"] = list(values["tags"])
    if "metadata" in values and isinstance(values["metadata"], dict):
        payload["metadata"] = {str(k): str(v) for k, v in values["metadata"].items()}
    return CanonicalQuestionRecord.from_dict(payload)

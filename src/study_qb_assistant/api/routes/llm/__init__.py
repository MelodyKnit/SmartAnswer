"""平台大模型配置与调用追溯相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ....auth import AuthError
from ....answering import AnswerService
from ....search import LocalQuestionIndex
from ...dependencies import LookupServiceDep, PlatformServiceDep
from ...context import (
    auth_error_response,
    require_permissions,
    require_roles,
)
from ...schemas import LlmModelCreatePayload, LlmModelUpdatePayload, LlmRuntimeConfigPayload


def build_llm_router() -> APIRouter:
    """构建大模型配置与调用追溯路由。"""
    router = APIRouter(tags=["llm"])

    def refresh_models(lookup: LocalQuestionIndex | AnswerService) -> None:
        """模型配置变更后热刷新答题服务，使主备链立即生效。"""
        if isinstance(lookup, AnswerService):
            from ....runtime import refresh_answer_service

            refresh_answer_service(lookup)

    @router.get("/llm-models")
    def llm_models_list(request: Request, platform: PlatformServiceDep) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"llm:read"})
        if denied:
            return denied
        return JSONResponse({"ok": True, "models": platform.list_llm_models()})

    @router.get("/llm-runtime-config")
    def llm_runtime_config(request: Request, platform: PlatformServiceDep) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"llm:read"})
        if denied:
            return denied
        return JSONResponse({"ok": True, "config": platform.get_llm_runtime_config()})

    @router.patch("/llm-runtime-config")
    def llm_runtime_config_update(
        request: Request,
        platform: PlatformServiceDep,
        lookup: LookupServiceDep,
        payload: LlmRuntimeConfigPayload,
    ) -> JSONResponse:
        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"llm:write"})
        if denied:
            return denied
        values = {key: value for key, value in payload.model_dump().items() if value is not None}
        try:
            config = platform.set_llm_runtime_config(values)
        except AuthError as exc:
            return auth_error_response(exc)
        refresh_models(lookup)
        return JSONResponse({"ok": True, "config": config})

    @router.post("/llm-models")
    def llm_models_create(
        request: Request,
        platform: PlatformServiceDep,
        lookup: LookupServiceDep,
        payload: LlmModelCreatePayload,
    ) -> JSONResponse:
        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"llm:write"})
        if denied:
            return denied
        try:
            model = platform.create_llm_model(
                name=payload.name,
                base_url=payload.base_url,
                model=payload.model,
                api_key=payload.api_key,
                role=payload.role,
                priority=payload.priority,
                stream=payload.stream,
                max_completion_tokens=payload.max_completion_tokens,
                timeout_seconds=payload.timeout_seconds,
                status=payload.status,
            )
        except AuthError as exc:
            return auth_error_response(exc)
        refresh_models(lookup)
        return JSONResponse({"ok": True, "model": model})

    @router.patch("/llm-models/{model_id}")
    def llm_models_update(
        request: Request,
        platform: PlatformServiceDep,
        lookup: LookupServiceDep,
        model_id: str,
        payload: LlmModelUpdatePayload,
    ) -> JSONResponse:
        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"llm:write"})
        if denied:
            return denied
        values = {key: value for key, value in payload.model_dump().items() if value is not None}
        try:
            model = platform.update_llm_model(model_id, values)
        except AuthError as exc:
            return auth_error_response(exc)
        refresh_models(lookup)
        return JSONResponse({"ok": True, "model": model})

    @router.delete("/llm-models/{model_id}")
    def llm_models_delete(
        request: Request,
        platform: PlatformServiceDep,
        lookup: LookupServiceDep,
        model_id: str,
    ) -> JSONResponse:
        denied = require_roles(request, {"superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"llm:write"})
        if denied:
            return denied
        try:
            platform.delete_llm_model(model_id)
        except AuthError as exc:
            return auth_error_response(exc)
        refresh_models(lookup)
        return JSONResponse({"ok": True})

    @router.get("/llm-stats")
    def llm_stats(request: Request, platform: PlatformServiceDep) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"llm:read"})
        if denied:
            return denied
        return JSONResponse({"ok": True, "stats": platform.llm_call_stats()})

    @router.get("/llm-traces")
    def llm_traces(
        request: Request,
        platform: PlatformServiceDep,
        request_id: str = "",
        model_id: str = "",
        phase: str = "",
        limit: int = 50,
        page: int = 1,
    ) -> JSONResponse:
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"llm:read"})
        if denied:
            return denied
        page = max(1, int(page))
        limit = max(1, min(int(limit), 200))
        offset = (page - 1) * limit
        traces = platform.list_llm_call_traces(
            request_id=request_id,
            model_id=model_id,
            phase=phase,
            limit=limit,
            offset=offset,
        )
        total = platform.count_llm_call_traces(
            request_id=request_id, model_id=model_id, phase=phase
        )
        return JSONResponse(
            {"ok": True, "traces": traces, "total": total, "page": page, "limit": limit}
        )

    return router

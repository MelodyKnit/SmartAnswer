"""查题、状态与 OCS 兼容接口路由。"""

from __future__ import annotations

from fastapi import APIRouter, Body, Query, Request
from starlette.responses import JSONResponse

from ....adapters import build_ocs_config
from ...context import (
    get_auth_service,
    get_lookup_service,
    get_platform_service,
    guard_protected_request,
    require_permissions,
    require_roles,
)
from ...query_parser import build_query_from_payload, sanitize_query_options, split_options
from ...route_support import (
    base_url_from_request,
    debug_events_payload,
    run_lookup,
    status_payload,
)
from ...schemas import QueryPayload


def build_query_router() -> APIRouter:
    """构建查题域路由。"""
    router = APIRouter()

    @router.get("/healthz")
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    @router.get("/status")
    def status(request: Request) -> JSONResponse:
        denied = guard_protected_request(request)
        if denied:
            return denied
        return JSONResponse(status_payload(get_lookup_service(request)))

    @router.get("/debug/recent")
    def debug_recent(request: Request) -> JSONResponse:
        denied = guard_protected_request(request)
        if denied:
            return denied
        denied = require_roles(request, {"admin", "superadmin"})
        if denied:
            return denied
        denied = require_permissions(request, {"system:read"})
        if denied:
            return denied
        return JSONResponse(debug_events_payload())

    @router.get("/configs/ocs-local-study-bank.json")
    def ocs_config(request: Request) -> JSONResponse:
        platform = get_platform_service(request)
        return JSONResponse(build_ocs_config(base_url_from_request(request, platform)))

    @router.get("/query")
    def query_get(
        request: Request,
        title: str = "",
        options: str = "",
        question_type: str = Query("unknown", alias="type"),
        request_id: str | None = None,
    ) -> JSONResponse:
        denied = guard_protected_request(request)
        if denied:
            return denied
        query = build_query_from_payload(
            QueryPayload(
                title=title,
                options=sanitize_query_options(
                    title, question_type or "unknown", split_options(options)
                ),
                type=question_type,
                request_id=request_id,
            )
        )
        return run_lookup(
            get_lookup_service(request),
            get_platform_service(request),
            get_auth_service(request),
            request,
            "/query",
            "GET",
            query,
        )

    @router.post("/query")
    def query_post(
        request: Request, payload: QueryPayload = Body(default_factory=QueryPayload)
    ) -> JSONResponse:
        denied = guard_protected_request(request)
        if denied:
            return denied
        return run_lookup(
            get_lookup_service(request),
            get_platform_service(request),
            get_auth_service(request),
            request,
            "/query",
            "POST",
            build_query_from_payload(payload),
        )

    @router.get("/ocs/query")
    def ocs_query_get(
        request: Request,
        title: str = "",
        options: str = "",
        question_type: str = Query("unknown", alias="type"),
        request_id: str | None = None,
    ) -> JSONResponse:
        denied = guard_protected_request(request)
        if denied:
            return denied
        query = build_query_from_payload(
            QueryPayload(
                title=title,
                options=sanitize_query_options(
                    title, question_type or "unknown", split_options(options)
                ),
                type=question_type,
                request_id=request_id,
            )
        )
        return run_lookup(
            get_lookup_service(request),
            get_platform_service(request),
            get_auth_service(request),
            request,
            "/ocs/query",
            "GET",
            query,
        )

    @router.post("/ocs/query")
    def ocs_query_post(
        request: Request, payload: QueryPayload = Body(default_factory=QueryPayload)
    ) -> JSONResponse:
        denied = guard_protected_request(request)
        if denied:
            return denied
        return run_lookup(
            get_lookup_service(request),
            get_platform_service(request),
            get_auth_service(request),
            request,
            "/ocs/query",
            "POST",
            build_query_from_payload(payload),
        )

    return router

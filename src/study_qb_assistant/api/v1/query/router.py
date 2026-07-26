"""查题、状态与 OCS 兼容接口路由。"""

from __future__ import annotations

from fastapi import APIRouter, Body, Query, Request
from starlette.responses import JSONResponse

from ....version import BUILD_INFO
from ...dependencies import (
    get_auth_service,
    get_lookup_service,
    get_ocs_integration,
    get_settings_service,
    get_token_service,
    get_usage_service,
)
from ...security import (
    guard_protected_request,
    require_permissions,
)
from study_qb_assistant.questions.parsing import (
    QueryInputError,
    build_query_from_payload,
    sanitize_query_options,
    split_options,
    split_raw_values,
)
from ...diagnostics import debug_events_payload, status_payload
from ...http import base_url_from_request
from ...query_execution import run_lookup
from ...contracts.query import QueryPayload


def build_query_router() -> APIRouter:
    """构建版本化查题、状态和配置路由。"""
    router = APIRouter()

    @router.get("/healthz")
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    @router.get("/version")
    def version() -> dict[str, object]:
        """返回不含敏感信息的当前构建版本。"""

        return {"ok": True, **BUILD_INFO.to_dict()}

    @router.get("/status")
    def status(request: Request) -> JSONResponse:
        denied = guard_protected_request(request)
        if denied:
            return denied
        return JSONResponse(status_payload(get_lookup_service(request)))

    @router.get("/debug/recent")
    def debug_recent(
        request: Request,
        start_date: str = "",
        end_date: str = "",
    ) -> JSONResponse:
        denied = guard_protected_request(request)
        if denied:
            return denied
        denied = require_permissions(request, {"system:read"})
        if denied:
            return denied
        try:
            payload = debug_events_payload(start_date, end_date)
        except ValueError:
            return JSONResponse(
                {
                    "ok": False,
                    "error": {
                        "code": "INVALID_DATE",
                        "message": "日期格式必须为 YYYY-MM-DD，且开始日期不能晚于结束日期",
                    },
                },
                status_code=400,
            )
        return JSONResponse(payload)

    @router.get("/debug/usage-audit")
    def debug_usage_audit(request: Request, date: str = "") -> JSONResponse:
        denied = guard_protected_request(request)
        if denied:
            return denied
        denied = require_permissions(request, {"system:read"})
        if denied:
            return denied
        usage = get_usage_service(request)
        try:
            payload = usage.usage_audit(date)
        except ValueError:
            return JSONResponse(
                {
                    "ok": False,
                    "error": {
                        "code": "INVALID_DATE",
                        "message": "日期格式必须为 YYYY-MM-DD",
                    },
                },
                status_code=400,
            )
        return JSONResponse({"ok": True, "audit": payload})

    @router.get("/configs/ocs-local-study-bank.json")
    def ocs_config(request: Request) -> JSONResponse:
        settings = get_settings_service(request)
        integration = get_ocs_integration(request)
        return JSONResponse(
            integration.build_config(
                base_url_from_request(request, settings),
                platform_name=str(settings.get_site_config()["site_title"]),
            )
        )

    @router.get("/query")
    def query_get(
        request: Request,
        title: str = "",
        options: str = "",
        question_type: str = Query("unknown", alias="type"),
        request_id: str | None = None,
        image_urls: str = "",
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
                image_urls=split_raw_values(image_urls),
            )
        )
        return run_lookup(
            get_lookup_service(request),
            get_usage_service(request),
            get_token_service(request),
            get_settings_service(request),
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
        try:
            query = build_query_from_payload(payload)
        except QueryInputError as exc:
            return JSONResponse(
                {
                    "ok": False,
                    "error": {
                        "code": "INVALID_INPUT",
                        "message": str(exc),
                    },
                },
                status_code=400,
            )
        return run_lookup(
            get_lookup_service(request),
            get_usage_service(request),
            get_token_service(request),
            get_settings_service(request),
            get_auth_service(request),
            request,
            "/query",
            "POST",
            query,
        )

    return router

"""OCS 公共查题接口路由。"""

from __future__ import annotations

from fastapi import APIRouter, Body, Query, Request
from starlette.responses import JSONResponse

from ..dependencies import (
    get_auth_service,
    get_lookup_service,
    get_ocs_integration,
    get_settings_service,
    get_token_service,
    get_usage_service,
)
from ..contracts.query import QueryPayload
from ..query_execution import run_lookup
from ..security import guard_protected_request
from ...questions.parsing import QueryInputError


def build_ocs_router() -> APIRouter:
    """构建稳定且不带版本前缀的 OCS 路由。"""

    router = APIRouter()

    @router.get("/ocs/query")
    def ocs_query_get(
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
        try:
            query = get_ocs_integration(request).parse_request(
                {
                    "title": title,
                    "options": options,
                    "type": question_type,
                    "request_id": request_id,
                    "image_urls": image_urls,
                }
            )
        except QueryInputError as exc:
            return ocs_input_error_response(exc)
        return run_lookup(
            get_lookup_service(request),
            get_usage_service(request),
            get_token_service(request),
            get_settings_service(request),
            get_auth_service(request),
            request,
            "/ocs/query",
            "GET",
            query,
        )

    @router.post("/ocs/query")
    def ocs_query_post(
        request: Request,
        payload: QueryPayload = Body(default_factory=QueryPayload),
    ) -> JSONResponse:
        denied = guard_protected_request(request)
        if denied:
            return denied
        try:
            query = get_ocs_integration(request).parse_request(payload.model_dump())
        except QueryInputError as exc:
            return ocs_input_error_response(exc)
        return run_lookup(
            get_lookup_service(request),
            get_usage_service(request),
            get_token_service(request),
            get_settings_service(request),
            get_auth_service(request),
            request,
            "/ocs/query",
            "POST",
            query,
        )

    return router


def ocs_input_error_response(error: QueryInputError) -> JSONResponse:
    """为 GET/POST 输入校验失败返回相同的 OCS 兼容错误。"""

    return JSONResponse(
        {
            "code": 1,
            "message": str(error),
            "data": {"answer": None, "ai": {"error_code": "INVALID_INPUT"}},
        },
        status_code=400,
    )

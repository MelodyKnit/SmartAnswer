"""FastAPI-based local HTTP API for question lookup and OCS integration."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from fastapi import Body, Cookie, FastAPI, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict
from starlette.responses import FileResponse, JSONResponse

from ..adapters import build_ocs_config, to_ocs_response
from ..answering import AnswerService
from ..auth import AuthError, AuthService
from ..models import QuestionQuery
from ..runtime_log import log_event, recent_events
from ..search import LocalQuestionIndex

_SESSION_COOKIE = "stqb_session"
_STATIC_DIR = Path(__file__).resolve().parent / "static"
_STATIC_PAGES = {
    "/": "index.html",
    "/dashboard": "index.html",
    "/dashboard.html": "index.html",
    "/index.html": "index.html",
}
_PROTECTED_PATHS = {"/query", "/ocs/query", "/status", "/debug/recent"}


class QueryPayload(BaseModel):
    """JSON request body accepted by `/query` and `/ocs/query`."""

    model_config = ConfigDict(extra="ignore")

    title: str = ""
    options: str | list[str] | tuple[str, ...] = ()
    type: str | None = None
    question_type: str | None = None
    request_id: str | None = None


class RegisterPayload(BaseModel):
    """Account registration payload."""

    model_config = ConfigDict(extra="ignore")

    username: str = ""
    password: str = ""
    email: str | None = None


class LoginPayload(BaseModel):
    """Account login payload."""

    model_config = ConfigDict(extra="ignore")

    username: str = ""
    password: str = ""
    remember: bool = False


class ResetRequestPayload(BaseModel):
    """Password reset request payload."""

    model_config = ConfigDict(extra="ignore")

    username: str = ""


class ResetConfirmPayload(BaseModel):
    """Password reset confirmation payload."""

    model_config = ConfigDict(extra="ignore")

    username: str = ""
    token: str = ""
    new_password: str = ""


def create_app(
    lookup: LocalQuestionIndex | AnswerService,
    *,
    auth_service: AuthService | None = None,
    require_auth: bool | None = None,
) -> FastAPI:
    """Build the FastAPI application used by scripts and tests."""
    auth = auth_service or AuthService(os.getenv("STQB_USERS_PATH") or "data/runtime/users.json")
    auth_required = _bool_env("STQB_REQUIRE_AUTH") if require_auth is None else require_auth
    app = FastAPI(title="Study Question Bank Assistant", version="0.1.0")
    app.state.lookup = lookup
    app.state.auth = auth
    app.state.require_auth = auth_required

    @app.middleware("http")
    async def cors_and_options(request: Request, call_next) -> Response:
        if request.method == "OPTIONS":
            return Response(status_code=204, headers=_cors_headers(request))
        response = await call_next(request)
        for key, value in _cors_headers(request).items():
            response.headers[key] = value
        return response

    @app.get("/healthz")
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/auth/session")
    def session(request: Request) -> JSONResponse:
        user = _current_user(request, auth)
        if user is None:
            return JSONResponse({"ok": False}, status_code=401)
        return JSONResponse({"ok": True, "user": user})

    @app.post("/auth/register")
    def register(payload: RegisterPayload) -> JSONResponse:
        try:
            user = auth.register(payload.username, payload.password, payload.email)
        except AuthError as exc:
            return _auth_error_response(exc)
        return JSONResponse({"ok": True, "user": user})

    @app.post("/auth/login")
    def login(request: Request, payload: LoginPayload) -> JSONResponse:
        try:
            token, user, ttl = auth.login(
                payload.username,
                payload.password,
                remember=payload.remember,
                client_ip=request.client.host if request.client else "",
            )
        except AuthError as exc:
            return _auth_error_response(exc)
        response = JSONResponse({"ok": True, "user": user, "token": token, "expires_in": ttl})
        response.set_cookie(
            _SESSION_COOKIE,
            token,
            path="/",
            httponly=True,
            samesite="strict",
            max_age=ttl if payload.remember else None,
        )
        return response

    @app.post("/auth/logout")
    def logout(request: Request) -> JSONResponse:
        auth.logout(_session_token(request))
        response = JSONResponse({"ok": True})
        response.delete_cookie(_SESSION_COOKIE, path="/")
        return response

    @app.post("/auth/reset-request")
    def reset_request(payload: ResetRequestPayload) -> dict[str, Any]:
        token = auth.create_reset_token(payload.username)
        if token is not None:
            print(f"[密码重置] 用户 {payload.username} 的一次性重置令牌（30 分钟内有效）：{token}")
        return {"ok": True, "message": "若该账号存在，重置令牌已打印到服务器控制台，请联系本机管理员获取"}

    @app.post("/auth/reset-confirm")
    def reset_confirm(payload: ResetConfirmPayload) -> JSONResponse:
        try:
            auth.confirm_reset(payload.username, payload.token, payload.new_password)
        except AuthError as exc:
            return _auth_error_response(exc)
        return JSONResponse({"ok": True, "message": "密码已重置，请使用新密码登录"})

    @app.get("/status")
    def status(request: Request) -> JSONResponse:
        denied = _guard(request, auth, auth_required)
        if denied:
            return denied
        return JSONResponse(_status_payload(lookup))

    @app.get("/debug/recent")
    def debug_recent(request: Request) -> JSONResponse:
        denied = _guard(request, auth, auth_required)
        if denied:
            return denied
        return JSONResponse({"ok": True, "events": recent_events()})

    @app.get("/configs/ocs-local-study-bank.json")
    def ocs_config(request: Request) -> JSONResponse:
        return JSONResponse(build_ocs_config(_base_url_from_request(request)))

    @app.get("/query")
    def query_get(
        request: Request,
        title: str = "",
        options: str = "",
        question_type: str = Query("unknown", alias="type"),
        request_id: str | None = None,
    ) -> JSONResponse:
        denied = _guard(request, auth, auth_required)
        if denied:
            return denied
        query = QuestionQuery(
            title=title,
            options=_sanitize_query_options(title, question_type or "unknown", _split_options(options)),
            question_type=question_type or "unknown",
            request_id=request_id,
        )
        return _run_lookup(lookup, "/query", "GET", query)

    @app.post("/query")
    def query_post(request: Request, payload: QueryPayload = Body(default_factory=QueryPayload)) -> JSONResponse:
        denied = _guard(request, auth, auth_required)
        if denied:
            return denied
        query = _query_from_payload(payload)
        return _run_lookup(lookup, "/query", "POST", query)

    @app.get("/ocs/query")
    def ocs_query_get(
        request: Request,
        title: str = "",
        options: str = "",
        question_type: str = Query("unknown", alias="type"),
        request_id: str | None = None,
    ) -> JSONResponse:
        denied = _guard(request, auth, auth_required)
        if denied:
            return denied
        query = QuestionQuery(
            title=title,
            options=_sanitize_query_options(title, question_type or "unknown", _split_options(options)),
            question_type=question_type or "unknown",
            request_id=request_id,
        )
        return _run_lookup(lookup, "/ocs/query", "GET", query)

    @app.post("/ocs/query")
    def ocs_query_post(
        request: Request, payload: QueryPayload = Body(default_factory=QueryPayload)
    ) -> JSONResponse:
        denied = _guard(request, auth, auth_required)
        if denied:
            return denied
        query = _query_from_payload(payload)
        return _run_lookup(lookup, "/ocs/query", "POST", query)

    @app.get("/{path:path}")
    def static_pages(path: str) -> Response:
        route = "/" + path
        filename = _STATIC_PAGES.get(route)
        if filename is None:
            return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
        html_path = _STATIC_DIR / filename
        if not html_path.exists():
            return JSONResponse({"ok": False, "error": f"failed to load page: {html_path}"}, status_code=500)
        return FileResponse(html_path, media_type="text/html; charset=utf-8")

    return app


def _run_lookup(
    lookup: LocalQuestionIndex | AnswerService,
    path: str,
    method: str,
    query: QuestionQuery,
) -> JSONResponse:
    started = time.time()
    result = lookup.query(query)
    _log_query(path, method, query, result, time.time() - started)
    return JSONResponse(_response_for_path(path, result))


def _guard(request: Request, auth: AuthService, require_auth: bool) -> JSONResponse | None:
    path = request.url.path
    if not require_auth or path not in _PROTECTED_PATHS:
        return None
    if path == "/ocs/query" and _bearer_authorized(request):
        return None
    if _current_user(request, auth) is not None:
        return None
    return JSONResponse(
        {"ok": False, "error": {"code": "UNAUTHORIZED", "message": "请先登录"}},
        status_code=401,
    )


def _bearer_authorized(request: Request) -> bool:
    token = _authorization_bearer(request)
    keys = _ocs_api_keys()
    return bool(token) and token in keys


def _current_user(request: Request, auth: AuthService) -> dict | None:
    return auth.resolve_session(_session_token(request))


def _session_token(request: Request) -> str | None:
    bearer = _authorization_bearer(request)
    if bearer:
        return bearer
    return request.cookies.get(_SESSION_COOKIE)


def _authorization_bearer(request: Request) -> str | None:
    header = request.headers.get("Authorization") or ""
    if not header.lower().startswith("bearer "):
        return None
    token = header[7:].strip()
    return token or None


def _auth_error_response(exc: AuthError) -> JSONResponse:
    return JSONResponse(
        {"ok": False, "error": {"code": exc.code, "message": exc.message}},
        status_code=exc.http_status,
    )


def _cors_headers(request: Request) -> dict[str, str]:
    origin = request.headers.get("Origin")
    headers = {
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }
    if origin:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Vary"] = "Origin"
        headers["Access-Control-Allow-Credentials"] = "true"
    else:
        headers["Access-Control-Allow-Origin"] = "*"
    return headers


def _bool_env(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", "disabled"}


def _ocs_api_keys() -> set[str]:
    raw = os.getenv("STQB_OCS_API_KEYS", "")
    return {part.strip() for part in raw.split(",") if part.strip()}


def _query_from_mapping(params: dict[str, list[str]]) -> QuestionQuery:
    """Build a query from a mapping used by legacy tests and adapters."""
    title = _first(params, "title")
    question_type = _first(params, "type") or "unknown"
    options = _sanitize_query_options(title, question_type, _split_options(_first(params, "options")))
    request_id = _first(params, "request_id") or None
    return QuestionQuery(title=title, options=options, question_type=question_type, request_id=request_id)


def _query_from_payload(payload: QueryPayload | dict) -> QuestionQuery:
    """Build a query from JSON body data."""
    if isinstance(payload, QueryPayload):
        raw_options = payload.options
        question_type = payload.type or payload.question_type or "unknown"
        title = str(payload.title or "")
        return QuestionQuery(
            title=title,
            options=_sanitize_query_options(title, str(question_type), _options_from_raw(raw_options)),
            question_type=str(question_type),
            request_id=payload.request_id,
        )
    raw_options = payload.get("options") or ()
    title = str(payload.get("title") or "")
    question_type = str(payload.get("type") or payload.get("question_type") or "unknown")
    return QuestionQuery(
        title=title,
        options=_sanitize_query_options(title, question_type, _options_from_raw(raw_options)),
        question_type=question_type,
        request_id=payload.get("request_id"),
    )


def _options_from_raw(raw_options: str | list[str] | tuple[str, ...] | Any) -> tuple[str, ...]:
    if isinstance(raw_options, str):
        return _split_options(raw_options)
    return tuple(str(value).strip() for value in raw_options or () if _is_real_option(str(value)))


def _first(params: dict[str, list[str]], key: str) -> str:
    values = params.get(key) or [""]
    return values[0]


def _split_options(value: str) -> tuple[str, ...]:
    """Split OCS option text while filtering editor noise."""
    if not value:
        return ()
    parts = value.splitlines() if "\n" in value else value.split("#")
    return tuple(part.strip() for part in parts if _is_real_option(part))


def _is_real_option(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return False
    noisy_markers = (
        "window.",
        "ueditor",
        "geteditor",
        "loadeditoranswerd",
        "answercontentchange",
        "allowpaste",
        "addlistener",
        "beforepaste",
        "initialframe",
        "var ",
        "function",
        "点击上传",
    )
    lowered = stripped.lower()
    if stripped in {"}", "{", "});", ");", ");}", "};"}:
        return False
    return not any(marker in lowered for marker in noisy_markers)


def _sanitize_query_options(title: str, question_type: str, options: tuple[str, ...]) -> tuple[str, ...]:
    if _is_completion_request(title, question_type):
        return ()
    return options


def _is_completion_request(title: str, question_type: str) -> bool:
    normalized_type = (question_type or "").strip().lower()
    stripped_title = (title or "").strip()
    return (
        normalized_type in {"completion", "blank", "fill", "填空", "填空题"}
        or stripped_title.startswith("填空题")
        or "____" in stripped_title
        or "___" in stripped_title
    )


def _response_for_path(path: str, result) -> dict:
    if path == "/ocs/query":
        return to_ocs_response(result)
    return result.to_api_dict()


def _status_payload(lookup: LocalQuestionIndex | AnswerService) -> dict:
    status = lookup.status()
    return {
        "ok": True,
        "service": "study-question-bank-assistant",
        **status,
    }


def _log_query(path: str, method: str, query: QuestionQuery, result, elapsed_seconds: float) -> None:
    answer = result.candidate_answer or result.answer_text
    log_event(
        "query",
        {
            "method": method,
            "path": path,
            "title": query.title,
            "title_length": len(query.title),
            "options_count": len(query.options),
            "options": list(query.options)[:8],
            "question_type": query.question_type,
            "ok": result.ok,
            "answer": answer,
            "answer_raw": result.candidate_answer,
            "answer_text": result.answer_text,
            "resolution_mode": result.resolution_mode,
            "confidence": result.confidence,
            "error_code": result.error_code,
            "error_message": result.error_message,
            "elapsed_ms": round(elapsed_seconds * 1000, 2),
        },
    )
    if path == "/ocs/query" and not result.candidate_answer and result.answer_text:
        log_event(
            "ocs_answer_fallback_used",
            {
                "title": query.title,
                "question_type": query.question_type,
                "answer_text": result.answer_text,
                "resolution_mode": result.resolution_mode,
            },
        )


def _base_url_from_request(request: Request) -> str:
    host = request.headers.get("Host") or "127.0.0.1:8765"
    return f"http://{host}"


def _base_url_from_headers(headers) -> str:
    """Legacy helper retained for tests that pass a header-like mapping."""
    host = headers.get("Host") or "127.0.0.1:8765"
    return f"http://{host}"


def _build_session_cookie(token: str, max_age: int | None) -> str:
    parts = [f"{_SESSION_COOKIE}={token}", "Path=/", "HttpOnly", "SameSite=Strict"]
    if max_age is not None:
        parts.append(f"Max-Age={int(max_age)}")
    return "; ".join(parts)


def _expire_session_cookie() -> str:
    return f"{_SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"

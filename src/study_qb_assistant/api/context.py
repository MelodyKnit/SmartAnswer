"""API 层上下文、鉴权与通用响应辅助。"""

from __future__ import annotations

import os
from collections.abc import Iterable

from fastapi import Request
from starlette.responses import JSONResponse

from ..answering import AnswerService
from ..auth import AuthError, AuthService
from ..platform import PlatformService
from ..search import LocalQuestionIndex
from ..storage.question_repository import IndexQuestionRepository, SqlAlchemyQuestionRepository

SESSION_COOKIE = "stqb_session"
PROTECTED_PATHS = {"/query", "/ocs/query", "/status", "/debug/recent", "/debug/usage-audit"}


def get_lookup_service(request: Request) -> LocalQuestionIndex | AnswerService:
    """读取当前应用挂载的查题服务。"""
    return request.app.state.lookup


def get_auth_service(request: Request) -> AuthService:
    """读取当前应用挂载的鉴权服务。"""
    return request.app.state.auth


def get_platform_service(request: Request) -> PlatformService:
    """读取当前应用挂载的平台服务。"""
    return request.app.state.platform


def get_question_repository(
    request: Request,
) -> IndexQuestionRepository | SqlAlchemyQuestionRepository:
    """读取题库管理仓储。

    后期路由拆分后题库管理依赖 repository 形态；当前运行时主数据仍在
    `LocalQuestionIndex` 中，因此默认按当前 lookup 构造索引适配器。
    """

    repository = getattr(request.app.state, "question_repository", None)
    if repository is not None:
        return repository
    lookup = get_lookup_service(request)
    index = lookup.index if isinstance(lookup, AnswerService) else lookup
    return IndexQuestionRepository(index)


def is_auth_required(request: Request) -> bool:
    """读取当前应用是否启用了数据接口鉴权。"""
    return bool(getattr(request.app.state, "require_auth", False))


def current_user(request: Request) -> dict | None:
    """解析当前请求关联的登录用户。"""
    auth = get_auth_service(request)
    return auth.resolve_session(session_token_from_request(request))


def require_roles(request: Request, roles: Iterable[str]) -> JSONResponse | None:
    """校验当前用户是否属于允许角色集合。"""
    user = current_user(request)
    if user is None:
        return unauthorized_response("请先登录")
    if user["role"] not in set(roles):
        return forbidden_response("权限不足")
    return None


def require_permissions(request: Request, permissions: Iterable[str]) -> JSONResponse | None:
    """校验当前用户是否具备指定权限。"""

    user = current_user(request)
    if user is None:
        return unauthorized_response("请先登录")
    if user["role"] == "superadmin":
        return None
    required = {item for item in permissions if item}
    if not required:
        return None
    platform = get_platform_service(request)
    owned = platform.role_permissions(str(user["role"]))
    if not required.issubset(owned):
        return forbidden_response("权限不足")
    return None


def guard_protected_request(request: Request) -> JSONResponse | None:
    """对受保护的数据接口执行统一鉴权。"""
    if not is_auth_required(request) or request.url.path not in PROTECTED_PATHS:
        return None
    if request.url.path == "/ocs/query":
        token = authorization_bearer(request)
        if token and token in ocs_api_keys():
            return None
        if token:
            platform = get_platform_service(request)
            auth = get_auth_service(request)
            try:
                token_info = platform.resolve_token(token)
            except AuthError as exc:
                return auth_error_response(exc)
            if (
                token_info is not None
                and auth.resolve_user_by_id(token_info["user_id"]) is not None
            ):
                return None
        return unauthorized_response("请提供有效 API Key")
    if current_user(request) is not None:
        return None
    return unauthorized_response("请先登录")


def bearer_authorized(request: Request) -> bool:
    """校验 Bearer 令牌是否可直接访问 OCS 接口。"""
    token = authorization_bearer(request)
    if not token:
        return False
    if token in ocs_api_keys():
        return True
    platform = get_platform_service(request)
    auth = get_auth_service(request)
    token_info = platform.resolve_token(token)
    if token_info is None:
        return False
    user = auth.resolve_user_by_id(token_info["user_id"])
    return user is not None


def session_token_from_request(request: Request) -> str | None:
    """优先读取 Authorization，其次读取会话 Cookie。"""
    bearer = authorization_bearer(request)
    if bearer:
        return bearer
    return request.cookies.get(SESSION_COOKIE)


def authorization_bearer(request: Request) -> str | None:
    """从 Authorization 请求头中提取 Bearer 令牌。"""
    header = request.headers.get("Authorization") or ""
    if not header.lower().startswith("bearer "):
        return None
    token = header[7:].strip()
    return token or None


def auth_error_response(exc: AuthError) -> JSONResponse:
    """把鉴权业务异常映射成统一 JSON 错误响应。"""
    return JSONResponse(
        {"ok": False, "error": {"code": exc.code, "message": exc.message}},
        status_code=exc.http_status,
    )


def unauthorized_response(message: str) -> JSONResponse:
    """构造未登录错误响应。"""
    return JSONResponse(
        {"ok": False, "error": {"code": "UNAUTHORIZED", "message": message}},
        status_code=401,
    )


def forbidden_response(message: str) -> JSONResponse:
    """构造权限不足错误响应。"""
    return JSONResponse(
        {"ok": False, "error": {"code": "FORBIDDEN", "message": message}},
        status_code=403,
    )


def cors_headers(request: Request) -> dict[str, str]:
    """生成当前请求对应的 CORS 响应头。"""
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


def bool_env(name: str, *, default: bool = False) -> bool:
    """按常见布尔环境变量语义解析配置。"""
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", "disabled"}


def ocs_api_keys() -> set[str]:
    """读取允许直接访问 OCS 接口的静态令牌集合。"""
    raw = os.getenv("STQB_OCS_API_KEYS", "")
    return {part.strip() for part in raw.split(",") if part.strip()}

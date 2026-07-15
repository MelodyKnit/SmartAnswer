"""API 会话解析、权限校验与鉴权响应。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Annotated

from fastapi import Depends, Request
from starlette.responses import JSONResponse

from ..auth import AuthError
from ..config import get_global_config
from .dependencies import (
    PermissionServiceDep,
    get_auth_service,
    get_permission_service,
    get_token_service,
)
from .legacy import unversioned_api_path

SESSION_COOKIE = "stqb_session"
PROTECTED_PATHS = {"/query", "/ocs/query", "/status", "/debug/recent", "/debug/usage-audit"}


def is_auth_required(request: Request) -> bool:
    """返回当前应用是否启用了数据接口鉴权。"""

    return bool(getattr(request.app.state, "require_auth", False))


def current_user(request: Request) -> dict | None:
    """解析当前请求关联的登录用户。"""

    return get_auth_service(request).resolve_session(session_token_from_request(request))


CurrentUserDep = Annotated[dict | None, Depends(current_user)]


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
    owned = get_permission_service(request).role_permissions(str(user["role"]))
    if not required.issubset(owned):
        return forbidden_response("权限不足")
    return None


def require_access(
    roles: Iterable[str] = (),
    permissions: Iterable[str] = (),
) -> Callable[[dict | None, PermissionServiceDep], None]:
    """构建可声明在路由参数中的权限门禁依赖。"""

    allowed_roles = {str(role).strip() for role in roles if str(role).strip()}
    required_permissions = {
        str(permission).strip() for permission in permissions if str(permission).strip()
    }

    def guard(user: CurrentUserDep, permissions_service: PermissionServiceDep) -> None:
        if user is None:
            raise AuthError("UNAUTHORIZED", "请先登录", http_status=401)
        if allowed_roles and str(user["role"]) not in allowed_roles:
            raise AuthError("FORBIDDEN", "权限不足", http_status=403)
        if not required_permissions or str(user["role"]) == "superadmin":
            return
        owned = permissions_service.role_permissions(str(user["role"]))
        if not required_permissions.issubset(owned):
            raise AuthError("FORBIDDEN", "权限不足", http_status=403)

    return guard


def guard_protected_request(request: Request) -> JSONResponse | None:
    """对受保护的数据接口执行统一鉴权。"""

    logical_path = unversioned_api_path(request.url.path)
    if not is_auth_required(request) or logical_path not in PROTECTED_PATHS:
        return None
    if logical_path == "/ocs/query":
        token = authorization_bearer(request)
        if token and token in ocs_api_keys():
            return None
        if token:
            token_service = get_token_service(request)
            auth = get_auth_service(request)
            try:
                token_info = token_service.resolve_token(token)
            except AuthError as exc:
                return auth_error_response(exc)
            if token_info is not None and auth.resolve_user_by_id(token_info["user_id"]):
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
    token_info = get_token_service(request).resolve_token(token)
    if token_info is None:
        return False
    return get_auth_service(request).resolve_user_by_id(token_info["user_id"]) is not None


def session_token_from_request(request: Request) -> str | None:
    """优先读取 Authorization，其次读取会话 Cookie。"""

    return authorization_bearer(request) or request.cookies.get(SESSION_COOKIE)


def authorization_bearer(request: Request) -> str | None:
    """从 Authorization 请求头中提取 Bearer 令牌。"""

    header = request.headers.get("Authorization") or ""
    if not header.lower().startswith("bearer "):
        return None
    return header[7:].strip() or None


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


def ocs_api_keys() -> set[str]:
    """返回允许直接访问 OCS 接口的静态令牌集合。"""

    return set(get_global_config().ocs_api_keys)

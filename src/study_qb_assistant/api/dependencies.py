"""FastAPI 依赖注入别名。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Annotated

from fastapi import Depends

from ..answering import AnswerService
from ..auth import AuthError, AuthService
from ..platform import PlatformService
from ..search import LocalQuestionIndex
from ..storage.question_repository import SqlAlchemyQuestionRepository
from .context import (
    current_user,
    get_auth_service,
    get_lookup_service,
    get_platform_service,
    get_question_repository,
)

LookupServiceDep = Annotated[LocalQuestionIndex | AnswerService, Depends(get_lookup_service)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
PlatformServiceDep = Annotated[PlatformService, Depends(get_platform_service)]
QuestionRepositoryDep = Annotated[
    SqlAlchemyQuestionRepository,
    Depends(get_question_repository),
]
CurrentUserDep = Annotated[dict | None, Depends(current_user)]


def require_access(
    roles: Iterable[str] = (),
    permissions: Iterable[str] = (),
) -> Callable[[dict | None, PlatformService], None]:
    """构建 FastAPI 权限门禁依赖。

    权限失败统一抛出 `AuthError`，由应用层异常处理器转换为项目既有 JSON 错误结构。
    """
    allowed_roles = {str(role).strip() for role in roles if str(role).strip()}
    required_permissions = {
        str(permission).strip() for permission in permissions if str(permission).strip()
    }

    def guard(user: CurrentUserDep, platform: PlatformServiceDep) -> None:
        if user is None:
            raise AuthError("UNAUTHORIZED", "请先登录", http_status=401)
        if allowed_roles and str(user["role"]) not in allowed_roles:
            raise AuthError("FORBIDDEN", "权限不足", http_status=403)
        if not required_permissions or str(user["role"]) == "superadmin":
            return
        owned = platform.role_permissions(str(user["role"]))
        if not required_permissions.issubset(owned):
            raise AuthError("FORBIDDEN", "权限不足", http_status=403)

    return guard

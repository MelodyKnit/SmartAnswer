"""FastAPI 本地服务入口。

本模块只负责组装应用，不再承担具体业务路由、请求模型或鉴权细节。
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request, Response

from ..answering import AnswerService
from ..auth import AuthService
from ..platform import PlatformService
from ..search import LocalQuestionIndex
from ..storage.question_repository import SqlAlchemyQuestionRepository
from .context import bool_env, cors_headers
from .query_parser import build_query_from_mapping, split_options
from .route_support import base_url_from_headers, build_session_cookie, expire_session_cookie
from .routes import (
    build_auth_router,
    build_platform_router,
    build_query_router,
    build_static_router,
)


def create_app(
    lookup: LocalQuestionIndex | AnswerService,
    *,
    auth_service: AuthService | None = None,
    platform_service: PlatformService | None = None,
    require_auth: bool | None = None,
) -> FastAPI:
    """构建本地 FastAPI 应用。"""
    configured_database = (
        os.getenv("STQB_DATABASE_URL")
        or os.getenv("STQB_DATABASE_PATH")
        or "data/runtime/study-qb.sqlite3"
    )
    database_locator = (
        getattr(platform_service, "path", None)
        or getattr(auth_service, "path", None)
        or configured_database
    )
    auth = auth_service or AuthService(database_locator)
    platform = platform_service or PlatformService(database_locator)
    question_repository = SqlAlchemyQuestionRepository(database_locator)
    auth_required = bool_env("STQB_REQUIRE_AUTH") if require_auth is None else require_auth
    lookup_index = lookup.index if isinstance(lookup, AnswerService) else lookup
    question_repository.sync_from_index(lookup_index)
    # 只有显式接入平台/鉴权服务时，才把数据库视为运行时索引的权威来源。
    if auth_service is not None or platform_service is not None:
        lookup_index.replace_records(tuple(question_repository.list_indexable_records()))
    if isinstance(lookup, AnswerService):
        lookup.question_repository = question_repository
    app = FastAPI(title="Study Question Bank Assistant", version="0.1.0")
    app.state.lookup = lookup
    app.state.auth = auth
    app.state.platform = platform
    app.state.question_repository = question_repository
    app.state.require_auth = auth_required

    @app.middleware("http")
    async def cors_and_options(request: Request, call_next) -> Response:
        if request.method == "OPTIONS":
            return Response(status_code=204, headers=cors_headers(request))
        response = await call_next(request)
        for key, value in cors_headers(request).items():
            response.headers[key] = value
        return response

    app.include_router(build_auth_router())
    app.include_router(build_query_router())
    app.include_router(build_platform_router())
    app.include_router(build_static_router())

    return app


# 兼容历史测试与旧调用方的最薄导出层。
_query_from_mapping = build_query_from_mapping
_split_options = split_options
_base_url_from_headers = base_url_from_headers
_build_session_cookie = build_session_cookie
_expire_session_cookie = expire_session_cookie

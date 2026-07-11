"""FastAPI 本地服务入口。

本模块只负责组装应用，不再承担具体业务路由、请求模型或鉴权细节。
"""

from __future__ import annotations

from fastapi import FastAPI, Request, Response
from starlette.responses import FileResponse

from .. import __version__
from ..answering import AnswerService
from ..auth import AuthService
from ..config import get_global_config
from ..logger import log_event
from ..platform import PlatformService
from ..search import LocalQuestionIndex
from ..storage.question_repository import SqlAlchemyQuestionRepository
from ..llm.tracing import set_trace_sink
from ..updates import ProjectUpdateService
from ..version import BUILD_INFO
from .context import bool_env, cors_headers
from .query_parser import build_query_from_mapping, split_options
from .route_support import (
    STATIC_DIR,
    base_url_from_headers,
    build_session_cookie,
    expire_session_cookie,
    should_serve_spa_shell,
)
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
    project_update_service: ProjectUpdateService | None = None,
    require_auth: bool | None = None,
) -> FastAPI:
    """构建本地 FastAPI 应用。"""
    configured_database = get_global_config().database_locator
    database_locator = (
        getattr(platform_service, "path", None)
        or getattr(auth_service, "path", None)
        or configured_database
    )
    auth = auth_service or AuthService(database_locator)
    platform = platform_service or PlatformService(database_locator)
    config = get_global_config()
    project_updates = project_update_service or ProjectUpdateService(
        config.update_dir,
        enabled=config.update_enabled,
        build_info=BUILD_INFO,
    )
    question_repository = SqlAlchemyQuestionRepository(database_locator)
    auth_required = bool_env("STQB_REQUIRE_AUTH") if require_auth is None else require_auth
    lookup_index = lookup.index if isinstance(lookup, AnswerService) else lookup
    log_event(
        "question_index_sync_start",
        {"record_count": len(lookup_index.records), "source_path": lookup_index.source_path},
    )
    sync_result = question_repository.sync_from_index(lookup_index)
    log_event(
        "question_index_sync_complete",
        {
            "record_count": sync_result.record_count,
            "synced_count": sync_result.synced_count,
            "skipped": sync_result.skipped,
        },
    )
    # 只有显式接入平台/鉴权服务时，才把数据库视为运行时索引的权威来源。
    if auth_service is not None or platform_service is not None:
        log_event("question_index_load_start", {})
        lookup_index.replace_records(tuple(question_repository.list_indexable_records()))
        log_event("question_index_load_complete", {"record_count": len(lookup_index.records)})
    if isinstance(lookup, AnswerService):
        lookup.question_repository = question_repository
    app = FastAPI(title="Study Question Bank Assistant", version=__version__)
    app.state.lookup = lookup
    app.state.auth = auth
    app.state.platform = platform
    app.state.question_repository = question_repository
    app.state.project_updates = project_updates
    app.state.require_auth = auth_required
    set_trace_sink(platform.save_llm_call_trace)

    @app.middleware("http")
    async def cors_and_options(request: Request, call_next) -> Response:
        if request.method == "OPTIONS":
            return Response(status_code=204, headers=cors_headers(request))
        if request.method == "GET" and should_serve_spa_shell(
            request, request.url.path
        ):
            html_path = STATIC_DIR / "index.html"
            if html_path.exists():
                response = FileResponse(html_path, media_type="text/html; charset=utf-8")
                for key, value in cors_headers(request).items():
                    response.headers[key] = value
                return response
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

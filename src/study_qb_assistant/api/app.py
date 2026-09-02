"""FastAPI 本地服务入口。

本模块只负责组装应用，不再承担具体业务路由、请求模型或鉴权细节。
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI

from .. import __version__
from ..adapters.ocs import DefaultOcsIntegration, OcsIntegrationPort
from ..answering import AnswerService
from ..auth import AuthService
from ..config import get_global_config
from ..logger import log_event
from ..logger.storage import configure_log_storage_policy
from ..platform.container import PlatformServices
from ..search import LocalQuestionIndex
from ..storage.repositories.questions import SqlAlchemyQuestionRepository
from ..llm.tracing import set_trace_sink
from .middleware import install_http_middleware
from .exception_handlers import install_exception_handlers
from .ocs import build_ocs_router
from .static import build_static_router
from .v1 import API_V1_PREFIX, build_api_v1_router
from .legacy import mark_legacy_api_request


def create_app(
    lookup: LocalQuestionIndex | AnswerService,
    *,
    auth_service: AuthService | None = None,
    platform_services: PlatformServices | None = None,
    ocs_integration: OcsIntegrationPort | None = None,
    require_auth: bool | None = None,
    lifespan: Any = None,
) -> FastAPI:
    """构建本地 FastAPI 应用。"""
    configured_database = get_global_config().database_locator
    database_locator = (
        getattr(platform_services, "path", None)
        or getattr(auth_service, "path", None)
        or configured_database
    )
    auth = auth_service or AuthService(database_locator)
    services = platform_services or PlatformServices(database_locator)
    configure_log_storage_policy(services.settings.get_log_storage_policy)
    question_repository = SqlAlchemyQuestionRepository(database_locator)
    auth_required = (
        get_global_config().require_auth if require_auth is None else require_auth
    )
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
    if auth_service is not None or platform_services is not None:
        log_event("question_index_load_start", {})
        lookup_index.replace_records(tuple(question_repository.list_indexable_records()))
        log_event("question_index_load_complete", {"record_count": len(lookup_index.records)})
    if isinstance(lookup, AnswerService):
        lookup.question_repository = question_repository
    app = FastAPI(
        title="Study Question Bank Assistant",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/v1/openapi.json",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.lookup = lookup
    app.state.auth = auth
    app.state.services = services
    app.state.question_repository = question_repository
    app.state.require_auth = auth_required
    app.state.ocs_integration = ocs_integration or DefaultOcsIntegration()
    set_trace_sink(services.llm.save_call_trace)

    install_exception_handlers(app)
    install_http_middleware(app)

    business_router = build_api_v1_router()
    app.include_router(business_router, prefix=API_V1_PREFIX)
    app.include_router(build_ocs_router())
    app.include_router(
        business_router,
        dependencies=[Depends(mark_legacy_api_request)],
        include_in_schema=False,
    )
    app.include_router(build_static_router())

    return app

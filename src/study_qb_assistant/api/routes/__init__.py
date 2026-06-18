"""按业务域拆分的 FastAPI 路由入口。"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter

from .auth import build_auth_router
from .catalog import build_catalog_router
from .feedback import build_feedback_router
from .import_scripts import build_import_script_router
from .llm import build_llm_router
from .query import build_query_router
from .static import build_static_router
from .system import build_system_router
from .tokens import build_token_router
from .users import build_user_router
from .wallet import build_wallet_router
from .workbench import build_workbench_router

RouterFactory = Callable[[], APIRouter]

PLATFORM_ROUTE_BUILDERS: tuple[RouterFactory, ...] = (
    build_user_router,
    build_token_router,
    build_feedback_router,
    build_wallet_router,
    build_workbench_router,
    build_catalog_router,
    build_import_script_router,
    build_llm_router,
    build_system_router,
)


def build_platform_router() -> APIRouter:
    """组合平台域下的多个子路由。"""
    router = APIRouter()
    for build_router in PLATFORM_ROUTE_BUILDERS:
        router.include_router(build_router())
    return router


__all__ = [
    "build_auth_router",
    "build_query_router",
    "build_static_router",
    "build_platform_router",
    "build_feedback_router",
    "build_token_router",
    "build_user_router",
    "build_wallet_router",
    "build_workbench_router",
    "build_catalog_router",
    "build_import_script_router",
    "build_llm_router",
    "build_system_router",
]

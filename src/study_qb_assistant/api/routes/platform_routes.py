"""平台组合路由入口。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from .platform_catalog_routes import build_platform_catalog_router
from .platform_integration_routes import build_platform_integration_router
from .platform_admin_routes import build_platform_admin_router
from .platform_user_routes import build_platform_user_router
from .platform_wallet_routes import build_platform_wallet_router
from .platform_workbench_routes import build_platform_workbench_router


def build_platform_router() -> APIRouter:
    """组合平台域下的多个子路由。"""
    router = APIRouter()
    router.include_router(build_platform_user_router())
    router.include_router(build_platform_admin_router())
    router.include_router(build_platform_wallet_router())
    router.include_router(build_platform_workbench_router())
    router.include_router(build_platform_integration_router())
    router.include_router(build_platform_catalog_router())
    return router

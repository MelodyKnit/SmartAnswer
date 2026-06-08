"""按业务域拆分的 FastAPI 路由。"""

from .auth_routes import build_auth_router
from .platform_catalog_routes import build_platform_catalog_router
from .platform_integration_routes import build_platform_integration_router
from .platform_routes import build_platform_router
from .platform_workbench_routes import build_platform_workbench_router
from .query_routes import build_query_router
from .static_routes import build_static_router

__all__ = [
    "build_auth_router",
    "build_platform_catalog_router",
    "build_platform_integration_router",
    "build_platform_router",
    "build_platform_workbench_router",
    "build_query_router",
    "build_static_router",
]

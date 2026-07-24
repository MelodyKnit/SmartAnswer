"""API v1 业务路由聚合入口。"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter

from .announcements import build_announcement_router
from .auth import build_auth_router
from .dashboard import build_dashboard_router
from .feedback import build_feedback_router
from .import_scripts import build_import_script_router
from .image_generation import build_image_generation_router
from .llm import build_llm_router
from .media import build_media_router
from .notifications import build_notification_router
from .permissions import build_permission_router
from .query import build_query_router
from .questions import build_question_router
from .system import build_system_router
from .tokens import build_token_router
from .usage import build_usage_router
from .users import build_user_router
from .wallet import build_wallet_router

RouterFactory = Callable[[], APIRouter]

ROUTER_FACTORIES: tuple[RouterFactory, ...] = (
    build_auth_router,
    build_query_router,
    build_user_router,
    build_token_router,
    build_announcement_router,
    build_feedback_router,
    build_wallet_router,
    build_dashboard_router,
    build_usage_router,
    build_notification_router,
    build_permission_router,
    build_question_router,
    build_import_script_router,
    build_image_generation_router,
    build_llm_router,
    build_media_router,
    build_system_router,
)


def build_api_v1_router() -> APIRouter:
    """组合当前版本的全部业务路由。"""

    router = APIRouter()
    for factory in ROUTER_FACTORIES:
        router.include_router(factory())
    return router

"""FastAPI 应用状态依赖。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from ..adapters.ocs import OcsIntegrationPort
from ..answering import AnswerService
from ..auth import AuthService
from ..llm.management import LlmManagementService
from ..platform.container import PlatformServices
from ..platform.announcements import AnnouncementService
from ..platform.dashboard import DashboardService
from ..platform.feedback import FeedbackService
from ..platform.import_scripts import ImportScriptService
from ..platform.notifications import NotificationService
from ..platform.permissions import PermissionService
from ..platform.settings import SettingsService
from ..platform.tokens import TokenService
from ..platform.updates.service import ProjectUpdateService
from ..platform.usage import UsageService
from ..platform.wallet import WalletService
from ..search import LocalQuestionIndex
from ..storage.repositories.questions import (
    IndexQuestionRepository,
    SqlAlchemyQuestionRepository,
)


def get_lookup_service(request: Request) -> LocalQuestionIndex | AnswerService:
    """返回当前应用挂载的查题服务。"""

    return request.app.state.lookup


def get_auth_service(request: Request) -> AuthService:
    """返回当前应用挂载的鉴权服务。"""

    return request.app.state.auth


def get_platform_services(request: Request) -> PlatformServices:
    """返回当前应用挂载的平台服务容器。"""

    return request.app.state.services


def get_token_service(request: Request) -> TokenService:
    return get_platform_services(request).tokens


def get_settings_service(request: Request) -> SettingsService:
    return get_platform_services(request).settings


def get_usage_service(request: Request) -> UsageService:
    return get_platform_services(request).usage


def get_feedback_service(request: Request) -> FeedbackService:
    return get_platform_services(request).feedback


def get_notification_service(request: Request) -> NotificationService:
    return get_platform_services(request).notifications


def get_announcement_service(request: Request) -> AnnouncementService:
    return get_platform_services(request).announcements


def get_wallet_service(request: Request) -> WalletService:
    return get_platform_services(request).wallet


def get_import_script_service(request: Request) -> ImportScriptService:
    return get_platform_services(request).import_scripts


def get_permission_service(request: Request) -> PermissionService:
    return get_platform_services(request).permissions


def get_dashboard_service(request: Request) -> DashboardService:
    return get_platform_services(request).dashboard


def get_llm_management_service(request: Request) -> LlmManagementService:
    return get_platform_services(request).llm


def get_project_update_service(request: Request) -> ProjectUpdateService:
    """返回当前应用的项目更新控制面服务。"""

    return get_platform_services(request).updates


def get_ocs_integration(request: Request) -> OcsIntegrationPort:
    """返回当前应用挂载的 OCS 集成实现。"""

    return request.app.state.ocs_integration


def get_question_repository(
    request: Request,
) -> IndexQuestionRepository | SqlAlchemyQuestionRepository:
    """返回题库仓储；测试场景缺省时使用运行时索引适配器。"""

    repository = getattr(request.app.state, "question_repository", None)
    if repository is not None:
        return repository
    lookup = get_lookup_service(request)
    index = lookup.index if isinstance(lookup, AnswerService) else lookup
    return IndexQuestionRepository(index)


LookupServiceDep = Annotated[LocalQuestionIndex | AnswerService, Depends(get_lookup_service)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
TokenServiceDep = Annotated[TokenService, Depends(get_token_service)]
SettingsServiceDep = Annotated[SettingsService, Depends(get_settings_service)]
UsageServiceDep = Annotated[UsageService, Depends(get_usage_service)]
FeedbackServiceDep = Annotated[FeedbackService, Depends(get_feedback_service)]
NotificationServiceDep = Annotated[
    NotificationService, Depends(get_notification_service)
]
AnnouncementServiceDep = Annotated[
    AnnouncementService, Depends(get_announcement_service)
]
WalletServiceDep = Annotated[WalletService, Depends(get_wallet_service)]
ImportScriptServiceDep = Annotated[
    ImportScriptService, Depends(get_import_script_service)
]
PermissionServiceDep = Annotated[PermissionService, Depends(get_permission_service)]
DashboardServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]
LlmManagementServiceDep = Annotated[
    LlmManagementService, Depends(get_llm_management_service)
]
ProjectUpdateServiceDep = Annotated[
    ProjectUpdateService, Depends(get_project_update_service)
]
QuestionRepositoryDep = Annotated[
    IndexQuestionRepository | SqlAlchemyQuestionRepository,
    Depends(get_question_repository),
]

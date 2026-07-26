"""平台领域服务装配容器。"""

from __future__ import annotations

from pathlib import Path
from threading import RLock

from ..llm.management import LlmManagementService
from ..storage.database import get_session_factory
from ..storage.repositories.announcements import AnnouncementRepository
from ..storage.repositories.feedback import FeedbackRepository
from ..storage.repositories.import_scripts import ImportScriptRepository
from ..storage.repositories.image_generation import ImageGenerationRepository
from ..storage.repositories.llm import LlmRepository
from ..storage.repositories.notifications import NotificationRepository
from ..storage.repositories.roles import RoleRepository
from ..storage.repositories.settings import SettingsRepository
from ..storage.repositories.tokens import TokenRepository
from ..storage.repositories.usage import UsageRepository
from ..storage.repositories.wallet import WalletRepository
from .announcements import AnnouncementService
from .dashboard import DashboardService
from .feedback import FeedbackService
from .import_scripts import ImportScriptService
from .image_generation.service import ImageGenerationService
from .notifications import NotificationService
from .permissions import PermissionService
from .settings import SettingsService
from .tokens import TokenService
from .updates.service import ProjectUpdateService
from .usage import UsageService
from .wallet import WalletService


class PlatformServices:
    """组装平台领域服务，不承载业务转发方法。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path) if isinstance(path, Path) or "://" not in str(path) else path
        session_factory = get_session_factory(path)
        lock = RLock()

        token_repository = TokenRepository(session_factory)
        usage_repository = UsageRepository(session_factory)
        feedback_repository = FeedbackRepository(session_factory)
        wallet_repository = WalletRepository(session_factory)
        settings_repository = SettingsRepository(session_factory)
        notification_repository = NotificationRepository(session_factory)
        announcement_repository = AnnouncementRepository(session_factory)
        import_script_repository = ImportScriptRepository(session_factory)
        role_repository = RoleRepository(session_factory, settings_repository)
        llm_repository = LlmRepository(session_factory, settings_repository)
        image_generation_repository = ImageGenerationRepository(session_factory)

        self.tokens = TokenService(token_repository, lock)
        self.settings = SettingsService(settings_repository, llm_repository, lock)
        self.usage = UsageService(usage_repository, lock)
        self.feedback = FeedbackService(feedback_repository, usage_repository, lock)
        self.notifications = NotificationService(
            notification_repository,
            announcement_repository,
            lock,
        )
        self.announcements = AnnouncementService(announcement_repository, lock)
        self.wallet = WalletService(wallet_repository, lock)
        self.import_scripts = ImportScriptService(
            import_script_repository,
            token_repository,
            lock,
        )
        self.permissions = PermissionService(role_repository, lock)
        self.permissions.ensure_system_roles()
        self.permissions.ensure_image_generation_permission_defaults()
        self.llm = LlmManagementService(llm_repository, lock)
        self.image_generation = ImageGenerationService(
            image_generation_repository,
            self.settings,
            lock,
        )
        self.updates = ProjectUpdateService(settings_repository, self.settings, lock)
        self.dashboard = DashboardService(
            usage=self.usage,
            notifications=self.notifications,
            wallet=self.wallet,
            settings=self.settings,
            llm=self.llm,
        )

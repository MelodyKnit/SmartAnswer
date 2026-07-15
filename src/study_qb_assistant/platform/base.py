"""平台领域服务共享基础设施。"""

from __future__ import annotations

from threading import RLock
from typing import Any


class PlatformDomainService:
    """为平台领域服务提供共享仓储和事务锁。"""

    def __init__(
        self,
        repository: Any,
        lock: RLock,
    ) -> None:
        self.repository = repository
        self.lock = lock

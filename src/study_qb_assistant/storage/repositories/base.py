"""SQLAlchemy 领域仓储基础设施。"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session


class SqlAlchemyRepository:
    """持有共享 SQLAlchemy Session 工厂。"""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory

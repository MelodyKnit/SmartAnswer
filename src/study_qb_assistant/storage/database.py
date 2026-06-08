"""数据库连接与会话工厂。"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

_ENGINE_CACHE: dict[str, Engine] = {}
_SESSION_FACTORY_CACHE: dict[str, sessionmaker[Session]] = {}


def resolve_database_url(path_or_url: str | Path | None) -> str:
    """解析数据库地址，默认使用 SQLite 文件。"""
    env_url = os.getenv("STQB_DATABASE_URL", "").strip()
    if env_url:
        return env_url

    raw = str(path_or_url or os.getenv("STQB_DATABASE_PATH") or "data/runtime/study-qb.sqlite3").strip()
    if "://" in raw:
        return raw

    path = Path(raw)
    if path.suffix.lower() == ".json":
        path = path.with_suffix(".sqlite3")
    elif not path.suffix:
        path = path.with_suffix(".sqlite3")
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.resolve().as_posix()}"


def get_engine(path_or_url: str | Path | None) -> Engine:
    """获取缓存的 SQLAlchemy Engine。"""
    from .orm import Base

    url = resolve_database_url(path_or_url)
    if url not in _ENGINE_CACHE:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite:///") else {}
        engine_kwargs = {"future": True, "connect_args": connect_args}
        if url.startswith("sqlite:///"):
            engine_kwargs["poolclass"] = NullPool
        engine = create_engine(url, **engine_kwargs)
        Base.metadata.create_all(engine)
        _ENGINE_CACHE[url] = engine
    return _ENGINE_CACHE[url]


def get_session_factory(path_or_url: str | Path | None) -> sessionmaker[Session]:
    """获取缓存的 SQLAlchemy Session 工厂。"""
    url = resolve_database_url(path_or_url)
    if url not in _SESSION_FACTORY_CACHE:
        _SESSION_FACTORY_CACHE[url] = sessionmaker(
            bind=get_engine(url),
            expire_on_commit=False,
            class_=Session,
        )
    return _SESSION_FACTORY_CACHE[url]

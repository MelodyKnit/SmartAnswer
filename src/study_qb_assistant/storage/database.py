"""数据库连接与会话工厂。"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
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

    raw = str(
        path_or_url or os.getenv("STQB_DATABASE_PATH") or "data/runtime/study-qb.sqlite3"
    ).strip()
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
        ensure_obsolete_platform_schema_cleanup(engine)
        if url.startswith("sqlite:///"):
            ensure_sqlite_compat_columns(engine)
        else:
            ensure_sql_compat_columns(engine)
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


def ensure_sqlite_compat_columns(engine: Engine) -> None:
    """为旧 SQLite 运行库补齐恢复后新增的轻量字段。"""
    table_columns = {
        "api_tokens": {
            "quota_limit": "INTEGER DEFAULT -1",
            "reject_low_confidence": "INTEGER DEFAULT 0",
            "min_answer_confidence": "REAL DEFAULT 0.0",
        },
        "import_scripts": {
            "description": "TEXT DEFAULT ''",
            "requires_token": "INTEGER DEFAULT 1",
            "tags": "TEXT DEFAULT '[]'",
            "builtin": "INTEGER DEFAULT 0",
            "is_default": "INTEGER DEFAULT 0",
            "ocs_config": "TEXT DEFAULT '[]'",
        },
        "feedbacks": {
            "category": "TEXT DEFAULT 'answer'",
            "admin_note": "TEXT DEFAULT ''",
            "corrected_answer": "TEXT DEFAULT ''",
            "reward_points": "INTEGER DEFAULT 0",
            "handled_by": "TEXT DEFAULT ''",
            "handled_at": "REAL DEFAULT 0",
        },
        "usage_logs": {
            "elapsed_ms": "REAL DEFAULT 0.0",
        },
        "questions": {
            "title_normalized": "TEXT DEFAULT ''",
            "options_raw": "TEXT DEFAULT '[]'",
            "answer_raw": "TEXT",
            "explanation": "TEXT",
            "subject": "TEXT DEFAULT 'default'",
            "chapter": "TEXT",
            "tags": "TEXT DEFAULT '[]'",
            "source_name": "TEXT DEFAULT ''",
            "source_url": "TEXT DEFAULT ''",
            "source_license": "TEXT DEFAULT ''",
            "source_split": "TEXT DEFAULT ''",
            "source_record_path": "TEXT DEFAULT ''",
            "passage": "TEXT",
            "metadata": "TEXT DEFAULT '{}'",
            "metadata_json": "TEXT DEFAULT '{}'",
            "status": "TEXT DEFAULT 'active'",
            "origin_kind": "TEXT DEFAULT ''",
            "record_status": "TEXT DEFAULT 'active'",
            "provider_name": "TEXT DEFAULT ''",
            "confidence": "REAL DEFAULT 0.0",
            "confirmations": "INTEGER DEFAULT 0",
            "conflicts": "INTEGER DEFAULT 0",
            "review_required": "INTEGER DEFAULT 0",
            "is_active": "INTEGER DEFAULT 1",
            "created_at": "REAL DEFAULT 0.0",
            "updated_at": "REAL DEFAULT 0.0",
        },
    }
    with engine.begin() as connection:
        for table, columns in table_columns.items():
            existing = {
                row[1] for row in connection.execute(text(f"PRAGMA table_info({table})")).fetchall()
            }
            if not existing:
                continue
            for column, definition in columns.items():
                if column not in existing:
                    connection.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                    )


def ensure_sql_compat_columns(engine: Engine) -> None:
    """为非 SQLite 运行库补齐轻量兼容字段。"""

    table_columns = {
        "api_tokens": {
            "reject_low_confidence": "INTEGER DEFAULT 0",
            "min_answer_confidence": "FLOAT DEFAULT 0.0",
        },
        "usage_logs": {
            "elapsed_ms": "FLOAT DEFAULT 0.0",
        },
        "questions": {
            "title_normalized": "TEXT DEFAULT ''",
            "options_raw": "TEXT DEFAULT '[]'",
            "answer_raw": "TEXT",
            "explanation": "TEXT",
            "subject": "TEXT DEFAULT 'default'",
            "chapter": "TEXT",
            "tags": "TEXT DEFAULT '[]'",
            "source_name": "TEXT DEFAULT ''",
            "source_url": "TEXT DEFAULT ''",
            "source_license": "TEXT DEFAULT ''",
            "source_split": "TEXT DEFAULT ''",
            "source_record_path": "TEXT DEFAULT ''",
            "passage": "TEXT",
            "metadata": "TEXT DEFAULT '{}'",
            "metadata_json": "TEXT DEFAULT '{}'",
            "status": "TEXT DEFAULT 'active'",
            "origin_kind": "TEXT DEFAULT ''",
            "record_status": "TEXT DEFAULT 'active'",
            "provider_name": "TEXT DEFAULT ''",
            "confidence": "FLOAT DEFAULT 0.0",
            "confirmations": "INTEGER DEFAULT 0",
            "conflicts": "INTEGER DEFAULT 0",
            "review_required": "INTEGER DEFAULT 0",
            "is_active": "INTEGER DEFAULT 1",
            "created_at": "FLOAT DEFAULT 0.0",
            "updated_at": "FLOAT DEFAULT 0.0",
        },
    }
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table, columns in table_columns.items():
            if table not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table)}
            for column, definition in columns.items():
                if column in existing_columns:
                    continue
                try:
                    connection.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                    )
                except Exception as exc:
                    raise RuntimeError(
                        f"数据库兼容字段补齐失败：无法为 {table} 添加字段 {column}，"
                        "请手动迁移数据库后再启动服务。"
                    ) from exc


def ensure_obsolete_platform_schema_cleanup(engine: Engine) -> None:
    """移除已废弃的平台数据库结构。"""

    if engine.url.get_backend_name() == "sqlite":
        ensure_sqlite_obsolete_platform_schema_cleanup(engine)
        return
    ensure_sql_obsolete_platform_schema_cleanup(engine)


def ensure_sqlite_obsolete_platform_schema_cleanup(engine: Engine) -> None:
    """SQLite 启动时受控清理废弃结构，清理前自动备份数据库文件。"""

    obsolete_tables = ("quota_packages", "wallet_profiles", "integrations")
    obsolete_columns = {
        "redeem_codes": ("subscription_days",),
        "wallet_orders": ("subscription_days",),
    }
    with engine.begin() as connection:
        existing_tables = sqlite_table_names(connection)
        needs_cleanup = any(table in existing_tables for table in obsolete_tables)
        needs_cleanup = needs_cleanup or any(
            column in sqlite_column_names(connection, table)
            for table, columns in obsolete_columns.items()
            for column in columns
        )
    if not needs_cleanup:
        return

    database_path = Path(str(engine.url.database or ""))
    if database_path.exists():
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        backup_path = database_path.with_suffix(
            f"{database_path.suffix}.pre-quota-cleanup-{timestamp}.bak"
        )
        shutil.copy2(database_path, backup_path)

    with engine.begin() as connection:
        for table in obsolete_tables:
            connection.execute(text(f"DROP TABLE IF EXISTS {table}"))
        for table, columns in obsolete_columns.items():
            for column in columns:
                if column in sqlite_column_names(connection, table):
                    try:
                        connection.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
                    except Exception as exc:
                        raise RuntimeError(
                            f"SQLite 数据库清理失败：无法从 {table} 删除废弃字段 {column}，"
                            "请使用启动前自动备份文件恢复或手动迁移数据库。"
                        ) from exc


def ensure_sql_obsolete_platform_schema_cleanup(engine: Engine) -> None:
    """非 SQLite 数据库清理废弃结构，失败时暴露明确启动错误。"""

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    obsolete_tables = ("quota_packages", "wallet_profiles", "integrations")
    obsolete_columns = {
        "redeem_codes": ("subscription_days",),
        "wallet_orders": ("subscription_days",),
    }
    with engine.begin() as connection:
        for table in obsolete_tables:
            if table in existing_tables:
                connection.execute(text(f"DROP TABLE {table}"))

        for table, columns in obsolete_columns.items():
            if table not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table)}
            for column in columns:
                if column not in existing_columns:
                    continue
                statement = f"ALTER TABLE {table} DROP COLUMN {column}"
                try:
                    connection.execute(text(statement))
                except Exception as exc:
                    raise RuntimeError(
                        f"数据库清理失败：无法从 {table} 删除废弃字段 {column}，"
                        "请先备份数据库并手动完成废弃平台结构清理。"
                    ) from exc


def sqlite_table_names(connection) -> set[str]:
    """读取 SQLite 当前表名集合。"""

    rows = connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
    return {str(row[0]) for row in rows}


def sqlite_column_names(connection, table: str) -> set[str]:
    """读取 SQLite 指定表的字段名集合。"""

    rows = connection.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {str(row[1]) for row in rows}

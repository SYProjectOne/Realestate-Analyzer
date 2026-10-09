"""Alembic 환경 (계약 2026-10-09.1, WP0 소유).

- DB URL: 환경변수 DATABASE_URL > alembic.ini 의 sqlalchemy.url (기본 sqlite:///./dev.db).
  'postgresql://' 은 psycopg 3 드라이버('postgresql+psycopg://')로 바꿔 쓴다.
- SQLite는 render_as_batch=True (ALTER 제약 회피). 0001은 CREATE/DROP만 하므로 두 DB에서 같다.
- autogenerate의 target_metadata는 backend/app/models 의 Base.metadata (backend/ 에서 실행할 때).
- 테스트는 config.attributes["connection"] 에 연결을 넘겨 같은 연결로 실행할 수 있다.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path
from typing import Any

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

if config.config_file_name is not None:
    _backend_dir = Path(config.config_file_name).resolve().parent
    if str(_backend_dir) not in sys.path:
        sys.path.insert(0, str(_backend_dir))

target_metadata: Any
try:
    from app.models import Base

    target_metadata = Base.metadata
except ImportError:  # 계약 디렉터리만 단독으로 쓸 때
    target_metadata = None


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url") or "sqlite:///./dev.db"
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    elif url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://") :]
    return url


def _configure(connection: Connection | None, url: str | None) -> None:
    dialect = connection.dialect.name if connection is not None else (url or "").split(":", 1)[0]
    opts: dict[str, Any] = {
        "target_metadata": target_metadata,
        "compare_type": True,
        "render_as_batch": dialect.startswith("sqlite"),
    }
    if connection is not None:
        context.configure(connection=connection, **opts)
    else:
        context.configure(url=url, literal_binds=True, dialect_opts={"paramstyle": "named"}, **opts)


def run_migrations_offline() -> None:
    _configure(None, _database_url())
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _configure(connection, None)
        with context.begin_transaction():
            context.run_migrations()
        return
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    engine = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as conn:
        _configure(conn, None)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

"""DB 엔진·세션 (ADR-2: 개발 SQLite → 운영 Postgres 16).

모델 ``Base`` 는 WP0-A 가 ``app.models`` 에 정의한다. 여기서는 ``DeclarativeBase`` 를 만들지 않고,
메타데이터가 필요할 때만 ``load_metadata()`` 로 지연 import 한다.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, create_engine, event, text
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import Settings, get_settings

_engines: dict[str, Engine] = {}
_sessionmakers: dict[str, sessionmaker[Session]] = {}


def _sqlite_file(url: str) -> Path | None:
    database = make_url(url).database
    if not database or database == ":memory:" or database.startswith("file:"):
        return None
    return Path(database)


def make_engine(url: str | None = None, *, settings: Settings | None = None, echo: bool = False) -> Engine:
    """설정에 맞는 엔진을 새로 만든다(캐시하지 않음). 앱 코드는 ``get_engine()`` 을 쓴다."""
    s = settings or get_settings()
    url = url or s.database_url
    if url.startswith("sqlite"):
        db_file = _sqlite_file(url)
        if db_file is not None:
            db_file.parent.mkdir(parents=True, exist_ok=True)
        busy_ms = s.sqlite_busy_timeout_ms
        engine = create_engine(
            url,
            echo=echo,
            connect_args={"check_same_thread": False, "timeout": busy_ms / 1000},
        )
        in_memory = db_file is None

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn: Any, _record: Any) -> None:
            # pysqlite 의 자체 BEGIN 을 끈다(SQLAlchemy 문서 'Serializable isolation / Savepoints /
            # Transactional DDL'). 끄지 않으면 pysqlite 가 BEGIN 을 늦게 내거나 SAVEPOINT 앞에서
            # COMMIT 해 begin_nested() 롤백이 바깥 트랜잭션까지 깨진다. BEGIN 은 아래 'begin' 이벤트가 낸다.
            dbapi_conn.isolation_level = None
            cur = dbapi_conn.cursor()
            try:
                if not in_memory:
                    cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA foreign_keys=ON")
                cur.execute(f"PRAGMA busy_timeout={int(busy_ms)}")
                cur.execute("PRAGMA synchronous=NORMAL")
            finally:
                cur.close()

        @event.listens_for(engine, "begin")
        def _sqlite_begin(conn: Connection) -> None:
            conn.exec_driver_sql("BEGIN")

        return engine

    return create_engine(
        url,
        echo=echo,
        pool_size=s.db_pool_size,
        max_overflow=s.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


def get_engine(settings: Settings | None = None) -> Engine:
    """``DATABASE_URL`` 별로 하나씩 캐시된 엔진."""
    s = settings or get_settings()
    engine = _engines.get(s.database_url)
    if engine is None:
        engine = make_engine(s.database_url, settings=s)
        _engines[s.database_url] = engine
    return engine


def get_sessionmaker(settings: Settings | None = None) -> sessionmaker[Session]:
    s = settings or get_settings()
    factory = _sessionmakers.get(s.database_url)
    if factory is None:
        factory = sessionmaker(bind=get_engine(s), expire_on_commit=False)
        _sessionmakers[s.database_url] = factory
    return factory


def reset_engine() -> None:
    """캐시된 엔진을 모두 닫는다(테스트 teardown·프로세스 종료)."""
    for engine in _engines.values():
        engine.dispose()
    _engines.clear()
    _sessionmakers.clear()


@contextmanager
def get_session(settings: Settings | None = None) -> Iterator[Session]:
    """정상 종료면 commit, 예외면 rollback 후 다시 던진다."""
    session = get_sessionmaker(settings)()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def session_dependency() -> Iterator[Session]:
    """FastAPI 의존성: ``Depends(session_dependency)``. commit 은 라우터가 명시적으로 한다."""
    session = get_sessionmaker()()
    try:
        yield session
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def ping(engine: Engine | None = None) -> bool:
    """``SELECT 1`` 이 되면 True. 실패는 예외 대신 False(헬스 체크용)."""
    try:
        with (engine or get_engine()).connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False


def load_metadata() -> MetaData | None:
    """``app.models.Base.metadata`` (WP0-A). 아직 없으면 None."""
    try:
        module = importlib.import_module("app.models")
    except ModuleNotFoundError as exc:
        if exc.name in {"app.models"}:
            return None
        raise
    base = getattr(module, "Base", None)
    metadata = getattr(base, "metadata", None)
    return metadata if isinstance(metadata, MetaData) else None

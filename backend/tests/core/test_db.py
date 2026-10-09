from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_engine, get_session, make_engine, ping, session_dependency
from app.core.settings import Settings


def test_sqlite_pragmas(test_settings: Settings) -> None:
    engine = get_engine(test_settings)
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert conn.execute(text("PRAGMA busy_timeout")).scalar() == test_settings.sqlite_busy_timeout_ms


def test_sqlite_parent_dir_created(tmp_path: Path, test_settings: Settings) -> None:
    db_file = tmp_path / "nested" / "deeper" / "x.db"
    engine = make_engine(f"sqlite:///{db_file.as_posix()}", settings=test_settings)
    assert ping(engine)
    assert db_file.exists()
    engine.dispose()


def test_get_engine_is_cached(test_settings: Settings) -> None:
    assert get_engine(test_settings) is get_engine(test_settings)
    assert get_engine() is get_engine(test_settings)


def test_get_session_commits_and_rolls_back(test_settings: Settings) -> None:
    engine = get_engine(test_settings)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT NOT NULL)"))

    with get_session() as s:
        s.execute(text("INSERT INTO t (v) VALUES ('a')"))

    with pytest.raises(RuntimeError), get_session() as s:
        s.execute(text("INSERT INTO t (v) VALUES ('b')"))
        raise RuntimeError("boom")

    with get_session() as s:
        assert s.execute(text("SELECT v FROM t ORDER BY id")).scalars().all() == ["a"]


def test_foreign_keys_enforced(test_settings: Settings) -> None:
    engine = get_engine(test_settings)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE p (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE c (id INTEGER PRIMARY KEY, p_id INTEGER NOT NULL REFERENCES p(id))"))
    with pytest.raises(Exception, match="FOREIGN KEY"), get_session() as s:
        s.execute(text("INSERT INTO c (p_id) VALUES (999)"))


def test_session_dependency_generator(test_settings: Settings) -> None:
    gen = session_dependency()
    session = next(gen)
    assert isinstance(session, Session)
    assert session.execute(text("SELECT 1")).scalar() == 1
    with pytest.raises(StopIteration):
        next(gen)


def test_postgres_pool_config(test_settings: Settings) -> None:
    engine = make_engine("postgresql+psycopg://u:p@localhost:5432/x", settings=test_settings)
    assert engine.dialect.name == "postgresql"
    assert engine.pool.size() == test_settings.db_pool_size  # type: ignore[attr-defined]
    assert engine.pool._pre_ping is True  # type: ignore[attr-defined]
    engine.dispose()


def test_ping_false_when_unreachable(tmp_path: Path, test_settings: Settings) -> None:
    # 디렉터리를 DB 파일로 열 수 없다 → 예외 대신 False
    bad = make_engine(f"sqlite:///{tmp_path.as_posix()}", settings=test_settings)
    assert ping(bad) is False
    bad.dispose()


def test_sqlite_savepoint_rollback_keeps_outer_transaction(test_settings: Settings) -> None:
    """begin_nested() 롤백은 SAVEPOINT 안만 되돌리고 바깥 트랜잭션은 살아 있다
    (pysqlite BEGIN 끔 + begin 이벤트)."""
    engine = get_engine(test_settings)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE sp (id INTEGER PRIMARY KEY, v TEXT NOT NULL)"))

    with get_session() as s:
        s.execute(text("INSERT INTO sp (v) VALUES ('outer')"))
        with pytest.raises(RuntimeError), s.begin_nested():
            s.execute(text("INSERT INTO sp (v) VALUES ('inner')"))
            raise RuntimeError("inner fails")
        with s.begin_nested():
            s.execute(text("INSERT INTO sp (v) VALUES ('inner-ok')"))

    with get_session() as s:
        assert s.execute(text("SELECT v FROM sp ORDER BY id")).scalars().all() == ["outer", "inner-ok"]


def test_sqlite_outer_rollback_discards_released_savepoint(test_settings: Settings) -> None:
    engine = get_engine(test_settings)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE sp2 (id INTEGER PRIMARY KEY, v TEXT NOT NULL)"))

    with pytest.raises(RuntimeError), get_session() as s:
        with s.begin_nested():
            s.execute(text("INSERT INTO sp2 (v) VALUES ('nested')"))
        raise RuntimeError("outer fails")

    with get_session() as s:
        assert s.execute(text("SELECT count(*) FROM sp2")).scalar() == 0

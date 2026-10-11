# ruff: noqa: E501
"""R3h CORE6 — D14-5 API 쓰기 대기: SQLite 개발 모드 API 프로세스는 요청 커밋이 WAL 체크포인트를 하지 않는다
(``core.db.sqlite_api_checkpointer`` — 배경 스레드가 PASSIVE 체크포인트). 측정 근거는 ``contracts/CHANGELOG.md`` .13 '측정'."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.core.db import make_engine, sqlite_api_checkpointer


def _autockpt(engine: object) -> int:
    with engine.connect() as c:  # type: ignore[attr-defined]
        return int(c.connection.dbapi_connection.execute("PRAGMA wal_autocheckpoint").fetchone()[0])


def _wal_frames(db: Path) -> tuple[int, int]:
    import sqlite3

    con = sqlite3.connect(str(db))
    try:
        _busy, log, ckpt = con.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
        return int(log), int(ckpt)
    finally:
        con.close()


def test_api_commits_do_not_checkpoint_and_background_thread_does(tmp_path: Path, monkeypatch: Any) -> None:
    import app.core.db as dbm

    calls = {"n": 0}
    real = dbm._passive_checkpoint

    def counted(engine: Any) -> None:
        calls["n"] += 1
        real(engine)

    monkeypatch.setattr(dbm, "_passive_checkpoint", counted)
    db = tmp_path / "ck.db"
    engine = make_engine(f"sqlite:///{db.as_posix()}")
    try:
        with engine.begin() as c:
            c.execute(text("CREATE TABLE t (x BLOB)"))
        assert _autockpt(engine) == 1000
        with sqlite_api_checkpointer(engine, interval_s=0.2):
            assert _autockpt(engine) == 0  # 요청 커밋은 체크포인트하지 않는다
            with engine.begin() as c:
                for _ in range(1500):  # 1000 페이지 넘게(자동 체크포인트였다면 커밋 안에서 돌았을 양)
                    c.execute(text("INSERT INTO t VALUES (randomblob(4000))"))
            time.sleep(1.0)
            assert calls["n"] >= 2  # 배경 스레드가 체크포인트한다
            log, ckpt = _wal_frames(db)
            assert log > 1000 and ckpt == log
        assert _autockpt(engine) == 1000  # 끝나면 기본으로
    finally:
        engine.dispose()


def test_postgres_or_memory_is_noop() -> None:
    engine = make_engine("sqlite://")
    try:
        with sqlite_api_checkpointer(engine):
            pass
    finally:
        engine.dispose()

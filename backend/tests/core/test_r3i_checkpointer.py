"""R3i CORE7 — 9차 리뷰 m12(재현 scratchpad ``r9/c/test_r9c_ckpt.py``): API 체크포인터가 예외를 기록 없이 삼키고(WAL 증가) 계속
요청 커밋의 자동 체크포인트를 꺼 두었다. 이제 실패는 경고 로그로 남고, 연달아 ``SQLITE_CHECKPOINT_FAIL_LIMIT`` 번 실패하면 요청 커밋의
자동 체크포인트를 되살린다(WAL 이 끝없이 자라지 않게). 체크포인트가 다시 되면 끈다."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app.core.db import make_engine, sqlite_api_checkpointer


def _autockpt(engine: Any) -> int:
    with engine.connect() as c:
        return int(c.connection.dbapi_connection.execute("PRAGMA wal_autocheckpoint").fetchone()[0])


def _wait(cond: Any, timeout: float = 5.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return bool(cond())


def test_m12_checkpoint_failures_are_logged_and_fall_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import app.core.db as dbm

    fail = {"on": True, "n": 0}
    real = dbm._passive_checkpoint

    def flaky(engine: Any) -> None:
        if fail["on"]:
            fail["n"] += 1
            raise RuntimeError("disk I/O error")
        real(engine)

    monkeypatch.setattr(dbm, "_passive_checkpoint", flaky)
    monkeypatch.setattr(dbm, "SQLITE_CHECKPOINT_FAIL_LIMIT", 3)
    engine = make_engine(f"sqlite:///{(tmp_path / 'ck.db').as_posix()}")
    try:
        with engine.begin() as c:
            c.execute(text("CREATE TABLE t (x BLOB)"))
        with caplog.at_level(logging.WARNING, logger="app.core.db"), sqlite_api_checkpointer(engine, interval_s=0.05):
            assert _autockpt(engine) == 0
            assert _wait(lambda: fail["n"] >= 3)
            assert _wait(lambda: _autockpt(engine) == 1000), "연속 실패 → 요청 커밋 자동 체크포인트 복귀"
            fail["on"] = False
            assert _wait(lambda: _autockpt(engine) == 0), "체크포인트가 다시 되면 다시 끈다"
        msgs = [r.getMessage() for r in caplog.records if r.name == "app.core.db"]
        assert any("sqlite.checkpoint_failed" in m for m in msgs), msgs
        assert any("sqlite.checkpoint_fallback" in m for m in msgs), msgs
    finally:
        engine.dispose()

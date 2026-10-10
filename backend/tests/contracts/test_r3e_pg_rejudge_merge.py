"""R3e CORE3 · D13-3(R3 5차 M1, Postgres 재현): rejudge 합치기 ↔ worker claim 경합.

API 트랜잭션이 queued rejudge 를 ``FOR UPDATE`` 로 잡고 합치는 동안 worker 의 claim(UPDATE … WHERE status='queued')은
그 커밋을 기다린다 → worker 가 시작 때 읽는 payload 에 합친 단지가 있다(누락 없음). 스레드 2개로 실제 경합을 만든다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import load_metadata
from app.models import JobRun

pytestmark = pytest.mark.postgres


@pytest.fixture
def pg_factory(postgres_url: str) -> Iterator[sessionmaker[Session]]:
    base, _, _ = postgres_url.rpartition("/")
    admin = sa.create_engine(base + "/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(sa.text("DROP DATABASE IF EXISTS r3e_rejudge"))
        c.execute(sa.text("CREATE DATABASE r3e_rejudge"))
    eng = sa.create_engine(base + "/r3e_rejudge")
    md = load_metadata()
    assert md is not None
    md.create_all(eng)
    try:
        yield sessionmaker(eng, expire_on_commit=False)
    finally:
        eng.dispose()
        with admin.connect() as c:
            c.execute(sa.text("DROP DATABASE IF EXISTS r3e_rejudge WITH (FORCE)"))
        admin.dispose()


def test_pg_merge_waits_for_lock_and_worker_sees_merged_payload(pg_factory: sessionmaker[Session]) -> None:
    from app.scheduler.context import SchedulerContext
    from app.scheduler.rejudge import enqueue_rejudge
    from app.scheduler.runner import claim

    with pg_factory() as s:  # FK 없이 job_run 만(snapshot_id 는 payload 숫자)
        jid = enqueue_rejudge(s, 12, [1], "변경 감지 1단지").id
        s.commit()
    ctx = SchedulerContext(session_factory=pg_factory, adapter_factory=lambda: None, collectors={})  # type: ignore[arg-type,return-value]
    seen: dict[str, Any] = {}
    api = pg_factory()
    merged = enqueue_rejudge(api, 12, [2], "사람 확인 입력")  # FOR UPDATE 잠금을 쥔 채 커밋 전

    def worker() -> None:
        seen["claimed"] = claim(ctx, jid)  # 잠금이 풀릴 때까지 기다린다
        with pg_factory() as w:
            row = w.get(JobRun, jid)
            seen["start"] = list((row.payload if row is not None else {})["complex_ids"])

    th = threading.Thread(target=worker)
    th.start()
    time.sleep(0.5)
    assert "claimed" not in seen, "worker 가 합치기 커밋 전에 집으면 안 된다"
    api.commit()
    api.close()
    th.join(timeout=30)
    assert seen["claimed"] is True and merged.id == jid
    assert seen["start"] == [1, 2], "worker 가 시작 때 본 단지에 합친 단지가 있다"

# ruff: noqa: E501
"""R3f CORE4 — R3 6차 minor 15: SQLite 에서 같은 트랜잭션이 먼저 읽고(읽기 스냅샷) 다른 연결이 쓴 뒤 rejudge 합치기(쓰기 잠금)를
하면 WAL 의 BUSY_SNAPSHOT 으로 즉시 'database is locked' 가 났다(busy_timeout 무관). 읽기만 한 트랜잭션이면 새 트랜잭션에서
쓰기 잠금부터 다시 잡는다. 이미 쓴 트랜잭션은 조용히 되돌리지 않는다(예외 그대로)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models import JobRun, Region
from app.scheduler.rejudge import enqueue_rejudge


def _region(engine: Engine) -> None:
    with Session(engine) as s, s.begin():
        s.add(
            Region(
                id=1, name="r", query_text="q", selections=[], sido_codes=[], sigungu_codes=[], legal_dong_codes=[],
                living_areas=[], age_premium_coef={}, applyhome_query={}, status="ready", created_at="2026-10-10",
            )
        )  # fmt: skip


def test_m15_read_then_merge_after_other_writer(db_engine: Engine) -> None:
    _region(db_engine)
    a = Session(db_engine)
    try:
        assert a.scalars(select(Region.id)).all() == [1]  # 읽기 트랜잭션 시작(스냅샷)
        with Session(db_engine) as b, b.begin():  # 다른 연결이 쓰고 커밋
            b.add(
                JobRun(
                    job_name="backup", kind="scheduled", payload={}, scheduled_at="x", status="done", stats={}
                )
            )
        job = enqueue_rejudge(a, 7, [1], "사람 확인")  # 예전: OperationalError database is locked
        a.commit()
        assert job.id is not None
        with Session(db_engine) as c:
            assert c.scalars(select(JobRun.job_name).where(JobRun.id == job.id)).one() == "rejudge"
    finally:
        a.close()


def test_m15_written_transaction_is_not_silently_rolled_back(db_engine: Engine) -> None:
    _region(db_engine)
    a = Session(db_engine)
    try:
        a.scalars(select(Region.id)).all()
        with Session(db_engine) as b, b.begin():
            b.add(
                JobRun(
                    job_name="backup", kind="scheduled", payload={}, scheduled_at="x", status="done", stats={}
                )
            )
        a.add(
            JobRun(job_name="backup", kind="scheduled", payload={}, scheduled_at="y", status="done", stats={})
        )
        with pytest.raises(
            OperationalError
        ):  # 대기 중인 쓰기가 있으면 되돌려 다시 하지 않는다(쓰기 손실 금지)
            enqueue_rejudge(a, 7, [1], "사람 확인")
        a.rollback()
    finally:
        a.close()

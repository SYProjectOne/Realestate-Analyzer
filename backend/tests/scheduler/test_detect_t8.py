"""T8 변경 없는 날 / 팝업 이미지 변경 (RA §9 T8, contracts/fixtures/.../raw/official_site/t8_popup_pairs.json).

1일차(2026-10-07): 공식 홈페이지 팝업 수집 → 이전 publish 스냅샷이 없으니 전체 판정 → publish.
2일차(2026-10-08) 같은 해시: change_event 0 · rejudge 잡 0 · 판정기 실제 호출 0 · 이전 판정 복사 후 publish.
2일차 다른 해시: change_event critical 1 + rejudge 잡 1(그 단지만).
"""

# ruff: noqa: E501  (한국어 docstring·픽스처 행)

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import ChangeEvent, IntakeStatus, JobRun, Ladder, ScoreRun, ScoreTotal, Snapshot
from app.scheduler import runner
from app.scheduler.context import SchedulerContext
from app.scheduler.jobs import enqueue

from .conftest import Clock, RowsCollector, SynthJev, popup_row


def _count(s: Session, model: Any, *where: Any) -> int:
    return int(s.scalar(select(func.count()).select_from(model).where(*where)) or 0)


def _daily(factory: sessionmaker[Session], ctx: SchedulerContext) -> list[int]:
    with factory() as s:
        enqueue(s, "collect.daily", {"region_id": 1, "sources": ["official_site"]})
        s.commit()
    return runner.run_until_idle(ctx)


def _day1(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], clock: Clock
) -> tuple[int, RowsCollector]:
    site = RowsCollector(factory, [popup_row("yesterday")])
    ctx = make_ctx(collectors={"official_site": lambda c: site})
    clock.day = date(2026, 10, 7)
    done = _daily(factory, ctx)
    with factory() as s:
        jobs = [s.get(JobRun, i) for i in done]
        assert [j.job_name for j in jobs if j] == ["collect.daily", "rejudge", "snapshot.publish"]
        assert all(j and j.status == "done" for j in jobs), [j.error_text for j in jobs if j]
        snap = s.scalars(select(Snapshot).where(Snapshot.asof_date == "2026-10-07")).one()
        assert snap.status == "published"
        return snap.id, site


def test_no_change_day_zero_events_zero_rejudge_zero_judge_calls(
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    seeded: int,
    jev: SynthJev,
    clock: Clock,
) -> None:
    day1, site = _day1(make_ctx, factory, clock)
    calls_before = len(jev.calls)
    with factory() as s:
        jobs_before = _count(s, JobRun, JobRun.job_name == "rejudge")
        runs_day1 = _count(s, ScoreRun, ScoreRun.snapshot_id == day1)
    site.rows = [popup_row("today_same")]  # 같은 내용(같은 sha256) → 수집기가 어제 행을 돌려준다
    clock.day = date(2026, 10, 8)
    ctx2 = make_ctx(collectors={"official_site": lambda c: site})
    done = _daily(factory, ctx2)

    assert len(jev.calls) == calls_before  # 판정기 실제 호출 0
    with factory() as s:
        day2 = s.scalars(select(Snapshot).where(Snapshot.asof_date == "2026-10-08")).one()
        assert _count(s, ChangeEvent, ChangeEvent.snapshot_id == day2.id) == 0
        assert _count(s, JobRun, JobRun.job_name == "rejudge") == jobs_before  # rejudge 0
        job = s.get(JobRun, done[0])
        assert job is not None and job.status == "done" and job.stats["change_events"] == 0
        # 이전 판정을 복사해 오늘 스냅샷도 publish(같은 사실 = 같은 판정)
        assert day2.status == "published"
        assert _count(s, ScoreRun, ScoreRun.snapshot_id == day2.id) == runs_day1
        assert _count(s, Ladder, Ladder.snapshot_id == day2.id) == _count(
            s, Ladder, Ladder.snapshot_id == day1
        )
        run = s.scalars(
            select(ScoreRun).where(ScoreRun.snapshot_id == day2.id, ScoreRun.scenario_id == 1)
        ).one()
        assert run.prev_score_run_id is not None
        assert _count(s, ScoreTotal, ScoreTotal.score_run_id == run.id, ScoreTotal.total.is_not(None)) > 0
        assert _count(s, IntakeStatus, IntakeStatus.snapshot_id == day2.id) >= _count(
            s, IntakeStatus, IntakeStatus.snapshot_id == day1
        )


def test_popup_change_one_critical_event_one_rejudge(
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    seeded: int,
    jev: SynthJev,
    clock: Clock,
) -> None:
    _day1(make_ctx, factory, clock)
    with factory() as s:
        jobs_before = _count(s, JobRun, JobRun.job_name == "rejudge")
    changed = popup_row("today_changed")
    site = RowsCollector(factory, [changed])
    clock.day = date(2026, 10, 8)
    ctx = make_ctx(collectors={"official_site": lambda c: site})
    with factory() as s:
        jid = enqueue(s, "collect.daily", {"region_id": 1, "sources": ["official_site"]}).id
        s.commit()
    assert runner.run_once(ctx) == jid  # 수집 잡만
    with factory() as s:
        day2 = s.scalars(select(Snapshot).where(Snapshot.asof_date == "2026-10-08")).one()
        events = list(s.scalars(select(ChangeEvent).where(ChangeEvent.snapshot_id == day2.id)))
        assert len(events) == 1
        ev = events[0]
        assert (ev.severity, ev.triggers_rejudge, ev.complex_id) == ("critical", True, 2)
        assert ev.old_text == popup_row("yesterday")["image_hash"] and ev.new_text == changed["image_hash"]
        rejudges = list(s.scalars(select(JobRun).where(JobRun.job_name == "rejudge")))
        assert len(rejudges) == jobs_before + 1
        new = rejudges[-1]
        assert new.status == "queued" and new.payload["complex_ids"] == [2]
        assert new.payload["snapshot_id"] == day2.id and new.payload["change_event_ids"] == [ev.id]
    # 그 단지만 재판정, 나머지 사다리는 이전 스냅샷에서
    calls = len(jev.calls)
    runner.run_until_idle(ctx)
    with factory() as s:
        day2 = s.scalars(select(Snapshot).where(Snapshot.asof_date == "2026-10-08")).one()
        assert day2.status == "published"
        assert _count(s, Ladder, Ladder.snapshot_id == day2.id) == 27  # 판정 대상 9 × 3(D9-1)
    assert jev.calls[calls:].count("jev_noul") <= 3

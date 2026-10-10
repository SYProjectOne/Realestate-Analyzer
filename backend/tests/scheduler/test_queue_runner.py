"""job_run 큐·잠금·runner (ADR-3): 동시 실행 2개 → 하나만, 실패는 잡 failed, --once, 시간표."""

# ruff: noqa: E501  (한국어 docstring·픽스처 행)

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import Settings
from app.models import JobRun, LegalDong
from app.scheduler import runner
from app.scheduler.context import SchedulerContext
from app.scheduler.handlers import HANDLERS
from app.scheduler.jobs import CRON, build_scheduler, enqueue, enqueue_for_regions, ensure_reference
from app.scheduler.rejudge import enqueue_rejudge

from .conftest import seed_region


def _job(factory: sessionmaker[Session], job_id: int) -> JobRun:
    with factory() as s:
        row = s.get(JobRun, job_id)
        assert row is not None
        return row


def test_enqueue_dedupes_same_queued_job(factory: sessionmaker[Session], db_engine: Any) -> None:
    with factory() as s:
        a = enqueue(s, "reference.refresh", {})
        b = enqueue(s, "reference.refresh", {})
        c = enqueue(s, "collect.daily", {"region_id": 1, "sources": ["official_site"]})
        s.commit()
    assert a.id == b.id != c.id


def test_rejudge_enqueue_merges_complex_ids(factory: sessionmaker[Session], db_engine: Any) -> None:
    with factory() as s:
        a = enqueue_rejudge(s, 12, [4], "사람 확인")
        b = enqueue_rejudge(s, 12, [2, 4], "팝업 변경", change_event_ids=[7])
        c = enqueue_rejudge(s, 13, [1], "다른 스냅샷")
        s.commit()
        assert a.id == b.id != c.id
        assert a.payload["complex_ids"] == [2, 4]
        assert a.payload["change_event_ids"] == [7]
        assert "팝업 변경" in a.payload["reason"]
        d = enqueue_rejudge(s, 12, None, "전체")
        s.commit()
        assert d.id == a.id and d.payload["complex_ids"] is None  # None(전부)이 이긴다
        assert s.scalar(select(func.count()).select_from(JobRun)) == 2


def test_two_workers_same_job_only_one_runs(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], db_engine: Any
) -> None:
    runs: list[str] = []
    lock = threading.Lock()

    def slow_refresh(day: Any) -> dict[str, Any]:
        with lock:
            runs.append(threading.current_thread().name)
        time.sleep(0.3)
        return {"ok": True}

    a = make_ctx(worker_id="worker-a", reference_refresh=slow_refresh)
    b = make_ctx(worker_id="worker-b", reference_refresh=slow_refresh)
    with factory() as s:
        job_id = enqueue(s, "reference.refresh", {}).id
        s.commit()
    barrier = threading.Barrier(2)
    results: dict[str, int | None] = {}

    def go(ctx: SchedulerContext, name: str) -> None:
        barrier.wait()
        results[name] = runner.run_once(ctx)

    threads = [threading.Thread(target=go, args=(c, n), name=n) for c, n in ((a, "a"), (b, "b"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert len(runs) == 1  # 실행은 한 번
    assert sorted(v for v in results.values() if v is not None) == [job_id]
    row = _job(factory, job_id)
    assert row.status == "done" and row.locked_by in {"worker-a", "worker-b"}
    assert row.started_at and row.finished_at and row.stats == {"reference": {"ok": True}}
    assert runner.claim(a, job_id) is False  # 이미 끝난 잡은 다시 잠기지 않는다


def test_failed_handler_marks_job_failed_and_worker_continues(
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    db_engine: Any,
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
) -> None:
    def boom(ctx: SchedulerContext, job: JobRun) -> dict[str, Any]:
        raise RuntimeError("010-1234-5678 로 연락")  # 오류 문구의 개인정보는 가린다

    monkeypatch.setitem(HANDLERS, "report", boom)
    ctx = make_ctx()
    with factory() as s:
        bad = enqueue(s, "report", {"snapshot_id": 1, "format": "html"}).id
        good = enqueue(s, "reference.refresh", {}).id
        s.commit()
    assert runner.run_until_idle(ctx) == [bad, good]
    row = _job(factory, bad)
    assert row.status == "failed" and row.error_text and "RuntimeError" in row.error_text
    assert "1234-5678" not in row.error_text
    assert _job(factory, good).status == "done"


def test_report_job_follows_wp8_contract(
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    db_engine: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """app.reports.job.run_report_job(payload, session=…) 위임 · 예외 → failed(blocked·not_found·invalid_payload)."""
    from app.reports import job as report_job
    from app.reports.errors import ReportBlocked

    ctx = make_ctx()
    with factory() as s:
        missing = enqueue(s, "report", {"snapshot_id": 999, "format": "pdf"}).id
        bad = enqueue(s, "report", {"snapshot_id": 1, "format": "docx"}).id
        s.commit()
    runner.run_until_idle(ctx)  # 실제 WP8 모듈: 스냅샷 없음 / format 형식 오류
    assert _job(factory, missing).status == "failed"
    assert (_job(factory, missing).error_text or "").startswith("not_found:")
    assert (_job(factory, bad).error_text or "").startswith("invalid_payload:")

    seen: list[tuple[dict[str, Any], bool]] = []

    def fake_ok(payload: dict[str, Any], *, session: Session | None = None, **kw: Any) -> dict[str, Any]:
        assert isinstance(kw.get("job_id"), int), "잡 id 가 파일 이름에 들어간다(R3 4차 C-4)"
        seen.append((payload, session is not None))
        return {"path": "r.html", "filename": "r.html", "format": "html", "blocked_reason": None}

    def fake_blocked(
        payload: dict[str, Any], *, session: Session | None = None, **_kw: Any
    ) -> dict[str, Any]:
        raise ReportBlocked("contradicted 2건")

    monkeypatch.setattr(report_job, "run_report_job", fake_ok)
    with factory() as s:
        ok = enqueue(s, "report", {"snapshot_id": 1, "format": "html"}).id
        s.commit()
    runner.run_until_idle(ctx)
    assert _job(factory, ok).status == "done" and _job(factory, ok).stats["filename"] == "r.html"
    assert seen == [({"snapshot_id": 1, "format": "html"}, True)]

    monkeypatch.setattr(report_job, "run_report_job", fake_blocked)
    with factory() as s:
        blocked = enqueue(s, "report", {"snapshot_id": 1, "format": "pdf"}).id
        s.commit()
    runner.run_until_idle(ctx)
    row = _job(factory, blocked)
    assert row.status == "failed" and row.error_text == "blocked: contradicted 2건"
    assert row.stats == {"blocked_reason": "contradicted 2건"}


def test_main_once_without_schema_returns_zero(test_settings: Settings) -> None:
    assert runner.main(["--once"]) == 0


def test_main_once_runs_queue(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], db_engine: Any
) -> None:
    ctx = make_ctx()
    with factory() as s:
        jid = enqueue(s, "reference.refresh", {}).id
        s.commit()
    assert runner.main(["--once"], ctx=ctx) == 0
    assert _job(factory, jid).status == "done"


def test_schedule_and_startup_reference(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], db_engine: Any
) -> None:
    ctx = make_ctx()
    sched = build_scheduler(ctx)
    jobs = {j.id: j for j in sched.get_jobs()}
    assert set(jobs) == {"collect.daily", "collect.weekly", "reference.refresh", "backup"}  # backup: D11-8
    fields = {name: {f.name: str(f) for f in jobs[name].trigger.fields} for name in jobs}
    assert (fields["backup"]["hour"], fields["backup"]["minute"]) == ("3", "0")
    assert (fields["collect.daily"]["hour"], fields["collect.daily"]["minute"]) == ("6", "0")
    assert fields["collect.weekly"]["day_of_week"] == "mon" and fields["collect.weekly"]["minute"] == "30"
    assert (fields["reference.refresh"]["day"], fields["reference.refresh"]["hour"]) == ("1", "5")
    assert str(jobs["collect.daily"].trigger.timezone) == "Asia/Seoul"
    assert CRON["collect.daily"] == {"hour": 6, "minute": 0}

    # 기동 시 참조 표가 비었으면 reference.refresh 1회, 있으면 안 넣는다
    first = ensure_reference(ctx)
    assert first is not None and ensure_reference(ctx) == first  # queued 중복 없음
    with factory() as s:
        s.add(
            LegalDong(
                code="1111010100", sido_name="시도", sigungu_name="구", eupmyeondong_name="동",
                ri_name=None, full_name="시도 구 동", sigungu_code="11110", active=True, source_date="2026-10-09",
            )
        )  # fmt: skip
        s.get(JobRun, first).status = "done"  # type: ignore[union-attr]
        s.commit()
    assert ensure_reference(ctx) is None

    # 시간표 콜백: ready 지역마다 collect.daily 1개
    with factory() as s:
        seed_region(s)
        s.commit()
    ids = enqueue_for_regions(ctx, "collect.daily")
    assert len(ids) == 1
    job = _job(factory, ids[0])
    assert job.payload == {"region_id": 1, "sources": ["applyhome_list", "official_site"]}
    assert enqueue_for_regions(ctx, "collect.daily") == ids  # 같은 잡이 queued 면 새로 넣지 않는다

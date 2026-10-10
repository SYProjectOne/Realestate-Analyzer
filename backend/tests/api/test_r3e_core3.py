"""R3e CORE3 — 5차 리뷰(`docs/design/wp/R3_REVIEW5.md`) K3·Major·minor 중 API 경계로 보는 것 (계약 2026-10-09.10).

D13-1 불변은 ``test_r3e_invariant``, D13-2 사람 확인 의미 단위는 ``test_r3e_human_semantic``.
"""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.settings import Settings, set_settings

from ._support import READ, WRITE
from .test_r3b_g3 import SNAP
from .test_r3d_core2 import run_jobs

# ====================================================================== K3 REPORT_DIR 상대 경로


@pytest.mark.parametrize("rel", ["./data/reports", "../r4/reports"])
def test_k3_relative_report_dir_download(
    api_settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rel: str
) -> None:
    """REPORT_DIR 이 상대 경로(.env.example ``./data/reports`` · runbook R4 ``../r4/reports``)여도 다운로드 200·같은 sha256.
    잡 stats.path 는 REPORT_DIR 기준 상대 이름(파일 이름)이다."""
    from app.core.db import get_session
    from app.main import create_app
    from app.models import JobRun

    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    settings = api_settings.model_copy(update={"report_dir": Path(rel)})
    set_settings(settings)
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        r = c.post("/api/reports", json={"snapshot_id": SNAP, "format": "html"}, headers=WRITE)
        assert r.status_code == 202, r.text
        jid = r.json()["id"]
        assert run_jobs("report") == [jid]
        with get_session() as s:
            row = s.get(JobRun, jid)
            assert row is not None and row.status == "done", row.error_text if row else None
            stored = (row.stats or {})["path"]
        assert "/" not in stored and stored.endswith(".html"), stored
        assert (work / rel / stored).resolve().is_file()
        got = c.get(f"/api/reports/{jid}", headers=READ)
        assert got.status_code == 200, got.text
        listed = {x["id"]: x for x in c.get("/api/reports", headers=READ).json()}[jid]
        assert hashlib.sha256(got.content).hexdigest() == listed["sha256"]


@pytest.mark.parametrize(
    ("base", "stored", "want"),
    [
        ("./data/reports", "report_x.html", "data/reports/report_x.html"),
        (
            "./data/reports",
            "data/reports/report_x.html",
            "data/reports/report_x.html",
        ),  # 옛 잡(앞에 붙여 저장)
        ("../r4/reports", "../r4/reports/report_x.html", "../r4/reports/report_x.html"),  # 옛 잡
        ("../r4/reports", "../etc/passwd", None),
        ("./data/reports", "sub/../x.html", None),
    ],
)
def test_k3_report_path_resolution(base: str, stored: str, want: str | None) -> None:
    from app.api.routers.reports import _report_path

    got = _report_path(Path(base), stored)
    assert (got.as_posix() if got is not None else None) == want


# ====================================================================== M1 · D13-3 잡 큐 합치기 원자성


def test_m1_claimed_between_read_and_merge_makes_new_job(client: TestClient) -> None:
    """합치는 UPDATE 가 ``status='queued'`` 조건에서 0행(그 사이 running)이면 그 잡을 고치지 않고 새 잡(D13-3).
    예전: 집힌 잡 payload 를 고쳐 worker 가 시작 때 본 단지 목록에서 새 단지가 빠지고 응답 rejudge_job_id = running 잡."""
    from sqlalchemy import event, select, text

    from app.core.db import get_session, get_sessionmaker
    from app.models import Complex, JobRun
    from app.scheduler.rejudge import enqueue_rejudge

    from .test_r3b_g3 import CX

    with get_session() as s:
        other = s.scalars(select(Complex.id).where(Complex.region_id == 1, Complex.id != CX)).first()
        assert other is not None
        jid = enqueue_rejudge(s, SNAP, [other], "변경 감지 1단지").id
    sess = get_sessionmaker()()
    fired: list[int] = []

    @event.listens_for(sess, "do_orm_execute")
    def _claimed(state: Any) -> None:  # 후보를 읽은 뒤·합치는 UPDATE 직전에 그 잡이 running 이 된다
        if state.is_update and "payload" in str(state.statement) and not fired:
            fired.append(1)
            state.session.execute(text("UPDATE job_run SET status='running' WHERE id=:i"), {"i": jid})

    try:
        got = enqueue_rejudge(sess, SNAP, [CX], "사람 확인 입력: X")
        sess.commit()
        new_id = got.id
    finally:
        sess.close()
    assert fired
    with get_session() as s:
        running = s.get(JobRun, jid)
        fresh = s.get(JobRun, new_id)
        assert running is not None and running.status == "running"
        assert running.payload["complex_ids"] == [other], "집힌 잡 payload 는 그대로"
        assert fresh is not None and new_id != jid and fresh.status == "queued"
        assert fresh.payload["complex_ids"] == [CX], "새 단지는 새 잡에(누락 없음)"


def test_m1_worker_claim_waits_for_merge_commit_sqlite(client: TestClient) -> None:
    """SQLite: 합치기가 쓰기 잠금을 먼저 잡아 worker claim 이 커밋을 기다린다 → worker 가 본 payload 에 합친 단지(D13-3)."""
    import threading
    import time

    from app.core.db import get_session, get_sessionmaker
    from app.models import JobRun
    from app.scheduler.context import SchedulerContext
    from app.scheduler.rejudge import enqueue_rejudge
    from app.scheduler.runner import claim

    with get_session() as s:
        jid = enqueue_rejudge(s, SNAP, [1], "a").id
    ctx = SchedulerContext(session_factory=get_sessionmaker(), adapter_factory=lambda: None, collectors={})  # type: ignore[arg-type,return-value]
    seen: dict[str, Any] = {}
    api = get_sessionmaker()()
    merged = enqueue_rejudge(api, SNAP, [2], "b")

    def worker() -> None:
        seen["claimed"] = claim(ctx, jid)
        with get_sessionmaker()() as w:
            row = w.get(JobRun, jid)
            seen["start"] = list((row.payload if row is not None else {})["complex_ids"])

    th = threading.Thread(target=worker)
    th.start()
    time.sleep(0.5)
    assert "claimed" not in seen
    api.commit()
    api.close()
    th.join(timeout=30)
    assert seen == {"claimed": True, "start": [1, 2]} and merged.id == jid


def test_m1_merge_into_queued_job_still_merges(client: TestClient) -> None:
    from app.core.db import get_session
    from app.scheduler.rejudge import enqueue_rejudge

    with get_session() as s:
        a = enqueue_rejudge(s, SNAP, [1], "a")
        b = enqueue_rejudge(s, SNAP, [2], "b")
        assert a.id == b.id and b.payload["complex_ids"] == [1, 2]


# ====================================================================== M2 · D13-4 이월·주간 리비전


def _ctx(day: str = "2026-10-21") -> Any:
    from datetime import date, datetime

    from app.core.db import get_sessionmaker
    from app.core.time import KST
    from app.scheduler.context import SchedulerContext

    ctx = SchedulerContext(session_factory=get_sessionmaker(), adapter_factory=lambda: None, collectors={})  # type: ignore[arg-type,return-value]
    y, m, d = map(int, day.split("-"))
    ctx.now = lambda: datetime(y, m, d, 6, 0, tzinfo=KST)  # type: ignore[method-assign]
    ctx.today = lambda: date(y, m, d)  # type: ignore[method-assign]
    return ctx


def _new_day(asof: str = "2026-10-21") -> int:
    from app.core.db import get_session
    from app.scheduler.snapshots import get_or_create

    with get_session() as s:
        return int(get_or_create(s, 1, asof, created_at=f"{asof}T06:00:00+09:00").id)


def test_d13_4_unchanged_weekly_makes_no_revision(client: TestClient) -> None:
    """변경 없는 주간 수집이 발행된 기준일에 만든 리비전은 지운다 — 같은 내용 리비전을 다시 발행하지 않는다(D13-4)."""
    from sqlalchemy import func, select

    from app.core.db import get_session
    from app.models import Snapshot
    from app.scheduler.handlers import _finish_unchanged_revision
    from app.scheduler.snapshots import get_or_create, latest_for_region

    with get_session() as s:
        rev = get_or_create(
            s, 1, "2026-10-08", created_at="2026-10-12T06:00:00+09:00"
        )  # 주간 수집 = 같은 기준일 재수집
        assert rev.status == "building" and rev.revision == 2
        rid = rev.id
        n0 = s.scalar(select(func.count()).select_from(Snapshot))
    out = _finish_unchanged_revision(_ctx("2026-10-12"), rid)
    assert out == {"discarded_revision": rid, "kept": SNAP}
    with get_session() as s:
        assert s.get(Snapshot, rid) is None and s.scalar(select(func.count()).select_from(Snapshot)) == n0 - 1
        newest = latest_for_region(s, 1)
        assert newest is not None and newest.id == SNAP and newest.status == "published"


def test_d13_4_failed_human_check_rejudge_is_not_published_with_old_scores(client: TestClient) -> None:
    """사람 확인 리비전의 자동 재판정이 실패(판정기 장애)한 뒤 변경 없는 주간 수집 — 옛 점수를 now 로 발행하지 않고 재판정 등록
    (R3 5차 M2 — 예전: ``_finish_unchanged_revision`` 이 바탕 파생 행을 복사해 발행)."""
    from app.core.db import get_session
    from app.models import ChangeEvent, JobRun, ScoreRun, Snapshot
    from app.scheduler.handlers import _finish_unchanged_revision

    from .test_r3d_core2 import human_check

    body = human_check(client, "move_in_ym", "2029-03", cx=1)
    with get_session() as s:
        rev = s.get(ChangeEvent, body["change_event_id"]).snapshot_id  # type: ignore[union-attr]
        j = s.get(JobRun, body["rejudge_job_id"])
        assert j is not None
        j.status, j.error_text, j.finished_at = (
            "failed",
            "judge_unavailable: degraded",
            "2026-10-09T11:00:00+09:00",
        )
    out = _finish_unchanged_revision(_ctx("2026-10-12"), rev)
    assert out is not None and "rejudge_job_id" in out and 1 in out["stale"], out
    with get_session() as s:
        snap = s.get(Snapshot, rev)
        assert snap is not None and snap.status == "building", "옛 점수로 발행하지 않는다"
        assert not list(s.scalars(select_runs(rev)))
        job = s.get(JobRun, out["rejudge_job_id"])
        assert job is not None and job.status == "queued" and job.payload["snapshot_id"] == rev
    del ScoreRun


def select_runs(sid: int) -> Any:
    from sqlalchemy import select

    from app.models import ScoreRun

    return select(ScoreRun).where(ScoreRun.snapshot_id == sid)


def test_d13_4_human_check_on_ready_revision_then_failed_rejudge_next_daily_rejudges(
    client: TestClient,
) -> None:
    """사람 확인이 ready(판정 끝·발행 대기) 리비전에 붙고 그 리비전이 발행된 뒤 자동 재판정이 실패 — 다음 날 일일 수집은
    이월하지 않고 재판정(R3 5차 M2·M-3 잔여: 예전에는 자기 리비전 이벤트를 빼서 옛 점수를 now 로 복사)."""
    from app.core.db import get_session
    from app.models import ChangeEvent, JobRun, Snapshot
    from app.scheduler import snapshots
    from app.scheduler.handlers import _after_daily
    from app.scheduler.persist import carry_forward

    from .test_r3d_core2 import _revision_of, human_check

    rev = _revision_of(SNAP, publish=False)
    with get_session() as s:
        carry_forward(s, SNAP, rev, created_at="2026-10-09T09:10:00+09:00")
        s.get(Snapshot, rev).status = "ready"  # type: ignore[union-attr]
    body = human_check(client, "move_in_ym", "2029-06", cx=1)
    with get_session() as s:
        assert s.get(ChangeEvent, body["change_event_id"]).snapshot_id == rev  # type: ignore[union-attr]
        ok, n = snapshots.publish(s, rev, now="2026-10-09T09:20:00+09:00")
        assert ok, n
        j = s.get(JobRun, body["rejudge_job_id"])
        assert j is not None
        j.status, j.error_text, j.finished_at = "failed", "judge_unavailable", "2026-10-09T09:30:00+09:00"
    nid = _new_day()
    out = _after_daily(_ctx(), nid, [], [])
    assert "rejudge_job_id" in out and out.get("carry_forward") == "사실 변경 — 재판정", out


def test_d13_4_region_change_event_blocks_carry_forward(client: TestClient) -> None:
    """지역 선택 축소(지역 단위 change_event) 뒤 region.expand 가 끝나지 않은 채 다음 날 — 이월 대신 지역 단지 전부 재판정."""
    from app.core.db import get_session
    from app.models import JobRun
    from app.scheduler.handlers import _after_daily

    region = client.get("/api/regions/1", headers=WRITE).json()
    sels = [{"kind": x["kind"], "code": x["code"], "full_name": x["full_name"]} for x in region["selections"]]
    assert len(sels) >= 2
    r = client.patch("/api/regions/1", headers=WRITE, json={"selections": sels[:-1]})
    assert r.status_code == 200, r.text
    nid = _new_day()
    out = _after_daily(_ctx(), nid, [], [])
    assert "rejudge_job_id" in out, out
    with get_session() as s:
        job = s.get(JobRun, out["rejudge_job_id"])
        assert job is not None and len(job.payload["complex_ids"]) >= 16


# ====================================================================== M3·M4 · D13-5 change_event 는 쓰기 가능 리비전에만


def test_d13_5_region_patch_event_is_on_writable_revision(client: TestClient) -> None:
    from app.core.db import get_session
    from app.models import ChangeEvent, Snapshot

    region = client.get("/api/regions/1", headers=WRITE).json()
    sels = [{"kind": x["kind"], "code": x["code"], "full_name": x["full_name"]} for x in region["selections"]]
    r = client.patch("/api/regions/1", headers=WRITE, json={"selections": sels[:-1]})
    assert r.status_code == 200, r.text
    with get_session() as s:
        ce = s.get(ChangeEvent, r.json()["change_event"]["id"])
        assert ce is not None and ce.snapshot_id is not None
        snap = s.get(Snapshot, ce.snapshot_id)
        assert snap is not None and snap.status != "published", (snap.id, snap.status)


def test_d13_5_redemote_event_on_writable_revision_with_rejudge(client: TestClient) -> None:
    """새 출처로 풀린 강등의 모순 값이 다시 채택 → 재강등 change_event 는 쓰기 가능 리비전 + 그 단지 rejudge(M3)."""
    from sqlalchemy import select

    from app.api.demotion import sync_demotions
    from app.core.db import get_session
    from app.models import ChangeEvent, FactDemotion, JobRun, Snapshot

    from .test_r3b_g3 import CX
    from .test_r3d_core2 import _demote_price, store_notice

    won = 658_140_000
    _pt, code, _claim = _demote_price(client, won)
    store_notice(CX, "2026990101", {"effective_from": "2026-10-08", "notice_kind": "무순위",
                                    f"price_by_type.{code}.max_price_won": won + 7_000_000})  # fmt: skip
    with get_session() as s:
        sync_demotions(s, {CX})
        assert s.scalars(select(FactDemotion)).one().restored_by == "new_source"
    store_notice(CX, "2026990102", {"effective_from": "2026-10-09", "notice_kind": "무순위",
                                    f"price_by_type.{code}.max_price_won": won}, observed_on="2026-10-09")  # fmt: skip
    with get_session() as s:
        assert sync_demotions(s, {CX}) >= 1
        ev = s.scalars(select(ChangeEvent).where(ChangeEvent.new_text.like("%다시 채택%"))).one()
        snap = s.get(Snapshot, ev.snapshot_id)
        assert snap is not None and snap.status != "published"
        jobs = [j for j in s.scalars(select(JobRun).where(JobRun.job_name == "rejudge", JobRun.status == "queued"))
                if j.payload.get("snapshot_id") == snap.id and CX in (j.payload.get("complex_ids") or [CX])]  # fmt: skip
        assert jobs and ev.id in (jobs[0].payload.get("change_event_ids") or [])


def test_m3_conflict_hold_is_not_readoption(client: TestClient) -> None:
    """새 출처로 풀린 뒤 '채택 보류'(같은 rank 다른 종류 상충)만 생기면 '모순 값이 다시 채택됨' 이벤트가 없다(M3)."""
    from sqlalchemy import select

    from app.api.demotion import sync_demotions
    from app.core.db import get_session
    from app.models import ChangeEvent, Complex

    from .test_r3b_g3 import CX, _fact_claim
    from .test_r3d_core2 import store_cx_field

    store_cx_field(CX, "move_in_ym", "2028-01", "applyhome_detail", "2026-09-01", "a")
    with get_session() as s:
        name = s.get(Complex, CX).name  # type: ignore[union-attr]
    claim = _fact_claim(field_text="입주 예정 시기는 2028-01이다")
    assert (
        client.patch(
            f"/api/claims/{claim}", json={"text": f"{name} 입주 예정 시기는 2028-06이다"}, headers=WRITE
        ).status_code
        == 202
    )
    store_cx_field(CX, "move_in_ym", "2028-06", "applyhome_detail", "2026-09-03", "b")  # 다른 값 → 복원
    with get_session() as s:
        sync_demotions(s, {CX})
    store_cx_field(
        CX, "move_in_ym", "2028-01", "applyhome_list", "2026-09-04", "c"
    )  # 같은 rank 다른 종류 → 채택 보류
    with get_session() as s:
        sync_demotions(s, {CX})
        assert not list(s.scalars(select(ChangeEvent).where(ChangeEvent.new_text.like("%다시 채택%"))))


def test_d13_5_every_new_change_event_is_on_an_unpublished_revision(client: TestClient) -> None:
    """D13-5 전 경로: 사람 확인·강등·재강등·지역 확장·생활권 편집·호재 PATCH·새 공고 뒤 새로 생긴 change_event 는 모두 그 시점
    발행되지 않은 리비전(또는 리비전 없음)에 붙는다 — 발행 리비전에 붙은 이벤트가 하나도 없다."""
    from sqlalchemy import func, select

    from app.core.db import get_session
    from app.models import ChangeEvent, Snapshot

    from .test_r3e_invariant import _mutations

    with get_session() as s:
        start = int(s.scalar(select(func.max(ChangeEvent.id))) or 0)
    for step, change in _mutations(client):
        if step.startswith("J"):
            continue  # 새 리비전 발행은 이 검사 밖(발행 뒤에 붙는 이벤트가 없음을 본다)
        with get_session() as s:
            published_before = {
                sn.id: sn.published_at
                for sn in s.scalars(select(Snapshot).where(Snapshot.status == "published"))
            }
            before = int(s.scalar(select(func.max(ChangeEvent.id))) or 0)
        change()
        with get_session() as s:
            new = list(s.scalars(select(ChangeEvent).where(ChangeEvent.id > before)))
        bad = [(e.id, e.field, e.snapshot_id) for e in new if e.snapshot_id in published_before]
        assert not bad, f"{step}: 발행 리비전에 붙은 change_event {bad}"
    with get_session() as s:
        assert int(s.scalar(select(func.max(ChangeEvent.id))) or 0) > start

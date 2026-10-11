"""R3i CORE7 — 9차 리뷰(``R3_REVIEW9.md``) major 3 · m6·m8~m11·m13·m14·m16 / **D17-3·D17-5** (재현: scratchpad ``r9/c``).

| 리뷰 | 테스트 |
| --- | --- |
| major 3 / D17-3 마지막 시나리오 commit 뒤·ready 전 중단 → 재실행이 publish_blocked | ``test_major3_crash_after_last_run_retry_publishes`` |
| major 3 / D17-3 이월 발행 실패 → 재시도 없음 → 뒤 쓰기가 building 리비전으로 끝없이 미뤄짐 | ``test_major3_failed_carry_is_retried_and_later_write_published`` |
| major 3 / D17-3 재시도 상한 뒤 실패 → 미뤄진 쓰기를 새 발행 잡으로 다시 등록 | ``test_major3_terminal_failure_reregisters_deferred_writes`` |
| D17-5 체크리스트 쓰기 → 발행 잡(보고서 본문) | ``test_d17_5_checklist_patch_leaves_publish_job`` |
| D17-5 지역 이름만 바꾸는 PATCH → 발행 잡 | ``test_d17_5_region_name_patch_leaves_publish_job`` |
| m8 좌표 소수 7자리 이상 같은 본문 재전송 → 바뀐 것 없음 200 | ``test_m8_catalyst_coordinate_precision_resend_is_unchanged`` |
| m9 compare 생략(기본 비교 = revision_of) 저장본 미완 → 503 | ``test_m9_implicit_compare_pending_is_503`` |
| m10 스키마 오류 + checked_at 오류 → checked_at 먼저 | ``test_m10_checked_at_error_comes_first`` |
| m13 임대를 잃은 이전 보유자는 저장본을 쓰지 않는다 | ``test_m13_lease_lost_writer_writes_nothing`` |
| m14 스냅샷 없는 지역 호재 PATCH → 200 + job_id null | ``test_m14_catalyst_patch_without_snapshot_is_200`` |
| m6 backfill 사람 확인 이전 예외 격리 · worker 주기 재시도 | ``test_m6_backfill_isolates_human_check_migration``·``test_m6_worker_retries_backfill`` |
| m11 재큐잉·stale 회수 카운터가 서로 지우지 않는다 | ``test_m11_requeue_and_stale_counters_kept`` |
| m16 ``--once`` 는 재큐잉 대기 잡을 기다리고, 남기면 0 이 아닌 종료 | ``test_m16_once_waits_for_requeued_job``·``test_m16_once_exits_nonzero_when_requeued_left`` |
"""

# ruff: noqa: E501

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update

from app.core.db import get_engine, get_session, get_sessionmaker
from app.models import (
    Catalyst,
    JobRun,
    Region,
    Scenario,
    ScoreRun,
    Snapshot,
    SnapshotView,
    SnapshotViewUnit,
)

from ._support import READ, WRITE, publish_revision, run_job
from .test_r3b_g3 import CX, SNAP


def _ctx() -> Any:
    from app.scheduler.context import SchedulerContext

    return SchedulerContext(session_factory=get_sessionmaker(), adapter_factory=lambda: None, collectors={})  # type: ignore[arg-type,return-value]


def _cat(name: str, region_id: int = 1) -> int:
    with get_session() as s:
        c = Catalyst(region_id=region_id, name=name, kind="교통", stage="계획", location_confirmed=False)
        s.add(c)
        s.flush()
        return int(c.id)


def _patch(client: TestClient, cid: int, **extra: Any) -> Any:
    return client.patch(
        f"/api/catalysts/{cid}",
        json={"location_confirmed": True, "complex_ids": [CX], **extra},
        headers=WRITE,
    )


def _latest_pub() -> int:
    with get_session() as s:
        return int(
            s.scalars(
                select(Snapshot.id)
                .where(Snapshot.region_id == 1, Snapshot.status == "published")
                .order_by(Snapshot.asof_date.desc(), Snapshot.revision.desc())
            ).first()
            or 0
        )


def _cats_in(client: TestClient, sid: int) -> set[int]:
    d = client.get(f"/api/complexes/{CX}", params={"snapshot": sid}, headers=READ).json()
    return {int(c["id"]) for c in d.get("catalysts") or []}


def _ready_now(jid: int) -> None:
    """지연 재큐잉 잡을 지금 집을 수 있게(not_before 지움) — 시험이 backoff 를 기다리지 않는다."""
    with get_session() as s:
        j = s.get(JobRun, jid)
        assert j is not None
        j.stats = {k: v for k, v in (j.stats or {}).items() if k != "not_before"}


def _crash_runs_after(monkeypatch: pytest.MonkeyPatch, n_checkpoints: int, msg: str) -> None:
    """이월 복사 ``checkpoint`` 가 n 번째 commit 한 뒤 예외(SQLite 단계 사이 잠금 실패·worker 강제 종료 흉내)."""
    import app.scheduler.handlers as handlers
    import app.scheduler.persist as persist

    real_cf = persist.carry_forward
    calls = {"n": 0}

    def cf(session: Any, src: int, dst: int, **k: Any) -> Any:
        inner = k.pop("checkpoint", None)

        def cp() -> None:
            if inner is not None:
                inner()
            calls["n"] += 1
            if calls["n"] == n_checkpoints:
                raise RuntimeError(msg)

        return real_cf(session, src, dst, checkpoint=cp, **k)

    monkeypatch.setattr(handlers, "carry_forward", cf)


# ====================================================================== major 3 / D17-3


def test_major3_crash_after_last_run_retry_publishes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """리뷰 재현 r9/b/test_r9_carry after_last_run: 마지막 시나리오 run commit 뒤·ready commit 전에 죽으면 예전엔 재실행이
    'publish_blocked: 판정·점수 미완료'(building 고착). 이제 실패한 잡은 재시도(queued)로 남고, 다시 돌면 building→ready 를
    끝까지 가서 발행한다(멱등 전환)."""
    import app.scheduler.handlers as handlers

    with get_session() as s:
        n_src = len(set(s.scalars(select(ScoreRun.scenario_id).where(ScoreRun.snapshot_id == SNAP))))
    c1 = _cat("R3i 마지막 run 뒤 중단")
    r = _patch(client, c1, expected_ym="2031-01")
    assert r.status_code == 202, r.text
    jid, rev = r.json()["job_id"], int(r.json()["job"]["payload"]["snapshot_id"])
    real = handlers.carry_forward
    _crash_runs_after(
        monkeypatch, 2 + n_src, "worker killed after last run commit, before status=ready commit"
    )
    st, _ = run_job(jid)
    monkeypatch.setattr(handlers, "carry_forward", real)
    with get_session() as s:
        snap = s.get(Snapshot, rev)
        runs = int(
            s.scalar(select(func.count()).select_from(ScoreRun).where(ScoreRun.snapshot_id == rev)) or 0
        )
        job = s.get(JobRun, jid)
        assert snap is not None and job is not None
        assert snap.status == "building" and runs == n_src, (snap.status, runs)
        assert st == "queued" and job.status == "queued", (st, job.status, job.error_text)
        assert int((job.stats or {}).get("error_retries") or 0) == 1, job.stats
        assert str((job.stats or {}).get("requeue_reason") or "").startswith("publish_error"), job.stats
    _ready_now(jid)
    st2, stats2 = run_job(jid)
    assert st2 == "done" and stats2.get("published") is True, (st2, stats2)
    with get_session() as s:
        assert s.get(Snapshot, rev).status == "published"  # type: ignore[union-attr]
    assert c1 in _cats_in(client, rev)


def test_major3_failed_carry_is_retried_and_later_write_published(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """리뷰 재현 r9/c test_failed_carry_then_next_patch mid_runs: 이월 복사 중 실패 → 예전엔 failed·재시도 없음, 뒤 PATCH 의
    후속 잡은 done ``deferred_to`` 로 끝나 두 연결 모두 영영 발행되지 않았다. 이제 실패한 잡이 재시도로 남아 다시 돌면 그 리비전을
    발행하고, 미뤄진 쓰기도 그 발행 계산에 들어 있다."""
    import app.scheduler.handlers as handlers

    c1, c2 = _cat("R3i 역A"), _cat("R3i 역B")
    r1 = _patch(client, c1, expected_ym="2031-01")
    j1, rev = r1.json()["job_id"], int(r1.json()["job"]["payload"]["snapshot_id"])
    real = handlers.carry_forward
    _crash_runs_after(monkeypatch, 2, "database is locked (simulated in checkpoint lock())")
    st1, _ = run_job(j1)
    monkeypatch.setattr(handlers, "carry_forward", real)
    assert st1 == "queued", st1
    r2 = _patch(client, c2, expected_ym="2032-02")
    assert r2.status_code == 202 and r2.json()["job"]["payload"] == {"snapshot_id": rev, "follow_up": True}, (
        r2.text
    )
    st2, s2 = run_job(r2.json()["job_id"])
    assert st2 == "done" and s2.get("deferred_to") == rev, s2  # 그 리비전을 끝낼 잡(j1 재시도)이 살아 있다
    _ready_now(j1)
    st3, s3 = run_job(j1)
    assert st3 == "done" and s3.get("published") is True, s3
    assert _latest_pub() == rev
    got = _cats_in(client, rev)
    assert {c1, c2} <= got, got


def test_major3_terminal_failure_reregisters_deferred_writes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """재시도 상한을 넘겨 이월 발행이 끝내 실패하면, 그 building 리비전으로 미뤄졌던 쓰기(후속 잡 done ``deferred_to``)는 새
    발행 잡으로 다시 등록된다(D17-3). 그 잡이 멈춘 리비전을 끝까지(이월 이어 채움 → ready → 발행) 가져간다."""
    import app.scheduler.handlers as handlers

    c1, c2 = _cat("R3i 역C"), _cat("R3i 역D")
    r1 = _patch(client, c1, expected_ym="2031-03")
    j1, rev = r1.json()["job_id"], int(r1.json()["job"]["payload"]["snapshot_id"])
    r2 = _patch(client, c2, expected_ym="2032-04")
    j2 = r2.json()["job_id"]
    st2, s2 = run_job(j2)
    assert st2 == "done" and s2.get("deferred_to") == rev, s2
    with get_session() as s:
        j = s.get(JobRun, j1)
        assert j is not None
        j.stats = {"error_retries": handlers.PUBLISH_ERROR_RETRY_MAX}
    real = handlers.carry_forward
    _crash_runs_after(monkeypatch, 2, "persistent failure")
    st1, _ = run_job(j1)
    monkeypatch.setattr(handlers, "carry_forward", real)
    assert st1 == "failed", st1
    with get_session() as s:
        again = [
            j
            for j in s.scalars(
                select(JobRun).where(JobRun.job_name == "snapshot.publish", JobRun.status == "queued")
            )
            if (j.payload or {}).get("snapshot_id") == rev and (j.payload or {}).get("follow_up")
        ]
        assert len(again) == 1, [(j.id, j.payload) for j in again]
        j2_row = s.get(JobRun, j2)
        assert j2_row is not None and (j2_row.stats or {}).get("redeferred_job_id") == again[0].id, (
            j2_row.stats
        )
        j3 = again[0].id
    st3, s3 = run_job(j3)
    assert st3 == "done" and s3.get("published") is True, s3
    assert {c1, c2} <= _cats_in(client, _latest_pub())


# ====================================================================== D17-5


def test_d17_5_checklist_patch_leaves_publish_job(client: TestClient) -> None:
    items = client.get("/api/ops/checklist", params={"status": "open"}, headers=READ).json()
    item = next(i for i in items if i["complex_id"] is not None and i["kind"] != "사실 재확인")
    r = client.patch(
        f"/api/ops/checklist/{item['id']}", json={"status": "done", "note": "R3i 처리"}, headers=WRITE
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "done" and isinstance(body.get("job_id"), int), body
    st, stats = run_job(body["job_id"])
    assert st == "done" and stats.get("published") is True, stats
    sid = int(stats["snapshot_id"])
    with get_session() as s:
        import app.snapshot_view as sv

        base = s.scalars(select(Scenario.id).where(Scenario.code == "base")).one()
        rep = sv.stored(s, sid, "report", scenario=str(base))
    from app.reports.codec import decode_data

    data = decode_data(rep["data"])
    rows = [c for c in data.checklist if c.title == item["title"]]
    assert rows and all(c.status == "done" and c.note == "R3i 처리" for c in rows), rows
    same = client.patch(
        f"/api/ops/checklist/{item['id']}", json={"status": "done", "note": "R3i 처리"}, headers=WRITE
    )
    assert same.status_code == 200 and same.json().get("job_id") is None, same.text


def test_d17_5_region_name_patch_leaves_publish_job(client: TestClient) -> None:
    region = client.get("/api/regions/1", headers=READ).json()
    r = client.patch(
        "/api/regions/1", json={"selections": region["selections"], "name": "R3i 새 이름"}, headers=WRITE
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["change_event"] is None and isinstance(body.get("job_id"), int), body
    with get_session() as s:
        job = s.get(JobRun, body["job_id"])
        assert job is not None and job.job_name == "snapshot.publish", job
    st, stats = run_job(body["job_id"])
    assert st == "done" and stats.get("published") is True, stats
    with get_session() as s:
        import app.snapshot_view as sv

        base = s.scalars(select(Scenario.id).where(Scenario.code == "base")).one()
        rep = sv.stored(s, int(stats["snapshot_id"]), "report", scenario=str(base))
    from app.reports.codec import decode_data

    assert decode_data(rep["data"]).region_name == "R3i 새 이름"


# ====================================================================== m8·m9·m10·m14


@pytest.mark.parametrize("lat", [37.1234567, 37.12345678901])
def test_m8_catalyst_coordinate_precision_resend_is_unchanged(client: TestClient, lat: float) -> None:
    c = _cat(f"R3i 정밀 {lat}")
    r1 = _patch(client, c, lat=lat, lon=126.7)
    assert r1.status_code == 202, r1.text
    run_job(r1.json()["job_id"])
    r2 = _patch(client, c, lat=lat, lon=126.7)
    assert r2.status_code == 200 and r2.json()["job_id"] is None, r2.text


def test_m9_implicit_compare_pending_is_503(client: TestClient) -> None:
    """리뷰 재현 r9/c test_m12_implicit_compare: compare 를 생략하면 잡은 revision_of 와 비교한다 — 그 저장본이 미완이면
    예전엔 202 뒤 잡 실패(materialize_pending), 이제 POST 에서 503."""
    rev = publish_revision(1, "R3i m9")
    with get_session() as s:
        snap = s.get(Snapshot, rev)
        assert snap is not None and snap.revision_of is not None
        base_rev = snap.revision_of
        base = s.scalars(select(Scenario.id).where(Scenario.code == "base")).one()
        s.execute(
            update(SnapshotViewUnit)
            .where(SnapshotViewUnit.snapshot_id == base_rev, SnapshotViewUnit.kind == "report_diff",
                   SnapshotViewUnit.scenario == str(base))
            .values(done=False)
        )  # fmt: skip
        s.execute(
            delete(SnapshotView).where(SnapshotView.snapshot_id == base_rev, SnapshotView.kind == "report_diff",
                                       SnapshotView.scenario == str(base))
        )  # fmt: skip
    r = client.post("/api/reports", json={"snapshot_id": rev, "format": "html"}, headers=WRITE)
    assert r.status_code == 503 and r.json()["code"] == "materialize_pending", r.text


@pytest.mark.parametrize("checked_at", ["2099-01-01T00:00:00+09:00", "garbage", "1990-01-01T00:00:00+09:00"])
def test_m10_checked_at_error_comes_first(client: TestClient, checked_at: str) -> None:
    body = {"complex_id": CX, "field": "move_in_ym", "value_text": "2028-06", "kind": "zzz",
            "checked_at": checked_at, "entered_by": "운영자"}  # fmt: skip
    r = client.post("/api/ops/human-checks", headers=WRITE, json=body)
    assert r.status_code == 422 and r.json()["code"] == "validation_error", r.text
    locs = [e["loc"] for e in r.json()["field_errors"]]
    assert locs[0] == ["body", "checked_at"] and ["body", "kind"] in locs, locs


def test_m14_catalyst_patch_without_snapshot_is_200(client: TestClient) -> None:
    with get_session() as s:
        reg = Region(name="R3i 빈 지역", query_text="R3i", selections=[], sido_codes=[], sigungu_codes=[],
                     legal_dong_codes=[], living_areas=[], age_premium_coef={"c_per_year": 0.015, "cap_years": 8, "label": "추정"},
                     applyhome_query={}, status="ready", created_at="2026-10-12T00:00:00+09:00")  # fmt: skip
        s.add(reg)
        s.flush()
        rid = int(reg.id)
    c = _cat("R3i 빈 지역 호재", region_id=rid)
    r = client.patch(
        f"/api/catalysts/{c}", json={"location_confirmed": False, "expected_ym": "2030-01"}, headers=WRITE
    )
    assert r.status_code == 200 and r.json()["job_id"] is None, r.text


# ====================================================================== m13


def test_m13_lease_lost_writer_writes_nothing(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """발행 계산 중 임대를 넘겨받은 새 보유자가 생기면(이전 보유자 멈춤 → TTL 지남) 이전 보유자는 저장본을 한 행도 쓰지 않는다
    (예전: 다시 확인하지 않고 나눠 쓰기를 끝까지 — 새 보유자의 리비전에 행을 섞었다)."""
    import app.snapshot_view as sv

    with get_session() as s:
        s.execute(delete(SnapshotView).where(SnapshotView.snapshot_id == SNAP))
        s.execute(delete(SnapshotViewUnit).where(SnapshotViewUnit.snapshot_id == SNAP))
        s.execute(
            update(Snapshot)
            .where(Snapshot.id == SNAP)
            .values(status="ready", published_at=None, publish_lease=None)
        )
    real = sv.compute
    thief = f"job:4242|{time.time():.0f}"

    def compute(*a: Any, **k: Any) -> Any:
        out = real(*a, **k)
        with get_engine().begin() as c:  # 멈춘 사이 다른 발행이 임대를 넘겨받았다
            c.execute(update(Snapshot).where(Snapshot.id == SNAP).values(publish_lease=thief))
        return out

    monkeypatch.setattr(sv, "compute", compute)
    try:
        res = sv.publish_revision(get_engine(), SNAP, now="2026-10-12T00:00:00+09:00", holder="job:1")
        published = res.published
    except sv.LeaseLost:
        published = False
    assert not published
    with get_session() as s:
        n = int(
            s.scalar(select(func.count()).select_from(SnapshotView).where(SnapshotView.snapshot_id == SNAP))
            or 0
        )
        lease = s.get(Snapshot, SNAP).publish_lease  # type: ignore[union-attr]
    assert n == 0, f"임대를 잃은 보유자가 저장본 {n}행을 썼다"
    assert lease == thief


# ====================================================================== m6·m11·m16 (worker)


def test_m6_backfill_isolates_human_check_migration(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.api.demotion as demotion
    import app.snapshot_view as sv

    def boom(*a: Any, **k: Any) -> int:
        raise RuntimeError("human check migration failed")

    monkeypatch.setattr(demotion, "migrate_row_human_checks", boom)
    with get_session() as s:
        s.execute(
            update(SnapshotViewUnit)
            .where(SnapshotViewUnit.snapshot_id == SNAP, SnapshotViewUnit.kind == "claims")
            .values(done=False)
        )
    res = sv.backfill(get_engine())
    assert SNAP in res["snapshots"], res  # 리비전 채우기는 그대로 돈다
    assert any(f.get("step") == "human_checks" for f in res["failed"]), res["failed"]


def test_m6_worker_retries_backfill(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """worker 시작 때 backfill 이 실패·미완(busy 포함)이면 상주 루프가 주기마다 다시 부른다(예전: 시작 때 한 번뿐)."""
    from app.scheduler import runner

    calls: list[int] = []

    def fake(ctx: Any) -> dict[str, Any] | None:
        calls.append(1)
        return None if len(calls) == 1 else {"snapshots": [], "failed": [], "busy": []}

    monkeypatch.setattr(runner, "backfill_views", fake)
    state = runner.LoopState()
    ctx = _ctx()
    runner.start_backfill(ctx, state)
    assert calls == [1] and state.backfill_due is not None
    state.backfill_due = 0.0  # 주기가 지났다
    runner.tick(ctx, state, recover=False)
    assert calls == [1, 1] and state.backfill_due is None  # 성공하면 더 부르지 않는다
    runner.tick(ctx, state, recover=False)
    assert calls == [1, 1]


def test_m11_requeue_and_stale_counters_kept(client: TestClient) -> None:
    """리뷰 재현 r9/c test_requeue_resets_stale_counter: 지연 재큐잉이 stale_recoveries 를, stale 회수가 requeue_count 를
    지웠다(합성)."""
    from app.scheduler.runner import claim, execute, recover_stale

    ctx = _ctx()
    with get_session() as s:
        s.execute(update(Snapshot).where(Snapshot.id == SNAP).values(status="ready", published_at=None))
        hold = JobRun(job_name="collect.daily", kind="manual", payload={"region_id": 1}, status="running",
                      scheduled_at="2026-10-11T00:00:00+09:00", started_at="2099-10-11T00:00:00+09:00", stats={})  # fmt: skip
        s.add(hold)
        s.flush()
        s.execute(
            update(Snapshot)
            .where(Snapshot.id == SNAP)
            .values(publish_lease=f"job:{hold.id}|{time.time():.0f}")
        )
        j = JobRun(job_name="snapshot.publish", kind="manual", payload={"snapshot_id": SNAP}, status="queued",
                   scheduled_at="2026-10-11T00:00:00+09:00", stats={"stale_recoveries": 1})  # fmt: skip
        s.add(j)
        s.flush()
        jid = j.id
    assert claim(ctx, jid)
    assert execute(ctx, jid) == "queued"
    with get_session() as s:
        st = dict(s.get(JobRun, jid).stats or {})  # type: ignore[union-attr]
    assert st.get("stale_recoveries") == 1 and st.get("requeue_count") == 1, st
    with get_session() as s:
        row = s.get(JobRun, jid)
        assert row is not None
        row.status, row.started_at = "running", "2000-01-01T00:00:00+09:00"
        row.stats = {**(row.stats or {}), "requeue_count": 7}
    recover_stale(ctx, stale_after_s=1)
    with get_session() as s:
        row = s.get(JobRun, jid)
        assert row is not None
        st = dict(row.stats or {})
    assert row.status == "failed", (row.status, st)  # 두 번째 멈춤(회수 1회 뒤) = 실패
    assert st.get("requeue_count") == 7 and st.get("stale_recoveries") == 1, st


def _requeued_job(delay_s: float) -> int:
    """이미 발행된 리비전의 발행 잡(돌면 '이미 발행됨'으로 끝) — 지연 재큐잉 모양(not_before = 지금 + delay)."""
    from datetime import timedelta

    from app.core.time import now_kst

    with get_session() as s:
        j = JobRun(job_name="snapshot.publish", kind="manual", payload={"snapshot_id": SNAP}, status="queued",
                   scheduled_at="2026-10-11T00:00:00+09:00",
                   stats={"requeue_count": 1, "not_before": (now_kst() + timedelta(seconds=delay_s)).isoformat(timespec="seconds")})  # fmt: skip
        s.add(j)
        s.flush()
        return int(j.id)


def test_m16_once_waits_for_requeued_job(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.scheduler import runner

    monkeypatch.setattr(runner, "backfill_views", lambda ctx: None)
    jid = _requeued_job(1.5)
    assert runner.main(["--once"], ctx=_ctx()) == 0
    with get_session() as s:
        assert s.get(JobRun, jid).status == "done"  # type: ignore[union-attr]


def test_m16_once_exits_nonzero_when_requeued_left(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.scheduler import runner

    monkeypatch.setattr(runner, "backfill_views", lambda ctx: None)
    monkeypatch.setattr(runner, "ONCE_REQUEUE_WAIT_S", 0.5)
    jid = _requeued_job(60)
    assert runner.main(["--once"], ctx=_ctx()) != 0
    with get_session() as s:
        assert s.get(JobRun, jid).status == "queued"  # type: ignore[union-attr]

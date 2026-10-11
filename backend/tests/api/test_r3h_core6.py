"""R3h CORE6 — 8차 리뷰(``R3_REVIEW8.md``) N-M3·N-M4·m3~m12·m21 / D16-3·D16-4 (재현: scratchpad ``r8/b``·``r8/c``).

| 리뷰 | 테스트 |
| --- | --- |
| N-M3 / D16-3 발행 중 후속 잡 busy → 실패 대신 지연 재큐잉, 이어 발행 | ``test_nm3_busy_follow_up_is_requeued_then_publishes`` |
| D16-3 재큐잉 잡은 not_before 전에는 집지 않는다 | ``test_d16_3_queued_ids_skip_not_before`` |
| D16-3 재큐잉 상한 → failed publish_in_progress | ``test_d16_3_requeue_cap_fails`` |
| m4 / D16-3 정리 DELETE 는 임대 보유자 조건 | ``test_m4_purge_requires_lease_holder`` |
| m5 / D16-3 그 자리 발행 holder = 잡 id → 포함된 후속 잡 publish_job_id | ``test_m5_inline_publish_holder_is_job_id`` |
| m5 / D16-3 그 자리 발행이 busy → 재시도 발행 잡(publish_job_id) | ``test_m5_inline_publish_busy_leaves_publish_job`` |
| m21 전환 트랜잭션 쓰기 잠금(수정 전 코드에서 실패하도록 다시 씀) | ``test_m21_flip_takes_write_lock_before_reading`` |
| N-M4 / D16-4 호재 PATCH 예정월·좌표만 바꿔도 발행 잡, 바뀐 것 없으면 200 job_id null | ``test_nm4_*`` |
| m3 행 있고 표식 없는 단위 → 503(404 아님) → backfill 이 표식 | ``test_m3_unmarked_rows_are_pending_not_404`` |
| m6 보고서 저장본 점수 prov = API 서랍 id 모양(sc_<실행>_<단지>_<성분>·st_<실행>_<단지>) | ``test_m6_report_score_provs_open_drawers`` |
| m7 점수만 재계산 rejudge 실패 → 이월 대신 재판정 | ``test_m7_failed_score_only_rejudge_blocks_carry`` |
| m8 판정기 버전 변경 이벤트 → 이월 대신 재판정 | ``test_m8_judge_version_event_blocks_carry`` |
| m9 판정 실행 중 들어온 이벤트(시작 < 이벤트 < 끝) → 판정되지 않음 | ``test_m9_event_during_running_judgment_is_stale`` |
| m10 prev 를 만든 뒤 옛 리비전에 쓴 판정은 prev 에 없다 | ``test_m10_judgment_on_older_revision_after_prev_built_not_counted`` |
| m11 checked_at 과 다른 필드가 함께 틀리면 validation_error + 두 칸 모두 | ``test_m11_checked_at_with_other_field_errors`` |
| m12 비교 리비전 report_diff 미완 → 503(202 뒤 잡 실패 아님) | ``test_m12_compare_report_diff_pending_is_503`` |
| m13(백엔드) 보고서 날짜 표시 KST — 시각 원문 없음 | ``test_m13_report_html_dates_are_kst`` |
"""

# ruff: noqa: E501

from __future__ import annotations

import re
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update

from app.core.db import get_engine, get_session, get_sessionmaker
from app.models import Catalyst, ChangeEvent, JobRun, Scenario, Snapshot, SnapshotView, SnapshotViewUnit

from ._support import READ, WRITE, publish_revision, run_job
from .test_r3b_g3 import CX, SNAP


def _cat(name: str) -> int:
    with get_session() as s:
        c = Catalyst(region_id=1, name=name, kind="교통", stage="계획", location_confirmed=False)
        s.add(c)
        s.flush()
        return int(c.id)


def _patch(client: TestClient, cid: int, **extra: Any) -> Any:
    return client.patch(
        f"/api/catalysts/{cid}",
        json={"location_confirmed": True, "complex_ids": [CX], **extra},
        headers=WRITE,
    )


def _link(client: TestClient, cid: int, **extra: Any) -> Any:
    r = _patch(client, cid, **extra)
    assert r.status_code == 202, r.text
    return r.json()


def _ctx() -> Any:
    from app.scheduler.context import SchedulerContext

    return SchedulerContext(session_factory=get_sessionmaker(), adapter_factory=lambda: None, collectors={})  # type: ignore[arg-type,return-value]


def _latest(client: TestClient) -> int:
    return int(client.get("/api/regions/1", headers=READ).json()["latest_snapshot"]["id"])


def _catalysts_in_latest(client: TestClient) -> dict[int, dict[str, Any]]:
    d = client.get(f"/api/complexes/{CX}", params={"snapshot": _latest(client)}, headers=READ).json()
    return {int(c["id"]): c for c in d.get("catalysts") or []}


def _new_building(asof: str) -> int:
    with get_session() as s:
        nxt = Snapshot(region_id=1, asof_date=asof, status="building", degraded=False,
                       created_at=f"{asof}T06:00:00+09:00", revision=1)  # fmt: skip
        s.add(nxt)
        s.flush()
        return int(nxt.id)


def _running_holder(sid: int, job_name: str = "snapshot.publish") -> int:
    """다른 worker 가 그 리비전을 발행 중인 모양: running 잡 + 그 잡이 든 임대."""
    payload = {"snapshot_id": sid} if job_name == "snapshot.publish" else {"region_id": 1}
    with get_session() as s:
        j = JobRun(job_name=job_name, kind="manual", payload=payload, status="running",
                   scheduled_at="2026-10-11T00:00:00+09:00", started_at="2026-10-11T00:00:00+09:00", stats={})  # fmt: skip
        s.add(j)
        s.flush()
        s.execute(
            update(Snapshot).where(Snapshot.id == sid).values(publish_lease=f"job:{j.id}|{time.time():.0f}")
        )
        return int(j.id)


# ====================================================================== D16-3 (N-M3·m4·m5·m21)


def test_nm3_busy_follow_up_is_requeued_then_publishes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """worker 2개(재현 r8/c test_followup_runs_while_other_publish_computes): P 가 발행 계산 중일 때 후속 잡 F 가 돌면
    예전엔 failed publish_in_progress·P 의 followups_included [] → 변경 유실. 이제 F 는 queued(지연 재큐잉)로 돌아가고,
    P 가 끝난 뒤 다시 돌면 새 리비전으로 발행해 두 연결 모두 최신 발행 리비전에 있다."""
    import app.snapshot_view as sv

    c1, c2 = _cat("R3h 역1"), _cat("R3h 역2")
    j1 = _link(client, c1)["job_id"]
    real = sv.compute
    box: dict[str, Any] = {}

    def hooked(*a: Any, **k: Any) -> Any:
        out = real(*a, **k)
        if "f" not in box:
            box["f"] = _link(client, c2)["job_id"]
            box["first"] = run_job(box["f"])  # 두 번째 worker
        return out

    monkeypatch.setattr(sv, "compute", hooked)
    st1, stats1 = run_job(j1)
    monkeypatch.setattr(sv, "compute", real)
    assert st1 == "done" and stats1["published"], stats1
    assert box["first"][0] == "queued", box["first"]
    with get_session() as s:
        jf = s.get(JobRun, box["f"])
        assert jf is not None
        assert jf.status == "queued" and jf.error_text is None, (jf.status, jf.error_text, jf.stats)
        assert int((jf.stats or {}).get("requeue_count") or 0) == 1 and (jf.stats or {}).get("not_before"), (
            jf.stats
        )
        assert "publish_in_progress" in str((jf.stats or {}).get("requeue_reason") or ""), jf.stats
    st2, stats2 = run_job(box["f"])
    assert st2 == "done" and stats2.get("published") and stats2.get("publish_job_id") == box["f"], stats2
    cats = _catalysts_in_latest(client)
    assert cats[c1].get("linked") and cats[c2].get("linked"), cats


def test_d16_3_queued_ids_skip_not_before(client: TestClient) -> None:
    """지연 재큐잉 잡(stats.not_before 가 미래)은 그 시각 전에는 worker 가 집지 않는다(바쁜 대기 없음)."""
    from app.scheduler.runner import queued_ids

    with get_session() as s:
        later = JobRun(job_name="snapshot.publish", kind="manual", payload={"snapshot_id": SNAP}, status="queued",
                       scheduled_at="2026-10-11T00:00:00+09:00", stats={"not_before": "2999-01-01T00:00:00+09:00"})  # fmt: skip
        now = JobRun(job_name="snapshot.publish", kind="manual", payload={"snapshot_id": SNAP}, status="queued",
                     scheduled_at="2026-10-11T00:00:00+09:00", stats={"not_before": "2000-01-01T00:00:00+09:00"})  # fmt: skip
        s.add_all([later, now])
        s.flush()
        ids = (later.id, now.id)
    got = queued_ids(_ctx(), limit=200)
    assert ids[1] in got and ids[0] not in got, got


def test_d16_3_requeue_cap_fails(client: TestClient) -> None:
    """재큐잉은 상한이 있다 — 상한에 이른 잡이 또 busy 면 failed ``publish_in_progress``(무한 대기 없음)."""
    from app.scheduler.handlers import PUBLISH_REQUEUE_MAX

    with get_session() as s:
        s.execute(update(Snapshot).where(Snapshot.id == SNAP).values(status="ready", published_at=None))
    _running_holder(SNAP)
    with get_session() as s:
        j = JobRun(job_name="snapshot.publish", kind="manual", payload={"snapshot_id": SNAP}, status="queued",
                   scheduled_at="2026-10-11T00:00:00+09:00", stats={"requeue_count": PUBLISH_REQUEUE_MAX})  # fmt: skip
        s.add(j)
        s.flush()
        jid = j.id
    st, _stats = run_job(jid)
    with get_session() as s:
        row = s.get(JobRun, jid)
        assert row is not None
        assert st == "failed" and (row.error_text or "").startswith("publish_in_progress"), (
            st,
            row.error_text,
        )


def test_m4_purge_requires_lease_holder(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """임대를 넘겨받은 뒤(이전 보유자 A 는 TTL 을 넘겨 멈췄다) A 가 깨어나 실패 정리를 해도 새 보유자 B 의 저장본을 지우지
    않는다(예전: 정리 DELETE 에 '발행 전' 상태 조건만 — B 가 전환 전이면 B 의 행을 지웠다)."""
    import app.snapshot_view as sv

    with get_session() as s:
        s.execute(delete(SnapshotView).where(SnapshotView.snapshot_id == SNAP))
        s.execute(delete(SnapshotViewUnit).where(SnapshotViewUnit.snapshot_id == SNAP))
        s.execute(
            update(Snapshot)
            .where(Snapshot.id == SNAP)
            .values(status="ready", published_at=None, publish_lease=None)
        )
    real = sv.write_rows

    def stolen(conn: Any, sid: int, rows: Any, **k: Any) -> Any:
        # A 가 쓰는 도중 B 가 임대를 넘겨받아 자기 행을 썼다(같은 연결로 흉내) — 그리고 A 의 쓰기가 실패한다
        with conn.begin():
            conn.execute(
                update(Snapshot)
                .where(Snapshot.id == sid)
                .values(publish_lease=f"job:999999|{time.time():.0f}")
            )
            conn.execute(sv.insert(SnapshotView), sv._row_dicts(sid, rows[:1]))
        raise RuntimeError("A 의 쓰기 실패")

    monkeypatch.setattr(sv, "write_rows", stolen)
    with pytest.raises(RuntimeError):
        sv.publish_revision(get_engine(), SNAP, now="2026-10-11T00:00:00+09:00", holder="job:888888")
    monkeypatch.setattr(sv, "write_rows", real)
    with get_session() as s:
        n = len(list(s.scalars(select(SnapshotView.id).where(SnapshotView.snapshot_id == SNAP))))
    assert n == 1, "B 의 행이 남아 있어야 한다"


def test_m5_inline_publish_holder_is_job_id(client: TestClient) -> None:
    """daily 이월(그 자리 발행)이 계산 중 본 후속 잡을 '포함됨'으로 닫으면 그 잡의 publish_job_id = daily 잡 id(F15)
    (예전: holder 'pid:…' → null, 넘겨받기도 15분 TTL 만)."""
    from app.scheduler.handlers import _after_daily

    nid = _new_building("2099-04-01")
    c1 = _cat("R3h 역5")
    f = _link(client, c1)["job_id"]
    res = _after_daily(_ctx(), nid, [], [], job_id=4242)
    assert res["published"] is True and res["publish_job_id"] == 4242, res
    with get_session() as s:
        j = s.get(JobRun, f)
        assert j is not None and j.status == "done", j.status if j else None
        assert (j.stats or {}).get("included_in_snapshot_id") == nid and (j.stats or {}).get(
            "publish_job_id"
        ) == 4242, j.stats


@pytest.mark.parametrize("holder_job", ["collect.daily", "snapshot.publish"])
def test_m5_inline_publish_busy_leaves_publish_job(client: TestClient, holder_job: str) -> None:
    """그 자리 발행이 busy(다른 발행이 같은 리비전을 들고 있음)면 실패로 끝내지 않고 그 리비전을 발행할 snapshot.publish 잡을
    publish_job_id 로 준다 — 들고 있는 잡이 그 리비전의 snapshot.publish 면 그 잡, 아니면 새 잡(재큐잉으로 이어 발행)."""
    from app.scheduler.handlers import _after_daily

    nid = _new_building(f"2099-04-0{2 if holder_job == 'collect.daily' else 3}")
    holder = _running_holder(nid, holder_job)
    res = _after_daily(_ctx(), nid, [], [], job_id=4343)
    assert res["published"] is False and res.get("publish_in_progress"), res
    pj = res.get("publish_job_id")
    assert isinstance(pj, int) and pj != 4343 and res.get("publish_retry_job_id") == pj, res
    with get_session() as s:
        j = s.get(JobRun, pj)
        assert (
            j is not None and j.job_name == "snapshot.publish" and (j.payload or {}).get("snapshot_id") == nid
        )
        if holder_job == "snapshot.publish":
            assert pj == holder
        else:
            assert j.status == "queued"


def test_m21_flip_takes_write_lock_before_reading(client: TestClient) -> None:
    """전환 트랜잭션: 첫 읽기 전에 쓰기 잠금을 잡는다. 읽기(남은 contradicted 재확인)와 published UPDATE 사이 다른 연결이
    커밋하려 하면 그 커밋이 잠금에 막힌다(전환이 BUSY_SNAPSHOT 으로 실패하지 않는다). 수정 전 코드(잠금 UPDATE 없음)에서는
    읽기 스냅샷 뒤 다른 커밋이 끼어들어 published UPDATE 가 'database is locked'(SQLITE_BUSY_SNAPSHOT)로 실패한다."""
    import sqlite3

    from app.judge.claims import remaining_contradicted
    from app.snapshot_view import _flip, write_connection

    lease = f"job:777|{time.time():.0f}"
    with get_session() as s:
        s.execute(
            update(Snapshot)
            .where(Snapshot.id == SNAP)
            .values(status="ready", published_at=None, publish_lease=lease)
        )
    db = str(get_engine().url.database)
    seen: dict[str, Any] = {}

    def remaining(session: Any, sid: int) -> Any:
        out = remaining_contradicted(session, sid)  # 이 트랜잭션의 읽기(스냅샷)
        other = sqlite3.connect(db, timeout=0.3, isolation_level=None)
        try:
            other.execute("BEGIN IMMEDIATE")
            other.execute("UPDATE region SET name = name || '' WHERE id = 1")
            other.execute("COMMIT")
            seen["other_committed"] = True
        except sqlite3.OperationalError as exc:
            seen["other_committed"] = False
            seen["other_error"] = str(exc)
        finally:
            other.close()
        return out

    with write_connection(get_engine()) as conn:
        done, n = _flip(
            conn, SNAP, now="2026-10-11T00:00:00+09:00", lease=lease, followups=[], remaining=remaining
        )
    assert (done, n) == (1, 0)
    assert seen["other_committed"] is False, seen  # 전환이 잠금을 먼저 들고 있었다


# ====================================================================== D16-4 (N-M4)


def test_nm4_expected_ym_only_patch_publishes(client: TestClient) -> None:
    """이미 연결된 호재의 예정월만 바꾼 PATCH — 예전 202 job_id None·발행 상세 옛 값. 이제 발행 잡 → 최신 발행 리비전에 새 값."""
    c1 = _cat("R3h 역6")
    st, _ = run_job(_link(client, c1, expected_ym="2030-01")["job_id"])
    assert st == "done"
    assert _catalysts_in_latest(client)[c1]["expected_ym"]["v"] == "2030-01"
    r = _patch(client, c1, expected_ym="2033-12")
    assert r.status_code == 202 and r.json()["job_id"] is not None, r.text
    st, stats = run_job(r.json()["job_id"])
    assert st == "done" and stats["published"], stats
    assert _catalysts_in_latest(client)[c1]["expected_ym"]["v"] == "2033-12"


def test_nm4_coordinates_only_patch_publishes(client: TestClient) -> None:
    c1 = _cat("R3h 역7")
    run_job(_link(client, c1)["job_id"])
    r = _patch(client, c1, lat=37.5, lon=126.7)
    assert r.status_code == 202 and r.json()["job_id"] is not None, r.text
    st, stats = run_job(r.json()["job_id"])
    assert st == "done" and stats["published"], stats


def test_nm4_unchanged_patch_is_200_without_job(client: TestClient) -> None:
    """바뀐 것이 없는 PATCH(같은 연결·같은 예정월·같은 좌표) → 200 + job_id null, 새 잡·리비전·출처 행 없음(D16-4)."""
    from sqlalchemy import func

    from app.models import FieldProvenance

    c1 = _cat("R3h 역8")
    run_job(_link(client, c1, expected_ym="2031-06", lat=37.5, lon=126.7)["job_id"])

    def counts() -> tuple[int, int, int]:
        with get_session() as s:
            return (
                int(s.scalar(select(func.count()).select_from(JobRun)) or 0),
                int(s.scalar(select(func.count()).select_from(Snapshot)) or 0),
                int(
                    s.scalar(
                        select(func.count())
                        .select_from(FieldProvenance)
                        .where(FieldProvenance.entity == "catalyst")
                    )
                    or 0
                ),
            )

    before = counts()
    r = _patch(client, c1, expected_ym="2031-06", lat=37.5, lon=126.7)
    assert r.status_code == 200, r.text
    assert r.json()["job_id"] is None and r.json()["job"] is None
    assert counts() == before


# ====================================================================== m3 · m6 (저장본)


def test_m3_unmarked_rows_are_pending_not_404(client: TestClient) -> None:
    """행은 있는데 완료 표식이 없는 단위(예: 표식 쓰기 전 중단) — 예전 404 not_found(영구, pending·backfill 둘 다 놓침).
    이제 503 materialize_pending + pending_count, backfill 이 표식만 쓰고 바이트는 그대로 → 200."""
    from sqlalchemy.orm import Session

    import app.snapshot_view as sv
    from app.core.settings import get_settings

    with get_session() as s:
        sc = s.scalars(select(Scenario.id).order_by(Scenario.id)).all()[2]
        s.execute(
            delete(SnapshotViewUnit).where(
                SnapshotViewUnit.snapshot_id == SNAP,
                SnapshotViewUnit.kind == "dashboard",
                SnapshotViewUnit.scenario == str(sc),
            )
        )
    r = client.get(f"/api/snapshots/{SNAP}/dashboard", params={"scenario": sc}, headers=READ)
    assert r.status_code == 503 and r.json()["code"] == "materialize_pending", r.text
    with Session(bind=get_engine()) as ses:
        assert sv.pending_count(ses) == 1
    res = sv.backfill(get_engine(), settings=get_settings())
    assert res["snapshots"] == [SNAP] and res["rows"] == 0, res
    r = client.get(f"/api/snapshots/{SNAP}/dashboard", params={"scenario": sc}, headers=READ)
    assert r.status_code == 200, r.text


def test_m6_report_score_provs_open_drawers(client: TestClient) -> None:
    """보고서 저장본의 점수 Fact prov(sc_·st_)가 API 서랍 id 모양이다 — 그 리비전 출처 서랍이 200(예전 sc_<성분 행 id>·
    st_<합계 행 id> → 서랍 없음·KPI st_<실행> 과 충돌)."""
    from app.snapshot_view import stored

    rev = publish_revision(1, "R3h m6")
    with get_session() as s:
        base = s.scalars(select(Scenario.id).where(Scenario.code == "base")).one()
        body = stored(s, rev, "report", scenario=str(base))
    provs = sorted(
        set(
            re.findall(
                r'"prov": ?"((?:sc|st)_[0-9A-Za-z_]+)"', __import__("json").dumps(body, ensure_ascii=False)
            )
        )
    )
    assert provs, "보고서에 점수 Fact 가 있다"
    bad = []
    for pid in provs:
        r = client.get(f"/api/provenance/{pid}", params={"snapshot_id": rev}, headers=READ)
        if r.status_code != 200:
            bad.append((pid, r.status_code))
    assert not bad, bad[:10]
    assert all(re.fullmatch(r"sc_\d+_\d+_[a-z0-9_]+|st_\d+_\d+", p) for p in provs), provs[:10]


# ====================================================================== m7~m10 (이월 판단)


def _event(s: Any, cid: int | None, at: str, *, entity: str = "complex", eid: int | None = None) -> None:
    s.add(ChangeEvent(snapshot_id=SNAP, entity=entity, entity_id=eid if eid is not None else cid, field="move_in_ym",
                      old_text="a", new_text="b", detected_at=at, severity="critical", triggers_rejudge=True, complex_id=cid))  # fmt: skip


def _judge_job(
    s: Any, status: str, sid: int, ids: list[int] | None, start: str, end: str, wrote: int | None = None
) -> None:
    s.add(JobRun(job_name="rejudge", kind="rejudge", status=status,
                 payload={"snapshot_id": sid, "scenario_id": None, "complex_ids": ids, "reason": "r3h"},
                 scheduled_at=start, started_at=start, finished_at=end,
                 stats={"snapshot_id": wrote} if wrote is not None else {}))  # fmt: skip


def _stale() -> list[int]:
    from app.scheduler.handlers import changed_after_runs

    with get_session() as s:
        snap = s.get(Snapshot, SNAP)
        assert snap is not None
        return changed_after_runs(s, snap)


def _region_ids() -> set[int]:
    from app.models import Complex

    with get_session() as s:
        return set(s.scalars(select(Complex.id).where(Complex.region_id == 1)))


def test_m7_failed_score_only_rejudge_blocks_carry(client: TestClient) -> None:
    """점수만 재계산 rejudge(complex_ids=[] — 주간 시장 자료·호재 URL) 실패 → 그 지역 단지는 옛 점수를 이월하지 않는다."""
    assert _stale() == []
    with get_session() as s:
        _judge_job(s, "failed", SNAP, [], "2099-01-01T10:00:00+09:00", "2099-01-01T10:05:00+09:00")
    assert set(_stale()) == _region_ids()


def test_m8_judge_version_event_blocks_carry(client: TestClient) -> None:
    """판정기 버전 변경(change_event entity 'judge', 단지 없음, 재판정) → 모든 단지 재판정(이월 없음)."""
    with get_session() as s:
        _event(s, None, "2099-01-01T10:00:00+09:00", entity="judge", eid=None)
    assert set(_stale()) == _region_ids()


def test_m9_event_during_running_judgment_is_stale(client: TestClient) -> None:
    """판정 잡이 사실을 읽기 시작한 뒤·끝나기 전에 들어온 변경 — 판정이 못 본 변경이다(기준 = 판정 시작 시각)."""
    with get_session() as s:
        _judge_job(
            s, "done", SNAP, [CX], "2099-01-01T10:00:00+09:00", "2099-01-01T10:30:00+09:00", wrote=SNAP
        )
        _event(s, CX, "2099-01-01T10:15:00+09:00")
    assert CX in _stale()
    with get_session() as s:  # 판정 시작 전 변경은 판정이 읽었다
        s.execute(delete(ChangeEvent).where(ChangeEvent.detected_at == "2099-01-01T10:15:00+09:00"))
        _event(s, CX, "2099-01-01T09:59:00+09:00")
    assert CX not in _stale()


def test_m10_judgment_on_older_revision_after_prev_built_not_counted(client: TestClient) -> None:
    """prev(12)를 만든 뒤 옛 발행 리비전(11)에 쓴 판정은 prev 에 들어 있지 않다(예전: 리비전 키가 작으면 셈)."""
    with get_session() as s:
        _event(s, CX, "2099-01-01T10:00:00+09:00")
        _judge_job(s, "done", 11, [CX], "2099-01-01T10:05:00+09:00", "2099-01-01T10:30:00+09:00", wrote=11)
    assert CX in _stale()


# ====================================================================== m11 · m12 · m13


def _hc(client: TestClient, checked_at: Any, **extra: Any) -> Any:
    body = {"complex_id": CX, "field": "move_in_ym", "value_text": "2028-06", "kind": "phone",
            "checked_at": checked_at, "entered_by": "운영자", **extra}  # fmt: skip
    return client.post("/api/ops/human-checks", headers=WRITE, json=body)


@pytest.mark.parametrize(
    ("checked_at", "extra", "other"),
    [
        ("1990-01-01T00:00:00+09:00", {"kind": "zzz"}, ["body", "kind"]),
        ("2099-01-01T00:00:00+09:00", {"kind": "zzz"}, ["body", "kind"]),
        ("1990-01-01T00:00:00+09:00", {"value_text": "abc"}, ["body", "value_text"]),
        ("2099-01-01T00:00:00+09:00", {"value_text": "abc"}, ["body", "value_text"]),
        ("garbage", {"kind": "zzz"}, ["body", "kind"]),
    ],
)
def test_m11_checked_at_with_other_field_errors(
    client: TestClient, checked_at: str, extra: dict[str, Any], other: list[str]
) -> None:
    """F14: checked_at 과 다른 필드가 함께 틀리면 code 는 validation_error, field_errors 에 두 칸 모두(예전: kind 만 있거나
    checked_at_* code 로 다른 칸 오류가 사라졌다)."""
    r = _hc(client, checked_at, **extra)
    assert r.status_code == 422, r.text
    body = r.json()
    locs = [e["loc"] for e in body.get("field_errors") or []]
    assert body["code"] == "validation_error", body
    assert ["body", "checked_at"] in locs and other in locs, locs


def test_m11_checked_at_only_keeps_specific_code(client: TestClient) -> None:
    r = _hc(client, "1990-01-01T00:00:00+09:00")
    assert r.status_code == 422 and r.json()["code"] == "checked_at_format"
    assert [e["loc"] for e in r.json()["field_errors"]] == [["body", "checked_at"]]


def test_m12_compare_report_diff_pending_is_503(client: TestClient) -> None:
    """비교 리비전(12)의 report_diff 단위가 미완이면 POST /reports 는 202 대신 503 materialize_pending(잡 실패 전에)."""
    rev = publish_revision(1, "R3h m12")
    with get_session() as s:
        base = s.scalars(select(Scenario.id).where(Scenario.code == "base")).one()
        s.execute(
            update(SnapshotViewUnit)
            .where(
                SnapshotViewUnit.snapshot_id == SNAP,
                SnapshotViewUnit.kind == "report_diff",
                SnapshotViewUnit.scenario == str(base),
            )
            .values(done=False)
        )
        s.execute(
            delete(SnapshotView).where(
                SnapshotView.snapshot_id == SNAP,
                SnapshotView.kind == "report_diff",
                SnapshotView.scenario == str(base),
            )
        )
    r = client.post(
        "/api/reports",
        json={"snapshot_id": rev, "format": "html", "compare_snapshot_id": SNAP},
        headers=WRITE,
    )
    assert r.status_code == 503 and r.json()["code"] == "materialize_pending", r.text


def test_m13_report_html_dates_are_kst(client: TestClient) -> None:
    """사람 확인 접수 '…T20:00:00Z'(KST 다음 날) → 보고서 HTML 에 KST 날짜(2026-10-10)만, 시각 원문(…T…)은 없다(D15-7·D16-5)."""
    from bs4 import BeautifulSoup

    from app.reports.data import load_report
    from app.reports.render import render_html

    r = client.post("/api/ops/human-checks", headers=WRITE, json={
        "complex_id": CX, "field": "intake_status", "value_text": "확인 불가", "kind": "phone",
        "checked_at": "2026-10-09T20:00:00Z", "entered_by": "운영자"})  # fmt: skip
    assert r.status_code == 201, r.text
    sid = int(r.json()["created_intake"]["snapshot_id"])
    with get_session() as s:
        text = BeautifulSoup(render_html(load_report(s, sid)).html, "html.parser").get_text(" ")
    assert "2026-10-10" in text
    utc = r"\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:[Zz]|[+-](?!09:00)\d{2}:\d{2})"
    assert not re.search(utc, text), re.findall(utc, text)[:5]  # KST 가 아닌 시각 원문 없음
    assert "2026-10-09T20" not in text


# ====================================================================== D14-5 이월 복사 나눠 쓰기(R3h 부하 측정)


def test_d14_5_carry_copy_is_chunked_and_resumes(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """이월 복사(호재 PATCH → snapshot.publish carry)를 단계마다 commit(쓰기 잠금을 짧게 — 부하 측정에서 한 트랜잭션 1.06s).
    중간에 멈춘 복사는 다시 돌 때 이어서 채운다(시나리오 run·비교군 중복 없음)."""
    from sqlalchemy import func

    import app.scheduler.persist as persist
    from app.models import ComparableSet, ScoreRun

    out = _link(client, _cat("R3h 역9"))
    jid, rev = out["job_id"], int(out["job"]["payload"]["snapshot_id"])
    real = persist.copy_runs
    calls = {"n": 0}

    def crash_after_two(session: Any, src: int, dst: int, **k: Any) -> Any:
        inner = k.pop("checkpoint")

        def cp() -> None:
            inner()
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("worker 사망 흉내")

        return real(session, src, dst, checkpoint=cp, **k)

    monkeypatch.setattr(persist, "copy_runs", crash_after_two)
    st, _ = run_job(jid)
    monkeypatch.setattr(persist, "copy_runs", real)
    assert st == "failed"
    with get_session() as s:
        n_src = len(set(s.scalars(select(ScoreRun.scenario_id).where(ScoreRun.snapshot_id == SNAP))))
        part = len(list(s.scalars(select(ScoreRun.id).where(ScoreRun.snapshot_id == rev))))
        assert 0 < part < n_src, (part, n_src)
        s.execute(update(JobRun).where(JobRun.id == jid).values(status="queued"))
    st, stats = run_job(jid)
    assert st == "done" and stats["published"], stats
    assert stats["carry_steps"] >= 3, stats
    with get_session() as s:
        runs = list(s.scalars(select(ScoreRun.scenario_id).where(ScoreRun.snapshot_id == rev)))
        assert sorted(runs) == sorted(set(runs)) and len(runs) == n_src
        cs = int(
            s.scalar(select(func.count()).select_from(ComparableSet).where(ComparableSet.snapshot_id == rev))
            or 0
        )
        cs_src = int(
            s.scalar(select(func.count()).select_from(ComparableSet).where(ComparableSet.snapshot_id == SNAP))
            or 0
        )
        assert cs == cs_src

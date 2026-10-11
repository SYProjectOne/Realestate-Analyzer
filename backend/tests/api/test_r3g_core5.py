"""R3g CORE5 — R3 7차 리뷰(`docs/design/wp/R3_REVIEW7.md`) / DECISIONS D15-2·D15-3·D15-4·D15-6 (계약 2026-10-09.12).

리뷰 재현 스크립트(scratchpad ``r7/a``·``r7/c``)를 픽스처(devseed 인천·김포 — 단지 16·시나리오 5·발행 스냅샷 11·12) 테스트로 옮겼다.

| 리뷰 | 내용 |
| --- | --- |
| M1 · m7 · m24 | 모든 시나리오·kind 응답의 prov(patch 행 ``{"$v":…}``)·접수 근거 ``rd_`` 서랍이 발행 리비전 저장본에 있다 |
| M2 · m9 · m11 | 완료 표식: backfill 중간 중단 → 503(영구 404 아님)·``POST /reports`` 503 → 재실행이 빠진 키만 채움(있던 바이트 그대로) |
| M3 · m14 | 이월 '판정됨' = prev 에 들어 있는 판정만, 시나리오 지정 rejudge 는 그 시나리오만 |
| M5 · m1 · m13 · m16 | 발행 계산 중 PATCH → 후속 발행 잡 · single-flight · 발행 재시도 잡 · POST /catalysts job_id |
| m4 · m6 · m8 · m10 | 의미 묶음 이전 이벤트 리비전 · 서랍 생략 경로 503 · patch 바이트 · POST /reports 준비 검사 |
"""

# ruff: noqa: E501

from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.core.db import get_engine, get_session
from app.models import (
    Catalyst,
    CatalystLink,
    ChangeEvent,
    JobRun,
    Scenario,
    ScoreRun,
    Snapshot,
    SnapshotView,
    SnapshotViewUnit,
)

from ._support import READ, WRITE, publish_revision, run_job
from .test_r3_f3 import fake_catalyst  # noqa: F401  (픽스처 재사용)
from .test_r3b_g3 import CX, SNAP

OTHER = 5


def _walk(body: Any, acc: set[str]) -> None:
    if isinstance(body, dict):
        p = body.get("prov")
        if isinstance(p, str):
            acc.add(p)
        rd = body.get("raw_document_id")
        if isinstance(rd, int) and not isinstance(rd, bool):
            acc.add(f"rd_{rd}")
        for v in body.values():
            _walk(v, acc)
    elif isinstance(body, list):
        for v in body:
            _walk(v, acc)


def _scenario_keys() -> list[str]:
    with get_session() as s:
        return [str(x.code or x.id) for x in s.scalars(select(Scenario).order_by(Scenario.id))]


def _all_ids(client: TestClient, rev: int) -> set[str]:
    """그 리비전 화면 응답 전부(모든 시나리오) + 접수 근거 rd_ — m24: 기본 시나리오만이 아니다."""
    acc: set[str] = set()
    with get_session() as s:
        cids = [int(i) for i in s.scalars(select(Snapshot.region_id).where(Snapshot.id == rev))]
        from app.models import Complex

        cx_ids = [int(i) for i in s.scalars(select(Complex.id).where(Complex.region_id == cids[0]))]
    for sc in _scenario_keys():
        q = f"scenario={sc}"
        for u in (
            f"/api/snapshots/{rev}/dashboard?{q}",
            f"/api/snapshots/{rev}/complexes?{q}",
            f"/api/snapshots/{rev}/market?{q}",
            f"/api/snapshots/{rev}/sensitivity?{q}",
            f"/api/snapshots/{rev}/compare?{q}&ids={','.join(map(str, cx_ids[:4]))}",
            *(f"/api/complexes/{c}?snapshot={rev}&{q}" for c in cx_ids),
        ):
            r = client.get(u, headers=READ)
            assert r.status_code == 200, (u, r.text[:200])
            _walk(r.json(), acc)
    for u in (f"/api/snapshots/{rev}/changes", f"/api/snapshots/{rev}/claims"):
        r = client.get(u, headers=READ)
        assert r.status_code == 200, (u, r.text[:200])
        _walk(r.json(), acc)
    return acc


# ====================================================================== M1 · m7 · m24 (D15-2)


def test_m1_patch_leaf_and_raw_document_ids_are_collected() -> None:
    from app.snapshot_view import _collect_prov

    acc: set[str] = set()
    _collect_prov(
        b'{"$patch":{"kpi":{"$p":{"prov":{"$v":"st_2"}}}},"x":{"prov":"fp_7","raw_document_id":9}}', acc
    )
    _collect_prov(b'{"intake":{"$v":{"raw_document_id":{"$v":31}}},"rows":[{"raw_document_id":null}]}', acc)
    assert acc == {"st_2", "fp_7", "rd_9", "rd_31"}


def test_m1_every_scenario_drawer_and_rd_is_stored(client: TestClient) -> None:
    """R3 7차 M1·m7·m24(r5_st_missing·r6_prov_coverage): 시나리오 A–D 대시보드 KPI(st_<run>)·접수 근거 rd_ 를 포함해 발행
    리비전 화면 응답 전부(모든 시나리오)의 출처 id 가 그 리비전 저장본 서랍에서 200."""
    rev = publish_revision(1, "R3g M1")
    ids = _all_ids(client, rev)
    assert any(p.startswith("st_") for p in ids) and any(p.startswith("rd_") for p in ids)
    bad = []
    for pid in sorted(ids):
        r = client.get(f"/api/provenance/{pid}?snapshot_id={rev}", headers=READ)
        if r.status_code != 200:
            bad.append((pid, r.status_code))
    assert not bad, bad[:10]


def test_m1_fixture_revision_scenario_kpi_drawers(client: TestClient) -> None:
    """devseed 발행 리비전 12 의 시나리오 A·D 대시보드 KPI 출처(st_2… — patch 행에만 있던 id)도 서랍 200."""
    for sc in ("A", "D"):
        body = client.get(f"/api/snapshots/{SNAP}/dashboard?scenario={sc}", headers=READ).json()
        sts = sorted(set(re.findall(r"st_\d+(?![_\d])", str(body))))
        assert sts, sc
        for st in sts:
            r = client.get(f"/api/provenance/{st}?snapshot_id={SNAP}", headers=READ)
            assert r.status_code == 200, (sc, st, r.text[:200])


# ====================================================================== M2 · m9 · m11 (D15-3)


def _unit_counts(sid: int) -> dict[tuple[str, str], int]:
    with get_session() as s:
        return {
            (str(k), str(sc)): int(n)
            for k, sc, n in s.execute(
                select(SnapshotView.kind, SnapshotView.scenario, func.count())
                .where(SnapshotView.snapshot_id == sid)
                .group_by(SnapshotView.kind, SnapshotView.scenario)
            )
        }


def _row_bytes(sid: int) -> dict[tuple[str, str, str], bytes]:
    with get_session() as s:
        return {
            (k, key, sc): bytes(b)
            for k, key, sc, b in s.execute(
                select(SnapshotView.kind, SnapshotView.key, SnapshotView.scenario, SnapshotView.body).where(
                    SnapshotView.snapshot_id == sid
                )
            )
        }


def test_m2_backfill_interrupted_is_503_then_resumes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R3 7차 M2(r3_backfill_partial·c/test_backfill_interrupted): 0010 이전 발행분처럼 저장본이 없는 리비전을 backfill 이 묶음
    쓰기 중간에 멈추면 — 예전: '그 kind 행 하나라도 있으면 완료' → 나머지 시나리오·단지 영구 404, POST /reports 422,
    pending_count 0. 지금: 미완 단위는 503 + Retry-After, POST /reports 503, pending_count 1 → 다시 backfill 이 빠진 행만 채워
    전부 200, 이미 있던 행 바이트는 그대로."""
    import app.snapshot_view as sv

    with get_session() as s:
        s.execute(delete(SnapshotView).where(SnapshotView.snapshot_id == SNAP))
        s.execute(delete(SnapshotViewUnit).where(SnapshotViewUnit.snapshot_id == SNAP))
    monkeypatch.setattr(sv, "CHUNK_BYTES", 20_000)  # 묶음 여럿
    real = sv._row_dicts
    calls = {"n": 0}

    def dying(sid: int, rows: Any) -> Any:  # 세 번째 묶음 트랜잭션 안에서 죽는다(앞 두 묶음·그 표식은 커밋됨)
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("worker killed")
        return real(sid, rows)

    monkeypatch.setattr(sv, "_row_dicts", dying)
    first = sv.backfill(get_engine())
    monkeypatch.setattr(sv, "_row_dicts", real)
    assert [f["snapshot_id"] for f in first["failed"]] == [SNAP]  # m11: 리비전마다 따로 실패
    before = _row_bytes(SNAP)
    assert before  # 일부는 썼다
    with get_session() as s:
        assert sv.pending_count(s) >= 1
        sc2 = s.scalars(select(Scenario.id).order_by(Scenario.id)).all()[1]
    g = client.get(f"/api/snapshots/{SNAP}/dashboard", params={"scenario": sc2}, headers=READ)
    assert g.status_code == 503 and g.json()["code"] == "materialize_pending" and g.headers.get("retry-after")
    r = client.post(
        "/api/reports", json={"snapshot_id": SNAP, "format": "html", "scenario_id": sc2}, headers=WRITE
    )
    assert r.status_code == 503 and r.json()["code"] == "materialize_pending", r.text

    again = sv.backfill(get_engine())
    assert again["snapshots"] == [SNAP] and not again["failed"]
    after = _row_bytes(SNAP)
    assert all(after[k] == v for k, v in before.items())  # 있던 행은 그대로(발행 순간 바이트)
    with get_session() as s:
        assert sv.pending_count(s) == 0
        units = list(s.scalars(select(SnapshotViewUnit).where(SnapshotViewUnit.snapshot_id == SNAP)))
    assert units and all(u.done for u in units)
    for sk in _scenario_keys():
        for u in (
            f"/api/snapshots/{SNAP}/dashboard?scenario={sk}",
            f"/api/complexes/{CX}?snapshot={SNAP}&scenario={sk}",
        ):
            assert client.get(u, headers=READ).status_code == 200, u
    assert sv.backfill(get_engine())["snapshots"] == []  # 멱등


def test_m2_deleted_rows_of_done_unit_is_503_and_backfill_restores(client: TestClient) -> None:
    """완료 표식이 있어도 실제 행 수가 표식보다 적으면 미완(503) — backfill 이 빠진 키만 다시 만든다."""
    import app.snapshot_view as sv

    with get_session() as s:
        s.execute(
            delete(SnapshotView).where(
                SnapshotView.snapshot_id == SNAP, SnapshotView.kind == "complex", SnapshotView.key == str(CX)
            )
        )
    r = client.get(f"/api/complexes/{CX}?snapshot={SNAP}", headers=READ)
    assert r.status_code == 503 and r.json()["code"] == "materialize_pending", r.text
    res = sv.backfill(get_engine())
    assert res["snapshots"] == [SNAP]
    assert client.get(f"/api/complexes/{CX}?snapshot={SNAP}", headers=READ).status_code == 200


def test_m2_scenario_created_after_publish_is_404_not_503(client: TestClient) -> None:
    """그 kind 의 다른 시나리오 단위는 완료인데 이 시나리오 표식이 없다 = 발행 뒤 만든 시나리오 → 404(미완 503 아님)."""
    body = {
        "name": "R3g 발행 뒤",
        "params": {"equity_won": 250000000, "loan_limit_won": 600000000, "holding_years": 4},
        "weights": {"p10": 0.3, "rerank": 0.15, "gap": 0.2, "benchmark": 0.1, "supply": 0.1, "move_in": 0.15},
        "requirements": None,
        "policy": None,
    }
    sc = client.post("/api/scenarios", json=body, headers=WRITE).json()["id"]
    r = client.get(f"/api/snapshots/{SNAP}/dashboard?scenario={sc}", headers=READ)
    assert r.status_code == 404, r.text


def test_m11_backfill_isolates_failing_revision(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.snapshot_view as sv

    with get_session() as s:
        for sid in (11, SNAP):
            s.execute(delete(SnapshotView).where(SnapshotView.snapshot_id == sid))
            s.execute(delete(SnapshotViewUnit).where(SnapshotViewUnit.snapshot_id == sid))
    real = sv.compute

    def boom(session: Any, snap: Any, **kw: Any) -> Any:
        if snap.id == 11:
            raise ValueError("이 리비전만 실패")
        return real(session, snap, **kw)

    monkeypatch.setattr(sv, "compute", boom)
    res = sv.backfill(get_engine())
    assert res["snapshots"] == [SNAP] and [f["snapshot_id"] for f in res["failed"]] == [11]
    assert client.get(f"/api/snapshots/{SNAP}/dashboard", headers=READ).status_code == 200
    assert client.get("/api/snapshots/11/dashboard", headers=READ).status_code == 503


# ====================================================================== m8


@pytest.mark.parametrize(
    ("base", "body"),
    [
        ({"a": 1.0, "b": 0}, {"a": 1, "b": 0}),
        ({"x": True}, {"x": 1}),
        ({"x": 0}, {"x": False}),
        ({"o": {"p": 1, "q": 2}}, {"o": {"q": 2, "p": 1}}),
        ({"l": [1, 2.0]}, {"l": [1.0, 2]}),
        ({"z": 0.0}, {"z": -0.0}),
        ({"d": {"x": [{"k": 1}]}}, {"d": {"x": [{"k": True}]}}),
    ],
)
def test_m8_patch_rebuilds_same_bytes(base: dict[str, Any], body: dict[str, Any]) -> None:
    import app.snapshot_view as sv

    patch = sv._patch(base, body)
    rebuilt = body if patch is None else sv._apply(base, {"$p": patch})  # None = 본문 통째 저장
    assert sv._dumps(rebuilt) == sv._dumps(body)
    assert sv._patch({"a": 1, "b": 2}, {"a": 1, "b": 3}) == {"b": {"$v": 3}}  # 정상 patch 는 그대로


# ====================================================================== M3 · m14 (D15-4)


def _event(s: Any, cid: int, at: str, sid: int = SNAP) -> None:
    s.add(
        ChangeEvent(
            snapshot_id=sid, entity="complex", entity_id=cid, field="move_in_ym", old_text="a", new_text="b",
            detected_at=at, severity="critical", triggers_rejudge=True, complex_id=cid,
        )
    )  # fmt: skip


def _job(
    s: Any,
    status: str,
    sid: int,
    ids: list[int] | None,
    at: str,
    *,
    scenario_id: int | None = None,
    wrote: int | None = None,
) -> None:
    s.add(
        JobRun(
            job_name="rejudge", kind="rejudge", status=status,
            payload={"snapshot_id": sid, "scenario_id": scenario_id, "complex_ids": ids, "reason": "r7"},
            scheduled_at=at, finished_at=at, stats={"snapshot_id": wrote} if wrote is not None else {},
        )
    )  # fmt: skip


def _revision(s: Any) -> Snapshot:
    snap = s.get(Snapshot, SNAP)
    r = Snapshot(
        region_id=1, asof_date=snap.asof_date, status="ready", degraded=False, created_at="2099-01-01T10:00:00+09:00",
        revision=int(snap.revision or 1) + 1, revision_of=SNAP, revision_reason="사람 확인",
    )  # fmt: skip
    s.add(r)
    s.flush()
    return r


def test_m3_success_on_unpublished_revision_does_not_mask_prev(client: TestClient) -> None:
    """R3 7차 M3(c/test_c_carry): 이벤트 뒤 단지 A 를 판정한 rejudge 가 **다른(미발행) 리비전 R** 에서 성공 — prev(SNAP) 의 A 점수는
    이벤트 전 값이다 → 이월하지 않고 재판정(예전: 성공으로 쳐 옛 점수를 새 기준일로 발행)."""
    from app.scheduler.handlers import changed_after_runs

    with get_session() as s:
        r = _revision(s)
        _event(s, CX, "2099-01-01T10:00:00+09:00", sid=r.id)
        _job(s, "done", r.id, [CX], "2099-01-01T10:10:00+09:00", wrote=r.id)
        s.flush()
        assert CX in changed_after_runs(s, s.get(Snapshot, SNAP))
        # payload 가 발행 리비전 SNAP 이어도 판정을 쓴 리비전(stats.snapshot_id)이 R 이면 같다
        _job(s, "done", SNAP, [CX], "2099-01-01T10:20:00+09:00", wrote=r.id)
        s.flush()
        assert CX in changed_after_runs(s, s.get(Snapshot, SNAP))
        # prev 자신에 쓴 판정은 센다
        _job(s, "done", SNAP, [CX], "2099-01-01T10:30:00+09:00", wrote=SNAP)
        s.flush()
        assert CX not in changed_after_runs(s, s.get(Snapshot, SNAP))
        s.rollback()


def test_m14_scenario_rejudge_counts_only_that_scenario(client: TestClient) -> None:
    """R3 7차 minor 14: 시나리오 지정 rejudge(다른 시나리오 실행은 prev 복사) 성공이 기본 시나리오까지 '판정됨'이 아니다."""
    from app.scheduler.handlers import changed_after_runs

    with get_session() as s:
        scs = sorted(
            int(x)
            for x in s.scalars(select(ScoreRun.scenario_id).where(ScoreRun.snapshot_id == SNAP)).unique()
        )
        _event(s, CX, "2099-01-01T10:00:00+09:00")
        _job(s, "done", SNAP, None, "2099-01-01T10:10:00+09:00", scenario_id=scs[-1], wrote=SNAP)
        s.flush()
        assert CX in changed_after_runs(s, s.get(Snapshot, SNAP))
        for sc in scs[:-1]:
            _job(s, "done", SNAP, None, "2099-01-01T10:20:00+09:00", scenario_id=sc, wrote=SNAP)
        s.flush()
        assert CX not in changed_after_runs(s, s.get(Snapshot, SNAP))  # 모든 시나리오가 이벤트 뒤 판정됨
        s.rollback()


def test_m3_daily_does_not_carry_stale_score(client: TestClient) -> None:
    """끝까지(c/test_e2e_daily_carries_stale_A): 다음 날 수집에 변경이 없어도 A 는 재판정 잡으로(옛 점수 복사·발행 아님)."""
    from app.core.db import get_sessionmaker
    from app.scheduler.context import SchedulerContext
    from app.scheduler.handlers import _after_daily

    with get_session() as s:
        r = _revision(s)
        _event(s, CX, "2099-01-01T10:00:00+09:00", sid=r.id)
        _job(s, "done", r.id, [CX], "2099-01-01T10:10:00+09:00", wrote=r.id)
        nxt = Snapshot(region_id=1, asof_date="2099-01-02", status="building", degraded=False,
                       created_at="2099-01-02T06:00:00+09:00", revision=1)  # fmt: skip
        s.add(nxt)
        s.flush()
        nid = nxt.id
    ctx = SchedulerContext(session_factory=get_sessionmaker(), adapter_factory=lambda: None, collectors={})  # type: ignore[arg-type,return-value]
    out = _after_daily(ctx, nid, [], [])
    assert out.get("rejudge_job_id"), out
    with get_session() as s:
        job = s.get(JobRun, out["rejudge_job_id"])
        assert job is not None and CX in (job.payload or {}).get("complex_ids", [])
        assert s.get(Snapshot, nid).status == "building"  # type: ignore[union-attr]


# ====================================================================== M5 · m1 · m16 (D15-6)


def _cat(name: str) -> int:
    with get_session() as s:
        c = Catalyst(region_id=1, name=name, kind="교통", stage="계획", location_confirmed=False)
        s.add(c)
        s.flush()
        return int(c.id)


def _link(client: TestClient, cid: int) -> Any:
    r = client.patch(
        f"/api/catalysts/{cid}", json={"location_confirmed": True, "complex_ids": [CX]}, headers=WRITE
    )
    assert r.status_code == 202, r.text
    return r.json()


def _drain() -> list[tuple[int, str, dict[str, Any]]]:
    out = []
    for _ in range(10):
        with get_session() as s:
            ids = list(s.scalars(select(JobRun.id).where(JobRun.status == "queued").order_by(JobRun.id)))
        if not ids:
            break
        for jid in ids:
            st, stats = run_job(jid)
            out.append((jid, st, stats))
    return out


def _linked_in_latest(client: TestClient, cid: int) -> bool:
    latest = client.get("/api/regions/1", headers=READ).json()["latest_snapshot"]["id"]
    d = client.get(f"/api/complexes/{CX}", params={"snapshot": latest}, headers=READ).json()
    return any(c["id"] == cid and c.get("linked") for c in d.get("catalysts") or [])


def test_m5_patch_during_publish_compute_gets_follow_up_job(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R3 7차 M5(c/test_catalyst_patch_during_publish_compute_is_lost): 발행 계산 중에 들어온 호재 PATCH — 예전 202 job_id None,
    queued 0, 발행에서 빠짐. 지금: 후속 발행 잡(job_id) → 그 잡이 새 리비전을 발행해 두 연결 모두 최신 발행 리비전에."""
    import app.snapshot_view as sv

    c1, c2 = _cat("R3g 역1"), _cat("R3g 역2")
    j1 = _link(client, c1)["job_id"]
    real = sv.compute
    box: dict[str, Any] = {}

    def hooked(*a: Any, **k: Any) -> Any:
        if "r2" not in box:  # worker 가 계산(읽기 트랜잭션) 중일 때 두 번째 PATCH 커밋
            out = real(*a, **k)
            box["r2"] = _link(client, c2)
            return out
        return real(*a, **k)

    monkeypatch.setattr(sv, "compute", hooked)
    st1, stats1 = run_job(j1)
    monkeypatch.setattr(sv, "compute", real)
    assert st1 == "done" and stats1["published"], stats1
    follow = box["r2"]["job_id"]
    assert follow is not None and box["r2"]["job"]["payload"].get("follow_up") is True
    st2, stats2 = run_job(follow)
    assert st2 == "done" and stats2["published"] and stats2["snapshot_id"] > stats1["snapshot_id"], stats2
    assert _linked_in_latest(client, c1) and _linked_in_latest(client, c2)


def test_m5_follow_up_seen_by_compute_is_closed_as_included(client: TestClient) -> None:
    """PATCH 가 발행 계산 **전에** 커밋됐으면 그 계산이 쓰기를 읽었다 — 전환 트랜잭션이 후속 잡을 done(포함됨)으로 닫는다."""
    c1, c2 = _cat("R3g 역3"), _cat("R3g 역4")
    j1 = _link(client, c1)["job_id"]
    second = _link(client, c2)  # j1 의 리비전이 아직 발행 전 → 후속 잡
    follow = second["job_id"]
    assert follow is not None and second["job"]["payload"].get("follow_up") is True
    st1, stats1 = run_job(j1)
    assert st1 == "done" and follow in stats1["followups_included"], stats1
    with get_session() as s:
        job = s.get(JobRun, follow)
        assert job is not None and job.status == "done"
        assert (job.stats or {}).get("included_in_snapshot_id") == stats1["snapshot_id"]
    assert _linked_in_latest(client, c1) and _linked_in_latest(client, c2)


def test_m1_two_publishes_of_same_revision_single_flight(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R3 7차 minor 1(c/test_two_publish…): 같은 리비전 발행 둘이 겹치면 — 예전: 늦은 쪽 정리 DELETE 가 먼저 끝난 쪽 저장본을
    지워 published + 0행(GET 500). 지금: 임대(single-flight) — 겹친 쪽은 busy 로 아무것도 지우지 않는다."""
    import app.snapshot_view as sv

    c1 = _cat("R3g 역5")
    out = _link(client, c1)
    j1, rev = out["job_id"], int(out["job"]["payload"]["snapshot_id"])
    real = sv.compute
    box: dict[str, Any] = {}

    def hooked(*a: Any, **k: Any) -> Any:
        res = real(*a, **k)
        if "b" not in box:
            box["b"] = sv.publish_revision(
                get_engine(), rev, now="2026-10-10T10:00:00+09:00", holder="job:999999"
            )
        return res

    monkeypatch.setattr(sv, "compute", hooked)
    st, stats = run_job(j1)
    monkeypatch.setattr(sv, "compute", real)
    assert box["b"].busy and not box["b"].published
    assert st == "done" and stats["published"], stats
    with get_session() as s:
        assert s.get(Snapshot, rev).status == "published"  # type: ignore[union-attr]
        assert s.scalar(select(func.count()).select_from(SnapshotView).where(SnapshotView.snapshot_id == rev))
        assert s.get(Snapshot, rev).publish_lease is None  # type: ignore[union-attr]
    assert client.get(f"/api/snapshots/{rev}/dashboard", headers=READ).status_code == 200


def test_m1_busy_job_fails_with_publish_in_progress(client: TestClient) -> None:
    from app.core.db import get_engine as eng
    from app.snapshot_view import acquire_lease, release_lease

    out = _link(client, _cat("R3g 역6"))
    j1, rev = out["job_id"], int(out["job"]["payload"]["snapshot_id"])
    lease = acquire_lease(eng(), rev, "pid:other")
    assert lease is not None
    st, stats = run_job(j1)
    # D16-3(R3h): busy 는 실패가 아니라 지연 재큐잉 — queued + requeue_reason 'publish_in_progress: …'(error_text 없음)
    assert st == "queued", stats
    with get_session() as s:
        row = s.get(JobRun, j1)
        assert row is not None and row.error_text is None
        assert "publish_in_progress" in str((row.stats or {}).get("requeue_reason")), row.stats
        assert (row.stats or {}).get("publish_in_progress") == "pid:other", row.stats
        assert s.get(Snapshot, rev).status == "ready"  # type: ignore[union-attr]
    release_lease(eng(), rev, lease)


def test_m1_purge_never_touches_published_revision(client: TestClient) -> None:
    from app.snapshot_view import _purge_unpublished

    n = len(_row_bytes(SNAP))
    with get_engine().begin() as conn:
        _purge_unpublished(conn, SNAP)
    assert len(_row_bytes(SNAP)) == n


# R3 8차 m21: 여기 있던 ``test_flip_transaction_takes_write_lock_first`` 는 수정 전 코드(쓰기 잠금 UPDATE 없음)에서도 통과해
# 결함을 잡지 못했다 — ``tests/api/test_r3h_core6.py::test_m21_flip_takes_write_lock_before_reading`` 으로 바꿨다(잠금을 빼면 실패).


def test_m16_post_catalyst_returns_job_id(client: TestClient, fake_catalyst: list[dict[str, Any]]) -> None:  # noqa: F811
    body = {"region_id": 1, "url": "https://news.example.org/r3g/1", "title": "역 신설", "excerpt": None}
    r = client.post("/api/catalysts", json=body, headers=WRITE)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["job"] is not None and out["job_id"] == out["job"]["id"]
    again = client.post("/api/catalysts", json=body, headers=WRITE).json()
    assert again["job"] is None and again["job_id"] is None


def test_m13_carry_publish_failure_leaves_retry_job(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R3 7차 minor 13: daily 이월 발행이 예외로 실패하면 재시도 snapshot.publish 잡을 남긴다(예전: 잡만 실패, 재시도 없음)."""
    from app.core.db import get_sessionmaker
    from app.scheduler import snapshots
    from app.scheduler.context import SchedulerContext
    from app.scheduler.handlers import _after_daily

    with get_session() as s:
        nxt = Snapshot(region_id=1, asof_date="2099-02-01", status="building", degraded=False,
                       created_at="2099-02-01T06:00:00+09:00", revision=1)  # fmt: skip
        s.add(nxt)
        s.flush()
        nid = nxt.id

    def boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("disk full")

    monkeypatch.setattr(snapshots, "publish_with_stats", boom)
    ctx = SchedulerContext(session_factory=get_sessionmaker(), adapter_factory=lambda: None, collectors={})  # type: ignore[arg-type,return-value]
    out = _after_daily(ctx, nid, [], [])
    assert (
        out["published"] is False and out["publish_error"] == "RuntimeError" and out["publish_retry_job_id"]
    ), out
    with get_session() as s:
        job = s.get(JobRun, out["publish_retry_job_id"])
        assert job is not None and job.status == "queued" and job.payload == {"snapshot_id": nid}
        assert s.get(Snapshot, nid).status == "ready"  # type: ignore[union-attr]
    monkeypatch.undo()
    st, stats = run_job(out["publish_retry_job_id"])
    assert st == "done" and stats["published"], stats


# ====================================================================== m6 · m10 · m4


def test_m6_provenance_without_snapshot_id_is_503_while_latest_pending(client: TestClient) -> None:
    """R3 7차 minor 6: snapshot_id 생략 + 그 지역 최신 발행 리비전 서랍 저장본 미완 → 실시간 200 이 아니라 503."""
    body = client.get(f"/api/complexes/{CX}?snapshot={SNAP}", headers=READ).json()
    acc: set[str] = set()
    _walk(body, acc)
    pid = sorted(p for p in acc if p.startswith("fp_"))[0]
    assert client.get(f"/api/provenance/{pid}", headers=READ).status_code == 200
    with get_session() as s:
        s.execute(
            delete(SnapshotView).where(SnapshotView.snapshot_id == SNAP, SnapshotView.kind == "provenance")
        )
        s.execute(
            delete(SnapshotViewUnit).where(
                SnapshotViewUnit.snapshot_id == SNAP, SnapshotViewUnit.kind == "provenance"
            )
        )
    r = client.get(f"/api/provenance/{pid}", headers=READ)
    assert r.status_code == 503 and r.json()["code"] == "materialize_pending", r.text


def test_m10_post_reports_checks_default_and_compare_inputs(client: TestClient) -> None:
    """R3 7차 minor 10: 기본 시나리오(생략)·비교 스냅샷 저장본 미완이면 202 뒤 잡 실패가 아니라 POST 에서 503."""
    with get_session() as s:
        base = s.scalars(select(Scenario.id).where(Scenario.code == "base")).one()
        s.execute(
            delete(SnapshotViewUnit).where(
                SnapshotViewUnit.snapshot_id == SNAP,
                SnapshotViewUnit.kind == "report_diff",
                SnapshotViewUnit.scenario == str(base),
            )
        )
    r = client.post("/api/reports", json={"snapshot_id": SNAP, "format": "html"}, headers=WRITE)
    assert r.status_code == 503 and r.json()["code"] == "materialize_pending", r.text
    rev = publish_revision(1, "R3g m10")
    with get_session() as s:
        s.execute(
            delete(SnapshotViewUnit).where(
                SnapshotViewUnit.snapshot_id == 11, SnapshotViewUnit.kind == "report"
            )
        )
    r = client.post(
        "/api/reports", json={"snapshot_id": rev, "format": "html", "compare_snapshot_id": 11}, headers=WRITE
    )
    assert r.status_code == 503 and r.json()["code"] == "materialize_pending", r.text
    r = client.post(
        "/api/reports",
        json={"snapshot_id": rev, "format": "html", "compare_snapshot_id": SNAP},
        headers=WRITE,
    )
    # R3h(D16-2·m3·m12): 비교 리비전(12)의 report_diff 는 행만 있고 표식이 없다 = 미완 → 503. backfill 이 표식을 쓰면 202
    assert r.status_code == 503 and r.json()["code"] == "materialize_pending", r.text
    from app.core.settings import get_settings
    from app.snapshot_view import backfill

    assert not backfill(get_engine(), settings=get_settings())["failed"]
    r = client.post(
        "/api/reports",
        json={"snapshot_id": rev, "format": "html", "compare_snapshot_id": SNAP},
        headers=WRITE,
    )
    assert r.status_code == 202, r.text


def test_m4_row_human_check_migration_events_attach_to_writable_revision(client: TestClient) -> None:
    """R3 7차 minor 4 · D13-5(b/test_m14_events): 행 단위 사람 확인 → 의미 묶음 이전이 만든 change_event 는 snapshot_id=None
    이 아니라 쓰기 가능 리비전에 붙고, 재판정 이벤트면 그 단지 rejudge 가 등록된다."""
    from app.api.demotion import migrate_row_human_checks
    from app.models import ComplexType, FieldProvenance

    from ._support import as_live
    from .test_r3d_core2 import human_check, store_notice
    from .test_r3e_human_semantic import _basis, _set_type_row_price

    x, y = 700_000_000, 690_000_000
    as_live()
    code = _set_type_row_price(x)
    store_notice(CX, "2026990110", {"effective_from": "2026-09-01", "notice_kind": "본청약",
                                    f"price_by_type.{code}.max_price_won": x}, observed_on="2026-09-01")  # fmt: skip
    human_check(client, "max_price_won", str(y), day="2026-10-09")
    t = _basis()
    with (
        get_session() as s
    ):  # 계약 .9 모양으로 되돌린다: 사람 확인 출처는 타입 행 하나에만, 사실 값은 공고 값
        for fp in s.scalars(
            select(FieldProvenance).where(
                FieldProvenance.entity == "complex_type",
                FieldProvenance.entity_id == t.id,
                FieldProvenance.field == "max_price_won",
            )
        ):
            if fp.raw_document_id is None:
                s.delete(fp)
            else:
                fp.chosen = fp.value_norm == str(x)
        row = s.get(ComplexType, t.id)
        assert row is not None
        row.max_price_won = x
    with get_session() as s:
        before = {int(i) for i in s.scalars(select(ChangeEvent.id))}
    with get_session() as s:
        migrate_row_human_checks(s)
    with get_session() as s:
        new = [e for e in s.scalars(select(ChangeEvent)) if e.id not in before]
        assert all(e.snapshot_id is not None for e in new), [(e.field, e.snapshot_id) for e in new]
        crit = [e for e in new if e.triggers_rejudge]
        if crit:
            jobs = list(
                s.scalars(select(JobRun).where(JobRun.job_name == "rejudge", JobRun.status == "queued"))
            )
            assert any(
                set((j.payload or {}).get("change_event_ids") or []) & {e.id for e in crit} for j in jobs
            )


def test_r3g_links_survive(client: TestClient) -> None:
    """후속 발행 뒤에도 연결 행은 그대로(파생 행 복사 경로 회귀 감시)."""
    cid = _cat("R3g 역8")
    _link(client, cid)
    _drain()
    with get_session() as s:
        assert s.scalars(select(CatalystLink).where(CatalystLink.catalyst_id == cid)).first() is not None


# ====================================================================== 계약 .12 추가(FE6 요청): publish_job_id


def test_publish_job_id_on_publish_and_included_follow_up(client: TestClient) -> None:
    """snapshot.publish 잡 stats.publish_job_id = 그 잡, 그 발행이 포함한 후속 잡의 stats.publish_job_id = 발행한 잡."""
    j1 = _link(client, _cat("R3g 역9"))["job_id"]
    follow = _link(client, _cat("R3g 역10"))["job_id"]
    st, stats = run_job(j1)
    assert st == "done" and stats["publish_job_id"] == j1, stats
    with get_session() as s:
        job = s.get(JobRun, follow)
        assert job is not None and (job.stats or {}).get("publish_job_id") == j1


def test_publish_job_id_on_rejudge_and_inline_paths(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """rejudge 잡 stats.publish_job_id = 등록한 snapshot.publish 잡, daily 이월(그 자리 발행) = 그 잡 자신."""
    from types import SimpleNamespace

    import app.scheduler.pipeline as pl
    from app.core.db import get_sessionmaker
    from app.scheduler.context import SchedulerContext
    from app.scheduler.handlers import _after_daily

    fake = SimpleNamespace(snapshot_id=SNAP, degraded=False, stats=lambda: {"snapshot_id": SNAP})
    monkeypatch.setattr(pl, "run_pipeline", lambda *a, **k: fake)
    with get_session() as s:
        rj = JobRun(
            job_name="rejudge", kind="rejudge", status="queued", scheduled_at="2026-10-11T10:00:00+09:00",
            payload={"snapshot_id": SNAP, "scenario_id": None, "complex_ids": [], "reason": "r3g"}, stats={},
        )  # fmt: skip
        s.add(rj)
        s.flush()
        rid = rj.id
    st, stats = run_job(rid)
    assert st == "done" and stats["publish_job_id"], stats
    with get_session() as s:
        pub = s.get(JobRun, stats["publish_job_id"])
        assert pub is not None and pub.job_name == "snapshot.publish" and pub.payload == {"snapshot_id": SNAP}
    monkeypatch.undo()

    with get_session() as s:
        nxt = Snapshot(region_id=1, asof_date="2099-03-01", status="building", degraded=False,
                       created_at="2099-03-01T06:00:00+09:00", revision=1)  # fmt: skip
        s.add(nxt)
        s.flush()
        nid = nxt.id
    ctx = SchedulerContext(session_factory=get_sessionmaker(), adapter_factory=lambda: None, collectors={})  # type: ignore[arg-type,return-value]
    out = _after_daily(ctx, nid, [], [], job_id=4242)
    assert out["published"] is True and out["publish_job_id"] == 4242, out

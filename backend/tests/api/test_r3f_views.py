"""R3f CORE4 — R3 6차 N-M2(D14-4) · N-M3(D14-5) · D14-8 · D14-9 · m2 · m3 · m19 (계약 2026-10-09.11): 저장본·발행 잡.

| 리뷰 | 이 파일 |
| --- | --- |
| N-M2 저장본에 계약 버전 없음·sha256 미검증(본문 조작 시 200) | ``test_nm2_*`` |
| N-M3 발행이 요청 안에서 돎(호재 PATCH) | ``test_nm3_*`` |
| D14-8 저장본 출처 누락 라벨 + 잡 통계 | ``test_d14_8_*`` |
| D14-9 · m2 0010 앱 import · backfill · 503 | ``test_d14_9_*`` · ``test_m2_*`` |
| m3 devseed reset(snapshot_state 잔존·alembic 0009) | ``test_m3_*`` |
| m19 bootstrap 저장본 실패 → 지역 failed | ``test_m19_*`` |
"""

# ruff: noqa: E501

from __future__ import annotations

import zlib
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update

from app.core.db import get_session
from app.models import Catalyst, JobRun, Snapshot, SnapshotView

from ._support import READ, WRITE, publish_revision, run_job
from .test_r3b_g3 import CX, SNAP

REPO = Path(__file__).resolve().parents[3]


# ====================================================================== N-M2 · D14-4


def test_nm2_tampered_body_is_500_stored_view_mismatch(client: TestClient) -> None:
    """본문을 바꾸면(sha256 그대로) 읽을 때 검증해 500 stored_view_mismatch — 예전: 조작된 본문 200."""
    import json

    url = f"/api/snapshots/{SNAP}/dashboard"
    assert client.get(url, headers=READ).status_code == 200
    with get_session() as s:
        row = s.scalars(
            select(SnapshotView).where(
                SnapshotView.snapshot_id == SNAP,
                SnapshotView.kind == "dashboard",
                SnapshotView.scenario == "1",
            )
        ).one()
        body = json.loads(zlib.decompress(row.body))
        body["kpis"]["judged_count"] = {
            "v": 999,
            "label": "확인됨",
            "prov": "st_1",
            "checked_at": "2026-10-08",
        }
        row.body = zlib.compress(json.dumps(body, ensure_ascii=False).encode("utf-8"))
    r = client.get(url, headers=READ)
    assert r.status_code == 500 and r.json()["code"] == "stored_view_mismatch"


def test_nm2_other_contract_version_is_500(client: TestClient) -> None:
    with get_session() as s:
        s.execute(
            update(SnapshotView)
            .where(SnapshotView.snapshot_id == SNAP, SnapshotView.kind == "complexes")
            .values(contract_version="2026-10-09.10")
        )
    r = client.get(f"/api/snapshots/{SNAP}/complexes", headers=READ)
    assert r.status_code == 500 and r.json()["code"] == "stored_view_mismatch"
    assert client.get(f"/api/snapshots/{SNAP}/dashboard", headers=READ).status_code == 200


def test_nm2_rows_carry_contract_version_and_patch_rows_rebuild_same_bytes(client: TestClient) -> None:
    """모든 저장본 행 = 현재 계약 버전. 시나리오 사이 같은 부분 행(기본 시나리오 + 바뀐 부분)도 실시간 계산과 같은 응답."""
    from app.core.protocols import CONTRACT_VERSION

    rev = publish_revision(1, "N-M2 버전")
    with get_session() as s:
        versions = set(
            s.scalars(select(SnapshotView.contract_version).where(SnapshotView.snapshot_id == rev))
        )
    assert versions == {CONTRACT_VERSION}
    stored = {
        sc: client.get(f"/api/complexes/{CX}?snapshot={rev}&scenario={sc}", headers=READ).json()
        for sc in ("base", "A", "D")
    }
    with get_session() as s:  # 같은 리비전을 발행 전으로 돌려 실시간 계산과 비교
        s.execute(update(Snapshot).where(Snapshot.id == rev).values(status="ready", published_at=None))
    for sc, body in stored.items():
        live = client.get(f"/api/complexes/{CX}?snapshot={rev}&scenario={sc}", headers=READ)
        assert live.status_code == 200
        live_body = live.json()
        assert live_body["header"] == body["header"] and live_body.get("score") == body.get("score"), sc


# ====================================================================== N-M3 · D14-5


def _catalyst() -> int:
    with get_session() as s:
        cat = Catalyst(region_id=1, name="N-M3 역", kind="교통", stage="계획", location_confirmed=False)
        s.add(cat)
        s.flush()
        return int(cat.id)


def test_nm3_catalyst_patch_is_202_and_publishes_only_in_worker(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """호재 연결 PATCH = 202 + job_id(snapshot.publish). 요청 안에서 저장본을 만들지 않는다(계산 함수를 막아도 202) — 잡이
    끝날 때까지 이전 발행 리비전이 기본, 잡이 끝나면 새 리비전이 published."""
    import app.snapshot_view as sv

    cid = _catalyst()

    def boom(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("API 요청 안에서 저장본을 만들었다(D14-5)")

    monkeypatch.setattr(sv, "compute", boom)
    monkeypatch.setattr(sv, "publish_revision", boom)
    r = client.patch(
        f"/api/catalysts/{cid}", json={"location_confirmed": True, "complex_ids": [CX]}, headers=WRITE
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["job_id"] == body["job"]["id"] and body["job"]["job_name"] == "snapshot.publish"
    rev = int(body["job"]["payload"]["snapshot_id"])
    with get_session() as s:
        assert s.get(Snapshot, rev).status == "building"  # type: ignore[union-attr]
    region = client.get("/api/regions/1", headers=READ).json()
    assert region["latest_snapshot"]["id"] == SNAP  # 잡 전 = 이전 발행 리비전
    monkeypatch.undo()
    status, stats = run_job(body["job_id"])
    assert status == "done" and stats["published"] is True, stats
    for k in ("rows", "bytes", "missing_provenance", "write_max_lock_s", "total_s", "carry_forward"):
        assert k in stats, k
    assert client.get("/api/regions/1", headers=READ).json()["latest_snapshot"]["id"] == rev


def test_nm3_publishing_writes_are_202_and_never_materialize_in_request(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """발행을 부르는 쓰기 API(생활권 편집 PUT·지역 선택 PATCH = 202 + job_id, 사람 확인 POST = 201 + job_id)는 요청 안에서
    저장본을 만들지 않는다."""
    import app.snapshot_view as sv

    def boom(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("API 요청 안에서 저장본을 만들었다(D14-5)")

    monkeypatch.setattr(sv, "compute", boom)
    monkeypatch.setattr(sv, "publish_revision", boom)
    region = client.get("/api/regions/1", headers=READ).json()
    areas = [
        {"id": a["id"], "name": a["name"] + "*", "legal_dong_codes": a["legal_dong_codes"]}
        for a in region["living_areas"]
    ]
    r = client.put("/api/regions/1/living-areas", json={"living_areas": areas}, headers=WRITE)
    assert r.status_code == 202 and r.json()["job_id"], r.text
    from .test_r3d_core2 import human_check

    hc = human_check(client, "move_in_ym", "2029-09", cx=3)
    assert hc["job_id"] == hc["rejudge_job_id"] and hc["job_id"]


def test_nm3_flip_is_last_and_short(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """저장본은 리비전이 ready 인 동안 나눠 쓰고(그동안 이전 발행 리비전이 기본), published 전환은 마지막 짧은 트랜잭션."""
    import app.snapshot_view as sv
    from app.scheduler.snapshots import republish

    seen: list[str] = []
    real = sv.write_rows

    def spy(engine: Any, sid: int, rows: Any) -> Any:
        with get_session() as s:
            seen.append(s.get(Snapshot, sid).status)  # type: ignore[union-attr]
            seen.append(str(s.scalar(select(func.count()).select_from(Snapshot).where(Snapshot.id == sid))))
        return real(engine, sid, rows)

    monkeypatch.setattr(sv, "write_rows", spy)
    with get_session() as s:
        job = republish(s, 1, reason="N-M3 전환", created_at="2026-10-09T08:00:00+09:00")
        assert job is not None
        jid = job.id
    status, stats = run_job(jid)
    assert status == "done", stats
    assert seen[0] == "ready"
    assert stats["write_chunks"] >= 1 and stats["flip_s"] < 1.0


# ====================================================================== D14-8


def test_d14_8_stored_missing_provenance_is_label_and_counted(client: TestClient) -> None:
    """출처 누락(T13): 발행 저장본은 ENV(dev)와 무관하게 '확인 불가(출처 누락)' 라벨로 저장되고(발행 뒤 500 불가) 잡 통계에
    건수가 남는다. 발행 전 리비전 실시간 GET 은 dev 500 그대로."""
    from app.models import FieldProvenance
    from app.scheduler.snapshots import republish

    with get_session() as s:
        s.execute(
            delete(FieldProvenance).where(
                FieldProvenance.entity == "complex",
                FieldProvenance.entity_id == CX,
                FieldProvenance.field == "units_total",
            )
        )
        job = republish(s, 1, reason="D14-8", created_at="2026-10-09T08:00:00+09:00")
        assert job is not None
        jid, rev = job.id, int((job.payload or {})["snapshot_id"])
    status, stats = run_job(jid)
    assert status == "done" and stats["published"] is True
    assert stats["missing_provenance"] >= 1
    r = client.get(f"/api/complexes/{CX}?snapshot={rev}", headers=READ)
    assert r.status_code == 200
    hh = r.json()["header"]["units_total"]
    assert hh["label"] == "확인 불가" and hh["reason"] == "출처 누락"
    from .test_r3d_core2 import _revision_of

    live = _revision_of(rev, publish=False)
    assert client.get(f"/api/complexes/{CX}?snapshot={live}", headers=READ).status_code == 500


# ====================================================================== D14-9 · m2


def test_m2_migrations_do_not_import_app_code() -> None:
    """R3 6차 m2·D14-9: 마이그레이션은 앱 코드(최신 ORM)를 import 하지 않는다 — 이후 열이 늘어도 0009→head 가 돈다."""
    versions = REPO / "contracts" / "migrations" / "versions"
    for name in ("0010_r3e.py", "0011_r3f.py"):
        text = (versions / name).read_text(encoding="utf-8")
        assert "from app" not in text and "import app" not in text, name


def test_d14_9_published_without_views_is_503_until_backfill(client: TestClient) -> None:
    """저장본이 아직 없는 발행 리비전 GET = 503 materialize_pending(실시간 폴백 없음). backfill 은 멱등으로 채운다."""
    from app.snapshot_view import KINDS, backfill

    with get_session() as s:
        s.execute(delete(SnapshotView).where(SnapshotView.snapshot_id == SNAP))
    for u in (
        f"/api/snapshots/{SNAP}/dashboard",
        f"/api/complexes/{CX}?snapshot={SNAP}",
        f"/api/snapshots/{SNAP}/claims",
    ):
        r = client.get(u, headers=READ)
        assert r.status_code == 503 and r.json()["code"] == "materialize_pending", (u, r.text[:200])
    first = backfill()
    assert SNAP in first["snapshots"] and first["rows"] > 0
    with get_session() as s:
        kinds = set(s.scalars(select(SnapshotView.kind).where(SnapshotView.snapshot_id == SNAP).distinct()))
        n1 = s.scalar(select(func.count()).select_from(SnapshotView))
    assert kinds == set(KINDS) - ({"report"} if "report" not in kinds else set())
    again = backfill()  # 멱등
    assert again["snapshots"] == [] and again["rows"] == 0
    with get_session() as s:
        assert s.scalar(select(func.count()).select_from(SnapshotView)) == n1
    assert client.get(f"/api/snapshots/{SNAP}/dashboard", headers=READ).status_code == 200


def test_d14_9_backfill_adds_only_missing_kinds(client: TestClient) -> None:
    """0011 로 올라온 .10 DB(provenance·claims 없음) — backfill 은 새 종류만 넣고 기존 행은 그대로 둔다."""
    from app.snapshot_view import backfill

    with get_session() as s:
        before = {
            (r.kind, r.key, r.scenario): r.sha256
            for r in s.scalars(
                select(SnapshotView).where(
                    SnapshotView.snapshot_id == SNAP, SnapshotView.kind.not_in(("provenance", "claims"))
                )
            )
        }
        s.execute(delete(SnapshotView).where(SnapshotView.kind.in_(("provenance", "claims"))))
    assert client.get(f"/api/snapshots/{SNAP}/claims", headers=READ).status_code == 503
    res = backfill()
    assert SNAP in res["snapshots"]
    with get_session() as s:
        after = {
            (r.kind, r.key, r.scenario): r.sha256
            for r in s.scalars(
                select(SnapshotView).where(
                    SnapshotView.snapshot_id == SNAP, SnapshotView.kind.not_in(("provenance", "claims"))
                )
            )
        }
        assert after == before
        assert s.scalar(
            select(func.count())
            .select_from(SnapshotView)
            .where(SnapshotView.snapshot_id == SNAP, SnapshotView.kind == "provenance")
        )
    assert client.get(f"/api/snapshots/{SNAP}/claims", headers=READ).status_code == 200


def test_d14_9_backfill_cli(client: TestClient, capsys: pytest.CaptureFixture[str]) -> None:
    from app.snapshot_view import main

    with get_session() as s:
        s.execute(delete(SnapshotView).where(SnapshotView.kind == "claims"))
    assert main(["backfill"]) == 0
    out = capsys.readouterr().out
    assert "backfill:" in out and "rows=" in out


def test_d14_9_worker_start_runs_backfill(client: TestClient) -> None:
    from app.core.db import get_sessionmaker
    from app.scheduler.context import SchedulerContext
    from app.scheduler.runner import backfill_views

    with get_session() as s:
        s.execute(delete(SnapshotView).where(SnapshotView.kind == "claims"))
    ctx = SchedulerContext(session_factory=get_sessionmaker(), adapter_factory=lambda: None, collectors={})  # type: ignore[arg-type,return-value]
    res = backfill_views(ctx)
    assert res is not None and SNAP in res["snapshots"]
    assert client.get(f"/api/snapshots/{SNAP}/claims", headers=READ).status_code == 200


# ====================================================================== m3


def test_m3_devseed_reset_drops_unknown_tables_and_stamps_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R3 6차 m3: 0009 DB(snapshot_state 행 + alembic_version 0009)에서 devseed --reset → FK 오류 없이 다시 만들고 alembic 은 head."""
    import sqlalchemy as sa
    from alembic.script import ScriptDirectory

    from app.api import devseed
    from app.core.db import reset_engine
    from app.core.settings import set_settings

    from ._support import FIXTURE
    from .conftest import make_settings

    db = tmp_path / "m3.db"
    settings = make_settings(db, tmp_path / "raw", tmp_path / "reports")
    eng = sa.create_engine(f"sqlite:///{db.as_posix()}")
    with eng.begin() as c:
        c.exec_driver_sql("PRAGMA foreign_keys=ON")
        c.exec_driver_sql("CREATE TABLE snapshot (id INTEGER PRIMARY KEY)")
        c.exec_driver_sql(
            "CREATE TABLE snapshot_state (id INTEGER PRIMARY KEY, snapshot_id INTEGER REFERENCES snapshot(id))"
        )
        c.exec_driver_sql("INSERT INTO snapshot (id) VALUES (12)")
        c.exec_driver_sql("INSERT INTO snapshot_state (id, snapshot_id) VALUES (1, 12)")
        c.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
        c.exec_driver_sql("INSERT INTO alembic_version VALUES ('0009')")
    eng.dispose()
    set_settings(settings)
    try:
        devseed.seed(settings, fixture_dir=FIXTURE, reference="region", reset=True)
    finally:
        set_settings(None)
        reset_engine()
    eng = sa.create_engine(f"sqlite:///{db.as_posix()}")
    try:
        names = set(sa.inspect(eng).get_table_names())
        assert "snapshot_state" not in names and "snapshot_view" in names
        heads = ScriptDirectory(str(REPO / "contracts" / "migrations")).get_heads()
        with eng.connect() as c:
            assert [r[0] for r in c.exec_driver_sql("SELECT version_num FROM alembic_version")] == heads
    finally:
        eng.dispose()


# ====================================================================== m19


def test_m19_bootstrap_publish_failure_keeps_region_ready_and_retries(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R3 6차 m19: bootstrap 의 저장본(발행) 실패가 지역을 failed 로 만들지 않는다 — 지역 ready + snapshot.publish 재시도 잡."""
    from types import SimpleNamespace

    import app.scheduler.handlers as h
    from app.core.db import get_sessionmaker
    from app.models import Region
    from app.scheduler.context import SchedulerContext

    from .test_r3d_core2 import _revision_of

    rev = _revision_of(SNAP, publish=False)
    with get_session() as s:
        s.execute(update(Snapshot).where(Snapshot.id == rev).values(status="ready"))

    def fake_collect(*_a: Any, **_k: Any) -> Any:
        return SimpleNamespace(
            snapshot_id=rev, asof_date="2026-10-08", stats=lambda: {}, errors={}, list_complex_ids=None
        )

    def fake_pipeline(*_a: Any, **_k: Any) -> Any:
        return SimpleNamespace(
            snapshot_id=rev, degraded=False, judge_calls=0, cached=0, cached_by_tool={}, stats=lambda: {}
        )

    def broken_publish(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("저장본 계산 실패(시험)")

    monkeypatch.setattr(h, "collect", fake_collect)
    monkeypatch.setattr("app.scheduler.pipeline.run_pipeline", fake_pipeline)
    monkeypatch.setattr(h.snapshots, "publish_with_stats", broken_publish)
    ctx = SchedulerContext(session_factory=get_sessionmaker(), adapter_factory=lambda: None, collectors={})  # type: ignore[arg-type,return-value]
    stats = h.handle_region_bootstrap(
        ctx, JobRun(id=0, job_name="region.bootstrap", payload={"region_id": 1})
    )
    assert stats["published"] is False and stats["publish_error"] == "RuntimeError"
    with get_session() as s:
        assert s.get(Region, 1).status == "ready"  # type: ignore[union-attr]
        retry = s.get(JobRun, stats["publish_retry_job_id"])
        assert retry is not None and retry.job_name == "snapshot.publish" and retry.status == "queued"


def test_d14_5_parallel_compute_equals_serial(client: TestClient) -> None:
    """나눠 계산(자식 프로세스 — 같은 한 시점의 DB 사본)은 한 프로세스 계산과 같은 저장본 행(종류·키·시나리오·sha256)."""
    import app.snapshot_view as sv
    from app.core.db import get_engine
    from app.core.settings import get_settings
    from app.scheduler.persist import carry_forward

    from .test_r3d_core2 import _revision_of

    rev = _revision_of(SNAP, publish=False)
    with get_session() as s:
        carry_forward(s, SNAP, rev, created_at="2026-10-09T09:01:00+09:00")
        s.get(Snapshot, rev).status = "ready"  # type: ignore[union-attr]
    now = "2026-10-09T09:05:00+09:00"
    rs = sv._read_session(get_engine())
    try:
        snap = rs.get(Snapshot, rev)
        assert snap is not None
        with sv._as_published(rs, snap, now):
            serial = sv.compute(rs, snap)
    finally:
        rs.rollback()
        rs.close()
    par = sv._compute_parallel(get_engine(), rev, now, get_settings(), sv.PARALLEL_GROUPS)
    a = {(r.kind, r.key, r.scenario): r.sha256 for r in serial.rows}
    b = {(r.kind, r.key, r.scenario): r.sha256 for r in par.rows}
    assert a == b
    assert par.stats["parallel"]["processes"] == 1 + len(sv.PARALLEL_GROUPS)
    with get_session() as s:
        assert s.get(Snapshot, rev).status == "ready"  # type: ignore[union-attr]  # 계산은 쓰지 않는다

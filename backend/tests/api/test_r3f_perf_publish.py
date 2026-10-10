"""R3f CORE4 — R3 6차 N-M3 / DECISIONS D14-5 (계약 2026-10-09.11): 발행(materialize) 잡 성능·API 쓰기 잠금.

기준(D14-5): 1000 단지 × 시나리오 5 에서 ``snapshot.publish`` 잡 **15초 이하**, 그동안 API 쓰기 잠금(쓰기 요청이 기다린 시간)
**1초 이하**. 리뷰 측정(.10 — 요청 안 발행): 1016 단지 × 5 = 28.8s 동안 쓰기 잠금 전체.

- 데이터: devseed(16 단지) + 합성 1,000 단지(``devseed.load_synth``) + 합성 단지마다 모든 점수 실행에 score_total + 성분 7개
  (``test_perf_r3._score_synth`` — 점수가 있어야 상세·비교·목록·출처 서랍(sc_·st_)이 실제 크기가 된다).
- 측정: 발행 리비전 12 위 새 리비전(파생 행 이월 → ready)을 worker 실행 함수로 발행하는 동안 다른 스레드가 **실제 API 쓰기**
  (``POST /api/share-links`` — 짧은 쓰기 트랜잭션)를 계속 보내 응답 시간을 잰다. 잡 stats(``total_s``·``write_max_lock_s``)도 본다.
- 발행은 상주 worker 와 같이 미리 띄운 자식 프로세스(``snapshot_view.warm_pool``)로 나눠 계산한다(1000 단지 × 5 ≥
  ``PARALLEL_MIN_CELLS``). 결과(나눠 계산 몫별 시간 포함)는 ``PUBLISH_PERF_OUT``(환경 변수, JSON 경로)에 남긴다(완료 보고 수치).
"""

# ruff: noqa: E501

from __future__ import annotations

import json
import os
import shutil
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_session, reset_engine
from app.core.settings import set_settings
from app.models import Snapshot, SnapshotView

from ._support import READ, WRITE, run_job
from .conftest import Seeded, make_settings
from .test_perf_r3 import _score_synth

SNAP = 12
JOB_LIMIT_S = 15.0
LOCK_LIMIT_S = 1.0


@pytest.fixture
def synth_client(seeded_db: Seeded, tmp_path: Path) -> Iterator[TestClient]:
    from app.api import devseed
    from app.main import create_app

    db = tmp_path / "publish_perf.db"
    shutil.copyfile(seeded_db.db, db)
    settings = make_settings(db, seeded_db.raw_dir, tmp_path / "reports")
    set_settings(settings)
    try:
        assert devseed.load_synth(settings, n=1000, snapshot_id=SNAP, materialize=False) == 1000
        assert _score_synth(SNAP) == 5000  # 합성 1000 단지 × 점수 실행 5
        with TestClient(create_app(settings), raise_server_exceptions=False) as c:
            yield c
    finally:
        set_settings(None)
        reset_engine()


def _ready_revision() -> int:
    """SNAP 위 새 리비전 + snapshot.publish(carry_from) 잡 — 잡이 파생 행을 복사하고 발행한다(호재 연결 PATCH 와 같은 경로)."""
    from app.scheduler.snapshots import republish

    with get_session() as s:
        job = republish(s, 1, reason="D14-5 성능", created_at="2026-10-09T08:00:00+09:00")
        assert job is not None
        return int(job.id)


def test_d14_5_publish_job_1000x5_under_15s_and_api_writes_wait_under_1s(synth_client: TestClient) -> None:
    from app.snapshot_view import warm_pool

    warm_pool()  # 상주 worker 는 시작 때 발행 자식 프로세스를 띄워 둔다(``runner._warm_publish_pool``)
    jid = _ready_revision()
    lat: list[float] = []
    errors: list[str] = []
    stop = threading.Event()

    def writer() -> None:
        while not stop.is_set():
            t = time.perf_counter()
            r = synth_client.post("/api/share-links", json={"label": "perf"}, headers=WRITE)
            lat.append(time.perf_counter() - t)
            if r.status_code != 201:
                errors.append(f"{r.status_code} {r.text[:120]}")
            stop.wait(0.05)

    th = threading.Thread(target=writer, daemon=True)
    th.start()
    t0 = time.perf_counter()
    try:
        status, stats = run_job(jid)
    finally:
        wall = time.perf_counter() - t0
        stop.set()
        th.join(timeout=30)
    assert status == "done" and stats["published"] is True, stats
    with get_session() as s:
        sid = int(stats["snapshot_id"])
        assert s.get(Snapshot, sid).status == "published"  # type: ignore[union-attr]
        n_cx = len(
            set(
                s.scalars(
                    select(SnapshotView.key).where(
                        SnapshotView.snapshot_id == sid, SnapshotView.kind == "complex"
                    )
                )
            )
        )
    result = {
        "complexes": n_cx,
        "scenarios": 5,
        "job_wall_s": round(wall, 3),
        "job_total_s": stats["total_s"],
        "compute_s": stats["compute_s"],
        "write_max_lock_s": stats["write_max_lock_s"],
        "flip_s": stats["flip_s"],
        "rows": stats["rows"],
        "bytes": stats["bytes"],
        "provenance_ids": stats["provenance_ids"],
        "api_writes": len(lat),
        "api_write_max_s": round(max(lat), 3) if lat else None,
        "api_write_p50_s": round(sorted(lat)[len(lat) // 2], 3) if lat else None,
        "timing_s": stats.get("timing_s"),
        "parallel": stats.get("parallel"),
    }
    out = os.environ.get("PUBLISH_PERF_OUT")
    if out:
        Path(out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    assert n_cx >= 1016
    assert not errors, errors[:3]
    assert len(lat) >= 10, "잡 동안 API 쓰기를 충분히 보냈다"
    assert wall <= JOB_LIMIT_S, result
    assert max(lat) <= LOCK_LIMIT_S, result
    assert stats["write_max_lock_s"] <= LOCK_LIMIT_S, result
    # 발행 목록 GET 0.2초 기준 유지(저장본 — D13-1)
    synth_client.get(f"/api/snapshots/{sid}/complexes?size=1000", headers=READ)
    t = time.perf_counter()
    r = synth_client.get(f"/api/snapshots/{sid}/complexes?size=1000", headers=READ)
    assert r.status_code == 200 and len(r.json()["items"]) == 1000
    assert time.perf_counter() - t < 0.5, "발행 목록 GET(저장본 + sha256 검증)"


def test_d14_5_score_provenance_batch_equals_single(synth_client: TestClient) -> None:
    """점수 출처 서랍(sc_·st_ — 합성 1000 단지 × 성분 7 × 시나리오 5) 한 번에 계산 = 한 건씩 계산."""
    from app.api.routers.complexes import _score_provs, provenance_body
    from app.models import ScoreComponent, ScoreRun

    with get_session() as s:
        runs = list(s.scalars(select(ScoreRun).where(ScoreRun.snapshot_id == SNAP)))
        ids: list[str] = []
        for run in runs[:2]:
            for c in s.scalars(select(ScoreComponent).where(ScoreComponent.score_run_id == run.id).limit(60)):
                ids += [f"sc_{run.id}_{c.complex_id}_{c.component}", f"st_{run.id}_{c.complex_id}"]
        ids += ["sc_999999_1_gap", "st_999999_1"]
        many = _score_provs(s, ids)
        from app.api.errors import ApiError

        for pid in sorted(set(ids)):
            try:
                one: dict[str, Any] | None = provenance_body(s, pid)
            except ApiError:
                one = None
            assert many.get(pid) == one, pid

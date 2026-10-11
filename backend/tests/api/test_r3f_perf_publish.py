"""R3f CORE4 — R3 6차 N-M3 / DECISIONS D14-5 (계약 2026-10-09.11, R3g 이름·격리 정리): 발행(materialize) 잡 성능·API 쓰기 잠금.

기준(D14-5, CEO 2026-10-10 수정): 1000 단지 × 시나리오 5 에서 ``snapshot.publish`` 잡 **30초 이하(한 프로세스)**, 그동안 API 쓰기 잠금(쓰기 요청이 기다린 시간)
**1초 이하**. 리뷰 측정(.10 — 요청 안 발행): 1016 단지 × 5 = 28.8s 동안 쓰기 잠금 전체.

- 데이터: devseed(16 단지) + 합성 1,000 단지(``devseed.load_synth``) + 합성 단지마다 모든 점수 실행에 score_total + 성분 7개
  (``test_perf_r3._score_synth`` — 점수가 있어야 상세·비교·목록·출처 서랍(sc_·st_)이 실제 크기가 된다).
- 측정: 발행 리비전 12 위 새 리비전(파생 행 이월 → ready)을 worker 실행 함수로 발행하는 동안 **다른 프로세스**(R3h —
  ``_perf_writer.py``, 운영처럼 api·worker 분리)가 **실제 API 쓰기**(``POST /api/share-links`` — 짧은 쓰기 트랜잭션)를 계속 보내
  응답 시간을 잰다. 잡 stats(``total_s``·``write_max_lock_s``)도 본다.
- 계산은 한 프로세스(읽기 전용 세션 하나). 결과는 ``PUBLISH_PERF_OUT``(환경 변수, JSON 경로)에 남긴다(완료 보고 수치).
"""

# ruff: noqa: E501

from __future__ import annotations

import json
import os
import shutil
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

from ._support import READ, run_job
from .conftest import Seeded, make_settings
from .test_perf_r3 import _score_synth

SNAP = 12
JOB_LIMIT_S = 30.0  # D14-5(CEO 2026-10-10): 한 프로세스 30초
LOCK_LIMIT_S = 1.0


@pytest.fixture
def synth_client(seeded_db: Seeded) -> Iterator[TestClient]:
    """측정 DB 는 pytest basetemp 밖 전용 임시 폴더(R3 7차 — 동시 pytest 회차에서 흔들림: 기본 basetemp 는 사용자마다 한
    ``pytest-of-<user>`` 아래 번호 폴더를 같이 쓰고 다른 회차 종료 정리가 돈다). 끝나면 지운다."""
    import tempfile

    from app.api import devseed
    from app.main import create_app

    root = Path(tempfile.mkdtemp(prefix="sa-perf-publish-"))
    db = root / "publish_perf.db"
    shutil.copyfile(seeded_db.db, db)
    settings = make_settings(db, seeded_db.raw_dir, root / "reports")
    set_settings(settings)
    try:
        assert devseed.load_synth(settings, n=1000, snapshot_id=SNAP, materialize=False) == 1000
        assert _score_synth(SNAP) == 5000  # 합성 1000 단지 × 점수 실행 5
        with TestClient(create_app(settings), raise_server_exceptions=False) as c:
            yield c
    finally:
        set_settings(None)
        reset_engine()
        shutil.rmtree(root, ignore_errors=True)


def _ready_revision() -> int:
    """SNAP 위 새 리비전 + snapshot.publish(carry_from) 잡 — 잡이 파생 행을 복사하고 발행한다(호재 연결 PATCH 와 같은 경로)."""
    from app.scheduler.snapshots import republish

    with get_session() as s:
        job = republish(s, 1, reason="D14-5 성능", created_at="2026-10-09T08:00:00+09:00")
        assert job is not None
        return int(job.id)


def test_d14_5_publish_job_1000x5_under_30s_and_api_writes_wait_under_1s(synth_client: TestClient) -> None:
    jid = _ready_revision()
    errors: list[str] = []
    # R3h: API 쓰기는 **다른 프로세스**(``_perf_writer.py``)가 보낸다 — 운영처럼 api·worker 가 다른 프로세스다. 같은 프로세스의
    # 스레드로 재면 잡의 계산(GIL·GC)이 API 스레드를 멈춰 쓰기 잠금과 무관한 지연(0.4~2.3s, WAL 크기 변화 없이 계산 구간에서만)이
    # 섞였다. 잡 쪽 GC 멈춤은 따로 잰다(gc_max_pause_s — 발행은 계산·쓰기 동안 GC 를 멈춘다)
    import gc
    import subprocess
    import sys
    import tempfile

    from app.core.settings import get_settings

    s_now = get_settings()
    work = Path(tempfile.mkdtemp(prefix="sa-perf-writer-"))
    out_f, ready_f, stop_f = work / "lat.json", work / "ready", work / "stop"
    backend = Path(__file__).resolve().parents[2]
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).with_name("_perf_writer.py")),
         s_now.database_url.removeprefix("sqlite:///"), str(s_now.raw_dir), str(s_now.report_dir),
         str(out_f), str(ready_f), str(stop_f)],
        cwd=backend, env={**os.environ, "PYTHONPATH": str(backend)},
    )  # fmt: skip
    deadline = time.perf_counter() + 120
    while not ready_f.exists():
        assert proc.poll() is None and time.perf_counter() < deadline, "API 쓰기 프로세스가 준비되지 않았다"
        time.sleep(0.1)

    pauses: list[float] = []
    started: dict[str, float] = {}

    def on_gc(phase: str, info: dict[str, int]) -> None:
        if phase == "start":
            started["t"] = time.perf_counter()
        elif "t" in started:
            pauses.append(time.perf_counter() - started.pop("t"))

    gc.callbacks.append(on_gc)
    t0 = time.perf_counter()
    try:
        status, stats = run_job(jid)
    finally:
        wall = time.perf_counter() - t0
        gc.callbacks.remove(on_gc)
        stop_f.write_text("stop", encoding="utf-8")
        proc.wait(timeout=120)
    rows = json.loads(out_f.read_text(encoding="utf-8"))
    shutil.rmtree(work, ignore_errors=True)
    lat = [float(r[1]) for r in rows]
    errors = [f"status {r[2]}" for r in rows if int(r[2]) != 201]
    slow = [[r[0], round(float(r[1]), 3)] for r in rows if float(r[1]) > 0.2]
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
        "carry_lock_s": stats.get("carry_lock_s"),
        "rows": stats["rows"],
        "bytes": stats["bytes"],
        "provenance_ids": stats["provenance_ids"],
        "api_writes": len(lat),
        "api_write_max_s": round(max(lat), 3) if lat else None,
        "api_write_p50_s": round(sorted(lat)[len(lat) // 2], 3) if lat else None,
        "gc_max_pause_s": round(max(pauses), 3) if pauses else 0.0,
        "gc_collections": len(pauses),
        "slow_writes": slow[:20],  # [쓰기 프로세스 시작 뒤 초, 지연]
        "timing_s": stats.get("timing_s"),
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

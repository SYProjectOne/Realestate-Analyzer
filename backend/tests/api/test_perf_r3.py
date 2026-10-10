"""T16 성능 보강 (R3 minor 9): 점수 행이 있는 합성 1,000단지, 워밍업 없는 cold 첫 요청, CSV 전체.

기존 ``test_perf_t16`` 은 점수 행 없이·워밍업 뒤에 쟀다. 여기서는 점수 실행에 합성 단지
1,000개의 score_total·score_component(7성분) 행을 넣고, 새 앱의 첫 요청(cold)으로 G2 첫 페이지를 잰다.

경계 안정화(R3 재리뷰 '기타': 1초 경계 흔들림): 한 번 잰 값 대신 반복 측정의 **중앙값**으로 판정한다 —
cold 는 새 앱·커넥션 풀 초기화를 ``COLD_RUNS`` 번, 나머지는 ``WARM_RUNS`` 번. 기준(1초·CSV 5초)은 그대로다.
"""

from __future__ import annotations

import shutil
import statistics
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_session, reset_engine
from app.core.settings import set_settings
from app.models import Complex, ScoreComponent, ScoreRun, ScoreTotal

from ._support import WRITE, validate
from .conftest import Seeded, make_settings

SNAP = 12
COLD_RUNS = 3
WARM_RUNS = 5
COMPONENTS = ("p10", "rerank", "gap", "benchmark", "supply", "liquidity", "move_in")


def _score_synth(snapshot_id: int) -> int:
    """합성 단지(점수 행 없음)마다 모든 점수 실행에 score_total + 성분 7개."""
    n = 0
    with get_session() as s:
        runs = list(s.scalars(select(ScoreRun).where(ScoreRun.snapshot_id == snapshot_id)))
        scored = {cid for (cid,) in s.execute(select(ScoreTotal.complex_id).distinct())}
        synth = [c.id for c in s.scalars(select(Complex).order_by(Complex.id)) if c.id not in scored]
        for run in runs:
            for k, cid in enumerate(synth):
                total = Decimal(5) - Decimal(k % 400) / Decimal(100)
                s.add(
                    ScoreTotal(
                        score_run_id=run.id, complex_id=cid, total=total, rank=None, tie_group=None,
                        unstable=False, judge_scope="판정 대상",
                    )
                )  # fmt: skip
                for comp in COMPONENTS:
                    s.add(
                        ScoreComponent(
                            score_run_id=run.id, complex_id=cid, component=comp, raw_value=total,
                            score_0_10=total, formula_text="합성", label="추정", reason=None, flags=[],
                        )
                    )  # fmt: skip
                n += 1
    return n


def test_minor9_cold_first_page_with_scores_and_csv(seeded_db: Seeded, tmp_path: Path) -> None:
    from app.api import devseed
    from app.main import create_app

    db = tmp_path / "t16r3.db"
    shutil.copyfile(seeded_db.db, db)
    settings = make_settings(db, seeded_db.raw_dir, tmp_path / "reports")
    set_settings(settings)
    runs: dict[str, list[float]] = {}

    def timed(key: str, client: TestClient, path: str, params: dict[str, Any] | None = None) -> Any:
        t0 = time.perf_counter()
        r = client.get(path, params=params, headers=WRITE)
        runs.setdefault(key, []).append(time.perf_counter() - t0)
        assert r.status_code == 200, r.text
        return r

    try:
        assert devseed.load_synth(settings, n=1000, snapshot_id=SNAP) == 1000
        assert _score_synth(SNAP) >= 1000
        from app.core.db import get_session

        with get_session() as s:  # 점수 행을 넣은 발행 스냅샷 저장본을 다시(D13-1 — GET 은 저장본)
            devseed.rematerialize(s, settings=settings, snapshot_ids=[SNAP])
        for cold in range(COLD_RUNS):
            reset_engine()  # cold: 커넥션 풀·캐시 없이 새 앱
            with TestClient(create_app(settings), raise_server_exceptions=False) as client:
                r = timed("cold_first_page", client, f"/api/snapshots/{SNAP}/complexes")  # 워밍업 없음
                if cold:
                    continue
                body = r.json()
                validate("listComplexes", 200, body)
                assert body["total"] >= 1000 and len(body["items"]) == 50
                assert all(it["total"]["label"] != "확인 불가" for it in body["items"][:10]), "점수 행이 있다"
                for _ in range(WARM_RUNS):
                    for params in ({"sort": "-price_mid"}, {"page": 5}, {"size": 100}):
                        timed(str(params), client, f"/api/snapshots/{SNAP}/complexes", params)
                for _ in range(COLD_RUNS):
                    csv = timed("csv_all", client, f"/api/snapshots/{SNAP}/complexes.csv")
                assert csv.content.decode("utf-8-sig").count("\n") >= 1000
        timings = {k: statistics.median(v) for k, v in runs.items()}
        print("T16 r3 timings(s, median):", {k: round(v, 3) for k, v in timings.items()})
        assert timings["cold_first_page"] < 1.0, runs
        assert timings["cold_first_page"] < 0.2, runs  # 발행 리비전 = 저장본(D13-1, R3e)
        for key in ("{'sort': '-price_mid'}", "{'page': 5}", "{'size': 100}"):
            assert timings[key] < 1.0, runs
        assert timings["csv_all"] < 5.0, runs
    finally:
        set_settings(None)
        reset_engine()

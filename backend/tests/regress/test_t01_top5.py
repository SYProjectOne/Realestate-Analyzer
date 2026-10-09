"""T1 통합 TOP 5 재현 (RA §9) — 시스템 경계: devseed 적재 → API(G1 대시보드·G2 리스트) → 값 검사.

(a) ``expected_scores.json``: 보고서 구성 점수 고정 + 기본 가중치 → 그란테르 5.87 > 엘리프 5.70 > 한내들 5.33 >
    스위첸(김포) 5.00 > 센트레빌 = 더샵 AB23 4.61 (±0.01, 공동 5위).
(b) ``expected_scores_v2.json`` 골든: DB 에 적재된 시장·판정 자료로 스케줄러의 점수 입력 빌더
    (``app.scheduler.inputs.build_score_inputs``)가 만든 입력을 §6-4 식(``app.analysis.score.run_detailed``)에
    넣으면 골든 파일의 종합 점수(±0.01)·순위·tie_group 이 나와야 한다.
"""

# ruff: noqa: E501

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pytest

from .conftest import FIXTURE, SNAP, RegressEnv, api_get, by_key, load_json

pytestmark = pytest.mark.regress

TOL = 0.01


def _expected_a() -> dict[str, Any]:
    data: dict[str, Any] = load_json(FIXTURE / "expected_scores.json")
    return data


def test_t01a_dashboard_top5_matches_expected_scores(env: RegressEnv) -> None:
    exp = _expected_a()
    ids = by_key()
    body = api_get(env, f"/snapshots/{SNAP}/dashboard", scenario="base")
    got = [(r["complex_id"], r["rank"], r["total"]["v"]) for r in body["top5"]]
    want = [(ids[o["key"]], o["rank"], o["total"]) for o in exp["t1"]["order"]]
    assert [g[0] for g in got] == [w[0] for w in want], got
    for (cid, rank, total), (_, wrank, wtotal) in zip(got, want, strict=True):
        assert rank == wrank, (cid, rank, wrank)
        assert abs(float(total) - wtotal) <= TOL, (cid, total, wtotal)
    # 공동 5위: 같은 tie_group
    tail = [r for r in body["top5"] if r["rank"] == 5]
    assert len(tail) == 2 and tail[0].get("tie_group") is not None
    assert tail[0]["tie_group"] == tail[1]["tie_group"]
    # 모든 숫자에 라벨
    for r in body["top5"]:
        assert r["total"]["label"], r


def test_t01a_full_list_ranks_and_totals(env: RegressEnv) -> None:
    exp = _expected_a()
    body = api_get(env, f"/snapshots/{SNAP}/complexes", scenario="base", size=100)
    assert body["total"] == 16
    rows = {r["complex_id"]: r for r in body["items"]}
    for c in exp["complexes"]:
        row = rows[c["complex_id"]]
        total = row["total"]
        if c.get("computed_total") is None:
            assert total["v"] is None, (c["key"], total)
            continue
        assert abs(float(total["v"]) - float(c["computed_total"])) <= TOL, (c["key"], total, c["computed_total"])
        assert row.get("rank") == c["expected_rank"], (c["key"], row.get("rank"), c["expected_rank"])


def test_t01b_v2_golden_from_db_inputs(env: RegressEnv) -> None:
    """DB(devseed) → 스케줄러 입력 빌더 → §6-4 식 = expected_scores_v2.json."""
    from app.analysis.scenarios import builtin
    from app.analysis.score import run_detailed
    from app.core.contracts_gen import RerankAnchor
    from app.models import JudgmentLog, Region, Snapshot
    from app.scheduler.inputs import load_facts
    from app.scheduler.payloads import score_base
    from app.scheduler.snapshots import snapshot_dto

    v2 = load_json(FIXTURE / "expected_scores_v2.json")
    seq = v2["inputs"]["rerank"]["judgment_seq"]
    with env.session() as s:
        snap = s.get(Snapshot, SNAP)
        assert snap is not None
        region = s.get(Region, snap.region_id)
        assert region is not None
        base, _cards = score_base(s, snap, region, load_facts(s, snap, region))
        jl = s.get(JudgmentLog, seq)
        assert jl is not None and jl.tool == "rerank", f"judgment_log #{seq}(rerank 녹화) 없음"
        anchor = RerankAnchor(judgment_seq=seq, status="ok", items=(jl.result_json or {})["items"])
        inputs = base.model_copy(update={"rerank": anchor})
        dto = snapshot_dto(snap)
    detail = run_detailed(dto, builtin("base"), inputs)
    totals = {t.complex_id: t for t in detail.result.totals}
    bad: list[str] = []
    for c in v2["complexes"]:
        t = totals.get(c["complex_id"])
        if t is None:
            bad.append(f"{c['key']}: 결과 없음")
            continue
        want = c["total"]
        got = None if t.total is None else Decimal(str(t.total))
        if (want is None) != (got is None) or (
            want is not None and got is not None and abs(got - Decimal(str(want))) > Decimal("0.01")
        ):
            bad.append(f"{c['key']}: total {got} != {want}")
        if t.rank != c["rank"]:
            bad.append(f"{c['key']}: rank {t.rank} != {c['rank']}")
        if t.tie_group != c["tie_group"]:
            bad.append(f"{c['key']}: tie_group {t.tie_group} != {c['tie_group']}")
    if bad:
        unknown = sorted(
            {f"{c.component}: {c.reason}" for c in detail.result.components if c.score_0_10 is None and c.complex_id <= 12}
        )
        got_in = json.loads(inputs.model_dump_json())
        want_in = v2["inputs"]
        diffs = [
            f"living_areas.households DB={[a['households'] for a in got_in['living_areas']]} v2={[a['households'] for a in want_in['living_areas']]}"
        ]
        for g, w in zip(got_in["complexes"], want_in["complexes"], strict=True):
            keys = ("price_low_won", "price_high_won", "down_payment_pct", "intake_status", "winner_date", "move_in_ym")
            d = {k: (g.get(k), w.get(k)) for k in keys if g.get(k) != w.get(k)}
            if d:
                diffs.append(f"complex {g['complex_id']}: {d}")
        bad += ["— 미계산 component: " + "; ".join(unknown), "— 입력 차이(DB vs v2 inputs):", *diffs]
    assert not bad, "DB 입력으로 v2 골든 재현 실패:\n" + "\n".join(bad)


def test_t01b_v2_golden_from_file_inputs() -> None:
    """v2 골든의 inputs 그대로 → 공개 점수 API(run_detailed) = 골든(±0.01·순위·tie_group). 식 자체의 회귀."""
    from app.analysis.scenarios import builtin
    from app.analysis.score import run_detailed
    from app.core.contracts_gen import ScoreInputs, Snapshot

    v2 = load_json(FIXTURE / "expected_scores_v2.json")
    inputs = ScoreInputs.model_validate(v2["inputs"])
    snaps = {s["id"]: s for s in load_json(FIXTURE / "snapshots.json")}
    detail = run_detailed(Snapshot.model_validate(snaps[inputs.snapshot_id]), builtin("base"), inputs)
    totals = {t.complex_id: t for t in detail.result.totals}
    for c in v2["complexes"]:
        t = totals[c["complex_id"]]
        if c["total"] is None:
            assert t.total is None, c["key"]
            continue
        assert t.total is not None and abs(float(t.total) - c["total"]) <= TOL, (c["key"], t.total, c["total"])
        assert (t.rank, t.tie_group) == (c["rank"], c["tie_group"]), c["key"]


def test_t01b_v2_top5_summary(env: RegressEnv) -> None:
    """v2 TOP 5(골든 summary.top5_b) 순서 = 골든 complexes 의 rank ≤ 5."""
    v2 = load_json(FIXTURE / "expected_scores_v2.json")
    ids = by_key()
    top5 = sorted((c for c in v2["complexes"] if c["rank"] is not None and c["rank"] <= 5), key=lambda c: (c["rank"], c["complex_id"]))
    assert [c["complex_id"] for c in top5] == [ids[o["key"]] for o in v2["summary"]["top5_b"]]

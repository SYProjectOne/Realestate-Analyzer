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


# ---------------------------------------------------------------- (b) DB 경로 — 골든 v2 + D9-1 + 기준 타입 규칙
#
# 골든 v2(사람 승인) inputs 의 judge_scope 는 보고서 당시 규칙이다. DB·파이프라인 경로는 DECISIONS D9-1
# (``app.analysis.scope.judge_scope``)을 따르므로 아래 단지만 범위가 달라진다(README 'D9-1로 인한 차이').
D91_SCOPE_DIFF: dict[int, tuple[str, str]] = {
    4: ("판정 대상", "미해결"),  # 오퍼스 한강 스위첸 — classify #110 review(.72)
    12: ("판정 대상", "참고"),  # 더샵 송도마리나베이 — 접수 '불가'(마감, 4회차 미정)
    14: ("참고", "미해결"),  # 사우역 지엔하임 — classify #110 review(.70)
    16: ("보류", "미해결"),  # 검단 센트레빌 그랑포레 — classify #62 review(.84)
}
# W1 로 complexes.json 을 v2 inputs 에 맞춘 뒤에도 남는 차이(픽스처로 맞출 수 없는 앱 규칙) — CHANGELOG 'fixtures' 소절.
# 칸타빌(7): 기준 타입 = 84㎡에 가장 가까운 타입(app.analysis.price.judge_type) = 84B(84.7529㎡) → 6.70~7.04억.
# 골든 v2 는 보고서 본문(84A 6.64~6.97억). 면적을 바꾸지 않는 한 픽스처로는 맞출 수 없다(README 데이터 주의 9).
RULE_PRICE: dict[int, tuple[int, int]] = {7: (670_000_000, 704_000_000)}
# 가격 반올림 규칙: v2 inputs 가격은 보고서 표기(억 소수 2~3자리)를 원으로 옮긴 값 — DB(공고문 원 단위)와 50만원 이하 차이는 같은 값.
PRICE_TOL_WON = 500_000
# 점수에 쓰이는 입력 필드(라벨·문구·요건 사전 계산용 필드는 제외 — 앱이 사실 행에서 만든다)
SCORE_FIELDS = ("living_area", "judge_scope", "price_low_won", "price_high_won", "winner_date", "resale_months",
                "residency_months", "down_payment_pct", "intake_status")  # fmt: skip
# 앱 규칙상 v2 와 표현이 다른 필드(점수 동일): 즉시 입주 단지는 move_in_ym(준공월)을 그대로 두고 completed_year=None,
# 공고 전 단지(15·16)는 비공식 접수 행만 있어 표시 접수 행 없음(None) — v2 는 '미정'.
NON_SCORE_DIFF: dict[int, set[str]] = {11: {"move_in_ym", "completed_year"}, 12: {"move_in_ym", "completed_year"},
                                       15: {"intake_status"}, 16: {"intake_status"}}  # fmt: skip


def _db_inputs(env: RegressEnv, seq: int) -> tuple[Any, Any, dict[int, str]]:
    from app.core.contracts_gen import RerankAnchor
    from app.models import JudgmentLog, Region, Snapshot
    from app.scheduler.inputs import load_facts
    from app.scheduler.payloads import score_base
    from app.scheduler.snapshots import snapshot_dto

    with env.session() as s:
        snap = s.get(Snapshot, SNAP)
        assert snap is not None
        region = s.get(Region, snap.region_id)
        assert region is not None
        facts = load_facts(s, snap, region)
        base, _cards = score_base(s, snap, region, facts)
        jl = s.get(JudgmentLog, seq)
        assert jl is not None and jl.tool == "rerank", f"judgment_log #{seq}(rerank 녹화) 없음"
        anchor = RerankAnchor(judgment_seq=seq, status="ok", items=(jl.result_json or {})["items"])
        return base.model_copy(update={"rerank": anchor}), snapshot_dto(snap), {f.complex_id: f.scope for f in facts}


def _v2_d91_inputs(v2: dict[str, Any], scopes: dict[int, str]) -> Any:
    """골든 v2 inputs + D9-1 판정 범위 + 기준 타입 규칙 가격 = DB 경로의 기대 입력."""
    from app.analysis.scope import contract_scope
    from app.core.contracts_gen import ScoreInputs

    want = json.loads(json.dumps(v2["inputs"]))
    for c in want["complexes"]:
        c["judge_scope"] = contract_scope(scopes[c["complex_id"]])  # type: ignore[arg-type]
        if c["complex_id"] in RULE_PRICE:
            c["price_low_won"], c["price_high_won"] = RULE_PRICE[c["complex_id"]]
    return ScoreInputs.model_validate(want)


def test_t01b_d91_scope_diff_matches_report_mapping(env: RegressEnv) -> None:
    """DB 사실에 D9-1 을 적용한 범위 vs 골든 v2(보고서 당시 규칙) — 차이는 D91_SCOPE_DIFF(README 표)뿐."""
    v2 = load_json(FIXTURE / "expected_scores_v2.json")
    _inputs, _dto, scopes = _db_inputs(env, v2["inputs"]["rerank"]["judgment_seq"])
    golden = {c["complex_id"]: c["judge_scope"] for c in v2["inputs"]["complexes"]}
    diff = {cid: (golden[cid], scopes[cid]) for cid in sorted(scopes) if scopes[cid] != golden[cid]}
    assert diff == D91_SCOPE_DIFF
    readme = (FIXTURE / "README.md").read_text(encoding="utf-8")
    assert "D9-1로 인한 차이" in readme


def test_t01b_db_inputs_match_v2_inputs(env: RegressEnv) -> None:
    """W1: complexes.json(devseed) → 입력 빌더 = 골든 v2 inputs(점수 필드, 가격 반올림 규칙·D9-1·기준 타입 규칙 반영)."""
    v2 = load_json(FIXTURE / "expected_scores_v2.json")
    inputs, _dto, scopes = _db_inputs(env, v2["inputs"]["rerank"]["judgment_seq"])
    got = json.loads(inputs.model_dump_json())
    want = json.loads(_v2_d91_inputs(v2, scopes).model_dump_json())
    bad: list[str] = []
    for key in ("living_areas", "supply", "unsold"):
        if got[key] != want[key]:
            bad.append(f"{key} 다름")
    for g, w in zip(got["complexes"], want["complexes"], strict=True):
        cid = g["complex_id"]
        for k in SCORE_FIELDS:
            gv, wv = g.get(k), w.get(k)
            if k.startswith("price_") and isinstance(gv, int) and isinstance(wv, int) and abs(gv - wv) <= PRICE_TOL_WON:
                continue
            if gv != wv and k not in NON_SCORE_DIFF.get(cid, set()):
                bad.append(f"complex {cid} {k}: DB {gv!r} != v2 {wv!r}")
        gl = [(x["horizon"], x["p10"]) for x in g["ladders"]]
        wl = [(x["horizon"], x["p10"]) for x in w["ladders"]]
        if gl != wl:
            bad.append(f"complex {cid} ladders: DB {gl} != v2 {wl}")
    assert not bad, "\n".join(bad)


def test_t01b_v2_golden_from_db_inputs(env: RegressEnv) -> None:
    """DB(devseed) → 스케줄러 입력 빌더 → §6-4 식 = 골든 v2 를 D9-1·기준 타입 규칙으로 고친 입력의 결과(±0.01·순위·tie_group)."""
    from app.analysis.scenarios import builtin
    from app.analysis.score import run_detailed

    v2 = load_json(FIXTURE / "expected_scores_v2.json")
    inputs, dto, scopes = _db_inputs(env, v2["inputs"]["rerank"]["judgment_seq"])
    got = {t.complex_id: t for t in run_detailed(dto, builtin("base"), inputs).result.totals}
    want = {t.complex_id: t for t in run_detailed(dto, builtin("base"), _v2_d91_inputs(v2, scopes)).result.totals}
    keys = {c["complex_id"]: c["key"] for c in v2["complexes"]}
    bad: list[str] = []
    for cid in sorted(keys):
        g, w = got.get(cid), want.get(cid)
        if (g is None) != (w is None):
            bad.append(f"{keys[cid]}: 결과 행 DB {g is not None} != 기대 {w is not None}")
            continue
        if g is None or w is None:
            continue
        gt = None if g.total is None else Decimal(str(g.total))
        wt = None if w.total is None else Decimal(str(w.total))
        if (gt is None) != (wt is None) or (gt is not None and wt is not None and abs(gt - wt) > Decimal("0.01")):
            bad.append(f"{keys[cid]}: total {gt} != {wt}")
        if (g.rank, g.tie_group) != (w.rank, w.tie_group):
            bad.append(f"{keys[cid]}: (rank, tie_group) {(g.rank, g.tie_group)} != {(w.rank, w.tie_group)}")
    assert not bad, "DB 입력 → 골든 v2(D9-1) 재현 실패:\n" + "\n".join(bad)
    # D9-1 미해결(4·14·16)은 판정 대상이 아니다 — 종합 점수 없음
    for cid, (_old, new) in D91_SCOPE_DIFF.items():
        if new == "미해결":
            t = got.get(cid)
            assert t is None or t.total is None, (keys[cid], t)
    # 골든 v2 와 같은 범위인 단지의 종합 점수는 골든 그대로(±0.01) — 칸타빌(기준 타입 규칙) 제외
    for c in v2["complexes"]:
        cid = c["complex_id"]
        if cid in D91_SCOPE_DIFF or cid in RULE_PRICE or c["total"] is None:
            continue
        t = got[cid]
        assert t.total is not None and abs(float(t.total) - c["total"]) <= TOL, (c["key"], t.total, c["total"])


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

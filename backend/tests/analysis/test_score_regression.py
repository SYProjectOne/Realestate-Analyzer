"""T1 회귀 (a)단계 · 동점 규칙 · formula_text · T12 민감도 (RA §6-4·§6-6·§9)."""

# ruff: noqa: E501
from __future__ import annotations

from decimal import Decimal

import pytest

from app.analysis.scenarios import builtin
from app.analysis.score import AnalysisScoreEngine, rank_totals, run_detailed
from app.core.protocols import ScoreEngine

from ._support import EXPECTED, ID_TO_KEY, KEY_TO_ID, a_stage_inputs, snapshot

TOL = Decimal("0.01")


def _run():  # type: ignore[no-untyped-def]
    return run_detailed(snapshot(), builtin("base"), a_stage_inputs())


def test_engine_implements_protocol() -> None:
    assert isinstance(AnalysisScoreEngine(), ScoreEngine)


def test_t1_totals_ranks_and_ties_reproduce_expected() -> None:
    result = AnalysisScoreEngine().run(snapshot(), builtin("base"), a_stage_inputs())
    totals = {t.complex_id: t for t in result.totals}
    assert result.rerank_judgment_seq == 124
    for c in EXPECTED["complexes"]:
        t = totals[c["complex_id"]]
        if c["computed_total"] is None:
            assert t.total is None and t.rank is None, c["key"]
            continue
        assert t.total is not None
        assert abs(Decimal(str(t.total)) - Decimal(str(c["computed_total"]))) <= TOL, c["key"]
        assert abs(Decimal(str(t.total)) - Decimal(str(c["report_total"]))) <= TOL, c["key"]
        assert t.rank == c["expected_rank"], c["key"]
        # tie_group 번호 체계는 기대값과 같다(1부터, 단독 null)
        assert t.tie_group == c["tie_group"], c["key"]


def test_t1_order_matches_ra_text() -> None:
    result = AnalysisScoreEngine().run(snapshot(), builtin("base"), a_stage_inputs())
    top = sorted((t for t in result.totals if t.rank is not None and t.rank <= 5), key=lambda t: (t.rank, t.complex_id))
    got = [(ID_TO_KEY[t.complex_id], round(Decimal(str(t.total)), 2), t.rank) for t in top]
    want = [(o["key"], round(Decimal(str(o["total"])), 2), o["rank"]) for o in EXPECTED["t1"]["order"]]
    for (gk, gt, gr), (wk, wt, wr) in zip(got, want, strict=True):
        assert gk == wk and gr == wr
        assert abs(gt - wt) <= TOL


def test_totals_are_exact_decimal_raw_values() -> None:
    """부동소수 합이면 5.325가 5.3249…가 된다 — 원값을 그대로 둔다(score_run.json)."""
    result = _run().result
    totals = {ID_TO_KEY[t.complex_id]: t.total for t in result.totals}
    assert totals["hannaedeul"] == 5.325
    assert totals["switzen"] == 4.995
    assert totals["thesharp_ab23"] == 4.605


def test_every_component_has_formula_text_and_label() -> None:
    result = _run().result
    assert result.components, "성분이 하나도 없다"
    for comp in result.components:
        assert comp.formula_text.strip(), (comp.complex_id, comp.component)
        assert comp.label in ("확인됨", "추정", "비공식", "재가공", "확인 불가")
    keys = {(c.complex_id, c.component) for c in result.components}
    for cid in KEY_TO_ID.values():
        for comp in ("p10", "rerank", "gap", "benchmark", "supply", "liquidity"):
            assert (cid, comp) in keys


def test_fixed_component_formula_mentions_source() -> None:
    result = _run().result
    comp = next(c for c in result.components if c.complex_id == KEY_TO_ID["elif"] and c.component == "rerank")
    assert comp.score_0_10 == 8.9
    assert "고정 입력" in comp.formula_text and "보고서 §12-4-3" in comp.formula_text


def test_null_component_means_total_not_computed() -> None:
    result = _run().result
    harrington = next(t for t in result.totals if t.complex_id == KEY_TO_ID["harrington_1bl"])
    assert harrington.total is None and harrington.rank is None and harrington.tie_group is None
    p10 = next(c for c in result.components if c.complex_id == KEY_TO_ID["harrington_1bl"] and c.component == "p10")
    assert p10.score_0_10 is None and "미판정" in p10.formula_text


@pytest.mark.parametrize(
    ("totals", "expected"),
    [
        ({1: "5.00", 2: "4.96", 3: "4.95", 4: "4.90"}, {1: (1, 1), 2: (1, 1), 3: (3, None), 4: (4, None)}),
        ({1: "5.00", 2: "5.00", 3: "4.00"}, {1: (1, 1), 2: (1, 1), 3: (3, None)}),
        ({2: "5.00", 1: "5.00"}, {1: (1, 1), 2: (1, 1)}),
        ({1: "3.94", 2: "3.90", 3: "3.895", 4: "3.5"}, {1: (1, 1), 2: (1, 1), 3: (1, 1), 4: (4, None)}),
    ],
)
def test_rank_totals_leader_grouping_competition_rank(
    totals: dict[int, str], expected: dict[int, tuple[int, int | None]]
) -> None:
    ranked = rank_totals({k: Decimal(v) for k, v in totals.items()})
    assert {k: (r.rank, r.tie_group) for k, r in ranked.items()} == expected


def test_t12_sensitivity_matches_expected_seed() -> None:
    detail = _run()
    sens = detail.sensitivity
    assert sens is not None
    exp = EXPECTED["t12_sensitivity"]
    assert [ID_TO_KEY[i] for i in sens.base_top5] == exp["base_top5"]
    assert len(sens.cells) == 12
    for cell, want in zip(sens.cells, exp["cells"], strict=True):
        assert cell.variant == want["variant"]
        for k, v in want["weights"].items():
            assert getattr(cell.weights, k) == pytest.approx(v, abs=1e-6), (cell.variant, k)
        assert sorted(ID_TO_KEY[i] for i in cell.top5) == sorted(want["top5"]), cell.variant
        assert cell.changed is want["changed"], cell.variant
        assert sorted(ID_TO_KEY[i] for i in cell.entered) == sorted(want["entered"]), cell.variant
        assert sorted(ID_TO_KEY[i] for i in cell.exited) == sorted(want["exited"]), cell.variant
    assert sens.unstable is exp["unstable"]
    assert sorted(ID_TO_KEY[i] for i in sens.unstable_complex_ids) == sorted(exp["unstable_keys"])
    assert sens.stable_components == exp["stable_components"]


def test_t12_unstable_flag_on_score_totals() -> None:
    result = _run().result
    unstable = sorted(ID_TO_KEY[t.complex_id] for t in result.totals if t.unstable)
    assert unstable == sorted(EXPECTED["t12_sensitivity"]["unstable_keys"])


def test_rerank_delta_against_prev_anchor() -> None:
    """T7: 후보 변경 → delta_rerank 열(현재 relevance − 이전 relevance)."""
    from app.core.contracts_gen import RerankPrev

    inputs = a_stage_inputs()
    t7 = EXPECTED["t7_incheon_only"]
    prev_items = [
        it.model_copy(update={"relevance": next(r["relevance_prev"] for r in t7["rows"] if r["key"] == ID_TO_KEY[it.complex_id or 0])})
        for it in inputs.rerank.items
        if ID_TO_KEY[it.complex_id or 0] in {r["key"] for r in t7["rows"]}
    ]
    inputs = inputs.model_copy(
        update={"rerank": inputs.rerank.model_copy(update={"prev": RerankPrev(judgment_seq=71, items=prev_items)})}
    )
    result = run_detailed(snapshot(), builtin("base"), inputs).result
    deltas = {ID_TO_KEY[c.complex_id]: c.delta for c in result.components if c.component == "rerank"}
    for row in t7["rows"]:
        assert deltas[row["key"]] == pytest.approx(row["delta_rerank"], abs=1e-9), row["key"]
    assert deltas["switzen"] is None  # 이전 호출에 없던 후보

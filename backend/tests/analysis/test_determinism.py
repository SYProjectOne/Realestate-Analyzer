"""같은 입력 = 같은 결과 (RA §4-3 ScoreEngine 규칙) — hypothesis 속성 테스트."""

from __future__ import annotations

import random
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.analysis.scenarios import BUILTIN_SCENARIOS
from app.analysis.score import run_detailed
from app.core.contracts_gen import RerankAnchor, RerankItem, ScoreInputs, TradeInput

from ._support import ladder, make_complex, make_inputs, snapshot

score = st.one_of(st.none(), st.floats(min_value=0, max_value=10, allow_nan=False).map(lambda x: round(x, 2)))


@st.composite
def score_inputs(draw: st.DrawFn) -> ScoreInputs:
    n = draw(st.integers(min_value=1, max_value=9))
    complexes = []
    items = []
    for cid in range(1, n + 1):
        fixed: dict[str, Any] | None = None
        if draw(st.booleans()):
            fixed = {"source": "h", **{k: draw(score) for k in ("gap", "benchmark", "supply")}}
        complexes.append(
            make_complex(
                cid,
                price_low_won=draw(st.integers(min_value=300_000_000, max_value=900_000_000)),
                price_high_won=950_000_000,
                move_in_ym=draw(st.sampled_from(["2027-06", "2028-03", "2029-12", "2031-01"])),
                ladders=[ladder(draw(st.floats(min_value=0, max_value=1, allow_nan=False)))],
                down_payment_pct=draw(st.sampled_from([5, 10, 20])),
                residency_months=draw(st.sampled_from([0, 36])),
                fixed_components=fixed,
            )
        )
        items.append(
            RerankItem(
                candidate_id=f"complex:{cid}",
                complex_id=cid,
                relevance=draw(st.floats(min_value=0, max_value=1, allow_nan=False)),
                rank=cid,
            )
        )
    trades = [
        TradeInput(
            living_area="la_1",
            apt_name=f"T{i % 4}",
            completed_year=draw(st.sampled_from([2016, 2018, 2021, 2024])),
            area_m2=84.9,
            price_won=draw(st.integers(min_value=400_000_000, max_value=1_100_000_000)),
            deal_date="2026-08-01",
            cancelled=False,
            source="openapi",
        )
        for i in range(draw(st.integers(min_value=0, max_value=12)))
    ]
    return make_inputs(
        rerank=RerankAnchor(judgment_seq=1, status="ok", items=items, prev=None),
        complexes=complexes,
        trades=trades,
    )


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(inputs=score_inputs(), scenario_idx=st.integers(min_value=0, max_value=4), seed=st.integers(0, 10_000))
def test_same_input_same_result_and_order_independent(
    inputs: ScoreInputs, scenario_idx: int, seed: int
) -> None:
    scenario = BUILTIN_SCENARIOS[scenario_idx]
    first = run_detailed(snapshot(), scenario, inputs)
    second = run_detailed(snapshot(), scenario, inputs.model_copy(deep=True))
    assert first.result.model_dump() == second.result.model_dump()
    assert first.sensitivity == second.sensitivity

    rng = random.Random(seed)
    shuffled = inputs.model_copy(deep=True)
    rng.shuffle(shuffled.complexes)
    rng.shuffle(shuffled.trades)
    rng.shuffle(shuffled.rerank.items)
    third = run_detailed(snapshot(), scenario, shuffled)
    assert third.result.model_dump() == first.result.model_dump()

    for comp in first.result.components:
        assert comp.formula_text.strip()
        if comp.score_0_10 is not None:
            assert 0 <= comp.score_0_10 <= 10
    for t in first.result.totals:
        assert t.total is None or 0 <= t.total <= 10

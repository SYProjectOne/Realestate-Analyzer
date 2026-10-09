"""R3 수정(F2): M2 유동성·입주 라벨 합성 · minor 24 가격 출처 누락 라벨 · minor 25 delta_rerank = 점수 차(§6-5)."""

# ruff: noqa: E501

from __future__ import annotations

from decimal import Decimal

import pytest

from app.analysis.gap import compute_gap
from app.analysis.scenarios import builtin
from app.analysis.score import liquidity_component, move_in_component, rerank_component, run_detailed
from app.core.contracts_gen import RerankAnchor, RerankItem, RerankPrev

from ._support import ASOF, make_complex, make_inputs, region_params, snapshot
from .test_components import trade

D = Decimal


# ---------------------------------------------------------------- M2


@pytest.mark.parametrize(
    ("labels", "want"),
    [
        ({}, "확인됨"),  # 라벨 null = 값이 있으면 확인됨(계약 2026-10-09.2 설명)
        ({"resale_label": "확인됨", "residency_label": "확인됨", "down_payment_label": "확인됨"}, "확인됨"),
        ({"down_payment_label": "추정"}, "추정"),
        ({"resale_label": "재가공", "residency_label": "비공식"}, "비공식"),
        ({"residency_label": "확인 불가"}, "확인 불가"),
    ],
)
def test_liquidity_label_is_weakest_input_label_m2(labels: dict[str, str], want: str) -> None:
    c = liquidity_component(make_complex(**labels), asof_date=ASOF)
    assert c.score is not None and c.label == want
    if want != "확인됨":
        assert c.reason and "라벨" in c.reason


def test_move_in_label_without_input_label_is_confirmed() -> None:
    """계약에 입주월 라벨 필드가 없다(2026-10-09.3) — 생기면 그 라벨(가장 약한 것)을 쓴다(F3 요청)."""
    m = move_in_component(make_complex(move_in_ym="2028-03"), asof_date=ASOF)
    assert m.label == "확인됨"


# ---------------------------------------------------------------- minor 24


def test_gap_price_without_source_label_is_unknown_minor24() -> None:
    trades = [trade("A", 6.0), trade("A", 6.2), trade("B", 6.4)]
    g = compute_gap(make_complex(price_label=None), trades, asof_date=ASOF, coef=region_params().age_premium_coef)
    assert g.score is not None
    assert g.label == "확인 불가" and g.reason is not None and "출처 누락" in g.reason
    ok = compute_gap(make_complex(price_label="확인됨"), trades, asof_date=ASOF, coef=region_params().age_premium_coef)
    assert ok.label == "확인됨" and ok.reason is None


# ---------------------------------------------------------------- minor 25


def _items(spec: list[tuple[int, float, int]]) -> list[RerankItem]:
    return [RerankItem(candidate_id=f"complex:{i}", complex_id=i, relevance=r, rank=k) for i, r, k in spec]


def test_delta_rerank_is_rerank_score_difference_minor25() -> None:
    """§6-5 '이전 run 과의 점수 차이' = s_rerank(이번) − s_rerank(이전), s = 10 × (N − rank)/(N − 1)."""
    prev = RerankPrev(judgment_seq=71, items=_items([(1, 0.9, 1), (2, 0.8, 2), (3, 0.7, 3)]))  # N=3
    anchor = RerankAnchor(
        judgment_seq=124, status="ok", prev=prev,
        items=_items([(1, 0.85, 2), (2, 0.86, 1), (3, 0.7, 3), (4, 0.6, 4), (5, 0.5, 5)]),  # N=5
    )  # fmt: skip
    got = {cid: rerank_component(make_complex(cid), anchor).delta for cid in (1, 2, 3, 4)}
    # 1: 7.5 − 10 = −2.5 / 2: 10 − 5 = +5 / 3: 5 − 0 = +5 / 4: 이전 후보 아님
    assert got == {1: D("-2.5"), 2: D(5), 3: D(5), 4: None}


def test_delta_rerank_on_fixed_components_uses_same_score_rule() -> None:
    fixed = {"source": "t", "p10": 4, "rerank": 8, "gap": 5, "benchmark": 5, "supply": 3, "liquidity": 5}
    prev = RerankPrev(judgment_seq=71, items=_items([(1, 0.9, 2), (2, 0.95, 1)]))
    anchor = RerankAnchor(judgment_seq=124, status="ok", prev=prev, items=_items([(1, 0.9, 1), (2, 0.8, 2)]))
    inputs = make_inputs(rerank=anchor, complexes=[make_complex(1, fixed_components=fixed), make_complex(2, fixed_components=fixed)])
    res = run_detailed(snapshot(), builtin("base"), inputs).result
    deltas = {c.complex_id: c.delta for c in res.components if c.component == "rerank"}
    assert deltas == {1: 10.0, 2: -10.0}

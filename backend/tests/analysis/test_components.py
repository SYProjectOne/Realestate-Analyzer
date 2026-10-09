"""성분 식 (RA §6-1·§6-2·§6-4): 가격 · 가격 갭(T4 이상치, T11 대체·보정) · 벤치마크 · 공급 · 유동성(T9) · 입주 · p10."""

# ruff: noqa: E501  (한국어 docstring·식 문자열은 화면 폭 기준으로 길다)

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from app.analysis.gap import compute_gap
from app.analysis.price import judge_type, price_change_pct, purchase_price
from app.analysis.scenarios import builtin
from app.analysis.score import (
    benchmark_component,
    liquidity_component,
    move_in_component,
    p10_component,
    rerank_component,
    run_detailed,
    supply_component,
)
from app.core.contracts_gen import (
    BenchmarkInput,
    RerankAnchor,
    RerankItem,
    SupplyInput,
    TradeInput,
    UnsoldInput,
)

from ._support import ASOF, ladder, make_complex, make_inputs, region_params, snapshot

D = Decimal


def trade(
    apt: str,
    price_eok: float,
    *,
    year: int | None = 2021,
    area: float = 84.9,
    date: str = "2026-08-01",
    la: str = "la_1",
    source: str = "openapi",
    cancelled: bool = False,
    presale: bool = False,
    tid: int | None = None,
) -> TradeInput:
    return TradeInput(
        id=tid,
        living_area=la,
        apt_name=apt,
        completed_year=year,
        area_m2=area,
        price_won=round(price_eok * 100_000_000),
        deal_date=date,
        cancelled=cancelled,
        source=source,
        is_presale=presale,
    )  # type: ignore[arg-type]


# ---------------------------------------------------------------- §6-1 가격


def test_purchase_price_low_high_mid() -> None:
    p = purchase_price(floor_won=575_000_000, max_won=605_000_000, balcony_won=3_140_000, options_won=0)
    assert (p.low_won, p.high_won, p.mid_won) == (578_140_000, 608_140_000, D(593_140_000))
    assert purchase_price(floor_won=None, max_won=605_000_000).low_won == 605_000_000


def test_confirmed_discount_only() -> None:
    p = purchase_price(
        floor_won=800_000_000, max_won=900_000_000, discount_won=50_000_000, discount_label="확인됨"
    )
    assert (p.low_won, p.high_won) == (750_000_000, 850_000_000)
    q = purchase_price(
        floor_won=800_000_000, max_won=900_000_000, discount_won=50_000_000, discount_label="비공식"
    )
    assert (q.low_won, q.high_won) == (800_000_000, 900_000_000)


def test_judge_type_nearest_84_and_price_change() -> None:
    assert judge_type([("59A", 59.9), ("84B", 84.75), ("84A", 84.96), ("101A", 101.0)]) == "84B"
    assert judge_type([]) is None
    assert price_change_pct(784_000_000, 759_000_000) == D("-3.19")


# ---------------------------------------------------------------- §6-2 가격 갭


def test_gap_basic_median_and_score() -> None:
    trades = [trade("A", 6.0), trade("A", 6.2), trade("B", 6.4)]
    g = compute_gap(make_complex(), trades, asof_date=ASOF, coef=region_params().age_premium_coef)
    # P_mid 5.93억, median 6.2억 → gap = −4.3548% → s = 5 + 1.0887 = 6.0887
    assert g.median_adjusted == D(620_000_000)
    assert g.gap_pct == D("-4.3548")
    assert g.score == D("6.0887")
    assert g.label == "확인됨" and not g.substitute
    assert "clamp(5 − (−4.35)/4, 0, 10) = 6.09" in g.formula_text


def test_gap_filters_window_area_year_cancel_presale_and_area() -> None:
    trades = [
        trade("A", 6.0),
        trade("A", 6.2),
        trade("B", 6.4),
        trade("A", 9.9, date="2026-03-01"),  # 6개월 밖
        trade("A", 9.9, area=59.9),  # 면적 밖
        trade("A", 9.9, cancelled=True),
        trade("A", 9.9, presale=True),
        trade("Z", 9.9, la="la_2"),  # 다른 생활권
        trade("A", 9.9, date="2026-10-09"),  # 기준일 이후
    ]
    g = compute_gap(make_complex(), trades, asof_date=ASOF, coef=region_params().age_premium_coef)
    assert g.n_trades == 3 and g.median_adjusted == D(620_000_000)


def test_gap_prefers_openapi_rows_per_apartment() -> None:
    trades = [
        trade("A", 6.0),
        trade("A", 6.2),
        trade("A", 8.8, source="reprocessed"),
        trade("B", 6.4, source="reprocessed"),
    ]
    g = compute_gap(make_complex(), trades, asof_date=ASOF, coef=region_params().age_premium_coef)
    assert g.n_trades == 3  # A의 재가공 행만 빠지고 B(재가공뿐)는 쓴다
    assert g.label == "재가공"


def test_t4_outlier_excluded_and_recorded() -> None:
    """메트로자이 2단지 '11억' 같은 1건 → 1.5×IQR 밖이면 비교군에서 빼고 comparable_set에 기록, 원본은 그대로."""
    trades = [trade("메트로자이2", p, tid=i) for i, p in enumerate([5.9, 6.0, 6.1, 6.2, 6.3, 6.5, 6.8, 11.0])]
    before = [t.model_dump() for t in trades]
    g = compute_gap(make_complex(), trades, asof_date=ASOF, coef=region_params().age_premium_coef)
    member = g.members[0]
    assert member.outliers_excluded == 1
    assert member.excluded_reason == "이상치 제외"
    assert member.n_trades == 7
    assert "11억" in (member.note or "")
    assert member.high_won == 680_000_000
    assert [t.model_dump() for t in trades] == before  # 원본 행 삭제·변경 없음
    assert g.n_trades == 7


def test_no_outlier_with_few_trades() -> None:
    trades = [trade("A", 6.0), trade("A", 6.1), trade("A", 9.0)]
    g = compute_gap(make_complex(), trades, asof_date=ASOF, coef=region_params().age_premium_coef)
    assert g.members[0].outliers_excluded == 0 and g.n_trades == 3


def test_t11_substitute_with_age_adjustment() -> None:
    """신축(2020 이후) 0건 → 준공이 가장 최근인 단지로 대체, 보정·미보정 중앙값 둘 다, 라벨 '추정(대체·보정 c=0.015)'."""
    cx = make_complex(
        4, name="스위첸", move_in_ym="2028-08", price_low_won=626_000_000, price_high_won=699_000_000
    )
    trades = [
        trade("리버시티1", 5.8, year=2018),
        trade("리버시티1", 6.0, year=2018),
        trade("센트럴자이", 5.9, year=2018),
        trade("센트럴자이", 6.1, year=2018),
        trade("구축", 4.0, year=2010),
        trade("구축", 4.1, year=2010),
        trade("구축", 4.2, year=2010),
    ]
    g = compute_gap(cx, trades, asof_date=ASOF, coef=region_params().age_premium_coef)
    assert g.substitute
    assert {m.member_apt_name for m in g.members} == {"리버시티1", "센트럴자이"}
    assert all(m.substitute and m.adjusted for m in g.members)
    # Y_ref 2028 − 2018 = 10 → min(10, 8) = 8 → ×1.12
    assert all(m.coef_used == D("0.12") for m in g.members)
    assert g.median_unadjusted == D(595_000_000)
    assert g.median_adjusted == D(666_400_000)
    assert g.gap_pct_unadjusted is not None and g.gap_pct is not None
    assert g.gap_pct < g.gap_pct_unadjusted
    assert g.label == "추정" and g.reason == "대체·보정 c=0.015"
    assert "substitute" in g.flags
    assert "미보정" in g.formula_text


def test_gap_empty_and_missing_price() -> None:
    g = compute_gap(make_complex(), [], asof_date=ASOF, coef=region_params().age_premium_coef)
    assert g.score is None and g.empty_reason and "비교군 없음" in g.formula_text
    h = compute_gap(
        make_complex(price_low_won=None, price_high_won=None),
        [trade("A", 6.0)] * 3,
        asof_date=ASOF,
        coef=region_params().age_premium_coef,
    )
    assert h.score is None and h.label == "확인 불가"


# ---------------------------------------------------------------- 유동성·입주 (T9)


def test_t9_down_payment_change_raises_liquidity_by_one() -> None:
    before = liquidity_component(make_complex(down_payment_pct=10), asof_date=ASOF)
    after = liquidity_component(make_complex(down_payment_pct=5), asof_date=ASOF)
    assert before.score is not None and after.score is not None
    assert after.score - before.score == D(1)
    assert "D/5" in after.formula_text and "5/5" in after.formula_text and "10/5" in before.formula_text


def test_liquidity_resale_registration_and_residency() -> None:
    # 엘리프: 전매 3년(2028-09-10) 등기 시 해제 → 입주 2028-03-01 기준, 510일 = 1.3973년
    c = liquidity_component(make_complex(), asof_date=ASOF)
    assert c.raw_value == D("1.3973")
    assert c.score == D("6.2054")  # 연수는 4자리로 자른 뒤 식에 넣는다(formula_text와 같은 수)
    assert c.label == "확인됨"
    # 더샵 AB23: 거주의무 → −3
    d = liquidity_component(
        make_complex(residency_months=36, resale_release_on_registration=False), asof_date=ASOF
    )
    assert d.score is not None and "3×[거주의무>0]=3" in d.formula_text
    # 전매 도과
    e = liquidity_component(
        make_complex(winner_date="2025-12-10", resale_months=6, down_payment_pct=5), asof_date=ASOF
    )
    assert e.raw_value == D(0) and e.score == D(9)
    # 입력 누락 → 미계산
    f = liquidity_component(make_complex(down_payment_pct=None), asof_date=ASOF)
    assert f.score is None and f.label == "확인 불가"


def test_move_in_component() -> None:
    m = move_in_component(make_complex(move_in_ym="2028-03"), asof_date=ASOF)
    assert m.raw_value == D("1.3973") and m.score == D("7.2054")
    now = move_in_component(make_complex(immediate_move_in=True, move_in_ym=None), asof_date=ASOF)
    assert now.raw_value == D(0) and now.score == D(10)


# ---------------------------------------------------------------- p10·rerank


def test_p10_uses_scenario_horizon_and_ok_status_only() -> None:
    cx = make_complex(ladders=[ladder(0.45), ladder(0.6, horizon="asof_plus_5y", seq=99)])
    assert p10_component(cx, horizon="move_in_plus_1y").score == D("4.5")
    c5 = p10_component(cx, horizon="asof_plus_5y")
    assert c5.score == D(6) and "jl_99" in c5.formula_text
    for status in ("review", "escaped", "blocked", "error"):
        r = p10_component(make_complex(ladders=[ladder(0.45, status=status)]), horizon="move_in_plus_1y")
        assert r.score is None and "미판정" in r.formula_text


def test_rerank_rank_formula_and_anchor_status() -> None:
    items = [
        RerankItem(candidate_id=f"complex:{i}", complex_id=i, relevance=r, rank=k)
        for i, r, k in [(1, 0.89, 1), (2, 0.89, 1), (3, 0.87, 3), (4, 0.5, 4), (5, 0.1, 5)]
    ]
    anchor = RerankAnchor(judgment_seq=124, status="ok", items=items, prev=None)
    assert rerank_component(make_complex(1), anchor).score == D(10)
    assert rerank_component(make_complex(3), anchor).score == D(5)  # 10×(5−3)/4
    assert rerank_component(make_complex(5), anchor).score == D(0)
    assert "jl_124" in rerank_component(make_complex(3), anchor).formula_text
    assert rerank_component(make_complex(9), anchor).score is None
    bad = anchor.model_copy(update={"status": "review"})
    assert rerank_component(make_complex(1), bad).score is None


# ---------------------------------------------------------------- 벤치마크·공급


def bm(
    name: str, sale: float, med: float, *, year: int = 2019, presale: bool = False, label: str = "확인됨"
) -> BenchmarkInput:
    return BenchmarkInput(
        living_area="la_1",
        name=name,
        sale_year=year,
        sale_price_84_won=round(sale * 1e8),
        trade_median_won=round(med * 1e8),
        is_presale=presale,
        label=label,
    )  # type: ignore[arg-type]


def test_benchmark_median_gain_and_flags() -> None:
    bms = [bm("A", 4.0, 6.0), bm("B", 5.0, 6.0), bm("C", 6.0, 6.0), bm("P", 6.0, 3.0, presale=True)]
    c = benchmark_component(make_complex(), bms, asof_date=ASOF)
    # gain 0.5, 0.2, 0.0 → median 0.2 → 10×0.2/0.5 = 4
    assert c.raw_value == D("0.2") and c.score == D(4)
    assert "no_recent_sale_case" in c.flags  # 2023 이후 분양 사례 0건
    few = benchmark_component(make_complex(), [*bms[:2], bm("N", 6.0, 6.3, year=2024)], asof_date=ASOF)
    assert "no_recent_sale_case" not in few.flags
    two = benchmark_component(make_complex(), bms[:2], asof_date=ASOF)
    assert two.label == "추정" and two.reason == "표본 2"
    none = benchmark_component(make_complex(), [], asof_date=ASOF)
    assert none.score is None


def test_supply_window_ref_and_penalty() -> None:
    supply = [
        SupplyInput(
            living_area="la_1", year=2028, ym="2028-03", units=4_000, label="추정"
        ),  # 창 시작(2028-03)
        SupplyInput(living_area="la_1", year=2030, ym="2030-03", units=1_000, label="추정"),  # 창 끝(2030-03)
        SupplyInput(living_area="la_1", year=2030, ym="2030-04", units=9_999, label="추정"),  # 창 밖
        SupplyInput(living_area="la_2", year=2029, ym="2029-01", units=9_999, label="추정"),  # 다른 생활권
    ]
    la = {"la_1": 100_000}
    c = supply_component(make_complex(), supply, [], households=la, ref_pct=0.08, asof_date=ASOF)
    # U_window 5,000, U_ref 8,000 → 10 − 6.25 = 3.75
    assert c.raw_value == D(5000) and c.score == D("3.75") and c.label == "추정"
    rising = [
        UnsoldInput(ym=f"2026-{m:02d}", scope_code="la_1", total=100 + m * 10, post_completion=10 + m)
        for m in (3, 6, 9)
    ]
    p = supply_component(make_complex(), supply, rising, households=la, ref_pct=0.08, asof_date=ASOF)
    assert p.score == D("0.75")  # 3.75 − 2 − 1
    assert "pen=3" in p.formula_text
    nohh = supply_component(
        make_complex(), supply, [], households={"la_1": None}, ref_pct=0.08, asof_date=ASOF
    )
    assert nohh.score is None and "세대수" in nohh.formula_text


def test_scenario_a_uses_move_in_instead_of_liquidity() -> None:
    cx = make_complex(
        fixed_components={"source": "t", "p10": 4, "rerank": 8, "gap": 5, "benchmark": 5, "supply": 3}
    )
    inputs = make_inputs(complexes=[cx])
    res = run_detailed(snapshot(), builtin("A"), inputs).result
    comps = {c.component for c in res.components}
    assert "move_in" in comps and "liquidity" not in comps
    assert res.weights.move_in == 0.1 and res.weights.liquidity is None


def test_scenario_d_excludes_not_open_from_ranking() -> None:
    fixed: dict[str, Any] = {"source": "t", "p10": 4, "rerank": 8, "gap": 5, "benchmark": 5, "supply": 3}
    inputs = make_inputs(
        complexes=[
            make_complex(1, fixed_components=fixed),
            make_complex(2, intake_status="불가", fixed_components={**fixed, "p10": 9}),
        ]
    )
    res = run_detailed(snapshot(), builtin("D"), inputs).result
    t = {x.complex_id: x for x in res.totals}
    assert t[1].rank == 1 and t[2].rank is None and t[2].total is not None


@pytest.mark.parametrize("scope", ["제외"])
def test_excluded_scope_not_scored(scope: str) -> None:
    inputs = make_inputs(complexes=[make_complex(1, judge_scope=scope)])
    res = run_detailed(snapshot(), builtin("base"), inputs).result
    assert res.totals == [] and res.components == []

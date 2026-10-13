"""R5-NORM 3a (minor, RA §6-2): 신축 거래 1~2건·대체 단지 없음 → 가격 갭 라벨 '추정(표본 n)'.

RA §6-2: 비교군 3건 미만이면 준공 연도가 가장 최근인 단지로 대체한다. 대체할 2020년 이전 준공 거래가 없으면 신축 1~2건으로
계산은 하되(점수 식 그대로), 표본이 작다는 것을 라벨로 드러낸다 — label '추정', reason '표본 n'(화면 '추정(표본 n)').
수정 전: 라벨이 거래 라벨 그대로('확인됨'·'재가공')라 3건 이상 비교군과 구별되지 않았다.

골든 영향 확인(R5-NORM 3 규칙): 골든 v2 입력 16단지의 신축 비교군은 최소 45건(또는 가격 없음 2단지) — 1~2건인 단지가 없어
``expected_scores_v2.json``·regress 출력이 바뀌지 않는다(아래 마지막 테스트가 고정).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from decimal import Decimal

import pytest

from app.analysis.gap import MIN_TRADES, compute_gap
from app.analysis.scenarios import builtin
from app.analysis.score import run_detailed
from app.core.contracts_gen import ScoreInputs, TradeInput

from ._support import ASOF, EXPECTED_V2_PATH, load_json, make_complex, make_inputs, region_params, snapshot


def trade(apt: str, price_eok: float, *, year: int = 2021, source: str = "openapi") -> TradeInput:
    return TradeInput(
        id=None,
        living_area="la_1",
        apt_name=apt,
        completed_year=year,
        area_m2=84.9,
        price_won=round(price_eok * 100_000_000),
        deal_date="2026-08-01",
        cancelled=False,
        source=source,
        is_presale=False,
    )  # type: ignore[arg-type]


COEF = region_params().age_premium_coef


@pytest.mark.parametrize("n", [1, 2])
def test_one_or_two_new_build_trades_without_substitute_is_estimated_sample_n(n: int) -> None:
    trades = [trade("신축A", 6.0 + 0.2 * i) for i in range(n)]
    g = compute_gap(make_complex(), trades, asof_date=ASOF, coef=COEF)
    assert g.score is not None and g.n_trades == n and not g.substitute
    assert g.label == "추정"
    assert g.reason == f"표본 {n}"


def test_score_formula_is_unchanged_by_sample_label() -> None:
    """라벨만 바뀐다 — 점수·gap%·식은 같은 거래로 계산한 값 그대로."""
    trades = [trade("신축A", 6.0), trade("신축B", 6.4)]
    g = compute_gap(make_complex(), trades, asof_date=ASOF, coef=COEF)
    # P_mid 5.93억, median 6.2억 → gap −4.3548% → s 6.0887(3건 기본 테스트와 같은 중앙값)
    assert g.median_adjusted == Decimal(620_000_000)
    assert g.gap_pct == Decimal("-4.3548") and g.score == Decimal("6.0887")


def test_three_trades_keep_source_label() -> None:
    trades = [trade("신축A", 6.0), trade("신축A", 6.2), trade("신축B", 6.4)]
    g = compute_gap(make_complex(), trades, asof_date=ASOF, coef=COEF)
    assert len(trades) == MIN_TRADES
    assert g.label == "확인됨" and g.reason is None


def test_one_new_build_with_substitute_stays_substitute_label() -> None:
    """대체 단지가 있으면 RA §6-2 대체 규칙(추정(대체·보정 c=…))이 그대로 — 표본 라벨이 아니다."""
    trades = [trade("신축A", 6.0), trade("구축B", 5.0, year=2015), trade("구축B", 5.2, year=2015)]
    g = compute_gap(make_complex(), trades, asof_date=ASOF, coef=COEF)
    assert g.substitute and g.label == "추정" and g.reason == "대체·보정 c=0.015"


def test_sample_reason_merges_with_price_source_missing() -> None:
    g = compute_gap(make_complex(price_label=None), [trade("신축A", 6.0)], asof_date=ASOF, coef=COEF)
    assert g.label == "확인 불가" and g.reason == "표본 1; 가격 출처 누락"


def test_score_component_carries_sample_label() -> None:
    cx = make_complex()
    inputs = make_inputs(trades=[trade("신축A", 6.0), trade("신축B", 6.4)], complexes=[cx])
    detail = run_detailed(snapshot(), builtin("base"), inputs)
    gap = next(c for c in detail.result.components if c.component == "gap")
    assert (gap.label, gap.reason) == ("추정", "표본 2")


def test_golden_v2_has_no_one_or_two_trade_comparable_set() -> None:
    """R5-NORM 3 골든 영향 규칙: 골든 v2 입력에는 신축 1~2건·대체 없음 단지가 없다 → 골든 라벨 불변."""
    v2 = load_json(EXPECTED_V2_PATH)
    inputs = ScoreInputs.model_validate(v2["inputs"])
    for cx in inputs.complexes:
        g = compute_gap(cx, inputs.trades, asof_date=inputs.asof_date, coef=inputs.region.age_premium_coef)
        assert not (g.n_trades in (1, 2) and not g.substitute), cx.name
        assert not (g.reason or "").startswith("표본"), cx.name

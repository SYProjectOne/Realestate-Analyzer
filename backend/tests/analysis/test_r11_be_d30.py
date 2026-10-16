"""R11-BE(계약 2026-10-09.22, DECISIONS D30-5·D30-6) — 분석 쪽.

- D30-5: 가격 갭 엔진이 gap% 기준 비교군 전체 중앙값(보정 median(T_adj))을 태그로 싣는다(저장 = score_component.median_won, 0019).
  화면·API 는 그 저장값을 보인다(단지별 중앙값을 다시 묶지 않는다).
- D30-6: 요건 근거 문장에 식 기호 'P_mid' 대신 '중간 가격'. 점수 성분 식(formula_text)의 식 기호는 그대로.
"""

# ruff: noqa: E501
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.analysis.gap import (
    compute_gap,
    is_unadjusted_tag,
    median_from_flags,
    unadjusted_from_flags,
    unadjusted_tags,
)
from app.analysis.scenarios import RequirementPrecalculator, builtin

from ._support import ASOF, make_complex, region_params
from .test_components import trade


def _won(x: Decimal) -> int:
    return int(x.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def test_d30_5_gap_tags_carry_adjusted_median_without_substitute() -> None:
    g = compute_gap(
        make_complex(), [trade("A", 6.0), trade("A", 6.2), trade("B", 6.4)], asof_date=ASOF,
        coef=region_params().age_premium_coef,
    )  # fmt: skip
    tags = unadjusted_tags(g)
    assert g.median_adjusted == Decimal(620_000_000)
    assert (
        median_from_flags(tags) == 620_000_000 == unadjusted_from_flags(tags)[1]
    )  # 대체 없음 → 보정 = 미보정
    assert all(is_unadjusted_tag(t) for t in tags)  # 저장 때 flags 에서 빠진다(열로 옮긴다)


def test_d30_5_gap_tags_carry_adjusted_median_with_substitute() -> None:
    cx = make_complex(
        4, name="스위첸", move_in_ym="2028-08", price_low_won=626_000_000, price_high_won=699_000_000
    )
    trades = [
        trade("리버시티1", 5.8, year=2018),
        trade("리버시티1", 6.0, year=2018),
        trade("센트럴자이", 5.9, year=2018),
        trade("센트럴자이", 6.1, year=2018),
    ]
    g = compute_gap(cx, trades, asof_date=ASOF, coef=region_params().age_premium_coef)
    assert g.substitute and g.median_adjusted is not None and g.gap_pct is not None
    tags = unadjusted_tags(g)
    med = median_from_flags(tags)
    assert med == _won(g.median_adjusted) == 666_400_000
    assert unadjusted_from_flags(tags)[1] == 595_000_000  # 미보정은 따로
    # gap% 의 기준이 이 값이다(화면 '비교 단지 전체 가운데값' 옆의 퍼센트와 같은 기준)
    mid = (Decimal(626_000_000) + Decimal(699_000_000)) / 2
    assert abs((mid - Decimal(med)) / Decimal(med) * 100 - g.gap_pct) < Decimal("0.0001")


def test_d30_5_no_gap_no_tags() -> None:
    g = compute_gap(make_complex(), [], asof_date=ASOF, coef=region_params().age_premium_coef)
    assert unadjusted_tags(g) == () and median_from_flags(()) is None


def test_d30_6_funds_evidence_says_mid_price_not_p_mid() -> None:
    """계약금 비율 확인 불가 근거(요건 사전 계산 → G4·G5 요건 칸)는 '중간 가격 5.93억'."""
    res = RequirementPrecalculator().evaluate(
        make_complex(2, down_payment_pct=None), builtin("B"), asof_date=ASOF
    )
    assert res.funds.status == "확인 불가"
    assert res.funds.evidence == "계약금 비율 확인 불가(중간 가격 5.93억) → 확인 불가", res.funds.evidence
    assert "P_mid" not in res.funds.evidence


def test_d30_6_score_formula_keeps_formula_symbol() -> None:
    """점수 성분 식(툴팁 식)은 RA §6 식 표기 그대로 — 회귀 골든 불변(요건 이유가 아니다)."""
    g = compute_gap(
        make_complex(), [trade("A", 6.0), trade("A", 6.2), trade("B", 6.4)], asof_date=ASOF,
        coef=region_params().age_premium_coef,
    )  # fmt: skip
    assert "P_mid 5.93억, 비교군 중앙 6.2억" in g.formula_text

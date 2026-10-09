"""§6-2 비교군과 가격 갭 (RA §6-2, §9 T4·T11).

비교군 = 같은 생활권, 준공 2020년 이후, 전용 80~85㎡, 기준일 이전 6개월 거래(기준일 − 6개월 ≤ 거래일 ≤ 기준일),
cancelled=false, 분양권 거래 제외, 같은 단지에 Open API 행이 있으면 재가공 행은 쓰지 않는다.

- 이상치(T4): 단지별로 거래가 4건 이상이면 |T − 중앙값| > 1.5 × IQR(선형 보간 사분위)인 거래를 비교군에서 뺀다.
  뺀 건수·사유는 comparable_set(``ComparableMember.outliers_excluded``·``excluded_reason='이상치 제외'``·``note``)에
  남기고, 입력 거래 행은 바꾸거나 지우지 않는다.
- 대체(T11): 이상치를 뺀 뒤 신축(2020 이후) 거래가 3건 미만이면 준공 연도가 가장 최근인 단지(같은 연도면 모두)로
  대체하고, 그래도 3건 미만이면 다음 연도 단지를 더한다. 신축 거래가 1~2건 있으면 그대로 두고 대체 단지를 더한다.
  대체 단지 거래는 연식 보정 T_adj = T × (1 + c × min(max(Y_ref − Y_built, 0), cap))을 하고 보정·미보정 중앙값을
  둘 다 계산한다. 점수는 보정값, 라벨 '추정', reason '대체·보정 c=…'. Y_ref = 판정 단지 입주 연도(즉시 입주면 기준일 연도).
- gap% = (P_mid − median(T_adj)) / median(T_adj) × 100 (중앙값은 비교군 전 거래를 합쳐서), s_gap = clamp(5 − gap%/4, 0, 10).
"""

# ruff: noqa: E501  (한국어 docstring·식 문자열은 화면 폭 기준으로 길다)

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.analysis._common import (
    ZERO,
    add_months_date,
    clamp,
    dec,
    fmt_won,
    median,
    num,
    paren,
    parse_date,
    q4,
    quantile,
)
from app.analysis.price import price_of
from app.analysis.types import ComparableMember, GapResult, Label, Trade, weakest_label
from app.core.contracts_gen import AgePremiumCoef, ComplexScoreInput, TradeInput

NEW_BUILD_YEAR = 2020
AREA_MIN = Decimal(80)
AREA_MAX = Decimal(85)
WINDOW_MONTHS = 6
MIN_TRADES = 3
OUTLIER_MIN_N = 4
OUTLIER_K = Decimal("1.5")
OUTLIER_REASON = "이상치 제외"
PRICE_SOURCE_MISSING = "가격 출처 누락"
UNADJUSTED_GAP_TAG = "unadjusted_gap_pct="
UNADJUSTED_MEDIAN_TAG = "unadjusted_median_won="


def unadjusted_tags(g: GapResult) -> tuple[str, ...]:
    """미보정 gap%·미보정 중앙값을 score_component.flags 에 싣는 태그(R3 W7 — 계약 컬럼이 생기기 전 영속 위치).

    예: ``("unadjusted_gap_pct=-3.1234", "unadjusted_median_won=612000000")``. 갭 미계산이면 빈 튜플.
    API 는 ``unadjusted_from_flags`` 로 읽는다(score_component.flags 는 화면에 그대로 나가지 않는다).
    """
    if g.gap_pct_unadjusted is None or g.median_unadjusted is None:
        return ()
    median = int(g.median_unadjusted.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return (f"{UNADJUSTED_GAP_TAG}{format(g.gap_pct_unadjusted, 'f')}", f"{UNADJUSTED_MEDIAN_TAG}{median}")


def unadjusted_from_flags(flags: Iterable[str] | None) -> tuple[Decimal | None, int | None]:
    """``unadjusted_tags`` 의 역 — (미보정 gap%, 미보정 중앙값 원). 없으면 (None, None)."""
    gap: Decimal | None = None
    median: int | None = None
    for f in flags or ():
        if f.startswith(UNADJUSTED_GAP_TAG):
            gap = Decimal(f.removeprefix(UNADJUSTED_GAP_TAG))
        elif f.startswith(UNADJUSTED_MEDIAN_TAG):
            median = int(f.removeprefix(UNADJUSTED_MEDIAN_TAG))
    return gap, median


def _as_trades(trades: Iterable[TradeInput | Trade]) -> list[Trade]:
    return [t if isinstance(t, Trade) else Trade.of(t) for t in trades]


def eligible_trades(
    trades: Iterable[TradeInput | Trade], *, living_area: str | None, asof: date
) -> list[Trade]:
    """생활권·기간·면적·취소·분양권·출처 우선 규칙을 통과한 거래(준공 연도 조건은 아직 적용하지 않음)."""
    if living_area is None:
        return []
    start = add_months_date(asof, -WINDOW_MONTHS)
    pool = [
        t
        for t in _as_trades(trades)
        if t.living_area == living_area
        and not t.cancelled
        and not t.is_presale
        and AREA_MIN <= t.area_m2 <= AREA_MAX
        and start <= t.deal_date <= asof
    ]
    with_openapi = {t.apt_name for t in pool if t.source == "openapi"}
    pool = [t for t in pool if t.source == "openapi" or t.apt_name not in with_openapi]
    return sorted(pool, key=lambda t: (t.apt_name, t.deal_date, t.price_won, t.trade_id or 0))


def split_outliers(trades: Sequence[Trade]) -> tuple[list[Trade], list[Trade]]:
    """(남긴 거래, 이상치). 4건 미만이면 판단하지 않는다."""
    if len(trades) < OUTLIER_MIN_N:
        return list(trades), []
    prices = sorted(Decimal(t.price_won) for t in trades)
    q1 = quantile(prices, Decimal("0.25"))
    q3 = quantile(prices, Decimal("0.75"))
    med = median(prices)
    limit = OUTLIER_K * (q3 - q1)
    kept = [t for t in trades if abs(Decimal(t.price_won) - med) <= limit]
    out = [t for t in trades if abs(Decimal(t.price_won) - med) > limit]
    return kept, out


def _round_won(x: Decimal) -> int:
    return int(x.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _member(
    name: str,
    year: int | None,
    kept: Sequence[Trade],
    outliers: Sequence[Trade],
    *,
    substitute: bool,
    premium: Decimal | None,
) -> ComparableMember:
    prices = tuple(sorted(t.price_won for t in kept))
    factor = Decimal(1) + (premium or ZERO)
    adjusted = tuple(Decimal(p) * factor for p in prices) if substitute else ()
    note = None
    if outliers:
        note = (
            OUTLIER_REASON
            + ": "
            + ", ".join(
                f"{fmt_won(t.price_won)}({t.deal_date.isoformat()}"
                + (f", id {t.trade_id})" if t.trade_id is not None else ")")
                for t in outliers
            )
        )
    return ComparableMember(
        member_apt_name=name,
        completed_year=year,
        substitute=substitute,
        adjusted=substitute,
        coef_used=premium if substitute else None,
        n_trades=len(prices),
        low_won=prices[0] if prices else None,
        median_won=_round_won(median([Decimal(p) for p in prices])) if prices else None,
        adjusted_median_won=_round_won(median(list(adjusted))) if adjusted else None,
        high_won=prices[-1] if prices else None,
        outliers_excluded=len(outliers),
        excluded_reason=OUTLIER_REASON if outliers else None,
        note=note,
        prices_won=prices,
        adjusted_prices_won=adjusted,
    )


def _ref_year(complex_: ComplexScoreInput, asof: date) -> int:
    if complex_.immediate_move_in or not complex_.move_in_ym:
        return asof.year
    return int(complex_.move_in_ym[:4])


def _empty(
    complex_: ComplexScoreInput, price_label: Label, reason: str, members: tuple[ComparableMember, ...] = ()
) -> GapResult:
    return GapResult(
        price=price_of(complex_),
        members=members,
        n_trades=0,
        median_adjusted=None,
        median_unadjusted=None,
        gap_pct=None,
        gap_pct_unadjusted=None,
        score=None,
        substitute=False,
        label="확인 불가",
        reason=reason,
        flags=(),
        formula_text=f"가격 갭 미계산: {reason}",
        empty_reason=reason,
    )


def compute_gap(
    complex_: ComplexScoreInput,
    trades: Iterable[TradeInput | Trade],
    *,
    asof_date: str,
    coef: AgePremiumCoef,
) -> GapResult:
    """§6-2 가격 갭과 비교군 기록(comparable_set). 순수 함수."""
    asof = parse_date(asof_date)
    price = price_of(complex_)
    # 가격 출처 행이 없으면(price_label null) '확인 불가(출처 누락)' — 확인됨으로 올리지 않는다(R3 minor 24, AGENTS 규칙 5)
    price_label: Label = complex_.price_label or "확인 불가"
    price_reason = PRICE_SOURCE_MISSING if complex_.price_label is None else None
    if price is None:
        return _empty(complex_, price_label, "현재 구매가 없음(분양가 미공개)")

    pool = eligible_trades(trades, living_area=complex_.living_area, asof=asof)
    groups: dict[str, list[Trade]] = {}
    for t in pool:
        groups.setdefault(t.apt_name, []).append(t)
    years = {
        name: max((t.completed_year for t in ts if t.completed_year is not None), default=None)
        for name, ts in groups.items()
    }
    cleaned = {name: split_outliers(ts) for name, ts in groups.items()}

    primary = sorted(n for n, y in years.items() if y is not None and y >= NEW_BUILD_YEAR)
    n_primary = sum(len(cleaned[n][0]) for n in primary)
    substitutes: list[str] = []
    if n_primary < MIN_TRADES:
        older = sorted({y for n, y in years.items() if y is not None and y < NEW_BUILD_YEAR}, reverse=True)
        total = n_primary
        for y in older:
            batch = sorted(n for n, yy in years.items() if yy == y and cleaned[n][0])
            substitutes.extend(batch)
            total += sum(len(cleaned[n][0]) for n in batch)
            if total >= MIN_TRADES:
                break

    c = dec(coef.c_per_year)
    y_ref = _ref_year(complex_, asof)
    members: list[ComparableMember] = []
    for n in primary:
        kept, out = cleaned[n]
        members.append(_member(n, years[n], kept, out, substitute=False, premium=None))
    for n in substitutes:
        kept, out = cleaned[n]
        built = years[n]
        assert built is not None
        age = max(0, min(y_ref - built, coef.cap_years))
        members.append(_member(n, built, kept, out, substitute=True, premium=c * age))

    unadjusted = [Decimal(p) for m in members for p in m.prices_won]
    adjusted = [
        a
        for m in members
        for a in (m.adjusted_prices_won if m.substitute else tuple(Decimal(p) for p in m.prices_won))
    ]
    if not unadjusted:
        return _empty(
            complex_,
            price_label,
            f"비교군 없음(같은 생활권 {NEW_BUILD_YEAR}년 이후 준공·전용 80~85㎡·기준일 전 {WINDOW_MONTHS}개월 거래 0건)",
            tuple(members),
        )

    med_adj = median(adjusted)
    med_raw = median(unadjusted)
    gap = q4((price.mid_won - med_adj) / med_adj * 100)
    gap_raw = q4((price.mid_won - med_raw) / med_raw * 100)
    score = q4(clamp(5 - gap / 4))
    is_sub = bool(substitutes)
    n_out = sum(m.outliers_excluded for m in members)
    flags: list[str] = []
    if is_sub:
        flags.append("substitute")
    if n_out:
        flags.append("outlier_excluded")
    if is_sub:
        label: Label = "추정"
        reason: str | None = f"대체·보정 c={num(c, 4)}"
    else:
        label = weakest_label(price_label, *(t.label for t in pool if t.apt_name in primary))
        reason = None
    if price_reason is not None:
        label = weakest_label(label, price_label)
        reason = f"{reason}; {price_reason}" if reason else price_reason

    detail = (
        f"P_mid {fmt_won(price.mid_won)}, 비교군 중앙 {fmt_won(med_adj)}"
        f" = 거래 {len(unadjusted)}건·{len(members)}개 단지"
    )
    if n_out:
        detail += f", 이상치 제외 {n_out}건"
    if is_sub:
        detail += (
            f"; 대체 {', '.join(substitutes)} 연식 보정 c={num(c, 4)}/년(상한 {coef.cap_years}년, Y_ref {y_ref})"
            f"; 미보정 중앙 {fmt_won(med_raw)} → gap {num(gap_raw)}%"
        )
    formula = f"clamp(5 − {paren(gap)}/4, 0, 10) = {num(score)} (gap {num(gap)}%: {detail})"
    return GapResult(
        price=price,
        members=tuple(members),
        n_trades=len(unadjusted),
        median_adjusted=med_adj,
        median_unadjusted=med_raw,
        gap_pct=gap,
        gap_pct_unadjusted=gap_raw,
        score=score,
        substitute=is_sub,
        label=label,
        reason=reason,
        flags=tuple(flags),
        formula_text=formula,
        empty_reason=None,
    )

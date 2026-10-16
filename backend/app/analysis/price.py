"""§6-1 현재 구매가 (RA §6-1).

판정 타입 = 전용 84㎡에 가장 가까운 complex_type. 범위 아래 = 공고문 대표층 공급금액, 위 = 최고가, 둘 다에
발코니 확장비·필수 옵션을 더한다. 점수는 중앙값을 쓴다. 할인은 label='확인됨'인 것만 뺀다.
임의공급에서 가격이 바뀌면 최신 payment_terms.effective_from 값을 쓰고 최초 공고 대비 증감률을 병기한다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.analysis._common import Q2, dec
from app.analysis.types import Label, PurchasePrice
from app.core.contracts_gen import ComplexScoreInput

TARGET_AREA_M2 = Decimal("84")
MID_PRICE_TEXT = "중간 가격"
"""D30-6(계약 .22): 화면에 나가는 사유·근거 문장에서 현재 구매가 중앙값(P_mid)을 부르는 말.

식 기호 ``P_mid`` 는 점수 성분 식(``formula_text``)·코드 주석에만 남는다."""


def judge_type(types: Iterable[tuple[str, float | Decimal | None]]) -> str | None:
    """84㎡에 가장 가까운 타입 코드. 거리 같으면 작은 면적, 그다음 타입 코드 순."""
    best: tuple[Decimal, Decimal, str] | None = None
    for code, area in types:
        if area is None:
            continue
        a = dec(area)
        key = (abs(a - TARGET_AREA_M2), a, code)
        if best is None or key < best:
            best = key
    return None if best is None else best[2]


def purchase_price(
    *,
    floor_won: int | None,
    max_won: int,
    balcony_won: int | None = 0,
    options_won: int | None = 0,
    discount_won: int | None = None,
    discount_label: Label | None = None,
) -> PurchasePrice:
    """P_low = P_floor + B + O − 할인(확인됨만), P_high = P_max + B + O − 할인, P_mid = (P_low + P_high)/2.

    대표층 가격이 없으면 아래도 최고가로 둔다(범위가 한 점).
    """
    extra = (balcony_won or 0) + (options_won or 0)
    discount = discount_won if (discount_won and discount_label == "확인됨") else 0
    high = max_won + extra - discount
    low = (floor_won if floor_won is not None else max_won) + extra - discount
    low, high = min(low, high), max(low, high)
    return PurchasePrice(low_won=low, high_won=high, mid_won=(Decimal(low) + Decimal(high)) / 2)


def price_of(complex_: ComplexScoreInput) -> PurchasePrice | None:
    """ScoreInputs의 단지 가격(이미 §6-1로 만든 low·high) → PurchasePrice. 한쪽만 있으면 한 점 범위."""
    low, high = complex_.price_low_won, complex_.price_high_won
    if low is None and high is None:
        return None
    lo = low if low is not None else high
    hi = high if high is not None else low
    assert lo is not None and hi is not None
    lo, hi = min(lo, hi), max(lo, hi)
    return PurchasePrice(low_won=lo, high_won=hi, mid_won=(Decimal(lo) + Decimal(hi)) / 2)


def price_change_vs_first(
    first: Mapping[str, Any] | None, latest: Mapping[str, Any] | None, type_code: str | None
) -> Decimal | None:
    """공고별 타입 가격(payment_terms.price_by_type, 2026-10-09.2)으로 판정 타입 최고가의 최초 대비 증감률(%).

    ``first``·``latest`` = 최초·현재 조건 행의 price_by_type, ``type_code`` = 판정 타입(``judge_type``).
    어느 한쪽에 그 타입의 max_price_won 이 없으면 None(계산하지 않는다 — 다른 타입으로 대신하지 않음).
    """
    if not type_code or not first or not latest:
        return None
    a, b = first.get(type_code), latest.get(type_code)
    if not isinstance(a, Mapping) or not isinstance(b, Mapping):
        return None
    lo, hi = a.get("max_price_won"), b.get("max_price_won")
    if not isinstance(lo, int) or not isinstance(hi, int) or isinstance(lo, bool) or lo <= 0:
        return None
    return price_change_pct(lo, hi)


def price_change_pct(initial_won: int, latest_won: int) -> Decimal:
    """최초 공고 대비 증감률(%) — 소수 2자리. 예: 78,400만 → 75,900만 = −3.19."""
    if initial_won <= 0:
        raise ValueError("최초 가격이 0 이하")
    return ((Decimal(latest_won) - Decimal(initial_won)) / Decimal(initial_won) * 100).quantize(
        Q2, rounding=ROUND_HALF_UP
    )


def share_won(mid_won: Decimal | int, pct: Decimal | float | int) -> int:
    """P_mid × 비율(%) ÷ 100 — 원 단위 ROUND_HALF_UP(RA §6-7 자금 요건 계약금 ``P_mid × D`` 와 같은 산술).

    계약 2026-10-09.20(D28-5 Q1): 비교 계약금 원 금액(TermsRow.down_payment_won)·
    단지 상세 납부 금액(PaymentAmounts)·목록 계약금 원 금액이 이 함수 하나를 쓴다.
    식은 ``scenarios._funds_pre`` 의 계약금과 같다(그 식은 바꾸지 않는다)."""
    return int((Decimal(mid_won) * dec(pct) / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))

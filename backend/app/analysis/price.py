"""§6-1 현재 구매가 (RA §6-1).

판정 타입 = 전용 84㎡에 가장 가까운 complex_type. 범위 아래 = 공고문 대표층 공급금액, 위 = 최고가, 둘 다에
발코니 확장비·필수 옵션을 더한다. 점수는 중앙값을 쓴다. 할인은 label='확인됨'인 것만 뺀다.
임의공급에서 가격이 바뀌면 최신 payment_terms.effective_from 값을 쓰고 최초 공고 대비 증감률을 병기한다.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

from app.analysis._common import Q2, dec
from app.analysis.types import Label, PurchasePrice
from app.core.contracts_gen import ComplexScoreInput

TARGET_AREA_M2 = Decimal("84")


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


def price_change_pct(initial_won: int, latest_won: int) -> Decimal:
    """최초 공고 대비 증감률(%) — 소수 2자리. 예: 78,400만 → 75,900만 = −3.19."""
    if initial_won <= 0:
        raise ValueError("최초 가격이 0 이하")
    return ((Decimal(latest_won) - Decimal(initial_won)) / Decimal(initial_won) * 100).quantize(
        Q2, rounding=ROUND_HALF_UP
    )

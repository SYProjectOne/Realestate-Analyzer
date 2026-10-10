"""R3 M3: '현재 구매가' 공용 함수(analysis/price_view.py) — §6-1 최신 payment_terms.price_by_type 우선, 없으면 complex_type."""

# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.analysis.price_view import FieldRef, basis_type, current_price, current_terms


@dataclass
class _Type:
    id: int
    type_code: str
    area_m2: Any
    max_price_won: int | None
    floor_sample_price_won: int | None = None
    balcony_won: int | None = None
    options_required_won: int | None = None


@dataclass
class _Terms:
    id: int
    effective_from: str | None
    notice_no: str | None = None
    price_by_type: dict[str, Any] | None = field(default=None)


TYPES = [
    _Type(1, "59A", Decimal("59.9"), 450_000_000),
    _Type(
        2,
        "84A",
        Decimal("84.97"),
        784_000_000,
        760_000_000,
        balcony_won=12_000_000,
        options_required_won=3_000_000,
    ),
    _Type(3, "84B", Decimal("84.99"), 770_000_000),
]


def test_basis_type_is_closest_to_84() -> None:
    t = basis_type(TYPES)
    assert t is not None and t.type_code == "84A"


def test_complex_type_price_when_no_terms() -> None:
    v = current_price(TYPES, [], discount_label=None)
    assert (v.basis_type_code, v.low_won, v.high_won) == ("84A", 775_000_000, 799_000_000)
    assert v.mid_won == Decimal(787_000_000) and not v.from_terms and v.known
    assert v.max_ref == FieldRef("complex_type", 2, "max_price_won", 784_000_000)
    assert v.floor_ref == FieldRef("complex_type", 2, "floor_sample_price_won", 760_000_000)
    assert [r.field for r in v.extra_refs] == ["balcony_won", "options_required_won"]
    assert v.composition == ("공급가", "발코니", "옵션")


def test_latest_terms_price_by_type_wins_m3() -> None:
    """임의공급 공고 가격이 바뀌면 최신 공고 값(§6-1) — 화면·CSV·보고서·점수가 같은 값을 쓴다."""
    terms = [
        _Terms(10, "2025-08-01", "2025000100", {"84A": {"max_price_won": 784_000_000}}),
        _Terms(
            11,
            "2026-09-01",
            "2026000200",
            {"84A": {"max_price_won": 759_000_000, "floor_sample_price_won": 740_000_000}},
        ),
    ]
    v = current_price(TYPES, terms, discount_label=None)
    assert v.from_terms and v.terms_id == 11
    assert (v.low_won, v.high_won) == (755_000_000, 774_000_000)  # + 발코니·옵션 1,500만
    assert v.max_ref == FieldRef("payment_terms", 11, "price_by_type.84A.max_price_won", 759_000_000)
    assert v.floor_ref == FieldRef(
        "payment_terms", 11, "price_by_type.84A.floor_sample_price_won", 740_000_000
    )
    assert v.change_vs_first_pct == Decimal("-3.19")
    # 최신 공고에 기준 타입 가격이 없으면 complex_type
    v2 = current_price(
        TYPES, [_Terms(12, "2026-10-01", "x", {"59A": {"max_price_won": 1}})], discount_label=None
    )
    assert not v2.from_terms and v2.high_won == 799_000_000


def test_current_terms_order_effective_then_notice_then_id() -> None:
    a = _Terms(1, "2026-09-01", "B")
    b = _Terms(2, "2026-09-01", "A")
    c = _Terms(3, "2026-08-01", "Z")
    assert current_terms([a, b, c]) is a
    assert current_terms([]) is None


def test_missing_price_is_unpublished() -> None:
    v = current_price([_Type(1, "59A", Decimal(59), None)], [], discount_label=None)
    assert not v.known and v.empty_reason == "분양가 미공개" and v.basis_type_code == "59A"
    assert current_price([], [], discount_label=None).empty_reason == "분양가 미공개"

"""현재 구매가 (RA §6-1, meta §2-2) — 파이프라인·API·보고서가 같은 값을 쓰도록 하나로 계산한다(R3 M3).

- 판정 기준 타입 = 전용 84㎡에 가장 가까운 complex_type(``price.judge_type``).
- 현재 조건 = payment_terms 중 effective_from 최신(같으면 notice_no, 그다음 id 큰 것).
- 가격: 현재 조건의 ``price_by_type[기준 타입].max_price_won`` 이 있으면 그 공고 값(임의공급 등 최신 공고가 기준),
  없으면 complex_type 의 공고문 값. 발코니·필수 옵션은 complex_type 값을 더한다(``price.purchase_price``).
- 결과에는 각 수치의 출처 필드(``FieldRef``)가 붙는다 — 라벨·출처 링크는 호출자가 그 필드의 field_provenance 로
  만든다(파이프라인: chosen 행 라벨, API: ``FactMaker.field``). 출처 행이 없으면 라벨 '확인 불가(출처 누락)'.

DB 접근 없음. ORM 행이든 DTO 든 아래 Protocol 속성만 있으면 된다.
"""

# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Final, Protocol, TypeVar

from app.analysis.price import judge_type, price_change_vs_first, purchase_price

__all__ = [
    "MISSING_PRICE_REASON",
    "FieldRef",
    "PaymentTermsLike",
    "PriceView",
    "TypeRowLike",
    "basis_type",
    "current_price",
    "current_terms",
]

MISSING_PRICE_REASON: Final = "분양가 미공개"


class TypeRowLike(Protocol):
    @property
    def id(self) -> int: ...
    @property
    def type_code(self) -> str: ...
    @property
    def area_m2(self) -> Any: ...
    @property
    def max_price_won(self) -> int | None: ...
    @property
    def floor_sample_price_won(self) -> int | None: ...
    @property
    def balcony_won(self) -> int | None: ...
    @property
    def options_required_won(self) -> int | None: ...


class PaymentTermsLike(Protocol):
    @property
    def id(self) -> int: ...
    @property
    def effective_from(self) -> str | None: ...
    @property
    def notice_no(self) -> str | None: ...
    @property
    def price_by_type(self) -> Mapping[str, Any] | None: ...


T = TypeVar("T", bound=TypeRowLike)
P = TypeVar("P", bound=PaymentTermsLike)


@dataclass(frozen=True, slots=True)
class FieldRef:
    """수치 1개의 출처 필드(field_provenance 의 entity·entity_id·field)와 값."""

    entity: str
    entity_id: int
    field: str
    value: Any


@dataclass(frozen=True)
class PriceView:
    """§6-1 현재 구매가(기준 타입). low/high/mid 가 None 이면 분양가 미공개(``empty_reason``)."""

    basis_type_code: str | None
    low_won: int | None
    high_won: int | None
    mid_won: Decimal | None
    max_ref: FieldRef | None = None
    floor_ref: FieldRef | None = None  # 대표층 가격 출처(없으면 아래도 최고가)
    extra_refs: tuple[FieldRef, ...] = ()  # 발코니·필수 옵션
    from_terms: bool = False  # 최신 공고(payment_terms.price_by_type) 값을 썼는가
    terms_id: int | None = None
    composition: tuple[str, ...] = field(default_factory=tuple)  # ("공급가", "발코니", "옵션")
    change_vs_first_pct: Decimal | None = None
    empty_reason: str | None = None

    @property
    def known(self) -> bool:
        return self.high_won is not None

    @property
    def low_refs(self) -> tuple[FieldRef, ...]:
        """P_low 를 만든 수치들(대표층 또는 최고가 + 발코니·옵션)."""
        base = self.floor_ref or self.max_ref
        return ((base,) if base is not None else ()) + self.extra_refs

    @property
    def high_refs(self) -> tuple[FieldRef, ...]:
        return ((self.max_ref,) if self.max_ref is not None else ()) + self.extra_refs


def basis_type(types: Iterable[T]) -> T | None:
    """판정 기준 타입(84㎡에 가장 가까운 것)."""
    rows = list(types)
    code = judge_type((t.type_code, t.area_m2) for t in rows)
    return next((t for t in rows if t.type_code == code), None)


def current_terms(terms: Iterable[P]) -> P | None:
    """현재 납부 조건 = effective_from 최신 → notice_no → id."""
    return max(terms, key=lambda p: (p.effective_from or "", p.notice_no or "", p.id), default=None)


def _int(v: Any) -> int | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def current_price(types: Sequence[TypeRowLike], terms: Sequence[PaymentTermsLike]) -> PriceView:
    """현재 구매가(§6-1). 기준 타입이 없거나 최고가가 없으면 미공개."""
    t = basis_type(types)
    if t is None:
        return PriceView(None, None, None, None, empty_reason=MISSING_PRICE_REASON)
    cur = current_terms(terms)
    max_won, floor_won = t.max_price_won, t.floor_sample_price_won
    max_ref: FieldRef | None = FieldRef("complex_type", t.id, "max_price_won", max_won)
    floor_ref: FieldRef | None = (
        FieldRef("complex_type", t.id, "floor_sample_price_won", floor_won) if floor_won is not None else None
    )
    from_terms = False
    by_type = cur.price_by_type if cur is not None else None
    latest = by_type.get(t.type_code) if isinstance(by_type, Mapping) else None
    if cur is not None and isinstance(latest, Mapping) and _int(latest.get("max_price_won")) is not None:
        key = f"price_by_type.{t.type_code}"
        max_won = _int(latest.get("max_price_won"))
        floor_won = _int(latest.get("floor_sample_price_won"))
        max_ref = FieldRef("payment_terms", cur.id, f"{key}.max_price_won", max_won)
        floor_ref = (
            FieldRef("payment_terms", cur.id, f"{key}.floor_sample_price_won", floor_won)
            if floor_won is not None
            else None
        )
        from_terms = True
    if max_won is None:
        return PriceView(t.type_code, None, None, None, empty_reason=MISSING_PRICE_REASON)
    extras = tuple(
        FieldRef("complex_type", t.id, name, getattr(t, name))
        for name in ("balcony_won", "options_required_won")
        if getattr(t, name) is not None
    )
    p = purchase_price(
        floor_won=floor_won, max_won=int(max_won), balcony_won=t.balcony_won, options_won=t.options_required_won
    )
    parts = ["공급가"]
    if t.balcony_won:
        parts.append("발코니")
    if t.options_required_won:
        parts.append("옵션")
    first = min(terms, key=lambda q: (q.effective_from or "", q.notice_no or "", q.id), default=None)
    change = None
    if first is not None and cur is not None and first.id != cur.id:
        change = price_change_vs_first(first.price_by_type, cur.price_by_type, t.type_code)
    return PriceView(
        basis_type_code=t.type_code,
        low_won=p.low_won,
        high_won=p.high_won,
        mid_won=(Decimal(p.low_won + p.high_won) / 2),
        max_ref=max_ref,
        floor_ref=floor_ref,
        extra_refs=extras,
        from_terms=from_terms,
        terms_id=cur.id if cur is not None else None,
        composition=tuple(parts),
        change_vs_first_pct=change,
    )


def mid_rounded(view: PriceView) -> int | None:
    """표시용 P_mid(원, 반올림)."""
    if view.mid_won is None:
        return None
    return int(view.mid_won.quantize(Decimal(1), rounding=ROUND_HALF_UP))

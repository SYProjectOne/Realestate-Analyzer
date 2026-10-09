"""field_provenance 쓰기·검사·Fact 만들기 (WP2, RA §3 '숫자 하나도 출처 없이 남기지 않는다').

- ``upsert_provenance``: Resolver가 돌려준 ProvenanceRow를 field_provenance에 반영한다.
  같은 출처 행(엔티티·필드·원문·발췌 위치·값 표기가 같음)은 갱신하고, 없으면 넣는다.
  행을 지우지 않는다(chosen=false로 보관).
- ``missing_provenance``: 사실 테이블의 모든 수치 컬럼 값마다 chosen 출처 행이 있고 라벨·URL·확인일이
  비어 있지 않은지 전수 검사한다(완료 기준·T13의 전제). 검사할 컬럼은 손으로 적지 않고
  **모델 컬럼 메타데이터**
  에서 모은다(R3 M16, ``numeric_columns``): 정수·소수 컬럼(PK·FK·``*_judgment_seq`` 제외), 날짜·연월 문자열
  컬럼(``*_date``·``*_ym``·``ym``·``effective_from``), 일정 JSON(``fields.JSON_FIELDS``, 비어 있지 않을 때),
  payment_terms.price_by_type 의 숫자 항목. 새 컬럼이 생기면 자동으로 검사 대상이 된다.
  출처가 field_provenance 가 아니라 판정기 행인 컬럼(``POINTER_PROVENANCE``: complex.inclusion_prob →
  inclusion_judgment_seq = prov 'jl_<seq>')은 그 포인터가 있으면 통과한다.
- ``fact_for``: 저장된 chosen 출처 행으로 계약의 Fact dict
  ({v, label, prov='fp_<id>', checked_at, reason, unit})를 만든다.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, BigInteger, Float, Integer, Numeric, String, select
from sqlalchemy.orm import Session

from app.core.contracts_gen import ProvenanceRow
from app.models import (
    Benchmark,
    Competition,
    Complex,
    ComplexType,
    FieldProvenance,
    PaymentTerms,
    RtmsTrade,
    Unsold,
)
from app.normalize.fields import JSON_FIELDS, PRICE_BY_TYPE_ITEMS, is_numeric_field, price_by_type_field

__all__ = [
    "FACT_TABLES",
    "POINTER_PROVENANCE",
    "MissingProvenance",
    "fact_for",
    "missing_provenance",
    "numeric_columns",
    "upsert_provenance",
]

FACT_TABLES: dict[str, Any] = {
    "complex": Complex,
    "complex_type": ComplexType,
    "payment_terms": PaymentTerms,
    "competition": Competition,
    "rtms_trade": RtmsTrade,
    "unsold": Unsold,
    "benchmark": Benchmark,
}
"""field_provenance(entity=키) 로 출처를 남기는 사실 테이블 — 전수 검사 대상."""
_ENTITY_MODELS = FACT_TABLES

POINTER_PROVENANCE: dict[tuple[str, str], str] = {
    ("complex", "inclusion_prob"): "inclusion_judgment_seq",
}
"""(엔티티, 컬럼) → 출처 포인터 컬럼. 값의 출처가 판정기 행(jl_)인 컬럼은 포인터가 있으면 통과."""

_DATE_SUFFIXES = ("_date", "_ym")
_DATE_NAMES = frozenset({"ym", "effective_from"})


def numeric_columns(model: Any) -> tuple[str, ...]:
    """모델 메타데이터 → 출처가 필요한 수치·날짜·일정 컬럼 이름(정의 순서)."""
    out: list[str] = []
    for col in model.__table__.columns:
        name = str(col.name)
        if col.primary_key or col.foreign_keys or name.endswith("_judgment_seq"):
            continue
        t = col.type
        numeric = isinstance(t, Integer | BigInteger | Numeric | Float)
        date_like = isinstance(t, String) and (name.endswith(_DATE_SUFFIXES) or name in _DATE_NAMES)
        schedule = isinstance(t, JSON) and name in JSON_FIELDS
        if numeric or date_like or schedule:
            out.append(name)
    return tuple(out)


_UNITS: dict[str, str] = {
    "units_total": "units",
    "units_general": "units",
    "units_special": "units",
    "officetel_units": "units",
    "units": "units",
    "notice_date": "date",
    "winner_date": "date",
    "effective_from": "date",
    "move_in_ym": "ym",
    "resale_months": "months",
    "residency_months": "months",
    "rewin_restriction_years": "years",
    "area_m2": "m2",
    "max_price_won": "won",
    "floor_sample_price_won": "won",
    "balcony_won": "won",
    "options_required_won": "won",
    "down_payment_first_won": "won",
    "down_payment_pct": "pct",
    "interim_pct": "pct",
    "balance_pct": "pct",
    "supply": "units",
    "applied": "count",
}


def _same_source(fp: FieldProvenance, row: ProvenanceRow) -> bool:
    return (
        fp.raw_document_id == row.raw_document_id
        and (fp.value_text or "") == (row.value_text or "")
        and fp.excerpt_start == row.excerpt_start
        and fp.label == row.label
    )


def upsert_provenance(session: Session, rows: list[ProvenanceRow]) -> list[FieldProvenance]:
    """ProvenanceRow(entity_id 채워진 것) → field_provenance. 반환은 rows와 같은 순서의 ORM 행.

    한 (entity, entity_id, field) 그룹에서 이번 rows에 없는 기존 행은 chosen=false로 내린다(삭제하지 않음).
    """
    out: list[FieldProvenance] = []
    groups: dict[tuple[str, int, str], list[FieldProvenance]] = {}
    for row in rows:
        if row.entity_id is None:
            raise ValueError(f"entity_id 없는 출처 행: {row.entity}.{row.field} key={row.entity_key}")
        gk = (row.entity, row.entity_id, row.field)
        if gk not in groups:
            groups[gk] = list(
                session.scalars(
                    select(FieldProvenance).where(
                        FieldProvenance.entity == row.entity,
                        FieldProvenance.entity_id == row.entity_id,
                        FieldProvenance.field == row.field,
                    )
                )
            )
        existing = next((fp for fp in groups[gk] if _same_source(fp, row) and fp not in out), None)
        fp = existing or FieldProvenance(entity=row.entity, entity_id=row.entity_id, field=row.field)
        fp.entity_key = row.entity_key
        fp.value_text = row.value_text
        fp.raw_document_id = row.raw_document_id
        fp.url = row.url
        fp.checked_at = row.checked_at
        fp.label = row.label
        fp.reason = row.reason
        fp.source_rank = row.source_rank
        fp.chosen = row.chosen
        fp.conflict_group = row.conflict_group
        fp.excerpt = row.excerpt
        fp.excerpt_start = row.excerpt_start
        fp.excerpt_end = row.excerpt_end
        fp.value_norm = row.value_norm
        fp.observed_on = row.observed_on
        if existing is None:
            session.add(fp)
            groups[gk].append(fp)
        out.append(fp)
    touched = set(map(id, out))
    for members in groups.values():
        if any(fp.chosen for fp in members if id(fp) in touched):
            for fp in members:
                if id(fp) not in touched:
                    fp.chosen = False
    session.flush()
    return out


@dataclass(frozen=True)
class MissingProvenance:
    entity: str
    entity_id: int
    field: str
    problem: str  # 'no_row' | 'empty_label' | 'no_url' | 'no_checked_at'


def missing_provenance(session: Session, entities: tuple[str, ...] | None = None) -> list[MissingProvenance]:
    """사실 테이블의 값이 있는 수치 필드마다 chosen 출처 행이 있는지 전수 검사한다(모듈 설명)."""
    out: list[MissingProvenance] = []
    for entity in entities or tuple(FACT_TABLES):
        model = FACT_TABLES.get(entity)
        if model is None:
            continue
        fields = numeric_columns(model)
        prov: dict[tuple[int, str], FieldProvenance] = {}
        for fp in session.scalars(
            select(FieldProvenance).where(FieldProvenance.entity == entity, FieldProvenance.chosen.is_(True))
        ):
            if fp.entity_id is not None:
                prov[(fp.entity_id, fp.field)] = fp
        for obj in session.scalars(select(model)):
            for f in fields:
                value = getattr(obj, f, None)
                if value is None or (f in JSON_FIELDS and not value):
                    continue
                pointer = POINTER_PROVENANCE.get((entity, f))
                if pointer is not None and getattr(obj, pointer, None) is not None:
                    continue
                problem = _problem(prov.get((obj.id, f)))
                if problem is not None:
                    out.append(MissingProvenance(entity, obj.id, f, problem))
            if entity == "payment_terms":
                for type_code, entry in (getattr(obj, "price_by_type", None) or {}).items():
                    for item in PRICE_BY_TYPE_ITEMS:
                        field = price_by_type_field(str(type_code), item)
                        if (entry or {}).get(item) is None or not is_numeric_field(entity, field):
                            continue
                        problem = _problem(prov.get((obj.id, field)))
                        if problem is not None:
                            out.append(MissingProvenance(entity, obj.id, field, problem))
    return out


def _problem(hit: FieldProvenance | None) -> str | None:
    if hit is None:
        return "no_row"
    if not (hit.label or "").strip():
        return "empty_label"
    if hit.label != "확인 불가" and not (hit.url or "").strip():
        return "no_url"
    if hit.label != "확인 불가" and not (hit.checked_at or "").strip():
        return "no_checked_at"
    return None


def fact_for(session: Session, entity: str, entity_id: int, field: str) -> dict[str, Any]:
    """저장된 값 + chosen 출처 행 → Fact dict. 출처 행이 없으면 '확인 불가(출처 누락)'(T13 prod 규칙)."""
    model = _ENTITY_MODELS[entity]
    obj = session.get(model, entity_id)
    value = getattr(obj, field, None) if obj is not None else None
    if isinstance(value, Decimal):
        value = float(value)
    fp = session.scalars(
        select(FieldProvenance).where(
            FieldProvenance.entity == entity,
            FieldProvenance.entity_id == entity_id,
            FieldProvenance.field == field,
            FieldProvenance.chosen.is_(True),
        )
    ).first()
    unit = _UNITS.get(field)
    if fp is None:
        return {
            "v": None,
            "label": "확인 불가",
            "reason": "출처 누락",
            "prov": None,
            "checked_at": None,
            "unit": unit,
        }
    fact: dict[str, Any] = {
        "v": value if fp.label != "확인 불가" else None,
        "label": fp.label,
        "prov": f"fp_{fp.id}",
        "checked_at": (fp.checked_at or None),
        "unit": unit,
    }
    if fp.reason:
        fact["reason"] = fp.reason
    elif fp.label == "확인 불가":
        fact["reason"] = "값 없음"
    if fact["v"] is None and fp.label != "확인 불가":
        # 값이 없으면 확인 불가 — 출처 행 reason(예: 채택 보류 '출처 상충 — compare 대기')을 사유로 둔다
        fact.update(label="확인 불가", reason=fp.reason or "값 없음")
    return fact

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
  inclusion_judgment_seq, catalyst.stage_prob → judgment_seq = prov 'jl_<seq>')은 그 포인터가 있으면 통과한다.
  **검사할 테이블도 손으로 적지 않는다**(R3b M16): 모델 레지스트리의 모든 테이블 중 출처가 필요한 수치 컬럼이
  있는 것이 사실 테이블(``FACT_TABLES``)이고, 사실이 아닌 테이블은 ``NON_FACT_TABLES`` 에 사유와 함께 적는다
  (둘 중 어디에도 없는 새 테이블은 사실 테이블로 검사된다 — 테스트가 분류를 강제한다).
  행 자체가 출처를 가진 테이블(``raw_document_id`` + ``label`` 컬럼: household_stat·supply)은 field_provenance
  행이 없어도 그 행의 원문(URL·확인일)과 라벨이 있으면 통과한다(행 단위 출처).
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
from app.facts_view import is_human
from app.models import Base, FieldProvenance, RawDocument
from app.normalize.fields import (
    JSON_FIELDS,
    PRICE_BY_TYPE_ITEMS,
    discount_field,
    is_numeric_field,
    price_by_type_field,
)

__all__ = [
    "FACT_TABLES",
    "NON_FACT_TABLES",
    "POINTER_PROVENANCE",
    "MissingProvenance",
    "fact_for",
    "missing_provenance",
    "numeric_columns",
    "upsert_provenance",
]

NON_FACT_TABLES: dict[str, str] = {
    "raw_document": "원문 자체(출처)",
    "field_provenance": "출처 행 자체",
    "region": "사용자 입력 지역 설정",
    "snapshot": "버전·기준일 기록",
    "legal_dong": "참조 코드표(행정표준코드) — 수치 사실 아님",
    "admin_dong": "참조 코드표(행정동) — 수치 사실 아님",
    "admin_legal_map": "참조 코드 매핑",
    "judgment_log": "판정기 호출 기록(출처 jl_ 자체)",
    "claim": "판정기 verify 기록",
    "fact_demotion": "사실 강등 기록(D10-3, 계약 .6) — 출처 아님(강등 출처 행은 field_provenance)",
    "scenario": "상황 설정",
    "score_run": "점수 계산 실행 기록(입력 지문·버전)",
    "score_component": "§6 수식 계산값(출처 = score_run·사실 Fact)",
    "score_total": "§6 수식 계산값",
    "ladder": "판정기 noul 결과(출처 = judgment_seq)",
    "decision": "판정기 decide 결과(출처 = judgment_seq)",
    "comparable_set": "비교군 계산 기록(출처 cs_)",
    "catalyst_link": "호재-단지 거리 계산값",
    "intake_status": "접수 상태 판정 행(출처 = evidence_url·raw_document_id·판정)",
    "change_event": "운영 기록(변경 이벤트)",
    "checklist_item": "운영 기록(체크리스트)",
    "human_check": "사람 확인 기록(입력자·시각이 출처)",
    "job_run": "운영 기록(잡 실행)",
    "share_link": "운영 기록(공유 링크)",
    "snapshot_view": "발행 리비전 저장본(D13-1) — 화면 응답·보고서 입력 사본(출처는 사본 안 Fact 의 prov)",
}
"""사실 테이블이 아닌 테이블과 사유 — 여기 없는 테이블은 모두 출처 전수 검사 대상이다(``FACT_TABLES``)."""

POINTER_PROVENANCE: dict[tuple[str, str], str] = {
    ("complex", "inclusion_prob"): "inclusion_judgment_seq",
    ("catalyst", "stage_prob"): "judgment_seq",
}
"""(엔티티, 컬럼) → 출처 포인터 컬럼. 값의 출처가 판정기 행(jl_)인 컬럼은 포인터가 있으면 통과."""

_DATE_SUFFIXES = ("_date", "_ym")
_DATE_NAMES = frozenset({"ym", "effective_from"})
_POINTER_NAMES = frozenset({"judgment_seq"})


def numeric_columns(model: Any) -> tuple[str, ...]:
    """모델 메타데이터 → 출처가 필요한 수치·날짜·일정 컬럼 이름(정의 순서)."""
    out: list[str] = []
    for col in model.__table__.columns:
        name = str(col.name)
        if col.primary_key or col.foreign_keys or name.endswith("_judgment_seq") or name in _POINTER_NAMES:
            continue
        t = col.type
        numeric = isinstance(t, Integer | BigInteger | Numeric | Float)
        date_like = isinstance(t, String) and (name.endswith(_DATE_SUFFIXES) or name in _DATE_NAMES)
        schedule = isinstance(t, JSON) and name in JSON_FIELDS
        if numeric or date_like or schedule:
            out.append(name)
    return tuple(out)


def _fact_tables() -> dict[str, Any]:
    """모델 레지스트리 → 사실 테이블(``NON_FACT_TABLES`` 밖이고 출처가 필요한 컬럼이 있는 것), 이름 순."""
    out: dict[str, Any] = {}
    for mapper in sorted(Base.registry.mappers, key=lambda m: str(m.class_.__tablename__)):
        cls = mapper.class_
        name = str(cls.__tablename__)
        if name in NON_FACT_TABLES or not numeric_columns(cls):
            continue
        out[name] = cls
    return out


FACT_TABLES: dict[str, Any] = _fact_tables()
"""출처 전수 검사 대상 사실 테이블(모델 메타데이터에서 — R3b M16). field_provenance.entity = 테이블 이름."""
_ENTITY_MODELS = FACT_TABLES


def _row_level(model: Any) -> bool:
    """행 자체가 출처를 가진 테이블인가(raw_document_id + label 컬럼)."""
    cols = model.__table__.columns
    return "raw_document_id" in cols and "label" in cols


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


def _no_nul(text: str | None) -> str | None:
    """Postgres text 열은 NUL 을 받지 않는다(R4 재시험 N2, D21-2) — 원문 읽기(``_text.read_raw_text``)가 이미 공백으로 바꾸지만
    다른 경로(판정기 추출 값·사람 입력)로 들어와도 원문 1건 정규화가 통째로 롤백되지 않게 마지막에 한 번 더 바꾼다."""
    return text.replace("\x00", " ") if text and "\x00" in text else text


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
        fp.value_text = _no_nul(row.value_text)
        fp.raw_document_id = row.raw_document_id
        fp.url = row.url
        fp.checked_at = row.checked_at
        fp.label = row.label
        fp.reason = _no_nul(row.reason)
        fp.source_rank = row.source_rank
        fp.chosen = row.chosen
        fp.conflict_group = row.conflict_group
        fp.excerpt = _no_nul(row.excerpt)
        fp.excerpt_start = row.excerpt_start
        fp.excerpt_end = row.excerpt_end
        fp.value_norm = _no_nul(row.value_norm)
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
        objs = list(session.scalars(select(model)))
        row_docs = _row_docs(session, objs) if _row_level(model) else {}
        for obj in objs:
            row_ok = _row_source_ok(obj, row_docs)
            for f in fields:
                value = getattr(obj, f, None)
                if value is None or (f in JSON_FIELDS and not value):
                    continue
                pointer = POINTER_PROVENANCE.get((entity, f))
                if pointer is not None and getattr(obj, pointer, None) is not None:
                    continue
                if row_ok and (obj.id, f) not in prov:
                    continue  # 행 단위 출처(원문 + 라벨)
                problem = _problem(prov.get((obj.id, f)))
                if problem is not None:
                    out.append(MissingProvenance(entity, obj.id, f, problem))
            if entity == "payment_terms":
                for type_code, won in (getattr(obj, "discount_by_type", None) or {}).items():
                    if won is None:
                        continue
                    problem = _problem(prov.get((obj.id, discount_field(str(type_code)))))
                    if problem is not None:  # 할인(계약 .8 D11-6)도 출처 전수 검사
                        out.append(MissingProvenance(entity, obj.id, discount_field(str(type_code)), problem))
                for type_code, entry in (getattr(obj, "price_by_type", None) or {}).items():
                    for item in PRICE_BY_TYPE_ITEMS:
                        field = price_by_type_field(str(type_code), item)
                        if (entry or {}).get(item) is None or not is_numeric_field(entity, field):
                            continue
                        problem = _problem(prov.get((obj.id, field)))
                        if problem is not None:
                            out.append(MissingProvenance(entity, obj.id, field, problem))
    return out


def _row_docs(session: Session, objs: list[Any]) -> dict[int, RawDocument]:
    ids = sorted({o.raw_document_id for o in objs if getattr(o, "raw_document_id", None) is not None})
    out: dict[int, RawDocument] = {}
    for i in range(0, len(ids), 500):
        for d in session.scalars(select(RawDocument).where(RawDocument.id.in_(ids[i : i + 500]))):
            out[d.id] = d
    return out


def _row_source_ok(obj: Any, docs: dict[int, RawDocument]) -> bool:
    """행 단위 출처: 원문 행(URL·확인일)과 비어 있지 않은 라벨."""
    rid = getattr(obj, "raw_document_id", None)
    doc = docs.get(rid) if rid is not None else None
    label = getattr(obj, "label", None)
    has_doc = doc is not None and bool((doc.url or "").strip() and doc.fetched_at)
    return has_doc and bool((label or "").strip())


def _problem(hit: FieldProvenance | None) -> str | None:
    if hit is None:
        return "no_row"
    if not (hit.label or "").strip():
        return "empty_label"
    if is_human(hit.reason) and hit.raw_document_id is None and (hit.checked_at or "").strip():
        return None  # 사람 확인 출처 행(D11-3): 입력 시각·종류가 출처(human_check — URL 없음)
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

"""D10-3 주장 대상·사실 강등·복원 (계약 2026-10-09.6, R3 재리뷰 N-C3).

contradicted 주장의 문장을 사람이 고쳐 publish 를 푸는 동안 그 판정의 근거가 된 DB 사실이 그대로 점수·화면에 나가던
문제(N-C3)를 막는다.

- **주장 대상**(``claim_target``): 주장이 생성된 DB 사실 (entity, entity_id, field). ``claim.entity·entity_id·field``
  (P9 가 채우는 계약 컬럼)가 있으면 그것, 없으면(0006 이전 행·P9 미갱신) P9 사실 문장 형식(section
  ``complex:<id>``, ``scheduler.pipeline._claim_text`` 의 필드 용어)과 근거 출처 id(``fp_<id>``)로 되찾는다 —
  우리가 만든 문장 형식의 문자열 대조이지 판단이 아니다(규칙 3).
- **같은 대상 검사**(``check_same_target``): 고친 문장의 원자 주장(``judge.claims.split_texts``)마다 원 주장
  field 의 용어가 있고 다른 사실 필드의 용어가 없어야 하며, 같은 지역의 다른 단지 이름만 가리키면 안 된다.
  어기면 422(``TargetMismatch``).
- **강등**(``demote``): 사실 테이블 값을 비우고(점수·요건 입력에서 빠짐 — 파이프라인은 값 null 을 '입력 없음'으로
  본다) chosen 출처 행 = 강등 행(라벨 '확인 불가', reason '검증 모순', 원문 없음)으로, 원래 chosen 행은 chosen=false
  로 보관한다. 체크리스트 '사실 재확인' 항목, change_event(critical, triggers_rejudge), 그 단지 rejudge 잡.
  ``write_chosen`` 의 채택 보류(CONFLICT_HOLD)와 같은 표현(값 null + chosen '확인 불가' 행)이다.
- **복원**: 사람 확인(``restore_by_human`` — POST /ops/human-checks 같은 단지·같은 field, 그 값이 사실) 또는
  새 원문(``sync_demotions`` — 정규화가 다른 원문 출처 행을 chosen 으로 올렸으면 'new_source'). 같은 원문
  출처(원래 행·같은 raw_document)가 다시 chosen 이 됐으면 새 원문이 아니므로 강등을 다시 건다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from sqlalchemy import Integer, Numeric, String, select
from sqlalchemy.orm import Session

from app.api.jobs import now_iso
from app.models import (
    ChangeEvent,
    ChecklistItem,
    Claim,
    Complex,
    ComplexType,
    FactDemotion,
    FieldProvenance,
    HumanCheck,
    PaymentTerms,
)

__all__ = [
    "DEMOTION_LABEL",
    "DEMOTION_REASON",
    "FIELD_ENTITY",
    "FIELD_NAMES",
    "FIELD_TERMS",
    "ClaimTarget",
    "TargetMismatch",
    "ValueParseError",
    "check_same_target",
    "checklist_title",
    "claim_target",
    "demote",
    "demotion_view",
    "fields_in",
    "latest_demotions",
    "restore_by_human",
    "sync_demotions",
]

DEMOTION_LABEL: Final = "확인 불가"
DEMOTION_REASON: Final = "검증 모순"
CHECKLIST_KIND: Final = "사실 재확인"

# P9 사실 문장(scheduler.pipeline._claim_text)의 필드 → 문장 용어. 용어는 문장 형식의 일부다(판단 아님).
FIELD_TERMS: Final[dict[str, tuple[str, ...]]] = {
    "max_price_won": ("공급금액", "분양가", "공급가"),
    "move_in_ym": ("입주",),
    "resale_months": ("전매",),
    "residency_months": ("거주의무", "거주 의무"),
    "down_payment_pct": ("계약금",),
}
FIELD_ENTITY: Final[dict[str, str]] = {
    "max_price_won": "complex_type",
    "move_in_ym": "complex",
    "resale_months": "complex",
    "residency_months": "complex",
    "down_payment_pct": "payment_terms",
}
FIELD_NAMES: Final[dict[str, str]] = {
    "max_price_won": "기준 타입 최고 공급금액",
    "move_in_ym": "입주 예정 시기",
    "resale_months": "전매제한 기간",
    "residency_months": "거주의무 기간",
    "down_payment_pct": "계약금 비율",
}
_MODELS: Final[dict[str, Any]] = {
    "complex": Complex,
    "complex_type": ComplexType,
    "payment_terms": PaymentTerms,
}
_SECTION_RE: Final = re.compile(r"^complex:(\d+)$")
_FP_RE: Final = re.compile(r"\bfp_(\d+)\b")
_YM_RE: Final = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class TargetMismatch(ValueError):
    """고친 문장이 원 주장과 같은 대상(section·complex·field)이 아니다(D10-3) → 422."""


class ValueParseError(ValueError):
    """사람 확인 값을 사실 컬럼 형으로 바꿀 수 없다 → 422."""


@dataclass(frozen=True)
class ClaimTarget:
    field: str
    entity: str | None
    entity_id: int | None

    @property
    def complete(self) -> bool:
        return self.entity is not None and self.entity_id is not None

    @property
    def name(self) -> str:
        return FIELD_NAMES.get(self.field, self.field)


def fields_in(text: str) -> set[str]:
    """문장에 용어가 나오는 사실 필드."""
    return {f for f, terms in FIELD_TERMS.items() if any(t in text for t in terms)}


def _evidence_fp(session: Session, claim: Claim, entity: str, field: str) -> int | None:
    """근거 출처 id(fp_<id>) 중 그 단지의 (entity, field) 행 → entity_id."""
    ids = [int(m) for m in _FP_RE.findall(claim.evidence_text or "")]
    if not ids or claim.complex_id is None:
        return None
    for fp in session.scalars(
        select(FieldProvenance).where(
            FieldProvenance.id.in_(ids), FieldProvenance.entity == entity, FieldProvenance.field == field
        )
    ):
        if fp.entity_id is None:
            continue
        row = session.get(_MODELS[entity], fp.entity_id)
        if row is not None and getattr(row, "complex_id", None) == claim.complex_id:
            return fp.entity_id
    return None


def claim_target(session: Session, claim: Claim) -> ClaimTarget | None:
    """주장이 생성된 DB 사실. 계약 컬럼이 있으면 그것, 없으면 P9 문장 형식으로 되찾는다(없으면 None)."""
    if claim.field:
        return ClaimTarget(claim.field, claim.entity, claim.entity_id)
    m = _SECTION_RE.match(claim.section or "")
    if m is None or claim.complex_id is None or int(m.group(1)) != claim.complex_id:
        return None
    found = fields_in(claim.text or "")
    if len(found) != 1:
        return None
    field = next(iter(found))
    entity = FIELD_ENTITY[field]
    if entity == "complex":
        return ClaimTarget(field, entity, claim.complex_id)
    return ClaimTarget(field, entity, _evidence_fp(session, claim, entity, field))


def _norm(name: str) -> str:
    return re.sub(r"\s+", "", name or "")


def check_same_target(session: Session, claim: Claim, text: str, target: ClaimTarget | None) -> None:
    """고친 문장이 원 주장과 같은 대상인지(D10-3). 어기면 ``TargetMismatch``(사유 문장)."""
    from app.judge.claims import split_texts

    pieces = split_texts(text) or [text]
    own = None
    others: list[str] = []
    if claim.complex_id is not None:
        cx = session.get(Complex, claim.complex_id)
        if cx is not None:
            own = _norm(cx.name)
            others = [
                _norm(n)
                for (n,) in session.execute(
                    select(Complex.name).where(Complex.region_id == cx.region_id, Complex.id != cx.id)
                )
                if n
            ]
    for piece in pieces:
        flat = _norm(piece)
        if own is not None and own not in flat:
            hit = next((o for o in others if len(o) >= 2 and o in flat), None)
            if hit is not None:
                raise TargetMismatch(f"다른 단지를 가리킨다('{piece}') — 원 주장의 단지만 고칠 수 있다")
        if target is None:
            continue
        found = fields_in(piece)
        if target.field not in found:
            raise TargetMismatch(
                f"원 주장의 대상('{target.name}')에 대한 문장이 아니다('{piece}') — 같은 사실만 고칠 수 있다"
            )
        extra = sorted(found - {target.field})
        if extra:
            names = ", ".join(f"'{FIELD_NAMES[f]}'" for f in extra)
            raise TargetMismatch(
                f"고친 문장은 원 주장과 같은 대상('{target.name}')만 말해야 한다 — {names} 용어가 있다"
            )


def checklist_title(field: str) -> str:
    return f"사실 재확인: {FIELD_NAMES.get(field, field)}(검증 모순)"


def _chosen(session: Session, entity: str, entity_id: int, field: str) -> list[FieldProvenance]:
    return list(
        session.scalars(
            select(FieldProvenance)
            .where(
                FieldProvenance.entity == entity,
                FieldProvenance.entity_id == entity_id,
                FieldProvenance.field == field,
                FieldProvenance.chosen.is_(True),
            )
            .order_by(FieldProvenance.id)
        )
    )


def _value_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return str(value)


def _active(session: Session, entity: str, entity_id: int, field: str) -> FactDemotion | None:
    return session.scalars(
        select(FactDemotion)
        .where(
            FactDemotion.entity == entity,
            FactDemotion.entity_id == entity_id,
            FactDemotion.field == field,
            FactDemotion.restored_at.is_(None),
        )
        .order_by(FactDemotion.id.desc())
    ).first()


def _complex_of(session: Session, entity: str, obj: Any) -> int | None:
    return int(obj.id) if entity == "complex" else getattr(obj, "complex_id", None)


def _checklist(session: Session, complex_id: int | None, field: str, note: str) -> ChecklistItem:
    title = checklist_title(field)
    item = session.scalars(
        select(ChecklistItem).where(
            ChecklistItem.complex_id == complex_id,
            ChecklistItem.kind == CHECKLIST_KIND,
            ChecklistItem.title == title,
        )
    ).first()
    if item is None:
        item = ChecklistItem(
            complex_id=complex_id, kind=CHECKLIST_KIND, title=title, status="open", note=note
        )
        session.add(item)
    else:
        item.status = "open"
    session.flush()
    return item


def _apply(session: Session, d: FactDemotion, obj: Any, *, now: str) -> FieldProvenance:
    """값 비움 + 강등 행 chosen(다른 chosen 행은 내림). 강등 행이 없으면 만든다."""
    for fp in _chosen(session, d.entity, d.entity_id, d.field):
        fp.chosen = False
    row = session.get(FieldProvenance, d.demotion_fp_id) if d.demotion_fp_id is not None else None
    if row is None:
        orig = session.get(FieldProvenance, d.original_fp_id) if d.original_fp_id is not None else None
        row = FieldProvenance(
            entity=d.entity,
            entity_id=d.entity_id,
            field=d.field,
            value_text=None,
            raw_document_id=None,  # 원문 없음 — 정규화가 이 행을 후보로 되살리지 않는다
            url=None,
            checked_at=now[:10],
            label=DEMOTION_LABEL,
            reason=DEMOTION_REASON,
            source_rank=orig.source_rank if orig is not None else 9,
            chosen=True,
            excerpt=f"주장 {d.claim_id} 수정 접수 — 강등 전 값 {d.original_value_text or '없음'}"[:500],
        )
        session.add(row)
        session.flush()
        d.demotion_fp_id = row.id
    row.chosen = True
    setattr(obj, d.field, None)
    session.flush()
    return row


def demote(
    session: Session, claim: Claim, target: ClaimTarget, *, rejudge: bool = True
) -> FactDemotion | None:
    """사실 강등(모듈 설명). 대상 행이 없거나 대상이 불완전하면 None. 같은 사실이 이미 강등 중이면 그 행."""
    if not target.complete or target.entity not in _MODELS:
        return None
    assert target.entity is not None and target.entity_id is not None
    model = _MODELS[target.entity]
    obj = session.get(model, target.entity_id)
    if obj is None or not hasattr(obj, target.field):
        return None
    if claim.field is None:  # 0006 이전 행·P9 미갱신 — 되찾은 대상을 저장한다
        claim.entity, claim.entity_id, claim.field = target.entity, target.entity_id, target.field
    now = now_iso()
    existing = _active(session, target.entity, target.entity_id, target.field)
    if existing is not None:
        _apply(session, existing, obj, now=now)
        return existing
    chosen = _chosen(session, target.entity, target.entity_id, target.field)
    original = chosen[-1] if chosen else None
    value = getattr(obj, target.field)
    old_text = (original.value_text if original is not None else None) or _value_text(value)
    cid = _complex_of(session, target.entity, obj)
    d = FactDemotion(
        claim_id=claim.id,
        snapshot_id=claim.snapshot_id,
        complex_id=cid,
        entity=target.entity,
        entity_id=target.entity_id,
        field=target.field,
        original_fp_id=original.id if original is not None else None,
        original_value_text=old_text,
        created_at=now,
    )
    session.add(d)
    session.flush()
    _apply(session, d, obj, now=now)
    item = _checklist(
        session,
        cid,
        target.field,
        f"주장 {claim.id} 수정 접수 — 강등 전 값 {old_text or '없음'}. 원문 확인 후 사람 확인(전화·방문)으로 "
        "입력하면 복원된다",
    )
    d.checklist_item_id = item.id
    ce = ChangeEvent(
        snapshot_id=claim.snapshot_id,
        entity=target.entity,
        entity_id=target.entity_id,
        field=target.field,
        old_text=old_text,
        new_text=f"{DEMOTION_LABEL}({DEMOTION_REASON})",
        detected_at=now,
        severity="critical",
        triggers_rejudge=True,
        complex_id=cid,
    )
    session.add(ce)
    session.flush()
    if rejudge and cid is not None:
        from app.scheduler.rejudge import enqueue_rejudge

        job = enqueue_rejudge(
            session,
            claim.snapshot_id,
            [cid],
            f"검증 모순 강등: {target.name}"[:200],
            change_event_ids=[ce.id],
        )
        d.rejudge_job_id = job.id
    session.flush()
    return d


def _parse(model: Any, field: str, text: str) -> Any:
    col = model.__table__.columns.get(field)
    if col is None:
        raise ValueParseError(f"알 수 없는 필드 {field}")
    raw = text.strip().replace(",", "")
    try:
        if isinstance(col.type, Integer):
            return int(Decimal(raw))
        if isinstance(col.type, Numeric):
            return Decimal(raw.rstrip("%"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueParseError(f"'{text}' 은 {field} 값(숫자)이 아니다") from exc
    if isinstance(col.type, String) and field.endswith("_ym") and not _YM_RE.match(raw):
        raise ValueParseError(f"'{text}' 은 연월(YYYY-MM)이 아니다")
    return raw


def restore_by_human(session: Session, hc: HumanCheck) -> list[FactDemotion]:
    """사람 확인 = 복원: 같은 단지·같은 field 의 강등을 그 값으로 되살린다(라벨 확인됨, reason '사람 확인(kind)')."""
    out: list[FactDemotion] = []
    for d in session.scalars(
        select(FactDemotion)
        .where(
            FactDemotion.complex_id == hc.complex_id,
            FactDemotion.field == hc.field,
            FactDemotion.restored_at.is_(None),
        )
        .order_by(FactDemotion.id)
    ):
        model = _MODELS.get(d.entity)
        obj = session.get(model, d.entity_id) if model is not None else None
        if obj is None:
            continue
        value = _parse(model, d.field, hc.value_text)
        for fp in _chosen(session, d.entity, d.entity_id, d.field):
            fp.chosen = False
        orig = session.get(FieldProvenance, d.original_fp_id) if d.original_fp_id is not None else None
        session.add(
            FieldProvenance(
                entity=d.entity,
                entity_id=d.entity_id,
                field=d.field,
                value_text=hc.value_text,
                raw_document_id=None,
                url=None,
                checked_at=hc.checked_at[:10],
                label="확인됨",
                reason=f"사람 확인({hc.kind})",
                source_rank=orig.source_rank if orig is not None else 0,
                chosen=True,
                excerpt=(hc.note or f"사람 확인 hc_{hc.id}")[:500],
            )
        )
        setattr(obj, d.field, value)
        _restored(session, d, "human_check", human_check_id=hc.id)
        out.append(d)
    session.flush()
    return out


def _restored(session: Session, d: FactDemotion, by: str, *, human_check_id: int | None = None) -> None:
    d.restored_at = now_iso()
    d.restored_by = by
    d.human_check_id = human_check_id
    if d.checklist_item_id is not None:
        item = session.get(ChecklistItem, d.checklist_item_id)
        if item is not None and item.status == "open":
            item.status = "done"


def sync_demotions(session: Session, complex_ids: set[int] | None = None) -> int:
    """강등 중인 사실의 chosen 출처 행이 바뀌었으면(정규화가 출처를 다시 골랐으면) 정리한다(바뀐 수).

    - 다른 원문 출처 행(raw_document 가 원래 행과 다름)이 chosen → 새 원문 = 복원('new_source').
    - 원래 행·같은 원문 행이 다시 chosen(같은 원문을 다시 정규화) → 새 원문이 아니다 → 강등을 다시 건다.
    """
    stmt = select(FactDemotion).where(FactDemotion.restored_at.is_(None))
    if complex_ids is not None:
        if not complex_ids:
            return 0
        stmt = stmt.where(FactDemotion.complex_id.in_(sorted(complex_ids)))
    n = 0
    for d in list(session.scalars(stmt.order_by(FactDemotion.id))):
        chosen = _chosen(session, d.entity, d.entity_id, d.field)
        if any(fp.id == d.demotion_fp_id for fp in chosen) and len(chosen) == 1:
            continue
        model = _MODELS.get(d.entity)
        obj = session.get(model, d.entity_id) if model is not None else None
        if obj is None:
            continue
        orig = session.get(FieldProvenance, d.original_fp_id) if d.original_fp_id is not None else None
        fresh = [
            fp
            for fp in chosen
            if fp.id != d.demotion_fp_id
            and fp.raw_document_id is not None
            and fp.id != d.original_fp_id
            and (orig is None or fp.raw_document_id != orig.raw_document_id)
        ]
        if fresh:
            demo = session.get(FieldProvenance, d.demotion_fp_id) if d.demotion_fp_id is not None else None
            if demo is not None:
                demo.chosen = False
            _restored(session, d, "new_source")
        else:
            _apply(session, d, obj, now=now_iso())
        n += 1
    session.flush()
    return n


def latest_demotions(session: Session, claim_ids: set[int]) -> dict[int, FactDemotion]:
    if not claim_ids:
        return {}
    out: dict[int, FactDemotion] = {}
    for d in session.scalars(
        select(FactDemotion).where(FactDemotion.claim_id.in_(sorted(claim_ids))).order_by(FactDemotion.id)
    ):
        out[d.claim_id] = d
    return out


def demotion_view(d: FactDemotion | None) -> dict[str, Any] | None:
    if d is None:
        return None
    return {
        "id": d.id,
        "claim_id": d.claim_id,
        "entity": d.entity,
        "entity_id": d.entity_id,
        "field": d.field,
        "status": "restored" if d.restored_at else "demoted",
        "label": DEMOTION_LABEL,
        "reason": DEMOTION_REASON,
        "created_at": d.created_at,
        "restored_at": d.restored_at,
        "restored_by": d.restored_by,
        "checklist_item_id": d.checklist_item_id,
        "rejudge_job_id": d.rejudge_job_id,
    }

"""주장 대상·사실 강등·복원 — D10-3 + D11-3 (계약 2026-10-09.8, R3 3차 리뷰 C-3·C-4·M-3·M-4·minor 9~14·20·21).

- **주장 대상**(``claim_target``): 주장이 생성된 DB 사실 (entity, entity_id, field). ``claim.entity·entity_id·field``
  (P9 가 채우는 계약 컬럼)가 있으면 그것, 없으면(0006 이전 행) P9 사실 문장 형식(section ``complex:<id>``, 필드 용어)과
  근거 출처 id(``fp_<id>``)로 되찾는다. 가격(max_price_won)은 점수·화면이 실제로 쓰는 필드(``analysis.price_view``
  현재 구매가의 max_ref — 최신 공고 ``payment_terms.price_by_type.<타입>.max_price_won``)를 대상으로 한다(M-4).
  대상이 불완전하면(entity_id 를 못 찾음) None 이 아니라 ``incomplete`` 대상 — PATCH 는 422(minor 14: 강등 없이
  reverify 로 publish 가 풀리지 않게).
- **같은 대상 검사**(``check_same_target``): 원자 주장마다 원 주장 field 용어가 있고 다른 사실 필드 용어가 없어야 하며,
  같은 지역의 다른 단지 이름만 가리키면 안 된다. 어기면 422(``TargetMismatch``).
- **강등**(``demote``): 사실 테이블 값을 **지우지 않는다**(D11-3). ``fact_demotion`` 에 모순 값(value_norm)을 기록하면
  ``app.facts_view`` 오버레이가 읽는 모든 곳(API·파이프라인·보고서·CSV)에서 그 값을 '확인 불가(검증 모순)'로 만든다.
  체크리스트 '사실 재확인', change_event(critical, triggers_rejudge), 그 단지 rejudge 잡(발행 스냅샷이면 새 리비전 — D11-1).
- **사람 확인**(``apply_human_check``): ``human_check`` 를 resolver **0순위 후보**(source_rank 0, label 확인됨, reason
  '사람 확인(kind)')로 그 필드 그룹을 다시 resolve 한다 — 사실 테이블·출처 행이 바뀌고, 같은 원문을 다시 정규화해도
  (``normalize.store._reparse_existing`` 가 사람 확인 출처 행을 후보로 되살린다) 사람 확인 값이 이긴다(C-3).
  값은 필드 형·범위를 검사한다(정수 필드에 '6.02' 거부, 개월 0~240 등 — minor 11). 같은 사실의 강등은 복원 기록.
- **복원 기록**(``sync_demotions``, 쓰기 경로 전용 — 파이프라인 시작·수집 끝·사람 확인·체크리스트 동기화): 오버레이가 풀린
  강등(chosen 이 사람 확인 / 새 출처의 **다른 값**)에 restored_at·restored_by 를 남기고 체크리스트를 닫는다. 같은 값 재수집·
  값 없는 행은 chosen 값이 그대로라 풀리지 않는다(C-4). 강등이 남았는데 사람이 '사실 재확인'을 done 으로 닫았으면 다시 연다
  (minor 12). GET 은 이 함수를 부르지 않는다(minor 13 — 읽기 전용·공유 토큰은 DB 를 쓰지 않는다).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from sqlalchemy import Integer, Numeric, select
from sqlalchemy.orm import Session

from app.api.jobs import now_iso
from app.facts_view import (
    DEMOTION_LABEL,
    DEMOTION_REASON,
    DemotionOverlay,
    load_overlay,
    logical_field,
)
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
    "HUMAN_FIELDS",
    "ClaimTarget",
    "HumanTarget",
    "TargetMismatch",
    "ValueParseError",
    "apply_human_check",
    "check_same_target",
    "checklist_title",
    "claim_target",
    "demote",
    "demotion_view",
    "fields_in",
    "human_target",
    "latest_demotions",
    "parse_human_value",
    "sync_demotions",
]

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
    "max_price_won": "complex_type",  # 최신 공고 가격이 있으면 payment_terms(price_by_type) — ``price_ref``
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
HUMAN_FIELDS: Final = (*FIELD_TERMS, "intake_status", "other")
"""POST /ops/human-checks field 값(계약 .8 HumanCheckField): 강등 가능한 사실 필드 + 접수 상태 + 기타(기록만)."""
_MODELS: Final[dict[str, Any]] = {
    "complex": Complex,
    "complex_type": ComplexType,
    "payment_terms": PaymentTerms,
}
_SECTION_RE: Final = re.compile(r"^complex:(\d+)$")
_FP_RE: Final = re.compile(r"\bfp_(\d+)\b")
_YM_RE: Final = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_PLAIN_NUMBER_RE: Final = re.compile(r"^-?\d+(?:\.\d+)?$")
"""사람 확인 숫자 = 십진 표기만(지수 '1E1'·'NaN'·'0x10' 거부)."""
# 사람 확인 값 범위(minor 11) — 형만 맞고 터무니없는 값('6.02개월'·'-3'·'2999-01')은 거부
_RANGES: Final[dict[str, tuple[Decimal, Decimal]]] = {
    "resale_months": (Decimal(0), Decimal(240)),
    "residency_months": (Decimal(0), Decimal(240)),
    "rewin_restriction_years": (Decimal(0), Decimal(20)),
    "down_payment_pct": (Decimal(0), Decimal(100)),
    "max_price_won": (Decimal(10_000_000), Decimal(100_000_000_000)),
}


class TargetMismatch(ValueError):
    """고친 문장이 원 주장과 같은 대상(section·complex·field)이 아니다(D10-3) → 422."""


class ValueParseError(ValueError):
    """사람 확인 값을 사실 컬럼 형·범위로 바꿀 수 없다 → 422."""


@dataclass(frozen=True)
class ClaimTarget:
    field: str  # 출처 필드 경로(가격은 'price_by_type.<타입>.max_price_won' 일 수 있다)
    entity: str | None
    entity_id: int | None

    @property
    def complete(self) -> bool:
        return self.entity is not None and self.entity_id is not None

    @property
    def logical(self) -> str:
        return logical_field(self.field)

    @property
    def name(self) -> str:
        return FIELD_NAMES.get(self.logical, self.logical)


@dataclass(frozen=True)
class HumanTarget:
    entity: str
    entity_id: int
    field: str  # 출처 필드 경로


def fields_in(text: str) -> set[str]:
    """문장에 용어가 나오는 사실 필드(논리 이름)."""
    return {f for f, terms in FIELD_TERMS.items() if any(t in text for t in terms)}


def price_ref(session: Session, complex_id: int) -> tuple[str, int, str] | None:
    """점수·화면이 쓰는 기준 타입 최고 공급금액의 출처 필드(``analysis.price_view.current_price``.max_ref)."""
    from app.analysis.price_view import current_price

    types = list(session.scalars(select(ComplexType).where(ComplexType.complex_id == complex_id)))
    terms = list(session.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == complex_id)))
    ref = current_price(types, terms, discount_label=None).max_ref  # 최고가 출처만(할인 무관)
    return (ref.entity, ref.entity_id, ref.field) if ref is not None else None


def _current_terms_id(session: Session, complex_id: int) -> int | None:
    from app.analysis.price_view import current_terms

    cur = current_terms(
        list(session.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == complex_id)))
    )
    return cur.id if cur is not None else None


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
    """주장이 생성된 DB 사실. 계약 컬럼이 있으면 그것(대상이 불완전하면 지금 사실로 채운다), 없으면 P9 문장 형식으로
    되찾는다. 사실 문장이 아니면 None."""
    if claim.field:
        target = ClaimTarget(claim.field, claim.entity, claim.entity_id)
        return target if target.complete else _fill(session, claim, target.logical)
    m = _SECTION_RE.match(claim.section or "")
    if m is None or claim.complex_id is None or int(m.group(1)) != claim.complex_id:
        return None
    found = fields_in(claim.text or "")
    if len(found) != 1:
        return None
    return _fill(session, claim, next(iter(found)))


def _fill(session: Session, claim: Claim, logical: str) -> ClaimTarget:
    """논리 필드 → 지금 사실의 대상 행. 못 찾으면 entity_id None(불완전)."""
    cid = claim.complex_id
    entity = FIELD_ENTITY.get(logical)
    if cid is None or entity is None:
        return ClaimTarget(logical, entity, None)
    if entity == "complex":
        return ClaimTarget(logical, "complex", cid)
    if logical == "max_price_won":
        ref = price_ref(session, cid)
        if ref is not None:
            return ClaimTarget(ref[2], ref[0], ref[1])
        return ClaimTarget(logical, entity, _evidence_fp(session, claim, entity, logical))
    eid = _evidence_fp(session, claim, entity, logical)
    if eid is None and entity == "payment_terms":
        eid = _current_terms_id(session, cid)
    return ClaimTarget(logical, entity, eid)


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
        if target.logical not in found:
            raise TargetMismatch(
                f"원 주장의 대상('{target.name}')에 대한 문장이 아니다('{piece}') — 같은 사실만 고칠 수 있다"
            )
        extra = sorted(found - {target.logical})
        if extra:
            names = ", ".join(f"'{FIELD_NAMES[f]}'" for f in extra)
            raise TargetMismatch(
                f"고친 문장은 원 주장과 같은 대상('{target.name}')만 말해야 한다 — {names} 용어가 있다"
            )


def checklist_title(field: str) -> str:
    logical = logical_field(field)
    return f"사실 재확인: {FIELD_NAMES.get(logical, logical)}(검증 모순)"


def _chosen(session: Session, entity: str, entity_id: int, field: str) -> FieldProvenance | None:
    return session.scalars(
        select(FieldProvenance)
        .where(
            FieldProvenance.entity == entity,
            FieldProvenance.entity_id == entity_id,
            FieldProvenance.field == field,
            FieldProvenance.chosen.is_(True),
        )
        .order_by(FieldProvenance.id)
    ).first()


def _current_value(obj: Any, field: str) -> Any:
    """사실 행의 현재 값(price_by_type 경로 포함)."""
    from app.normalize.fields import split_price_by_type

    pbt = split_price_by_type(field)
    if pbt is not None:
        entry = (getattr(obj, "price_by_type", None) or {}).get(pbt[0]) or {}
        return entry.get(pbt[1]) if isinstance(entry, dict) else None
    return getattr(obj, field, None)


def _has_field(obj: Any, field: str) -> bool:
    from app.normalize.fields import split_price_by_type

    return (split_price_by_type(field) is not None and hasattr(obj, "price_by_type")) or hasattr(obj, field)


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


def _complex_of(entity: str, obj: Any) -> int | None:
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
        item.closed_by = None
    session.flush()
    return item


def demote(
    session: Session, claim: Claim, target: ClaimTarget, *, rejudge: bool = True
) -> FactDemotion | None:
    """사실 강등(모듈 설명) — 사실 테이블은 그대로 두고 모순 값을 기록한다. 대상 행이 없거나 불완전하면 None.

    같은 사실이 같은 모순 값으로 이미 강등 중이면 그 행(같은 사실의 두 번째 주장 — ``latest_demotions`` 가 대상으로 찾는다)."""
    if not target.complete or target.entity not in _MODELS:
        return None
    assert target.entity is not None and target.entity_id is not None
    obj = session.get(_MODELS[target.entity], target.entity_id)
    if obj is None or not _has_field(obj, target.field):
        return None
    if claim.field is None or claim.entity_id is None:  # 0006 이전 행·불완전 대상 — 되찾은 대상을 저장
        claim.entity, claim.entity_id, claim.field = target.entity, target.entity_id, target.field
    from app.normalize.fields import norm_value

    chosen = _chosen(session, target.entity, target.entity_id, target.field)
    value = _current_value(obj, target.field)
    value_norm = (
        chosen.value_norm
        if chosen is not None and chosen.value_norm is not None
        else norm_value(float(value) if isinstance(value, Decimal) else value)
    )
    existing = _active(session, target.entity, target.entity_id, target.field)
    if existing is not None and existing.value_norm == value_norm:
        return existing
    now = now_iso()
    old_text = (chosen.value_text if chosen is not None else None) or _value_text(value)
    cid = _complex_of(target.entity, obj)
    d = FactDemotion(
        claim_id=claim.id,
        snapshot_id=claim.snapshot_id,
        complex_id=cid,
        entity=target.entity,
        entity_id=target.entity_id,
        field=target.field,
        original_fp_id=chosen.id if chosen is not None else None,
        demotion_fp_id=None,  # 0008: 강등 출처 행을 만들지 않는다(읽기 시점 오버레이)
        original_value_text=old_text,
        value_norm=value_norm,
        created_at=now,
    )
    session.add(d)
    session.flush()
    item = _checklist(
        session,
        cid,
        target.field,
        f"주장 {claim.id} 수정 접수 — 모순 값 {old_text or '없음'}. 원문 확인 후 사람 확인(전화·방문)으로 입력하거나 "
        "새 원문이 다른 값을 내면 복원된다",
    )
    d.checklist_item_id = item.id
    # 발행 스냅샷은 불변(D11-1) — 변경 이벤트·재판정은 그 지역 가장 새 (기준일, 리비전)의 쓰기 가능 리비전에(R3 4차 minor·M-2)
    from app.models import Snapshot
    from app.scheduler.snapshots import latest_for_region, writable

    base_snap = session.get(Snapshot, claim.snapshot_id)
    newest = latest_for_region(session, base_snap.region_id) if base_snap is not None else None
    snap_w = (
        writable(session, newest.id, reason=f"검증 모순 강등: {target.name}"[:200], created_at=now)
        if newest
        else None
    )
    ce = ChangeEvent(
        snapshot_id=snap_w.id if snap_w is not None else claim.snapshot_id,
        entity=target.entity,
        entity_id=target.entity_id,
        field=target.field[:64],
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
            snap_w.id if snap_w is not None else claim.snapshot_id,
            [cid],
            f"검증 모순 강등: {target.name}"[:200],
            change_event_ids=[ce.id],
        )
        d.rejudge_job_id = job.id
    from app.normalize.checklist import sync_checklist_for

    sync_checklist_for(session, [cid] if cid is not None else [])
    session.flush()
    return d


# ---------------------------------------------------------------- 사람 확인 (resolver 0순위 후보)


def human_target(
    session: Session, complex_id: int, field: str, entity_id: int | None = None
) -> HumanTarget | None:
    """사람 확인 field(논리) → 사실 행. 접수 상태·기타는 None(사실 행 없음). 찾을 수 없으면 ``ValueParseError``."""
    if field not in FIELD_TERMS:
        return None
    entity = FIELD_ENTITY[field]
    if entity == "complex":
        if entity_id is not None and entity_id != complex_id:
            raise ValueParseError(f"entity_id {entity_id} 는 단지 {complex_id} 의 행이 아니다")
        return HumanTarget("complex", complex_id, field)
    if field == "max_price_won":
        ref = price_ref(session, complex_id)
        if entity_id is not None:
            # R3 4차 M-11: complex_type·payment_terms 가 같은 id 번호면 화면·점수가 쓰는 행(현재 구매가 max_ref)이 이긴다 —
            # 예전에는 complex_type 을 먼저 봐서 현재 공고 가격 강등이 풀리지 않았다
            if ref is not None and ref[1] == entity_id:
                return HumanTarget(ref[0], ref[1], ref[2])
            pt = session.get(PaymentTerms, entity_id)
            if (
                pt is not None
                and pt.complex_id == complex_id
                and ref is not None
                and ref[0] == "payment_terms"
            ):
                return HumanTarget("payment_terms", pt.id, ref[2])
            t = session.get(ComplexType, entity_id)
            if t is not None and t.complex_id == complex_id:
                return HumanTarget("complex_type", t.id, "max_price_won")
            raise ValueParseError(f"entity_id {entity_id} 는 단지 {complex_id} 의 가격 행이 아니다")
        if ref is None:
            raise ValueParseError("이 단지에는 기준 타입 가격 행이 없다 — 사람 확인 대상을 정할 수 없다")
        return HumanTarget(ref[0], ref[1], ref[2])
    # down_payment_pct → 현재 납부 조건(또는 지정 행)
    if entity_id is not None:
        pt = session.get(PaymentTerms, entity_id)
        if pt is None or pt.complex_id != complex_id:
            raise ValueParseError(f"entity_id {entity_id} 는 단지 {complex_id} 의 납부 조건이 아니다")
        return HumanTarget("payment_terms", pt.id, field)
    tid = _current_terms_id(session, complex_id)
    if tid is None:
        raise ValueParseError("이 단지에는 납부 조건 행이 없다 — 사람 확인 대상을 정할 수 없다")
    return HumanTarget("payment_terms", tid, field)


def parse_human_value(target: HumanTarget, text: str) -> int | float | str:
    """사람 확인 값 → 사실 값(형·범위 검사, minor 11). 못 바꾸면 ``ValueParseError``."""
    logical = logical_field(target.field)
    raw = text.strip().replace(",", "").replace(" ", "")
    if logical.endswith("_ym"):
        m = _YM_RE.match(raw)
        if m is None or not 2000 <= int(m.group(1)) <= 2100:
            raise ValueParseError(f"'{text}' 은 연월(YYYY-MM, 2000~2100)이 아니다")
        return raw
    model = _MODELS[target.entity]
    col = model.__table__.columns.get(logical)
    integer = logical == "max_price_won" or (col is not None and isinstance(col.type, Integer))
    numeric = integer or (col is not None and isinstance(col.type, Numeric))
    if not numeric:
        raise ValueParseError(f"알 수 없는 필드 {target.field}")
    # 단위 접미어는 그 필드의 단위만(R3 4차 minor: '3년'이 3개월로, '1E1'이 10으로 들어갔다). 개월 필드의 'N년'은 N×12
    allowed = {"resale_months": ("개월", "년"), "residency_months": ("개월", "년"), "max_price_won": ("원",),
               "down_payment_pct": ("%",)}.get(logical, ())  # fmt: skip
    factor = 1
    for suffix in allowed:
        if raw.endswith(suffix):
            raw = raw.removesuffix(suffix)
            factor = 12 if suffix == "년" else 1
            break
    if not _PLAIN_NUMBER_RE.match(raw):
        raise ValueParseError(
            f"'{text}' 은 {FIELD_NAMES.get(logical, logical)} 값(숫자, 단위 {', '.join(allowed) or '없음'})이 아니다"
        )
    try:
        dec = Decimal(raw) * factor
    except (InvalidOperation, ValueError) as exc:
        raise ValueParseError(f"'{text}' 은 {FIELD_NAMES.get(logical, logical)} 값(숫자)이 아니다") from exc
    if not dec.is_finite():
        raise ValueParseError(f"'{text}' 은 유한한 숫자가 아니다")
    if integer and dec != dec.to_integral_value():
        raise ValueParseError(
            f"'{text}' 은 정수가 아니다({FIELD_NAMES.get(logical, logical)}) — 소수를 자르지 않는다"
        )
    lo, hi = _RANGES.get(logical, (Decimal("-1e18"), Decimal("1e18")))
    if not lo <= dec <= hi:
        raise ValueParseError(f"'{text}' 은 {FIELD_NAMES.get(logical, logical)} 범위({lo}~{hi}) 밖이다")
    if integer:
        return int(dec)
    if dec.as_tuple().exponent < -2:  # type: ignore[operator]
        raise ValueParseError(f"'{text}' 은 소수 둘째 자리까지만 받는다")
    return float(dec)


def apply_human_check(
    session: Session, hc: HumanCheck, *, snapshot_id: int | None = None
) -> list[FactDemotion]:
    """사람 확인 = resolver 0순위 후보로 그 필드 그룹을 다시 resolve(사실 테이블·출처 행) + 같은 사실 강등 복원 기록.

    ``hc.entity·entity_id``(``human_target`` 이 채움)와 ``hc.field``(논리)가 사실 행을 가리켜야 한다."""
    if hc.entity is None or hc.entity_id is None or hc.field not in FIELD_TERMS:
        return []
    target = human_target(session, hc.complex_id, hc.field, hc.entity_id)
    if target is None:
        return []
    value = parse_human_value(target, hc.value_text)
    from app.core.contracts_gen import FieldCandidate
    from app.normalize.store import resolve_field_group

    stamp = hc.created_at or now_iso()
    cand = FieldCandidate.model_validate(
        {
            "entity": target.entity,
            "entity_id": target.entity_id,
            "entity_key": None,
            "field": target.field,
            "value_text": hc.value_text.strip()[:200],
            "value": value,
            "source_rank": 0,
            "source_kind": None,
            "primary": True,
            "label": "확인됨",
            "reason": f"사람 확인({hc.kind})",
            "excerpt": (hc.note or f"사람 확인 hc_{hc.id} ({hc.entered_by})")[:500],
            "excerpt_start": None,
            "excerpt_end": None,
            "raw_document_id": None,
            "url": None,
            "checked_at": stamp,  # 같은 필드의 사람 확인이 여럿이면 최신이 이긴다(resolver 최신 규칙)
            "observed_on": hc.checked_at[:10],
            "needs_extract": False,
        }
    )
    resolve_field_group(
        session, target.entity, target.entity_id, target.field, [cand], snapshot_id=snapshot_id
    )
    # 같은 의미 필드(D12-2)의 강등 중 지금 쓰는 행이 사람 확인이 된 것만 복원 기록(옛 공고 행을 확인해도 현재 사실은 그대로)
    from app.facts_view import RESTORED_HUMAN

    session.flush()
    out: list[FactDemotion] = []
    ov = load_overlay(session, complex_ids=[hc.complex_id])
    for d in ov.demotions:
        if ov.status.get(d.id) == RESTORED_HUMAN and d.restored_by != RESTORED_HUMAN:
            _restored(session, d, RESTORED_HUMAN, human_check_id=hc.id)
            out.append(d)
    session.flush()
    from app.normalize.checklist import sync_checklist_for

    sync_checklist_for(session, [hc.complex_id])
    return out


def _restored(session: Session, d: FactDemotion, by: str, *, human_check_id: int | None = None) -> None:
    d.restored_at = now_iso()
    d.restored_by = by
    d.human_check_id = human_check_id
    if d.checklist_item_id is not None:
        item = session.get(ChecklistItem, d.checklist_item_id)
        if item is not None and item.status == "open":
            item.status = "done"
            item.closed_by = "auto"


def _redemote(session: Session, d: FactDemotion) -> None:
    """새 출처로 풀렸던 강등의 모순 값이 다시 지금 쓰는 값이 됐다(compare 재채택 등, R3 4차 M-17) → 다시 강등 기록."""
    d.restored_at = None
    d.restored_by = None
    d.human_check_id = None
    if d.checklist_item_id is not None:
        item = session.get(ChecklistItem, d.checklist_item_id)
        if item is not None:
            item.status, item.closed_by = "open", None
    session.add(
        ChangeEvent(
            snapshot_id=d.snapshot_id,
            entity=d.entity,
            entity_id=d.entity_id,
            field=d.field[:64],
            old_text=d.original_value_text,
            new_text=f"{DEMOTION_LABEL}({DEMOTION_REASON}) — 모순 값이 다시 채택됨",
            detected_at=now_iso(),
            severity="critical",
            triggers_rejudge=True,
            complex_id=d.complex_id,
        )
    )


def sync_demotions(session: Session, complex_ids: set[int] | None = None) -> int:
    """쓰기 경로 전용: 강등 상태(``facts_view`` 오버레이 — 지금 쓰는 행 기준, D12-2)를 기록과 맞춘다. 바뀐 수.

    - 지금 쓰는 행이 사람 확인 → 복원 'human_check'(사람 확인 입력 API 가 이미 기록했으면 건너뜀)
    - 지금 쓰는 행이 원문의 **다른 값** → 복원 'new_source'
    - 그대로 모순 값·값 없음·채택 보류(같은 값 재수집·새 공고 같은 값 — C-4·C-1·M-17) → 강등 유지, 닫힌 '사실 재확인'은
      다시 연다(minor 12)
    - 'new_source' 로 풀렸는데 모순 값이 다시 지금 쓰는 값 → 재강등(M-17)
    """
    if complex_ids is not None and not complex_ids:
        return 0
    from app.facts_view import STATUS_DEMOTED

    ov = load_overlay(session, complex_ids=complex_ids)
    n = 0
    for d in ov.demotions:
        st = ov.status.get(d.id, STATUS_DEMOTED)
        if st == STATUS_DEMOTED:
            if d.restored_at is not None:
                _redemote(session, d)
                n += 1
                continue
            if d.checklist_item_id is not None:
                item = session.get(ChecklistItem, d.checklist_item_id)
                if item is not None and item.status != "open":
                    item.status, item.closed_by = "open", None  # minor 12: 강등이 남았으면 다시 연다
                    n += 1
            continue
        if d.restored_at is None:
            _restored(session, d, st)
            n += 1
    session.flush()
    return n


def latest_demotions(
    session: Session, claims: list[Claim], targets: dict[int, ClaimTarget | None] | None = None
) -> dict[int, FactDemotion]:
    """주장 id → 그 주장의 강등(없으면 같은 사실(대상)의 최신 강등 — minor 9: 같은 사실의 두 번째 주장).
    대상 = ``targets``(``claim_target`` — 계약 컬럼이 빈 옛 주장도 문장 형식으로 되찾은 것) 또는 claim 컬럼."""
    if not claims:
        return {}
    out: dict[int, FactDemotion] = {}
    ids = sorted({c.id for c in claims})
    for d in session.scalars(
        select(FactDemotion).where(FactDemotion.claim_id.in_(ids)).order_by(FactDemotion.id)
    ):
        out[d.claim_id] = d
    want: dict[int, tuple[str, int, str]] = {}
    for c in claims:
        if c.id in out:
            continue
        t = (targets or {}).get(c.id)
        if t is not None and t.entity is not None and t.entity_id is not None:
            want[c.id] = (t.entity, t.entity_id, t.field)
        elif c.entity and c.entity_id is not None and c.field:
            want[c.id] = (c.entity, c.entity_id, c.field)
    if want:
        by_target: dict[tuple[str, int, str], FactDemotion] = {}
        for d in session.scalars(
            select(FactDemotion)
            .where(FactDemotion.entity_id.in_(sorted({k[1] for k in want.values()})))
            .order_by(FactDemotion.id)
        ):
            by_target[(d.entity, d.entity_id, d.field)] = d
        for cid, key in want.items():
            hit = by_target.get(key)
            if hit is not None:
                out[cid] = hit
    return out


def demotion_view(d: FactDemotion | None, overlay: DemotionOverlay | None = None) -> dict[str, Any] | None:
    """FactDemotion 계약 모양. status 는 읽는 순간의 오버레이(복원 기록 전이라도 풀렸으면 'restored')."""
    if d is None:
        return None
    from app.facts_view import STATUS_DEMOTED

    restored = overlay.state(d) != STATUS_DEMOTED if overlay is not None else d.restored_at is not None
    return {
        "id": d.id,
        "claim_id": d.claim_id,
        "entity": d.entity,
        "entity_id": d.entity_id,
        "field": d.field,
        "status": "restored" if restored else "demoted",
        "label": DEMOTION_LABEL,
        "reason": DEMOTION_REASON,
        "created_at": d.created_at,
        "restored_at": d.restored_at,
        "restored_by": d.restored_by,
        "checklist_item_id": d.checklist_item_id,
        "rejudge_job_id": d.rejudge_job_id,
    }


def overlay_for(session: Session, complex_ids: set[int] | None = None) -> DemotionOverlay:
    return load_overlay(session, complex_ids=complex_ids)

"""판정기 결과 → 사실 테이블·출처 행 반영 (WP2, 계약 2026-10-09.3).

여기서는 판단하지 않는다. WP3 봉투가 정한 것(extract 필드 decision, audit flagged, compare relation)을 그대로
옮기고, 값 문자열을 형으로 바꾸는 파싱(정규식 — 판단 아님, AGENTS 규칙 3)과 RA §3 우선순위만 쓴다.

``apply_extracted`` — P2 extract(+ P3 audit) 결과를 ``needs_extract`` 필드에 반영한다.
  입력 = ``ExtractRequest``(어느 원문·엔티티·필드) + 필드별 값·decision + extract judgment_seq (+ audit 표시).
  - extract decision=auto, audit 통과 → 라벨 '확인됨', reason '판정기 추출 jl_<n>·감사 jl_<m>'
  - extract decision=auto, audit 없음(미호출·미해결) → 라벨 '추정', reason '판정기 추출 jl_<n>(감사 전)'
  - extract decision=review → 미반영(원래 '확인 불가' 출처 행 그대로)
  - audit flagged → 미반영: 추출 출처 행은 '확인 불가', reason '판정기 감사 flagged jl_<m> — 원문 대조 필요'
    (이미 반영된 값이면 사실 테이블 값도 거둔다 — 다른 출처가 있으면 그 값)
  추출 출처 행은 원래 needs_extract 출처 행과 같은 원문·발췌·rank 로 새 행 1개(재실행이면 그 행을 갱신).
  채택은 그 필드의 모든 출처를 다시 resolve(RA §3) 해서 정한다.

``apply_compare`` — P5 compare 가 contradicts 면 1차 공고 자료(공고문·청약홈)를 채택하고 나머지는 병기한다
  (chosen 변경 + 사실 테이블 값 + change_event). conflict_group 은 그대로 둔다(상충 이력). 1차 공고 자료가
  없으면(둘 다 2차) 채택을 바꾸지 않고 병기 표시만 한다(meta §2-1 P5).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contracts_gen import FieldCandidate
from app.models import ChangeEvent, Complex, FieldProvenance, RawDocument
from app.normalize import changes
from app.normalize._text import parse_date
from app.normalize.extract_request import ExtractRequest
from app.normalize.fields import INT_FIELDS, norm_value, split_price_by_type
from app.normalize.living_area import assign_complex_area
from app.normalize.provenance import upsert_provenance
from app.normalize.resolver import resolve
from app.normalize.store import _MODELS, candidate_from_row, write_chosen

__all__ = [
    "AUDIT_FLAG_REASON",
    "COMPARE_PRIMARY_SOURCES",
    "EXTRACT_REASON",
    "AuditMark",
    "CompareApplyResult",
    "ExtractApplyResult",
    "ExtractedValue",
    "apply_compare",
    "apply_extracted",
    "parse_extracted",
]

EXTRACT_REASON: Final = "판정기 추출"
AUDIT_FLAG_REASON: Final = "판정기 감사 flagged"
COMPARE_PRIMARY_SOURCES: Final = frozenset({"notice_pdf", "applyhome_detail", "applyhome_list"})
"""P5 contradicts 때 채택할 '1차 자료'(공고문·청약홈, meta §2-1)."""
_COMPARE_SIDE: Final = "판정기 compare 상충"
_REASON_MAX: Final = 120

_WON_FIELDS: Final = frozenset(
    {
        "max_price_won",
        "floor_sample_price_won",
        "balcony_won",
        "options_required_won",
        "down_payment_first_won",
    }
)
_PCT_FIELDS: Final = frozenset({"down_payment_pct", "interim_pct", "balance_pct"})
_MONTH_FIELDS: Final = frozenset({"resale_months", "residency_months"})
_DATE_FIELDS: Final = frozenset({"effective_from", "notice_date", "winner_date"})
_NUM_RE: Final = re.compile(r"[0-9][0-9,]*(?:\.[0-9]+)?")
_EOK_RE: Final = re.compile(r"([0-9][0-9,]*)\s*억(?:\s*([0-9][0-9,]*)\s*만)?")
_YM_RE: Final = re.compile(r"(20[0-9]{2})\s*[.\-/년]\s*([0-9]{1,2})")
_NONE_RE: Final = re.compile(r"없음|해당\s*없|미적용|비대상")


# ====================================================================== 값 파싱 (판단 아님)


def _dec(text: str) -> Decimal | None:
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None


def _won(text: str) -> int | None:
    m = _EOK_RE.search(text)
    if m:
        eok, man = _dec(m.group(1)), _dec(m.group(2) or "0")
        if eok is None or man is None:
            return None
        return int(eok * 100_000_000 + man * 10_000)
    n = _NUM_RE.search(text)
    if n is None:
        return None
    v = _dec(n.group(0))
    if v is None:
        return None
    tail = text[n.end() :].lstrip()
    if tail.startswith("만"):
        v *= 10_000
    elif tail.startswith("천"):
        v *= 1_000
    return int(v)


def _months(text: str, *, years: bool = False) -> int | None:
    n = _NUM_RE.search(text)
    if n is None:
        return 0 if _NONE_RE.search(text) else None
    v = _dec(n.group(0))
    if v is None:
        return None
    tail = text[n.end() :].lstrip()
    in_years = tail.startswith("년")
    in_months = tail.startswith("개월")
    if years:
        if in_months:
            return int(v / 12) if v % 12 == 0 else None
        return int(v)
    return int(v * 12) if in_years else int(v)


def parse_extracted(field_name: str, value_text: str | None) -> int | float | str | None:
    """판정기 extract 값 문자열 → 필드 형(원·%·개월·날짜·연월·세대). 못 읽으면 None(반영하지 않는다)."""
    if value_text is None or not value_text.strip():
        return None
    text = value_text.strip()
    pbt = split_price_by_type(field_name)
    item = pbt[1] if pbt is not None else field_name
    if item in _WON_FIELDS:
        return _won(text)
    if item in _PCT_FIELDS:
        n = _NUM_RE.search(text)
        d = _dec(n.group(0)) if n else None
        return float(d) if d is not None else None
    if item in _MONTH_FIELDS:
        return _months(text)
    if item == "rewin_restriction_years":
        return _months(text, years=True)
    if item in _DATE_FIELDS:
        return parse_date(text)
    if item == "move_in_ym":
        m = _YM_RE.search(text)
        if m is None or not 1 <= int(m.group(2)) <= 12:
            return None
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    if item in INT_FIELDS:
        n = _NUM_RE.search(text)
        d = _dec(n.group(0)) if n else None
        return int(d) if d is not None and d == d.to_integral_value() else None
    return None


# ====================================================================== 공통


def _kinds(session: Session, rows: Sequence[FieldProvenance]) -> dict[int, str | None]:
    out: dict[int, str | None] = {}
    for rid in {r.raw_document_id for r in rows if r.raw_document_id is not None}:
        raw = session.get(RawDocument, rid)
        out[rid] = raw.source_kind if raw is not None else None
    return out


def _candidate(fp: FieldProvenance, kind: str | None) -> FieldCandidate:
    """출처 행 → 후보. value_norm 이 없는 옛 행(값 있음)은 value_text 를 값으로 본다(비교용)."""
    c = candidate_from_row(fp, kind)
    if c.value is None and fp.value_text and fp.label != "확인 불가":
        c = c.model_copy(update={"value": fp.value_text})
    return c


def _group_rows(session: Session, entity: str, entity_id: int, field_name: str) -> list[FieldProvenance]:
    return list(
        session.scalars(
            select(FieldProvenance)
            .where(
                FieldProvenance.entity == entity,
                FieldProvenance.entity_id == entity_id,
                FieldProvenance.field == field_name,
            )
            .order_by(FieldProvenance.id)
        )
    )


def _clear_value(
    session: Session,
    entity: str,
    entity_id: int,
    field_name: str,
    *,
    snapshot_id: int | None,
    detected_at: str,
) -> ChangeEvent | None:
    """채택할 값이 없어졌다 → 사실 테이블 값을 거둔다(price_by_type 항목은 건드리지 않는다)."""
    model = _MODELS.get(entity)
    if model is None or split_price_by_type(field_name) is not None or not hasattr(model, field_name):
        return None
    obj = session.get(model, entity_id)
    if obj is None or getattr(obj, field_name) is None:
        return None
    old = getattr(obj, field_name)
    setattr(obj, field_name, None)
    cid = obj.id if entity == "complex" else getattr(obj, "complex_id", None)
    return changes.value_change_event(
        entity=entity,
        entity_id=entity_id,
        field=field_name,
        old=old,
        new=None,
        snapshot_id=snapshot_id,
        complex_id=cid,
        detected_at=detected_at,
        initial=False,
    )


def _reresolve(
    session: Session,
    entity: str,
    entity_id: int,
    field_name: str,
    *,
    snapshot_id: int | None,
    detected_at: str,
) -> tuple[FieldProvenance | None, list[ChangeEvent]]:
    """그 필드의 모든 출처를 다시 resolve(RA §3) → chosen·conflict_group 갱신 + 사실 테이블 값."""
    rows = _group_rows(session, entity, entity_id, field_name)
    kinds = _kinds(session, rows)
    cands = [_candidate(fp, kinds.get(fp.raw_document_id or -1)) for fp in rows]
    resolved = resolve(cands)
    fps = upsert_provenance(session, list(resolved.provenance))
    chosen_fp = next((fp for fp in fps if fp.chosen), None)
    events: list[ChangeEvent] = []
    chosen = resolved.chosen[0] if resolved.chosen else None
    if chosen is not None and chosen.value is not None and chosen.label != "확인 불가":
        written, touched = write_chosen(session, [chosen], snapshot_id=snapshot_id, detected_at=detected_at)
        events.extend(written)
        for cid in sorted(touched):
            cx = session.get(Complex, cid)
            if cx is not None:
                assign_complex_area(session, cx)
    else:
        ev = _clear_value(
            session, entity, entity_id, field_name, snapshot_id=snapshot_id, detected_at=detected_at
        )
        if ev is not None:
            events.append(ev)
    session.add_all(events)
    session.flush()
    return chosen_fp, events


# ====================================================================== extract (+ audit)


@dataclass(frozen=True, slots=True)
class ExtractedValue:
    """판정기 extract 필드 1개(정규화 봉투 ``result.fields[]``): 필드 이름·값 문자열·decision(auto|review)."""

    field: str
    value_text: str | None
    decision: str | None


@dataclass(frozen=True, slots=True)
class AuditMark:
    """판정기 audit 레코드 1개(정규화 봉투 ``result.items[]``): flagged·p_wrong."""

    flagged: bool
    p_wrong: float | None = None


@dataclass
class ExtractApplyResult:
    applied: dict[str, int] = field(default_factory=dict)  # 필드 → 반영한 출처 행 id
    flagged: dict[str, int] = field(default_factory=dict)  # 필드 → '확인 불가(감사 flagged)' 출처 행 id
    skipped: dict[str, str] = field(default_factory=dict)  # 필드 → 사유(review·형식 해석 실패·대상 행 없음)
    change_events: list[ChangeEvent] = field(default_factory=list)


def _jl(seq: int | None) -> str:
    return f"jl_{seq}" if seq is not None else "jl_?"


def apply_extracted(
    session: Session,
    request: ExtractRequest,
    values: Sequence[ExtractedValue],
    *,
    judgment_seq: int | None,
    audit: Mapping[str, AuditMark] | None = None,
    audit_seq: int | None = None,
    snapshot_id: int | None = None,
    now: datetime | None = None,
) -> ExtractApplyResult:
    """extract(+audit) 결과를 그 원문의 needs_extract 필드에 반영한다(모듈 설명의 라벨 규칙).

    commit 은 호출자.
    """
    detected_at = changes.detected_now(now)
    out = ExtractApplyResult()
    wanted = set(request.fields)
    with session.begin_nested():
        for v in values:
            if v.field not in wanted:
                out.skipped[v.field] = "요청 밖 필드"
                continue
            rows = list(
                session.scalars(
                    select(FieldProvenance)
                    .where(
                        FieldProvenance.entity == request.entity,
                        FieldProvenance.entity_key == request.entity_key,
                        FieldProvenance.field == v.field,
                        FieldProvenance.raw_document_id == request.raw_document_id,
                    )
                    .order_by(FieldProvenance.id)
                )
            )
            judged = next(
                (r for r in rows if (r.reason or "").startswith((EXTRACT_REASON, AUDIT_FLAG_REASON))),
                None,
            )
            origin = next((r for r in rows if r is not judged and r.label == "확인 불가"), None)
            base = origin or judged
            if base is None or base.entity_id is None:
                out.skipped[v.field] = "대상 출처 행 없음"
                continue
            if v.decision != "auto":
                out.skipped[v.field] = "review(미반영)"
                continue
            if not (v.value_text or "").strip():
                out.skipped[v.field] = "값 없음(판정기 not_found)"
                continue
            mark = (audit or {}).get(v.field)
            if mark is not None and mark.flagged:
                label, value, reason = (
                    "확인 불가",
                    None,
                    f"{AUDIT_FLAG_REASON} {_jl(audit_seq)} — 원문 대조 필요",
                )
            else:
                value = parse_extracted(v.field, v.value_text)
                if value is None:
                    out.skipped[v.field] = "형식 해석 실패"
                    continue
                if mark is not None:
                    label, reason = "확인됨", f"{EXTRACT_REASON} {_jl(judgment_seq)}·감사 {_jl(audit_seq)}"
                else:
                    label, reason = "추정", f"{EXTRACT_REASON} {_jl(judgment_seq)}(감사 전)"
            row = judged
            if row is None:
                row = FieldProvenance(
                    entity=base.entity,
                    entity_id=base.entity_id,
                    entity_key=base.entity_key,
                    field=base.field,
                    raw_document_id=base.raw_document_id,
                    url=base.url,
                    checked_at=base.checked_at,
                    source_rank=base.source_rank,
                    chosen=False,
                    excerpt=base.excerpt,
                    excerpt_start=base.excerpt_start,
                    excerpt_end=base.excerpt_end,
                    observed_on=base.observed_on,
                )
                session.add(row)
            row.value_text = (v.value_text or "").strip()[:500] or None
            row.value_norm = norm_value(value)
            row.label = label
            row.reason = reason[:_REASON_MAX]
            session.flush()
            _, events = _reresolve(
                session,
                base.entity,
                base.entity_id,
                base.field,
                snapshot_id=snapshot_id,
                detected_at=detected_at,
            )
            out.change_events.extend(events)
            if label == "확인 불가":
                out.flagged[v.field] = row.id
            else:
                out.applied[v.field] = row.id
    return out


# ====================================================================== compare


@dataclass
class CompareApplyResult:
    conflict_group: str
    relation: str | None
    changed: bool = False
    chosen_id: int | None = None
    side_ids: list[int] = field(default_factory=list)  # 병기(채택 안 됨) 출처 행
    note: str = ""
    change_events: list[ChangeEvent] = field(default_factory=list)


def _recency(fp: FieldProvenance) -> tuple[int, str, str, int]:
    return (-fp.source_rank, fp.observed_on or "", fp.checked_at or "", fp.id)


def apply_compare(
    session: Session,
    conflict_group: str,
    *,
    relation: str | None,
    judgment_seq: int | None,
    snapshot_id: int | None = None,
    now: datetime | None = None,
) -> CompareApplyResult:
    """P5 결과 반영. contradicts → 1차 공고 자료 채택(이미 채택이면 유지)·나머지 병기.

    그 밖 relation 은 기록만.

    모든 그룹 행의 compare_judgment_seq 가 비어 있으면 채운다. commit 은 호출자.
    """
    detected_at = changes.detected_now(now)
    res = CompareApplyResult(conflict_group, relation)
    rows = list(
        session.scalars(
            select(FieldProvenance)
            .where(FieldProvenance.conflict_group == conflict_group)
            .order_by(FieldProvenance.id)
        )
    )
    valued = [r for r in rows if r.label != "확인 불가" and r.entity_id is not None]
    for r in rows:
        if r.compare_judgment_seq is None and judgment_seq is not None:
            r.compare_judgment_seq = judgment_seq
    current = next((r for r in valued if r.chosen), None)
    res.chosen_id = current.id if current is not None else None
    if relation != "contradicts" or len(valued) < 2:
        res.note = f"relation={relation} — 채택 유지"
        session.flush()
        return res
    kinds = _kinds(session, valued)
    primary = [r for r in valued if kinds.get(r.raw_document_id or -1) in COMPARE_PRIMARY_SOURCES]
    tag = f"{_COMPARE_SIDE} {_jl(judgment_seq)}"
    if not primary:
        for r in valued:
            if not (r.reason or "").startswith(_COMPARE_SIDE):
                r.reason = f"{tag} — 2차끼리 병기, 판정 미사용"[:_REASON_MAX]
        res.side_ids = [r.id for r in valued]
        res.note = "1차 공고 자료 없음 — 병기, 판정 미사용(채택 유지)"
        session.flush()
        return res
    target = current if current is not None and current in primary else max(primary, key=_recency)
    with session.begin_nested():
        for r in valued:
            r.chosen = r is target
            if r is target:
                if r.reason is None:
                    r.reason = f"{tag} — 1차 자료 채택"[:_REASON_MAX]
            elif not (r.reason or "").startswith(_COMPARE_SIDE):
                r.reason = f"{tag} — 1차 자료 채택, 병기"[:_REASON_MAX]
        for r in rows:
            if r not in valued:
                r.chosen = False
        session.flush()
        res.changed = current is not target
        res.chosen_id = target.id
        res.side_ids = [r.id for r in valued if r is not target]
        res.note = "1차 자료 채택·병기"
        cand = _candidate(target, kinds.get(target.raw_document_id or -1))
        assert target.entity_id is not None
        written, touched = write_chosen(session, [cand], snapshot_id=snapshot_id, detected_at=detected_at)
        for cid in sorted(touched):
            cx = session.get(Complex, cid)
            if cx is not None:
                assign_complex_area(session, cx)
        session.add_all(written)
        session.flush()
        res.change_events = written
    return res

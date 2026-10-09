"""이전값 diff → change_event (WP2, RA §3 스냅샷 규칙 · T9).

사실 테이블(complex·complex_type·payment_terms·competition)은 현재값만 두고,
바뀐 내역은 change_event에 남긴다.
severity(RA §3 · contracts/schemas/change_event.json):
- critical: 새 공고(새 단지·새 납부 조건 공고), 가격·발코니·옵션 변경, 계약금·중도금·잔금 비율·1차 정액 변경,
  중도금 납부일(interim_schedule)·중도금 조건 변경, 계약일 변경 — triggers_rejudge=true
- notice: 세대수·일정·전매·거주의무 등 그 밖의 수치·날짜
- info: 이름·주소 같은 문자열
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import now_kst
from app.models import ChangeEvent, PaymentTerms
from app.normalize.fields import CRITICAL_FIELDS, NUMERIC_FIELDS, split_price_by_type

__all__ = [
    "PAYMENT_DIFF_FIELDS",
    "current_terms",
    "detected_now",
    "first_terms",
    "fmt_value",
    "make_event",
    "new_notice_event",
    "payment_change_events",
    "severity_for",
    "value_change_event",
]

PAYMENT_DIFF_FIELDS = (
    "down_payment_pct",
    "down_payment_first_won",
    "interim_pct",
    "balance_pct",
    "interim_schedule",
    "interim_terms_text",
)


def detected_now(now: datetime | None = None) -> str:
    return (now or now_kst()).isoformat(timespec="seconds")


def severity_for(entity: str, field: str) -> str:
    if (entity, field) in CRITICAL_FIELDS or entity == "notice":
        return "critical"
    pbt = split_price_by_type(field) if entity == "payment_terms" else None
    if pbt is not None:  # 공고별 타입 가격(2026-10-09.2): 가격 변경 = critical
        return "critical" if pbt[1] in ("max_price_won", "floor_sample_price_won") else "notice"
    if field in NUMERIC_FIELDS.get(entity, ()) or field in {
        "apply_dates",
        "contract_dates",
        "interim_schedule",
    }:
        return "notice"
    return "info"


def fmt_value(v: Any) -> str | None:
    """change_event.old_text/new_text 표기: Decimal은 끝 0 제거, json은 정규 JSON, bool은 true/false."""
    if v is None:
        return None
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, Decimal):
        s = format(v.normalize(), "f")
        return s
    if isinstance(v, float):
        return fmt_value(Decimal(str(v)))
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(v)


def make_event(
    *,
    entity: str,
    entity_id: int | None,
    field: str,
    old: Any,
    new: Any,
    snapshot_id: int | None,
    complex_id: int | None,
    detected_at: str,
    severity: str | None = None,
) -> ChangeEvent:
    sev = severity or severity_for(entity, field)
    return ChangeEvent(
        snapshot_id=snapshot_id,
        entity=entity,
        entity_id=entity_id,
        field=field,
        old_text=fmt_value(old),
        new_text=fmt_value(new),
        detected_at=detected_at,
        severity=sev,
        triggers_rejudge=(sev == "critical"),
        complex_id=complex_id,
    )


def value_change_event(
    *,
    entity: str,
    entity_id: int,
    field: str,
    old: Any,
    new: Any,
    snapshot_id: int | None,
    complex_id: int | None,
    detected_at: str,
    initial: bool,
) -> ChangeEvent | None:
    """같으면 None. 행을 막 만든 경우(initial)는 값 하나하나를 이벤트로 남기지 않는다(새 공고 이벤트 1건이
    대신)."""
    if initial or fmt_value(old) == fmt_value(new):
        return None
    return make_event(
        entity=entity,
        entity_id=entity_id,
        field=field,
        old=old,
        new=new,
        snapshot_id=snapshot_id,
        complex_id=complex_id,
        detected_at=detected_at,
    )


def new_notice_event(
    *,
    field: str,
    new_text: str,
    entity_id: int | None,
    snapshot_id: int | None,
    complex_id: int | None,
    detected_at: str,
) -> ChangeEvent:
    """새 공고(새 단지 또는 같은 단지의 새 무순위·임의공급 공고) — critical."""
    return make_event(
        entity="notice",
        entity_id=entity_id,
        field=field,
        old=None,
        new=new_text,
        snapshot_id=snapshot_id,
        complex_id=complex_id,
        detected_at=detected_at,
        severity="critical",
    )


def current_terms(session: Session, complex_id: int, *, exclude_id: int | None = None) -> PaymentTerms | None:
    """현재 조건 = effective_from이 가장 늦은 행(같으면 notice_no 큰 것)."""
    stmt = select(PaymentTerms).where(PaymentTerms.complex_id == complex_id)
    if exclude_id is not None:
        stmt = stmt.where(PaymentTerms.id != exclude_id)
    rows = list(session.scalars(stmt))
    if not rows:
        return None
    return max(rows, key=lambda r: (r.effective_from, r.notice_no))


def first_terms(session: Session, complex_id: int) -> PaymentTerms | None:
    """최초 조건 = effective_from이 가장 이른 행(같으면 notice_no 작은 것).

    최초 대비 증감(change_vs_first)의 기준.
    """
    rows = list(session.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == complex_id)))
    if not rows:
        return None
    return min(rows, key=lambda r: (r.effective_from, r.notice_no))


def payment_change_events(
    session: Session,
    new_terms: PaymentTerms,
    *,
    snapshot_id: int | None,
    detected_at: str,
) -> list[ChangeEvent]:
    """새 공고의 납부 조건을 직전 현재 조건과 비교한다(새 행이 현재 조건이 될 때만). 예: 계약금 10% →
    5%(T9)."""
    prev = current_terms(session, new_terms.complex_id, exclude_id=new_terms.id)
    if prev is None or (prev.effective_from, prev.notice_no) > (
        new_terms.effective_from,
        new_terms.notice_no,
    ):
        return []
    out: list[ChangeEvent] = []
    for f in PAYMENT_DIFF_FIELDS:
        old, new = getattr(prev, f), getattr(new_terms, f)
        if new is None or fmt_value(old) == fmt_value(new):
            continue
        if f == "interim_schedule" and not new:
            continue
        out.append(
            make_event(
                entity="payment_terms",
                entity_id=new_terms.id,
                field=f,
                old=old,
                new=new,
                snapshot_id=snapshot_id,
                complex_id=new_terms.complex_id,
                detected_at=detected_at,
                severity="critical",
            )
        )
    return out

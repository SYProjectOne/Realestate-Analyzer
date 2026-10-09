"""변경 감지 (RA §5 WP7, §3 change_event, T8): 팝업 이미지 해시 · 청약홈 목록 diff · 새 공고.

- 팝업 해시: 오늘 받은 공식 홈페이지 원문(image_hash 있는 행)을 그 단지의 **기준일 전 마지막 해시**와 비교한다.
  같은 내용이면 수집기가 기존 행(같은 sha256)을 돌려주므로 비교 대상이 자기 자신 → 변경 없음.
  처음 보는 단지는 비교 대상이 없어 이벤트를 만들지 않는다(기준선). 바뀌면 critical + triggers_rejudge.
- 목록 diff: 오늘 목록 원문에서 나온 단지 집합을 직전 collect.daily 잡이 남긴 집합(stats.list_complex_ids)과 비교.
  사라진 단지 → notice(재판정 없음). 새 단지·새 공고는 정규화(normalize.store)가 critical 이벤트를 이미 낸다.
- 판정하지 않는다: 문구가 무엇을 뜻하는지는 판정기·사람이 정한다. 여기서는 해시·집합 비교(산술)만.
"""

# ruff: noqa: E501  (한국어 docstring·로그 필드)

from __future__ import annotations

from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contracts_gen import RawDocument as RawDTO
from app.models import ChangeEvent, Complex, RawDocument

__all__ = ["list_changes", "popup_changes", "rejudge_targets"]

POPUP_FIELD = "official_popup_hash"
LIST_FIELD = "applyhome_list"


def _previous_hash(session: Session, complex_id: int, before_date: str) -> RawDocument | None:
    stmt = (
        select(RawDocument)
        .where(
            RawDocument.source_kind == "official_site",
            RawDocument.complex_id == complex_id,
            RawDocument.image_hash.is_not(None),
            RawDocument.fetched_at < before_date,
        )
        .order_by(RawDocument.fetched_at.desc(), RawDocument.id.desc())
        .limit(1)
    )
    return session.scalars(stmt).first()


def popup_changes(
    session: Session,
    docs: Sequence[RawDTO],
    *,
    asof_date: str,
    snapshot_id: int,
    detected_at: str,
) -> list[ChangeEvent]:
    """팝업 이미지 해시가 기준일 전 마지막 해시와 다르면 critical change_event(행은 세션에 추가)."""
    current: dict[int, RawDTO] = {}
    for d in docs:
        if d.source_kind != "official_site" or not d.image_hash or d.complex_id is None:
            continue
        prev = current.get(d.complex_id)
        if prev is None or (d.fetched_at, d.id or 0) > (prev.fetched_at, prev.id or 0):
            current[d.complex_id] = d
    events: list[ChangeEvent] = []
    for cid, doc in sorted(current.items()):
        # 오늘 원문이 예전 행(같은 sha256)이면 그 행 자신이 '기준일 전 마지막'일 수 있다 → 같은 해시, 변경 없음
        prev_row = _previous_hash(session, cid, asof_date)
        if prev_row is None or prev_row.image_hash == doc.image_hash:
            continue
        old = prev_row.image_hash
        ev = ChangeEvent(
            snapshot_id=snapshot_id,
            entity="complex",
            entity_id=cid,
            field=POPUP_FIELD,
            old_text=old,
            new_text=doc.image_hash,
            detected_at=detected_at,
            severity="critical",
            triggers_rejudge=True,
            complex_id=cid,
        )
        session.add(ev)
        events.append(ev)
    session.flush()
    return events


def list_changes(
    session: Session,
    *,
    today_ids: Iterable[int],
    previous_ids: Iterable[int] | None,
    snapshot_id: int,
    detected_at: str,
) -> list[ChangeEvent]:
    """직전 목록에 있던 단지가 오늘 목록에서 빠졌으면 notice 이벤트(재판정 없음). 직전 기록이 없으면 없음."""
    if previous_ids is None:
        return []
    gone = sorted(set(previous_ids) - set(today_ids))
    events: list[ChangeEvent] = []
    for cid in gone:
        if session.get(Complex, cid) is None:
            continue
        ev = ChangeEvent(
            snapshot_id=snapshot_id,
            entity="complex",
            entity_id=cid,
            field=LIST_FIELD,
            old_text="목록에 있음",
            new_text="목록에서 빠짐",
            detected_at=detected_at,
            severity="notice",
            triggers_rejudge=False,
            complex_id=cid,
        )
        session.add(ev)
        events.append(ev)
    session.flush()
    return events


def rejudge_targets(events: Iterable[ChangeEvent]) -> list[int]:
    """재판정 대상 단지 = triggers_rejudge 인 이벤트의 complex_id(없으면 entity_id가 단지인 경우)."""
    out: set[int] = set()
    for e in events:
        if not e.triggers_rejudge:
            continue
        cid = e.complex_id
        if cid is None and e.entity == "complex":
            cid = e.entity_id
        if cid is not None:
            out.add(cid)
    return sorted(out)

"""변경 감지 (RA §5 WP7, §3 change_event, T8): 팝업 이미지 해시 · 청약홈 목록 diff · 새 공고.

- 팝업 해시: 오늘 받은 공식 홈페이지 원문(image_hash 있는 행)의 해시가 그 단지·같은 홈페이지 주소에서 **기준일 전에 본
  적 없는 값**이면 critical + triggers_rejudge(D33-2 — 전에는 '기준일 전 마지막 해시'와만 비교해, 홈페이지를 같이 쓰는 두
  단지와 번갈아 바뀌는 팝업이 매일 변경이 됐다). 같은 내용이면 수집기가 기존 행(같은 sha256)을 돌려주므로 본 값 → 변경 없음.
  처음 보는 단지는 본 값이 없어 이벤트를 만들지 않는다(기준선).
- 목록 diff: 오늘 목록 원문에서 나온 단지 집합을 직전 collect.daily 잡이 남긴 집합(stats.list_complex_ids)과 비교.
  사라진 단지 → notice(재판정 없음). 새 단지·새 공고는 정규화(normalize.store)가 critical 이벤트를 이미 낸다.
- 판정하지 않는다: 문구가 무엇을 뜻하는지는 판정기·사람이 정한다. 여기서는 해시·집합 비교(산술)만.
"""

# ruff: noqa: E501  (한국어 docstring·로그 필드)

from __future__ import annotations

from collections.abc import Iterable, Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.contracts_gen import RawDocument as RawDTO
from app.models import ChangeEvent, Complex, RawDocument

__all__ = ["list_changes", "popup_changes", "rejudge_targets"]

POPUP_FIELD = "official_popup_hash"
LIST_FIELD = "applyhome_list"


def _seen_hashes(
    session: Session, complex_id: int, url: str | None, before_date: str
) -> tuple[set[str], str | None]:
    """D33-2: 이 단지 또는 같은 홈페이지 주소에서 기준일 전에 본 팝업 해시 전부 + 가장 최근 값.

    원문 행(같은 화면이면 수집기가 예전 스크린샷 행을 다시 쓴다 — 그 행은 처음 찍은 단지에 묶인다)과 지난 팝업 변경
    이벤트(old·new)를 같이 본다. 같은 홈페이지를 쓰는 두 단지, 번갈아 바뀌는 팝업이 매일 '변경'이 되지 않게."""
    where = RawDocument.complex_id == complex_id
    if url:
        where = or_(where, RawDocument.url == url)
    seen: dict[str, str] = {}  # 해시 → 마지막으로 본 시각
    for h, at in session.execute(
        select(RawDocument.image_hash, RawDocument.fetched_at).where(
            RawDocument.source_kind == "official_site",
            RawDocument.image_hash.is_not(None),
            RawDocument.fetched_at < before_date,
            where,
        )
    ):
        if h and (h not in seen or at > seen[h]):
            seen[h] = at
    for old, new, at in session.execute(
        select(ChangeEvent.old_text, ChangeEvent.new_text, ChangeEvent.detected_at).where(
            ChangeEvent.field == POPUP_FIELD, ChangeEvent.complex_id == complex_id
        )
    ):
        for h, t in ((old, at), (new, at)):
            if h and (h not in seen or t > seen[h]):
                seen[h] = t
    latest = max(seen, key=lambda h: seen[h]) if seen else None
    return set(seen), latest


def popup_changes(
    session: Session,
    docs: Sequence[RawDTO],
    *,
    asof_date: str,
    snapshot_id: int,
    detected_at: str,
) -> list[ChangeEvent]:
    """팝업 이미지 해시가 처음 보는 값이면 critical change_event(행은 세션에 추가).

    D33-2: 이 단지·같은 홈페이지 주소에서 전에 본 해시(원문·지난 이벤트)면 변경이 아니다 — 첫 관찰(본 해시 없음)도 아니다.
    old_text 는 가장 최근에 본 해시."""
    current: dict[int, RawDTO] = {}
    for d in docs:
        if d.source_kind != "official_site" or not d.image_hash or d.complex_id is None:
            continue
        prev = current.get(d.complex_id)
        if prev is None or (d.fetched_at, d.id or 0) > (prev.fetched_at, prev.id or 0):
            current[d.complex_id] = d
    events: list[ChangeEvent] = []
    for cid, doc in sorted(current.items()):
        # 오늘 원문이 예전 행(같은 sha256)이면 그 해시는 이미 본 값 → 변경 없음
        seen, latest = _seen_hashes(session, cid, doc.url, asof_date)
        if not seen or doc.image_hash in seen:
            continue
        old = latest
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

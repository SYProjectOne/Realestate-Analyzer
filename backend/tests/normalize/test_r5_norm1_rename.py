"""R5-NORM 1 (major, RA §3 complex 행 규칙): 같은 ``applyhome_id`` 의 이름 변경.

RA §3: "applyhome_id 유일; 개명은 former_names에 추가, 행은 유지". 같은 주택관리번호의 청약홈 상세를 다시 수집했는데
단지명이 바뀌었으면
- 단지 행은 그대로(id 불변, 새 행 없음),
- ``name`` = 새 이름, ``former_names`` 에 옛 이름(중복 없이, 바뀐 순서대로),
- change_event(entity=complex, field=name, old → new) 1건,
- 출처 행은 원문별로 남고 채택(chosen)은 새 이름 하나.
실제 녹화 상세(``detail_2025000271.html``)의 이름 칸만 바꾼 원문으로 실제 파서(ApplyhomeParser)를 거친다.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ChangeEvent, Complex, FieldProvenance, Region
from app.normalize.store import store_raw_document

from ._support import APPLYHOME, DETAIL_URL, AddRaw

KEY = "2025000271"
OLD = "해링턴플레이스 풍무(1BL)"
NEW = "해링턴플레이스 풍무 리버파크(1BL)"
NEWER = "풍무 해링턴 리버파크(1BL)"


def _html(name: str) -> str:
    html = (APPLYHOME / f"detail_{KEY}.html").read_text(encoding="utf-8")
    assert OLD in html
    return html.replace(OLD, name)


def _store(db: Session, add_raw: AddRaw, region: Region, name: str, day: str) -> list[ChangeEvent]:
    raw = add_raw(
        _html(name),
        source_kind="applyhome_detail",
        url=DETAIL_URL.format(n=KEY),
        region_id=region.id,
        fetched_at=f"{day}T06:00:00+09:00",
    )
    res = store_raw_document(db, raw)
    db.flush()
    return list(res.change_events)


def _complexes(db: Session) -> list[Complex]:
    return list(db.scalars(select(Complex).where(Complex.applyhome_id == KEY)))


def _name_events(db: Session, cid: int) -> list[tuple[str | None, str | None]]:
    rows = db.scalars(
        select(ChangeEvent)
        .where(ChangeEvent.entity == "complex", ChangeEvent.entity_id == cid, ChangeEvent.field == "name")
        .order_by(ChangeEvent.id)
    )
    return [(e.old_text, e.new_text) for e in rows]


def test_rename_keeps_row_and_records_former_name_and_event(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    _store(db_session, add_raw, region, OLD, "2026-10-09")
    [cx] = _complexes(db_session)
    cid = cx.id
    assert (cx.name, cx.former_names) == (OLD, [])
    before_events = _name_events(db_session, cid)

    _store(db_session, add_raw, region, NEW, "2026-10-10")
    rows = _complexes(db_session)
    assert [r.id for r in rows] == [cid], "개명해도 단지 행은 하나, id 불변(RA §3)"
    cx = rows[0]
    assert cx.name == NEW
    assert cx.former_names == [OLD], "옛 이름은 former_names 에"
    assert _name_events(db_session, cid)[len(before_events) :] == [(OLD, NEW)], "이름 변경 change_event 1건"

    chosen = list(
        db_session.scalars(
            select(FieldProvenance).where(
                FieldProvenance.entity == "complex",
                FieldProvenance.entity_id == cid,
                FieldProvenance.field == "name",
                FieldProvenance.chosen.is_(True),
            )
        )
    )
    assert [p.value_text for p in chosen] == [NEW], "채택 출처 = 새 이름 하나"


def test_second_rename_appends_in_order_without_duplicates(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    _store(db_session, add_raw, region, OLD, "2026-10-09")
    _store(db_session, add_raw, region, NEW, "2026-10-10")
    _store(db_session, add_raw, region, NEWER, "2026-10-11")
    [cx] = _complexes(db_session)
    assert cx.name == NEWER
    assert cx.former_names == [OLD, NEW]
    assert _name_events(db_session, cx.id)[-2:] == [(OLD, NEW), (NEW, NEWER)]


def test_same_name_refetch_is_no_rename(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    """같은 이름 재수집(다른 날)은 개명이 아니다 — former_names·이름 이벤트 변화 없음."""
    _store(db_session, add_raw, region, OLD, "2026-10-09")
    [cx] = _complexes(db_session)
    n_events = len(_name_events(db_session, cx.id))
    ev = _store(db_session, add_raw, region, OLD + " ", "2026-10-10")  # 원문 바이트만 다름(공백)
    [cx] = _complexes(db_session)
    assert (cx.name, cx.former_names) == (OLD, [])
    assert len(_name_events(db_session, cx.id)) == n_events
    assert not [e for e in ev if e.field == "name"]

"""D33-1: 옛 파서 모양({kind, date}) 접수 일정 — 채택된 출처 원문을 지금 파서로 다시 읽어 {kind, start, end} 로.

값 모양만 바뀌므로 change_event 없이 요약 수(folded)로 센다. 다시 돌리면 대상이 없다.
"""

# ruff: noqa: E501

from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ChangeEvent, Complex, Region
from app.normalize.schedule_legacy import is_legacy_schedule, legacy_apply_raw_ids, reparse_legacy_apply_dates
from app.normalize.store import store_raw_document

from ._support import FIX, AddRaw

API = FIX / "applyhome_api"
NAME = "getAPTLttotPblancDetail_2026000367.json"
URL = {m["file"]: m["url"] for m in json.loads((API / "manifest.json").read_text(encoding="utf-8"))}[NAME]


def test_is_legacy_schedule() -> None:
    assert is_legacy_schedule([{"kind": "1순위", "date": "2024-10-08"}])
    assert not is_legacy_schedule([{"kind": "1순위", "start": "2024-10-08", "end": "2024-10-09"}])
    assert not is_legacy_schedule([]) and not is_legacy_schedule(None)


def test_legacy_apply_dates_are_reparsed_without_change_events(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    raw = add_raw(
        (API / NAME).read_text(encoding="utf-8"),
        source_kind="applyhome_detail",
        url=URL,
        region_id=region.id,
        ext="json",
    )
    store_raw_document(db_session, raw)
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2026000367")).one()
    current = list(cx.apply_dates or [])
    assert current and not is_legacy_schedule(current)
    # 옛 파서가 저장했던 모양으로 되돌린다(시작일만)
    cx.apply_dates = [{"kind": it["kind"], "date": it["start"]} for it in current]
    db_session.flush()
    assert legacy_apply_raw_ids(db_session, region.id) == [raw.id]
    events_before = db_session.scalar(select(func.count()).select_from(ChangeEvent))

    out = reparse_legacy_apply_dates(db_session, region.id)
    db_session.refresh(cx)
    assert (out.complexes, out.skipped, out.errors) == (1, 0, [])
    assert cx.apply_dates == current  # 지금 파서 모양(기간) 그대로
    assert db_session.scalar(select(func.count()).select_from(ChangeEvent)) == events_before  # 이벤트 없음
    assert legacy_apply_raw_ids(db_session, region.id) == []  # 다음 날은 대상 없음

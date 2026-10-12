"""R4-FIX m3 (D18-7) — 지역 첫 적재(bootstrap)의 빈 값 → 값 변경은 change_event 대신 '첫 적재' 한 줄로 요약.

R4: 첫 적재인데 null → 값 change_event 가 critical 326건(옵션 93·평형 샘플가 54·발코니 45·공고번호 88 …) — G1 '최근 변경'이
첫날부터 critical 로 가득했다. 녹화 재생은 ``test_r4_fix_d18_4`` 와 같은 R4 원문.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import Settings
from app.models import ChangeEvent, Region
from app.scheduler.context import SchedulerContext

from .test_r4_fix_d18_4 import _collect, _setup

EMPTY = (None, "", "[]", "{}")


def _events(factory: sessionmaker[Session], ids: list[int]) -> list[ChangeEvent]:
    with factory() as s:
        return list(s.scalars(select(ChangeEvent).where(ChangeEvent.id.in_(ids))))


def test_bootstrap_first_load_is_one_summary_line(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], test_settings: Settings
) -> None:
    ah, pdf = _setup(test_settings, factory)
    with factory() as s:
        region = s.get(Region, 1)
        assert region is not None
        region.status = "bootstrapping"  # handle_region_bootstrap 이 수집 전에 두는 상태
        s.commit()
    res = _collect(make_ctx, ah, pdf)
    events = _events(factory, res.change_event_ids)
    empty_to_value = [e for e in events if e.old_text in EMPTY and e.entity != "region"]
    assert empty_to_value == [], (
        f"첫 적재 빈 값 → 값 이벤트 {len(empty_to_value)}건: {sorted({(e.entity, e.field) for e in empty_to_value})}"
    )
    summary = [e for e in events if (e.entity, e.field) == ("region", "first_load")]
    assert len(summary) == 1 and summary[0].severity == "info" and not summary[0].triggers_rejudge
    assert res.first_load_folded > 0 and f"값 {res.first_load_folded}건" in (summary[0].new_text or "")


def test_ready_region_still_records_new_notice_events(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], test_settings: Settings
) -> None:
    """첫 적재가 아니면(운영 중 새 공고) 지금처럼 이벤트를 남긴다."""
    ah, pdf = _setup(test_settings, factory)
    res = _collect(make_ctx, ah, pdf)
    events = _events(factory, res.change_event_ids)
    assert any(e.entity == "notice" and e.field == "applyhome_id" for e in events)
    assert not any((e.entity, e.field) == ("region", "first_load") for e in events)

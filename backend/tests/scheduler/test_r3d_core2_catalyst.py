"""R3d CORE2 — 호재 쪽 4차 리뷰 재현(M-14) — '호재 아님'을 내는 가짜 판정기(모듈 전용 ``jev``).

| 리뷰 | 테스트 |
| --- | --- |
| M-14 | 사람이 넣은 호재의 '판정기: 호재 아님' 병기는 한 번만, 판정 payload 에 들어가지 않는다 → 두 번째 실행은 캐시(호출 0) |
"""

# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.models import Catalyst
from app.scheduler.context import SchedulerContext
from app.scheduler.pipeline import run_pipeline

from .conftest import SynthJev
from .test_r3c_features import NotCatalystJev


@pytest.fixture
def jev() -> SynthJev:
    return NotCatalystJev()


def test_m14_human_catalyst_note_mark_is_stable_and_not_in_payload(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    with factory() as s:
        human = Catalyst(region_id=1, name="사람이 넣은 역 신설", kind="교통", stage="계획", note="시 보도자료",
                         source_url="https://www.example.go.kr/notice/1", location_confirmed=False)  # fmt: skip
        s.add(human)
        s.commit()
        hid = human.id
    assert not run_pipeline(make_ctx(), seeded).degraded
    with factory() as s:
        h = s.get(Catalyst, hid)
        assert h is not None
        first_note = h.note
    assert first_note == "시 보도자료 · 판정기: 호재 아님", first_note
    jev.calls.clear()
    assert not run_pipeline(make_ctx(), seeded).degraded
    with factory() as s:
        h = s.get(Catalyst, hid)
        assert h is not None and h.note == first_note, "병기가 쌓이면 안 된다"
    assert "classify" not in jev.calls, f"같은 호재 = 같은 payload = 캐시(재호출 0): {jev.calls}"

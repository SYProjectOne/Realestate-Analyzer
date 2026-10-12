"""R4 재시험 minor m-b·m-c (DECISIONS D21-7).

- m-b: 첫 적재(bootstrap) 요약이 같은 bootstrap 안의 값 → 다른 값 덮어쓰기도 포함한다. R4: 공고문이 차례로 같은 타입 가격을
  덮어 값 → 다른 값 change_event 92건(가격 critical 33) — G1 '최근 변경'이 첫날 critical 로 찼다.
- m-c: 포함 classify 배치는 입력이 바뀐 단지만 다시 판정하고 나머지는 이전 판정을 재사용한다. R4: 한 단지 입력이 바뀌면 지역
  전체 배치(58건)가 다시 판정되어 다른 단지 분류가 바뀌었다(39·62 review → auto).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import Settings
from app.models import ChangeEvent, Complex, Region
from app.scheduler.context import SchedulerContext
from app.scheduler.pipeline import run_pipeline

from ..normalize import _r4b
from .conftest import SynthJev

STORE_ENTITIES = {"complex", "complex_type", "payment_terms", "competition", "remaining_event", "notice"}


def _mb_events(factory: sessionmaker[Session], ids: list[int]) -> list[ChangeEvent]:
    with factory() as s:
        return list(s.scalars(select(ChangeEvent).where(ChangeEvent.id.in_(ids))))


def test_mb_bootstrap_folds_value_to_value_overwrites(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], test_settings: Settings
) -> None:
    """R4 원문 재생(``test_r4_fix_d18_4`` 녹화 — 그란테르·금강펜테리움·레이크 송도 4차·엘리프: 원 공고문 뒤에 잔여 공고문이 같은
    타입 가격을 차례로 덮는다) + R4 재시험 엘리프 무순위·임의공급(하이픈 인용)."""
    from .test_r4_fix_d18_4 import _collect, _setup

    ah, pdf = _setup(test_settings, factory)
    _r4b.install(test_settings.raw_dir)
    ah.rows = [*ah.rows, *(r for r in _r4b.rows("elif") if r["source_kind"] != "notice_pdf")]
    pdf.rows = [*pdf.rows, *(r for r in _r4b.rows("elif") if r["source_kind"] == "notice_pdf")]
    with factory() as s:
        region = s.get(Region, 1)
        assert region is not None
        region.status = "bootstrapping"
        s.commit()
    res = _collect(make_ctx, ah, pdf)
    events = _mb_events(factory, res.change_event_ids)
    store_events = [e for e in events if e.entity in STORE_ENTITIES]
    assert store_events == [], (
        f"첫 적재 중 값 기록·덮어쓰기 이벤트 {len(store_events)}건: "
        f"{sorted({(e.entity, e.field, e.old_text, e.new_text) for e in store_events})[:6]}"
    )
    summary = [e for e in events if (e.entity, e.field) == ("region", "first_load")]
    assert len(summary) == 1 and summary[0].severity == "info"
    assert res.first_load_folded > 0 and f"값 {res.first_load_folded}건" in (summary[0].new_text or "")


class InclusionSpy(SynthJev):
    """포함/제외 classify 항목 id 를 기록하는 가짜 판정기(나머지는 SynthJev)."""

    def __init__(self) -> None:
        super().__init__()
        self.inclusion_items: list[list[str]] = []

    def _classify(self, a: dict[str, Any]) -> dict[str, Any]:
        if any(c["id"] == "private_sale_apt" for c in a["classes"]):
            self.inclusion_items.append([str(it["id"]) for it in a["items"]])
        return super()._classify(a)


@pytest.fixture
def jev() -> SynthJev:
    return InclusionSpy()


def test_mc_inclusion_batch_rejudges_only_changed_inputs(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    assert isinstance(jev, InclusionSpy)
    ctx = make_ctx()
    run_pipeline(ctx, seeded)
    assert jev.inclusion_items, "1회차: 지역 단지 포함/제외 배치"
    first = sorted(i for batch in jev.inclusion_items for i in batch)
    assert len(first) > 3
    with factory() as s:
        before = {c.id: (c.inclusion_class, c.inclusion_judgment_seq) for c in s.scalars(select(Complex))}
    jev.inclusion_items.clear()
    run_pipeline(ctx, seeded)
    assert jev.inclusion_items == [], "입력이 그대로면 포함/제외 판정을 다시 보내지 않는다"
    target = int(first[0].split(":")[1])
    with factory() as s:
        cx = s.get(Complex, target)
        assert cx is not None
        cx.developer = f"{cx.developer or ''} 변경 시행사".strip()
        s.commit()
    run_pipeline(ctx, seeded)
    sent = [i for batch in jev.inclusion_items for i in batch]
    assert sent == [f"complex:{target}"], f"입력이 바뀐 단지만 다시 판정: {sent}"
    with factory() as s:
        after = {c.id: (c.inclusion_class, c.inclusion_judgment_seq) for c in s.scalars(select(Complex))}
    changed = {cid for cid in before if before[cid] != after.get(cid)}
    assert changed <= {target}, f"다른 단지 분류·판정 seq 는 그대로: {sorted(changed)}"

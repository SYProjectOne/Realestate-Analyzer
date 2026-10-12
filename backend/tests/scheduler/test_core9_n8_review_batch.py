"""R4 3차 재시험 N8(major — 게이트 조건 위반, D22-2) — 미분류(review)로 남은 단지는 그 단지 입력이 바뀌었을 때만 다시 보낸다.

R4 3차 2회차 (a): 같은 스냅샷 재판정에서 판정기 ``tools/call`` = 1(classify — 포함/제외 배치 [52, 64]). m-c 수정
(``_inclusion_changed``)이 review 결과로 '미분류'인 단지를 '입력 바뀜'과 같이 다뤄, 입력이 그대로인데도 그 단지들만 담은 **새 배치**
(구성이 달라 input_hash 가 새로 생김)를 매번 보냈다. 미분류 집합이 바뀌면(a3) 또 1회 — D18-5 '2회차 tools/call 0(엄격)' 위반.

D22-2: 배치 입력은 단지 순서·구성과 무관하게 결정적이고, review 단지는 그 단지 입력이 바뀌었을 때만 다시 보낸다. 같은 스냅샷 재판정은
어떤 경우에도 ``tools/call`` 0 — 가짜 판정기(전송 계층 계수 ``SynthJev.calls``)로 연속 3회.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Complex, JobRun, JudgmentLog, Snapshot
from app.scheduler import runner
from app.scheduler.context import SchedulerContext
from app.scheduler.rejudge import enqueue_rejudge

from .conftest import SynthJev

REVIEW = {2, 5}  # 판정기가 review 로 답하는 단지(포함/제외)


class ReviewInclusionJev(SynthJev):
    """포함/제외 classify 에서 ``review_ids`` 단지만 decision review(미분류 그대로), 나머지는 SynthJev(auto). 보낸 항목을 기록."""

    def __init__(self, review_ids: set[int]) -> None:
        super().__init__()
        self.review_ids = {f"complex:{i}" for i in review_ids}
        self.inclusion_items: list[list[str]] = []

    def _classify(self, a: dict[str, Any]) -> dict[str, Any]:
        out = super()._classify(a)
        if not any(c["id"] == "private_sale_apt" for c in a["classes"]):
            return out
        self.inclusion_items.append([str(it["id"]) for it in a["items"]])
        for r in out["results"]:
            if r["id"] in self.review_ids:
                r.update(decision="review", confidence=0.4, top_probability=0.5)
        return out


@pytest.fixture
def jev() -> SynthJev:
    return ReviewInclusionJev(REVIEW)


def _unclassify(factory: sessionmaker[Session], ids: set[int]) -> None:
    with factory() as s:
        for cid in ids:
            cx = s.get(Complex, cid)
            assert cx is not None
            cx.inclusion_class, cx.inclusion_decision, cx.inclusion_judgment_seq = "미분류", None, None
        s.commit()


def _latest(factory: sessionmaker[Session]) -> int:
    with factory() as s:
        sid = s.scalar(select(func.max(Snapshot.id)).where(Snapshot.region_id == 1))
        assert sid is not None
        return int(sid)


def _rejudge(factory: sessionmaker[Session], ctx: SchedulerContext) -> dict[str, Any]:
    with factory() as s:
        job = enqueue_rejudge(s, _latest(factory), None, "같은 스냅샷 재판정")
        s.commit()
        jid = job.id
    runner.run_until_idle(ctx)
    with factory() as s:
        row = s.get(JobRun, jid)
        assert row is not None and row.status == "done", (
            row.status if row else None,
            row.error_text if row else None,
        )
        return dict(row.stats or {})


def test_same_snapshot_rejudge_three_times_sends_no_tools_call(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    assert isinstance(jev, ReviewInclusionJev)
    _unclassify(factory, REVIEW)
    first = _rejudge(factory, make_ctx())  # 1회차: 전체 판정(포함/제외 배치에 미분류 단지 포함)
    assert first["tools_calls"] > 0
    with factory() as s:
        for cid in REVIEW:
            cx = s.get(Complex, cid)
            assert cx is not None and (cx.inclusion_class, cx.inclusion_decision) == ("미분류", "review")
        rows_before = s.scalar(select(func.count()).select_from(JudgmentLog))
    for n in (1, 2, 3):
        jev.calls.clear()
        jev.inclusion_items.clear()
        stats = _rejudge(factory, make_ctx())  # 새 문맥 = 새 어댑터(다음 실행)
        assert jev.calls == [], (
            f"{n}회째 같은 스냅샷 재판정 tools/call {len(jev.calls)}건: {jev.calls} · 포함 배치 {jev.inclusion_items}"
        )
        assert stats.get("tools_calls") == 0 and stats.get("judge_calls", 0) == 0, stats
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(JudgmentLog)) == rows_before


def test_review_complex_with_changed_input_is_sent_alone(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    """review 단지도 **그 단지 입력이 바뀌면** 다시 보낸다(그 단지만)."""
    assert isinstance(jev, ReviewInclusionJev)
    _unclassify(factory, REVIEW)
    _rejudge(factory, make_ctx())
    with factory() as s:
        cx = s.get(Complex, 5)
        assert cx is not None
        cx.developer = f"{cx.developer or ''} 변경 시행사".strip()
        s.commit()
    jev.inclusion_items.clear()
    _rejudge(factory, make_ctx())
    assert jev.inclusion_items == [["complex:5"]], jev.inclusion_items


def test_inclusion_batch_items_are_in_complex_id_order(
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    seeded: int,
    jev: SynthJev,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """배치 입력은 단지 순서와 무관하다 — 사실 묶음 순서를 뒤집어도 항목은 단지 id 순(같은 집합 = 같은 input_hash)."""
    import app.scheduler.pipeline as pl

    assert isinstance(jev, ReviewInclusionJev)
    real = pl.load_facts
    monkeypatch.setattr(pl, "load_facts", lambda *a, **k: list(reversed(real(*a, **k))))
    _rejudge(factory, make_ctx())
    assert jev.inclusion_items, "포함/제외 배치가 나갔다"
    for items in jev.inclusion_items:
        ids = [int(i.split(":")[1]) for i in items]
        assert ids == sorted(ids), ids

"""D24-1(R4 5차 N16 — R4-CORE11) 단위: 판정 파이프라인이 판정 뒤·ready 전에 체크리스트를 다시 맞춘다.

| 테스트 | 확인 |
| --- | --- |
| ``test_pipeline_resyncs_checklist_after_inclusion_judgment`` | 일일 단계처럼 체크리스트를 먼저 맞춘 뒤 판정(P4 포함 classify)이 단지 하나를 제외하면 그 단지 자동 항목이 같은 실행에서 na(auto), 결과 stats ``checklist``, 다시 맞춰도 바뀌는 행 0 |
| ``test_pipeline_on_older_asof_leaves_checklist_alone`` | 그 지역에 더 새 기준일 스냅샷이 있으면(옛 기준일 재판정) 체크리스트를 건드리지 않는다(stats ``checklist`` None) — 최신 기준일 재판정은 맞춘다 |

픽스처 지역(회귀 픽스처 16단지)·가짜 판정기(``SynthJev`` — 포함 classify 에서 지정 단지만 public_sale auto). 외부 호출 없음.
"""

# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.judge.jev_mcp import JevMcpAdapter
from app.judge.payloads import INCLUSION_CLASSES
from app.models import ChecklistItem, Complex, Snapshot
from app.normalize.checklist import ALWAYS_LEGAL, item_key, sync_checklist
from app.scheduler.context import SchedulerContext
from app.scheduler.pipeline import run_pipeline

from .conftest import SynthJev

INCLUSION_IDS = [c["id"] for c in INCLUSION_CLASSES]


@dataclass
class ExcludeJev(SynthJev):
    excluded: frozenset[str] = frozenset()

    def _classify(self, a: dict[str, Any]) -> dict[str, Any]:
        out = super()._classify(a)
        if [c["id"] for c in a["classes"]] == INCLUSION_IDS:
            for r in out["results"]:
                if r["id"] in self.excluded:
                    r.update(classification="public_sale", probabilities={"public_sale": 0.96})
        return out


def _ctx(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], jev: SynthJev
) -> SchedulerContext:
    return make_ctx(adapter_factory=lambda: JevMcpAdapter(transport=jev, session_factory=factory, secrets=[]))


def _auto_open(s: Session, cid: int) -> list[str]:
    return [
        i.title
        for i in s.scalars(select(ChecklistItem).where(ChecklistItem.complex_id == cid))
        if i.status == "open" and not item_key(i.kind, i.title).startswith("title:")
    ]


def _target(s: Session) -> int:
    """포함 classify 대상(범위 경계 아님)이고 지금 포함인 가장 작은 단지."""
    return min(
        c.id
        for c in s.scalars(select(Complex).where(Complex.region_id == 1))
        if c.inclusion_class
        not in (
            "범위 경계",
            "public_sale",
            "public_rental",
            "private_rental",
            "non_apartment",
            "out_of_scope",
        )
        and c.applyhome_id is not None
    )


def test_pipeline_resyncs_checklist_after_inclusion_judgment(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int
) -> None:
    with factory() as s:
        snap = s.get(Snapshot, seeded)
        assert snap is not None
        asof = snap.asof_date
        sync_checklist(s, 1, asof_date=asof)  # 일일 단계 조립이 먼저 맞춘 상태
        s.commit()
        cid = _target(s)
        assert _auto_open(s, cid), "대상 단지에 자동 항목이 열려 있어야 한다(사전 조건)"
    jev = ExcludeJev(excluded=frozenset({f"complex:{cid}"}))
    res = run_pipeline(_ctx(make_ctx, factory, jev), seeded)
    assert not res.degraded, res.error
    with factory() as s:
        cx = s.get(Complex, cid)
        assert cx is not None and (cx.inclusion_class, cx.inclusion_decision) == ("public_sale", "auto")
        assert _auto_open(s, cid) == [], "판정이 제외한 단지의 자동 항목은 같은 실행에서 닫혀야 한다(N16)"
        closed = [
            i
            for i in s.scalars(select(ChecklistItem).where(ChecklistItem.complex_id == cid))
            if i.status == "na"
        ]
        assert closed and all(i.closed_by == "auto" for i in closed)
        again = sync_checklist(s, 1, asof_date=asof).stats()
        s.rollback()
    assert res.checklist is not None and res.checklist["closed"] >= len(closed), res.checklist
    assert res.stats()["checklist"] == res.checklist
    assert (again["inserted"], again["updated"], again["closed"], again["reopened"]) == (0, 0, 0, 0), again


def test_pipeline_on_older_asof_leaves_checklist_alone(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int
) -> None:
    with factory() as s:
        old = s.get(Snapshot, seeded)
        assert old is not None
        sync_checklist(s, 1, asof_date=old.asof_date)
        newer = Snapshot(
            region_id=1, asof_date="2026-10-08", status="building", created_at="2026-10-08T06:00:00+09:00"
        )
        s.add(newer)
        s.flush()
        newer_id = newer.id
        gone = s.scalars(
            select(ChecklistItem.id).where(ChecklistItem.title == ALWAYS_LEGAL[0]).order_by(ChecklistItem.id)
        ).first()
        assert gone is not None
        s.execute(delete(ChecklistItem).where(ChecklistItem.id == gone))
        s.commit()
        before = s.scalar(select(ChecklistItem.id).where(ChecklistItem.id == gone))
        assert before is None
        n_before = len(list(s.scalars(select(ChecklistItem.id))))
    jev = SynthJev()
    res = run_pipeline(_ctx(make_ctx, factory, jev), seeded)
    assert not res.degraded and res.checklist is None, res.checklist
    with factory() as s:
        assert (
            len(list(s.scalars(select(ChecklistItem.id)))) == n_before
        )  # 옛 기준일 재판정은 체크리스트 그대로
    res2 = run_pipeline(_ctx(make_ctx, factory, jev), newer_id)
    assert not res2.degraded and res2.checklist is not None and res2.checklist["inserted"] >= 1, (
        res2.checklist
    )

"""R7-FIX2(CEO 결정): 보고서 순위표(§6·§8 TOP 5·§12 순위 비교)의 공동 순위 안 순서 = 종합 점수 높은 순 → complex_id — 화면과
같은 키(``analysis._ranking.display_order_key``). §12 순위 비교 표는 예전에 순위만으로 정렬해 같은 순위·순위 없는 단지가 집합
순회 순서였다."""

# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Scenario, ScoreRun, ScoreTotal

from ._seed import live

SNAP = 12  # devseed 발행 스냅샷(지역 1)


@pytest.fixture
def scratch(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory() as s:
        live(s)
        try:
            yield s
        finally:
            s.rollback()


def test_report_scores_tie_group_ordered_by_total_then_id(scratch: Session) -> None:
    from app.reports.data import load_report

    base = scratch.scalars(select(Scenario).where(Scenario.code == "base")).one()
    run = scratch.scalars(
        select(ScoreRun)
        .where(ScoreRun.snapshot_id == SNAP, ScoreRun.scenario_id == base.id)
        .order_by(ScoreRun.id.desc())
    ).first()
    assert run is not None
    tail = sorted(
        scratch.scalars(select(ScoreTotal).where(ScoreTotal.score_run_id == run.id, ScoreTotal.rank == 5)),
        key=lambda t: t.complex_id,
    )
    assert len(tail) == 2 and tail[0].tie_group == tail[1].tie_group is not None
    lo, hi = tail
    lo.total, hi.total = Decimal("4.6050"), Decimal("4.6400")
    scratch.flush()
    data = load_report(scratch, SNAP, scenario_id=base.id)
    assert [s.complex_id for s in data.scores if s.rank == 5] == [hi.complex_id, lo.complex_id]
    lo.total, hi.total = Decimal("4.6100"), Decimal("4.6100")  # 같은 점수면 complex_id
    scratch.flush()
    data = load_report(scratch, SNAP, scenario_id=base.id)
    assert [s.complex_id for s in data.scores if s.rank == 5] == [lo.complex_id, hi.complex_id]

"""T18 판정기 다운: 수집·정규화는 성공, degraded=true, 점수 미계산, 복구 감지 시 rejudge 자동 등록(1개)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.judge.base import JudgeCaller
from app.judge.mock import MockAdapter
from app.models import JobRun, RawDocument, ScoreRun, Snapshot
from app.scheduler import runner
from app.scheduler.context import SchedulerContext
from app.scheduler.degraded import RECOVERY_REASON, check_recovery
from app.scheduler.jobs import enqueue

from .conftest import FIXTURE, RowsCollector, popup_row


def _count(s: Session, model: Any, *where: Any) -> int:
    return int(s.scalar(select(func.count()).select_from(model).where(*where)) or 0)


def test_judge_down_degraded_then_recovery_enqueues_one_rejudge(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int
) -> None:
    down = MockAdapter(FIXTURE, unavailable=True)  # 모든 호출 JudgeUnavailable
    state = {"up": False}
    site = RowsCollector(factory, [popup_row("yesterday")])
    healthy: list[JudgeCaller] = []

    def adapter() -> JudgeCaller:
        if state["up"]:
            from app.judge.jev_mcp import JevMcpAdapter

            from .conftest import SynthJev

            a = JevMcpAdapter(transport=SynthJev(), session_factory=factory, secrets=[])
            healthy.append(a)
            return a
        return down

    ctx = make_ctx(
        adapter_factory=adapter,
        probe_judge=lambda: state["up"],
        collectors={"official_site": lambda c: site},
    )
    with factory() as s:
        collect_id = enqueue(s, "collect.daily", {"region_id": 1, "sources": ["official_site"]}).id
        s.commit()
    done = runner.run_until_idle(ctx)
    with factory() as s:
        jobs = {j.job_name: j for j in (s.get(JobRun, i) for i in done) if j is not None}
        assert jobs["collect.daily"].id == collect_id and jobs["collect.daily"].status == "done"  # 수집 성공
        assert _count(s, RawDocument) >= 1  # 원문 행(정규화 입력)은 남았다
        rejudge = jobs["rejudge"]
        assert rejudge.status == "failed" and "judge_unavailable" in (rejudge.error_text or "")
        assert rejudge.stats["degraded"] is True
        snap = s.get(Snapshot, seeded)
        assert snap is not None and snap.degraded is True and snap.status == "building"
        assert _count(s, ScoreRun) == 0  # 점수 미계산

    # 아직 다운: 복구 감지 안 함
    assert check_recovery(ctx) == []
    # 복구: degraded 스냅샷마다 rejudge 1개(중복 등록 없음)
    state["up"] = True
    first = check_recovery(ctx)
    assert len(first) == 1
    assert check_recovery(ctx) == []
    with factory() as s:
        queued = list(s.scalars(select(JobRun).where(JobRun.job_name == "rejudge", JobRun.status == "queued")))
        assert len(queued) == 1 and queued[0].payload == {
            "snapshot_id": seeded,
            "scenario_id": None,
            "complex_ids": None,
            "reason": RECOVERY_REASON,
        }
    runner.run_until_idle(ctx)
    with factory() as s:
        snap = s.get(Snapshot, seeded)
        assert snap is not None and snap.degraded is False and snap.status == "published"
        assert _count(s, ScoreRun) == 5
    assert healthy  # 복구 후 새 어댑터로 판정

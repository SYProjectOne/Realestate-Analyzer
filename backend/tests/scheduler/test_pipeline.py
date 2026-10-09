"""rejudge 파이프라인 P1~P9 + 점수 + publish, 멱등(T17), 판정기 버전 변경(D6), contradicted → publish 거부."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.judge.jev_mcp import JevMcpAdapter
from app.models import (
    ChangeEvent,
    Claim,
    ComparableSet,
    Complex,
    Decision,
    JobRun,
    JudgmentLog,
    Ladder,
    ScoreComponent,
    ScoreRun,
    ScoreTotal,
    Snapshot,
)
from app.scheduler import runner
from app.scheduler.context import SchedulerContext
from app.scheduler.rejudge import enqueue_rejudge

from .conftest import SynthJev


def _count(s: Session, model: Any, *where: Any) -> int:
    return int(s.scalar(select(func.count()).select_from(model).where(*where)) or 0)


def _rejudge(
    factory: sessionmaker[Session], ctx: SchedulerContext, sid: int, ids: list[int] | None
) -> list[int]:
    with factory() as s:
        enqueue_rejudge(s, sid, ids, "테스트")
        s.commit()
    return runner.run_until_idle(ctx)


def _jobs(factory: sessionmaker[Session], ids: list[int]) -> list[JobRun]:
    with factory() as s:
        return [j for j in (s.get(JobRun, i) for i in ids) if j is not None]


def test_full_rejudge_writes_derived_rows_and_publishes(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    ctx = make_ctx()
    done = _rejudge(factory, ctx, seeded, None)
    jobs = _jobs(factory, done)
    assert [j.job_name for j in jobs] == ["rejudge", "snapshot.publish"]
    assert all(j.status == "done" for j in jobs), [j.error_text for j in jobs]
    stats = jobs[0].stats
    assert stats["judge_calls"] > 0 and stats["score_runs"] == 5 and not stats["degraded"]
    with factory() as s:
        snap = s.get(Snapshot, seeded)
        assert snap is not None and snap.status == "published" and snap.published_at and not snap.degraded
        # P4: 포함 분류(판정기 auto 결과 기록)
        assert (
            _count(
                s,
                Complex,
                Complex.inclusion_class == "private_sale_apt",
                Complex.inclusion_decision == "auto",
            )
            == 16
        )
        # P6: 사다리 3시점(입주월 있는 판정 대상), 판정기 seq 기록
        assert _count(s, Ladder, Ladder.snapshot_id == seeded) >= 30
        assert _count(s, Ladder, Ladder.snapshot_id == seeded, Ladder.judgment_seq.is_(None)) == 0
        horizons = set(s.scalars(select(Ladder.horizon).where(Ladder.snapshot_id == seeded)))
        assert horizons == {"move_in_plus_1y", "asof_plus_3y", "asof_plus_5y"}
        # 점수: 시나리오 5개 × (component·total), rerank 고정 앵커 seq
        runs = list(s.scalars(select(ScoreRun).where(ScoreRun.snapshot_id == seeded)))
        assert len(runs) == 5 and len({r.rerank_judgment_seq for r in runs}) == 1
        assert runs[0].rerank_judgment_seq is not None
        base = next(r for r in runs if r.scenario_id == 1)
        totals = list(s.scalars(select(ScoreTotal).where(ScoreTotal.score_run_id == base.id)))
        scored = [t for t in totals if t.total is not None]
        assert len(scored) >= 8 and all(t.rank is not None for t in scored)
        assert (
            _count(
                s, ScoreComponent, ScoreComponent.score_run_id == base.id, ScoreComponent.formula_text == ""
            )
            == 0
        )
        # P8: decide — 시나리오마다 후보 + escape hatch, chosen 은 analysis.decide_outcome 규칙
        decisions = list(s.scalars(select(Decision).where(Decision.score_run_id == base.id)))
        assert decisions and sum(d.chosen for d in decisions) == 1
        assert all(d.req_access_pre and d.req_funds_pre for d in decisions if d.option_key == "complex")
        assert _count(s, Decision) >= 5 * 3
        # P9: claim (원자 주장), contradicted 0
        assert _count(s, Claim, Claim.snapshot_id == seeded, Claim.verify_status == "verified") > 0
        assert _count(s, Claim, Claim.verify_status == "contradicted") == 0
        assert _count(s, ComparableSet) >= 0


def test_second_rejudge_makes_no_real_calls_t17(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    ctx = make_ctx()
    _rejudge(factory, ctx, seeded, None)
    first = len(jev.calls)
    assert first > 0
    with factory() as s:
        n_log = _count(s, JudgmentLog)
    done = _rejudge(factory, make_ctx(), seeded, None)  # 새 worker(새 어댑터)여도 DB 캐시
    assert len(jev.calls) == first  # 두 번째 실제 호출 0
    rejudge = _jobs(factory, done)[0]
    assert rejudge.status == "done"
    assert rejudge.stats["judge_calls"] == 0 and rejudge.stats["cached"] > 0
    with factory() as s:
        assert _count(s, JudgmentLog) == n_log
        assert _count(s, Ladder, Ladder.snapshot_id == seeded) >= 30  # 갱신(중복 행 없음)
        assert _count(s, ScoreRun, ScoreRun.snapshot_id == seeded) == 10
        assert _count(s, ScoreRun, ScoreRun.prev_score_run_id.is_not(None)) == 5


def test_subset_rejudge_only_calls_changed_complexes(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    ctx = make_ctx()
    _rejudge(factory, ctx, seeded, None)
    with factory() as s:
        cx = s.get(Complex, 2)
        assert cx is not None
        cx.move_in_ym = "2028-06"  # 사실 변경(입주월) → 단지 2만 다시
        s.commit()
    jev.calls.clear()
    done = _rejudge(factory, ctx, seeded, [2])
    stats = _jobs(factory, done)[0].stats
    assert stats["targets"] == 1
    noul = jev.calls.count("jev_noul")
    assert 1 <= noul <= 3  # 단지 2의 사다리만
    assert jev.calls.count("jev_classify") == 0  # 분류 입력이 같으면 캐시
    assert "jev_rerank" in jev.calls  # 카드가 바뀌면 후보군 전체 1회 재호출(§6-5)


def test_judge_version_change_records_event_and_full_rejudge_once(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    _rejudge(factory, make_ctx(), seeded, None)
    newer = SynthJev(version=jev.version, model="jev-1.14.0")

    def adapter() -> JevMcpAdapter:
        return JevMcpAdapter(transport=newer, session_factory=factory, secrets=[])

    ctx = make_ctx(adapter_factory=adapter)
    with factory() as s:
        cx = s.get(Complex, 2)
        assert cx is not None
        cx.move_in_ym = "2028-06"  # 새 입력이 있어야 판정기 응답(model)을 본다 — 같은 입력은 캐시
        enqueue_rejudge(s, seeded, [2], "단지 2 변경")
        s.commit()
    first = runner.run_once(ctx)  # rejudge 1개만
    assert first is not None
    with factory() as s:
        events = list(s.scalars(select(ChangeEvent).where(ChangeEvent.entity == "judge")))
        assert len(events) == 1
        ev = events[0]
        assert ev.field == "version" and ev.severity == "critical" and ev.triggers_rejudge
        assert (
            ev.old_text
            and ev.old_text.endswith("+jev-1.13.0")
            and ev.new_text
            and ev.new_text.endswith("+jev-1.14.0")
        )
        queued = list(
            s.scalars(select(JobRun).where(JobRun.job_name == "rejudge", JobRun.status == "queued"))
        )
        assert len(queued) == 1 and queued[0].payload["complex_ids"] is None
        assert ev.id in queued[0].payload["change_event_ids"]
    runner.run_until_idle(ctx)
    with factory() as s:
        assert _count(s, ChangeEvent, ChangeEvent.entity == "judge") == 1  # 1회
        assert _count(s, JobRun, JobRun.job_name == "rejudge", JobRun.status == "queued") == 0


def test_contradicted_claim_blocks_publish(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    jev.verdict = "contradicted"
    done = _rejudge(factory, make_ctx(), seeded, None)
    jobs = _jobs(factory, done)
    publish = next(j for j in jobs if j.job_name == "snapshot.publish")
    assert publish.status == "failed" and "publish_blocked" in (publish.error_text or "")
    assert publish.stats["contradicted"] > 0
    with factory() as s:
        snap = s.get(Snapshot, seeded)
        assert snap is not None and snap.status == "ready" and snap.published_at is None

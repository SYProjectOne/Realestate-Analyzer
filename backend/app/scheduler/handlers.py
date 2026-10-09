"""잡 이름 → 처리 함수 (RA §4-4 + DECISIONS D2-4). 처리 함수는 stats(dict)를 돌려주고, 실패는 예외(JobError 면
그 stats 도 남긴다). runner.py 가 job_run 상태를 바꾼다.

| job_name | 처리 |
| --- | --- |
| collect.daily | 수집(청약홈·공고문·공식 홈페이지) → 변경 감지 → 변경 단지만 rejudge 등록 / 변경 없으면 이전 스냅샷 파생 행 복사 + publish(T8) → critical 웹훅 |
| collect.weekly | 실거래·미분양·입주물량·뉴스 → 시장 자료가 바뀌면 점수 재계산 rejudge(판정 대상 단지 0개) |
| rejudge | pipeline P1~P9 (rejudge.py) → snapshot.publish 등록 |
| snapshot.publish | contradicted claim 0 이면 published, 아니면 failed(publish_blocked) |
| reference.refresh | 법정동·행정동·매핑·세대 현황 갱신(collectors.reference) |
| region.bootstrap | region.status=bootstrapping → daily+weekly 수집 → 전체 파이프라인 → publish → ready(실패 failed) |
| claim.reverify | contradicted 주장의 고친 문장 → 원자 분할 → verify → parent_claim_id 자식 행(reverify.py, 계약 2026-10-09.4) |
| report | WP8 ``app.reports.job.run_report_job(payload, session=…)`` (예외 → failed: blocked·not_found·invalid_payload) |
"""

# ruff: noqa: E501  (한국어 docstring·로그 필드)

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import func, select

from app.core.logging import get_logger
from app.models import ChangeEvent, Complex, JobRun, Region, ScoreRun, Snapshot
from app.scheduler import snapshots
from app.scheduler.collect import collect
from app.scheduler.jobs import DAILY_SOURCES, WEEKLY_SOURCES, JobError
from app.scheduler.persist import carry_forward
from app.scheduler.rejudge import enqueue_rejudge, handle_rejudge
from app.scheduler.reverify import handle_claim_reverify

if TYPE_CHECKING:
    from app.scheduler.context import SchedulerContext

__all__ = ["HANDLERS", "Handler"]

log = get_logger("app.scheduler.handlers")

Handler = Callable[["SchedulerContext", JobRun], dict[str, Any]]


def _since(session: Any, region_id: int, job_name: str, exclude_id: int) -> str | None:
    """같은 지역의 직전 성공 수집 잡 시작 시각(수집기 since)."""
    for job in session.scalars(
        select(JobRun)
        .where(JobRun.job_name == job_name, JobRun.status == "done", JobRun.id != exclude_id)
        .order_by(JobRun.id.desc())
    ):
        if (job.payload or {}).get("region_id") == region_id:
            return str(job.started_at) if job.started_at else None
    return None


def _names(session: Any, ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    return {c.id: c.name for c in session.scalars(select(Complex).where(Complex.id.in_(ids)))}


def _notify(ctx: SchedulerContext, event_ids: list[int]) -> dict[str, Any]:
    if not event_ids:
        return {"sent": 0, "skipped": "no_events"}
    with ctx.session_factory() as session:
        events = list(session.scalars(select(ChangeEvent).where(ChangeEvent.id.in_(event_ids))))
        names = _names(session, sorted({e.complex_id for e in events if e.complex_id is not None}))
    r = ctx.notifier.notify(events, names)
    return {"sent": r.sent, "skipped": r.skipped, "status": r.status}


def _after_daily(
    ctx: SchedulerContext, snapshot_id: int, rejudge_ids: list[int], event_ids: list[int]
) -> dict[str, Any]:
    """변경 단지만 rejudge. 변경이 없으면(T8) 이전 publish 스냅샷의 판정·점수를 복사하고 publish — 판정기 호출 0."""
    with ctx.session_factory() as session:
        snap = session.get(Snapshot, snapshot_id)
        assert snap is not None
        if rejudge_ids:
            job = enqueue_rejudge(
                session, snapshot_id, rejudge_ids, f"변경 감지 {len(rejudge_ids)}단지",
                change_event_ids=event_ids, now=ctx.now(),
            )  # fmt: skip
            session.commit()
            return {"rejudge_job_id": job.id}
        has_runs = session.scalar(
            select(func.count()).select_from(ScoreRun).where(ScoreRun.snapshot_id == snapshot_id)
        )
        if snap.status == "published" or has_runs:
            return {"carry_forward": "이미 판정됨"}
        prev = snapshots.previous(session, snap, published_only=True)
        if prev is None:
            job = enqueue_rejudge(
                session, snapshot_id, None, "이전 publish 스냅샷 없음 — 전체 판정", now=ctx.now()
            )
            session.commit()
            return {"rejudge_job_id": job.id}
        copied = carry_forward(session, prev.id, snapshot_id, created_at=ctx.iso_now())
        snap.status = "ready"
        ok, n = snapshots.publish(session, snapshot_id, now=ctx.iso_now())
        session.commit()
        return {"carry_forward": {"from_snapshot_id": prev.id, **copied}, "published": ok, "contradicted": n}


def handle_collect_daily(ctx: SchedulerContext, job: JobRun) -> dict[str, Any]:
    p = job.payload or {}
    region_id = int(p["region_id"])
    with ctx.session_factory() as session:
        since = _since(session, region_id, "collect.daily", job.id)
    res = collect(
        ctx, region_id, p.get("sources") or list(DAILY_SOURCES), asof_date=p.get("asof_date"), since=since
    )
    stats = res.stats()
    stats.update(_after_daily(ctx, res.snapshot_id, res.rejudge_complex_ids, res.change_event_ids))
    stats["notify"] = _notify(ctx, res.change_event_ids)
    if res.errors:
        raise JobError(f"수집 단계 오류: {', '.join(sorted(res.errors))}", stats)
    return stats


def handle_collect_weekly(ctx: SchedulerContext, job: JobRun) -> dict[str, Any]:
    p = job.payload or {}
    region_id = int(p["region_id"])
    with ctx.session_factory() as session:
        since = _since(session, region_id, "collect.weekly", job.id)
    res = collect(
        ctx, region_id, p.get("sources") or list(WEEKLY_SOURCES), asof_date=p.get("asof_date"), since=since
    )
    stats = res.stats()
    if res.change_event_ids:
        with ctx.session_factory() as session:
            snap = session.get(Snapshot, res.snapshot_id)
            has_runs = session.scalar(
                select(func.count()).select_from(ScoreRun).where(ScoreRun.snapshot_id == res.snapshot_id)
            )
            if snap is not None and (has_runs or snapshots.previous(session, snap, published_only=True)):
                rj = enqueue_rejudge(
                    session, res.snapshot_id, [], "주간 시장 자료 변경 — 점수 재계산",
                    change_event_ids=res.change_event_ids, now=ctx.now(),
                )  # fmt: skip
                session.commit()
                stats["rejudge_job_id"] = rj.id
    if res.errors:
        raise JobError(f"수집 단계 오류: {', '.join(sorted(res.errors))}", stats)
    return stats


def handle_snapshot_publish(ctx: SchedulerContext, job: JobRun) -> dict[str, Any]:
    sid = int((job.payload or {})["snapshot_id"])
    with ctx.session_factory() as session:
        ok, n = snapshots.publish(session, sid, now=ctx.iso_now())
        snap = session.get(Snapshot, sid)
        session.commit()
        stats = {"snapshot_id": sid, "published": ok, "contradicted": n}
        if not ok:
            why = f"publish_blocked: contradicted {n}건" if n else "publish_blocked: degraded(점수 미계산)"
            if snap is not None and snap.status == "building" and not snap.degraded:
                why = "publish_blocked: 판정·점수 미완료"
            raise JobError(why, stats)
    return stats


def handle_reference_refresh(ctx: SchedulerContext, job: JobRun) -> dict[str, Any]:
    return {"reference": ctx.reference_refresh(ctx.today())}


def handle_region_bootstrap(ctx: SchedulerContext, job: JobRun) -> dict[str, Any]:
    from app.scheduler.pipeline import run_pipeline

    region_id = int((job.payload or {})["region_id"])
    with ctx.session_factory() as session:
        region = session.get(Region, region_id)
        if region is None:
            raise JobError(f"region {region_id} 없음")
        region.status = "bootstrapping"
        session.commit()
    try:
        daily = collect(ctx, region_id, [*DAILY_SOURCES, "notice_pdf"], detect_list=False)
        weekly = collect(ctx, region_id, list(WEEKLY_SOURCES), detect_list=False)
        result = run_pipeline(ctx, daily.snapshot_id, complex_ids=None, reason="region.bootstrap")
        stats: dict[str, Any] = {
            "region_id": region_id,
            "snapshot_id": daily.snapshot_id,
            "asof_date": daily.asof_date,
            "daily": daily.stats(),
            "weekly": weekly.stats(),
            "pipeline": result.stats(),
            "degraded": result.degraded,
        }
        if daily.list_complex_ids is not None:
            stats["list_complex_ids"] = daily.list_complex_ids
        with ctx.session_factory() as session:
            if not result.degraded:
                ok, n = snapshots.publish(session, daily.snapshot_id, now=ctx.iso_now())
                stats.update({"published": ok, "contradicted": n})
            region = session.get(Region, region_id)
            assert region is not None
            region.status = "ready"
            session.commit()
        errors = {**daily.errors, **weekly.errors}
        if errors:
            stats["errors"] = errors
        return stats
    except Exception:
        with ctx.session_factory() as session:
            region = session.get(Region, region_id)
            if region is not None:
                region.status = "failed"
                session.commit()
        raise


def handle_report(ctx: SchedulerContext, job: JobRun) -> dict[str, Any]:
    """WP8 잡 규약(app/reports/README.md '잡 규약'): ``run_report_job(payload, session=…)`` → stats.

    ReportBlocked → failed ``blocked: <사유>`` + stats.blocked_reason, ReportNotFound → ``not_found: <사유>``,
    ValueError(payload 검증) → ``invalid_payload: …``.
    """
    from app.reports import job as report_job
    from app.reports.errors import ReportBlocked, ReportNotFound

    try:
        with ctx.session_factory() as session:
            stats = report_job.run_report_job(dict(job.payload or {}), session=session)
            session.commit()
    except ReportBlocked as exc:
        raise JobError(f"blocked: {exc.reason}", {"blocked_reason": exc.reason}) from exc
    except ReportNotFound as exc:
        raise JobError(f"not_found: {exc.reason}") from exc
    except ValueError as exc:
        raise JobError(f"invalid_payload: {str(exc)[:300]}") from exc
    return dict(stats)


HANDLERS: Final[dict[str, Handler]] = {
    "collect.daily": handle_collect_daily,
    "collect.weekly": handle_collect_weekly,
    "rejudge": handle_rejudge,
    "snapshot.publish": handle_snapshot_publish,
    "reference.refresh": handle_reference_refresh,
    "region.bootstrap": handle_region_bootstrap,
    "report": handle_report,
    "claim.reverify": handle_claim_reverify,  # 계약 2026-10-09.4 (R3 M8, reverify.py)
}

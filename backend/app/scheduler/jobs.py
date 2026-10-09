"""잡 정의·큐 등록·APScheduler 시간표 (RA §4-4, §10, DECISIONS D2-4).

시간표(Asia/Seoul)
- 매일 06:00 ``collect.daily`` — 지역(status ready)마다 ``{region_id, sources:[applyhome_list, official_site]}``
- 매주 월 06:30 ``collect.weekly`` — ``{region_id, sources:[rtms, stats, news]}``
- 매월 1일 05:00 ``reference.refresh`` — ``{}``
- 기동 시 참조 표(legal_dong)가 비어 있으면 ``reference.refresh`` 1회(``ensure_reference``)

APScheduler 는 잡을 **실행하지 않고 job_run 행만 넣는다**(ADR-3: DB job_run 이 큐, 상태가 G7에 보인다).
실행은 runner.py 가 polling 으로 한다. 같은 잡(이름·payload 같음)이 이미 queued 면 새로 넣지 않는다.
"""

# ruff: noqa: E501  (한국어 docstring·로그 필드)

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.snapshot import canonical_json
from app.core.time import now_kst
from app.models import JobRun, LegalDong, Region

if TYPE_CHECKING:
    from apscheduler.schedulers.background import BackgroundScheduler

    from app.scheduler.context import SchedulerContext

__all__ = [
    "CRON",
    "DAILY_SOURCES",
    "JOB_NAMES",
    "WEEKLY_SOURCES",
    "JobError",
    "build_scheduler",
    "enqueue",
    "enqueue_for_regions",
    "ensure_reference",
    "find_pending",
]

log = get_logger("app.scheduler.jobs")

JobName = Literal[
    "collect.daily",
    "collect.weekly",
    "rejudge",
    "report",
    "snapshot.publish",
    "reference.refresh",
    "region.bootstrap",
]
JobKind = Literal["scheduled", "manual", "rejudge"]
JOB_NAMES: Final[tuple[JobName, ...]] = (
    "collect.daily",
    "collect.weekly",
    "rejudge",
    "report",
    "snapshot.publish",
    "reference.refresh",
    "region.bootstrap",
)
DAILY_SOURCES: Final = ("applyhome_list", "official_site")
WEEKLY_SOURCES: Final = ("rtms", "stats", "news")
TIMEZONE: Final = "Asia/Seoul"
CRON: Final[dict[str, dict[str, Any]]] = {
    "collect.daily": {"hour": 6, "minute": 0},
    "collect.weekly": {"day_of_week": "mon", "hour": 6, "minute": 30},
    "reference.refresh": {"day": 1, "hour": 5, "minute": 0},
}


class JobError(RuntimeError):
    """잡을 failed 로 끝낸다(error_text = 메시지, stats 도 남긴다)."""

    def __init__(self, message: str, stats: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.stats = dict(stats or {})


def _iso(now: datetime | None) -> str:
    return (now or now_kst()).isoformat(timespec="seconds")


def find_pending(session: Session, job_name: str, payload: Mapping[str, Any]) -> JobRun | None:
    """같은 이름·같은 payload(정규 JSON 비교)로 queued 인 잡."""
    key = canonical_json(dict(payload))
    for row in session.scalars(
        select(JobRun).where(JobRun.job_name == job_name, JobRun.status == "queued").order_by(JobRun.id)
    ):
        if canonical_json(row.payload or {}) == key:
            return row
    return None


def enqueue(
    session: Session,
    job_name: JobName,
    payload: Mapping[str, Any],
    *,
    kind: JobKind = "scheduled",
    now: datetime | None = None,
    dedupe: bool = True,
) -> JobRun:
    """job_run 행을 넣는다(queued). commit 은 호출자. dedupe 면 같은 queued 잡을 돌려준다."""
    if job_name not in JOB_NAMES:
        raise ValueError(f"알 수 없는 잡: {job_name}")
    if dedupe:
        existing = find_pending(session, job_name, payload)
        if existing is not None:
            return existing
    row = JobRun(
        job_name=job_name,
        kind=kind,
        payload=dict(payload),
        scheduled_at=_iso(now),
        status="queued",
        stats={},
    )
    session.add(row)
    session.flush()
    log.info("worker.job.enqueued", extra={"job_id": row.id, "job_name": job_name, "kind": kind})
    return row


def enqueue_for_regions(
    ctx: SchedulerContext, job_name: Literal["collect.daily", "collect.weekly"]
) -> list[int]:
    """status=ready 인 지역마다 수집 잡 1개(시간표 콜백)."""
    sources = list(DAILY_SOURCES if job_name == "collect.daily" else WEEKLY_SOURCES)
    ids: list[int] = []
    with ctx.session_factory() as session:
        regions = session.scalars(select(Region.id).where(Region.status == "ready").order_by(Region.id))
        for region_id in list(regions):
            row = enqueue(session, job_name, {"region_id": region_id, "sources": sources}, now=ctx.now())
            ids.append(row.id)
        session.commit()
    return ids


def ensure_reference(ctx: SchedulerContext) -> int | None:
    """참조 표가 비어 있으면 reference.refresh 1회 등록(DECISIONS D2-4 '최초 기동 시 1회')."""
    with ctx.session_factory() as session:
        n = session.scalar(select(func.count()).select_from(LegalDong)) or 0
        if n > 0:
            return None
        row = enqueue(session, "reference.refresh", {}, now=ctx.now())
        session.commit()
        return row.id


def _enqueue_reference(ctx: SchedulerContext) -> None:
    with ctx.session_factory() as session:
        enqueue(session, "reference.refresh", {}, now=ctx.now())
        session.commit()


def build_scheduler(ctx: SchedulerContext) -> BackgroundScheduler:
    """시간표 3개를 단 BackgroundScheduler(시작은 호출자). 콜백은 job_run 행만 넣는다."""
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    sched = BackgroundScheduler(timezone=TIMEZONE)
    sched.add_job(
        enqueue_for_regions,
        CronTrigger(timezone=TIMEZONE, **CRON["collect.daily"]),
        args=[ctx, "collect.daily"],
        id="collect.daily",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,
    )
    sched.add_job(
        enqueue_for_regions,
        CronTrigger(timezone=TIMEZONE, **CRON["collect.weekly"]),
        args=[ctx, "collect.weekly"],
        id="collect.weekly",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,
    )
    sched.add_job(
        _enqueue_reference,
        CronTrigger(timezone=TIMEZONE, **CRON["reference.refresh"]),
        args=[ctx],
        id="reference.refresh",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,
    )
    return sched

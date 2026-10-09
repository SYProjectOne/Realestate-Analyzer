"""worker 본체: job_run polling·잠금·실행 (ADR-3, contracts/schemas/job_run.json).

``python -m app.worker [--once] [--interval 초] [--no-schedule]`` → ``main(argv)``.

- 잠금: ``UPDATE job_run SET status='running', locked_by=?, started_at=? WHERE id=? AND status='queued'`` 가
  1행을 바꿨을 때만 실행한다 → 같은 잡을 worker 둘이 집어도 하나만 동작한다(동시 실행 2개 → 하나만).
- 끝: done(stats) / failed(error_text, stats). 처리 함수 예외는 잡 failed 로 남기고 worker 는 계속 돈다.
  error_text 는 비밀값을 가린 뒤 500자까지(로그에도 payload 원문 없음).
- ``--once``: 큐에 있는 잡을 비울 때까지(최대 ``--max-jobs``) 실행하고 0 으로 끝난다(운영 점검·CI). 시간표·
  참조 표 자동 등록은 하지 않는다. 스키마가 없으면(마이그레이션 전) 경고만 남기고 0.
- 상주: 기동 시 참조 표가 비면 reference.refresh 1회(jobs.ensure_reference), APScheduler 시간표 시작,
  매 주기 degraded 복구 감지(degraded.check_recovery) → 큐 실행.
"""

from __future__ import annotations

import argparse
import signal
import threading
import time
from collections.abc import Sequence
from types import FrameType
from typing import Any

from sqlalchemy import inspect, select, update
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.core.logging import get_logger
from app.core.protocols import JudgeUnavailable
from app.core.redact import redact_text
from app.core.settings import get_settings
from app.models import JobRun
from app.scheduler.context import SchedulerContext, default_context
from app.scheduler.jobs import JobError

__all__ = ["claim", "execute", "main", "queued_ids", "run_once", "run_until_idle"]

log = get_logger("app.worker")
ERROR_TEXT_MAX = 500
RECOVERY_EVERY_S = 300.0


def claim(ctx: SchedulerContext, job_id: int) -> bool:
    """queued → running 원자 갱신. 1행이 바뀌었을 때만 True(이 worker 가 실행권을 가짐)."""
    with ctx.session_factory() as session:
        result = session.execute(
            update(JobRun)
            .where(JobRun.id == job_id, JobRun.status == "queued")
            .values(status="running", locked_by=ctx.worker_id[:64], started_at=ctx.iso_now())
        )
        session.commit()
        return int(getattr(result, "rowcount", 0) or 0) == 1


def queued_ids(ctx: SchedulerContext, limit: int = 20) -> list[int]:
    """먼저 들어온 순서(id). scheduled_at 은 등록 시각이라 시간대 표기가 섞여도 순서에 쓰지 않는다."""
    with ctx.session_factory() as session:
        stmt = select(JobRun.id).where(JobRun.status == "queued").order_by(JobRun.id).limit(limit)
        return list(session.scalars(stmt))


def _error_text(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}" if not isinstance(exc, JobError) else str(exc)
    return redact_text(text, get_settings().secret_values())[:ERROR_TEXT_MAX]


def _jsonable(stats: Any) -> dict[str, Any]:
    import json

    return dict(json.loads(json.dumps(stats, ensure_ascii=False, default=str))) if stats else {}


def execute(ctx: SchedulerContext, job_id: int) -> str:
    """잠근 잡 1개 실행 → 최종 status('done'|'failed')."""
    from app.scheduler.handlers import HANDLERS

    with ctx.session_factory() as session:
        job = session.get(JobRun, job_id)
        if job is None:
            raise LookupError(f"job_run {job_id} 없음")
        session.expunge(job)
    handler = HANDLERS.get(job.job_name)
    status, stats, error = "done", {}, None
    started = time.monotonic()
    log.info("worker.job.start", extra={"job_id": job_id, "job_name": job.job_name})
    try:
        if handler is None:
            raise JobError(f"처리 함수 없음: {job.job_name}")
        stats = handler(ctx, job)
    except JobError as exc:
        status, stats, error = "failed", exc.stats, _error_text(exc)
    except JudgeUnavailable as exc:
        status, error = "failed", _error_text(exc)
        ctx.reset_adapter()
    except Exception as exc:  # 처리 함수 버그·외부 오류: 잡만 실패, worker 는 계속
        status, error = "failed", _error_text(exc)
        log.exception("worker.job.error", extra={"job_id": job_id, "job_name": job.job_name})
    with ctx.session_factory() as session:
        row = session.get(JobRun, job_id)
        assert row is not None
        row.status = status
        row.stats = _jsonable(stats)
        row.error_text = error
        row.finished_at = ctx.iso_now()
        session.commit()
    log.info(
        "worker.job.finish",
        extra={
            "job_id": job_id,
            "job_name": job.job_name,
            "status": status,
            "seconds": round(time.monotonic() - started, 2),
        },
    )
    return status


def run_once(ctx: SchedulerContext) -> int | None:
    """큐에서 잡 1개를 잠가 실행한다. 실행한 잡 id(없으면 None)."""
    for job_id in queued_ids(ctx):
        if claim(ctx, job_id):
            execute(ctx, job_id)
            return job_id
    return None


def run_until_idle(ctx: SchedulerContext, max_jobs: int = 200) -> list[int]:
    done: list[int] = []
    while len(done) < max_jobs:
        job_id = run_once(ctx)
        if job_id is None:
            break
        done.append(job_id)
    return done


def _has_schema(ctx: SchedulerContext) -> bool:
    try:
        with ctx.session_factory() as session:
            bind = session.get_bind()
            return bool(inspect(bind).has_table("job_run"))
    except (OperationalError, ProgrammingError):
        return False


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m app.worker", description="subscription-analyzer worker (WP7)")
    p.add_argument("--once", action="store_true", help="큐를 비우고 끝낸다")
    p.add_argument("--interval", type=float, default=None, help="polling 간격(초)")
    p.add_argument("--max-jobs", type=int, default=200, help="--once 에서 실행할 최대 잡 수")
    p.add_argument("--no-schedule", action="store_true", help="APScheduler 시간표를 켜지 않는다(큐만 처리)")
    args, _unknown = p.parse_known_args(list(argv))
    return args


def main(argv: list[str] | None = None, *, ctx: SchedulerContext | None = None) -> int:
    from app.scheduler.degraded import check_recovery
    from app.scheduler.jobs import build_scheduler, ensure_reference

    args = _parse(argv or [])
    settings = get_settings()
    ctx = ctx or default_context(settings)
    interval = args.interval if args.interval is not None else min(settings.worker_heartbeat_s, 10.0)

    if not _has_schema(ctx):
        log.warning("worker.no_schema", extra={"hint": "alembic upgrade head"})
        if args.once:
            return 0
    if args.once:
        check_recovery(ctx)
        done = run_until_idle(ctx, max_jobs=args.max_jobs)
        log.info("worker.once.done", extra={"jobs": len(done)})
        ctx.reset_adapter()
        return 0

    stop = threading.Event()
    previous: dict[signal.Signals, Any] = {}

    def _stop(signum: int, _frame: FrameType | None) -> None:
        log.info("worker.stop", extra={"signal": signum})
        stop.set()

    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.getsignal(sig)
            signal.signal(sig, _stop)
    sched = None
    try:
        while not stop.is_set() and not _has_schema(ctx):
            if stop.wait(interval):
                return 0
        ensure_reference(ctx)
        if not args.no_schedule:
            sched = build_scheduler(ctx)
            sched.start()
        log.info("worker.start", extra={"mode": "scheduler", "worker_id": ctx.worker_id})
        last_recovery = 0.0
        while not stop.is_set():
            if time.monotonic() - last_recovery >= RECOVERY_EVERY_S:
                check_recovery(ctx)
                last_recovery = time.monotonic()
            run_until_idle(ctx)
            stop.wait(interval)
    finally:
        if sched is not None:
            sched.shutdown(wait=False)
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        ctx.reset_adapter()
    return 0

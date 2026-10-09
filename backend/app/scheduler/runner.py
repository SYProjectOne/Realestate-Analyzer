"""worker 본체: job_run polling·잠금·실행 (ADR-3, contracts/schemas/job_run.json).

``python -m app.worker [--once] [--interval 초] [--no-schedule]`` → ``main(argv)``.

- 잠금: ``UPDATE job_run SET status='running', locked_by=?, started_at=? WHERE id=? AND status='queued'`` 가
  1행을 바꿨을 때만 실행한다 → 같은 잡을 worker 둘이 집어도 하나만 동작한다(동시 실행 2개 → 하나만).
- 끝: done(stats) / failed(error_text, stats). 처리 함수 예외는 잡 failed 로 남기고 worker 는 계속 돈다.
  error_text 는 비밀값을 가린 뒤 500자까지(로그에도 payload 원문 없음).
- 하트비트: 실행 중 잡은 ``worker_heartbeat_s`` 마다 ``stats.heartbeat_at`` 을 갱신한다(별도 스레드·세션).
  ``recover_stale``: running 인데 마지막 하트비트(없으면 started_at)가 3 × heartbeat 보다 오래된 잡(worker 사망)을
  queued 로 되돌린다(1회, ``stats.stale_recoveries``). 두 번째로 멈추면 failed('stale: …'). 큐 실행 전에 매번 부른다
  (R3 minor 33).
- stats 의 오류 문구(error·errors·store_errors·skipped 키 아래 문자열)는 비밀값·개인정보를 가린 뒤 저장한다
  (읽기 전용 토큰으로 /jobs 를 봐도 노출 없음, R3 minor 14).
- ``--once``: 큐에 있는 잡을 비울 때까지(최대 ``--max-jobs``) 실행하고 0 으로 끝난다(운영 점검·CI). 시간표·
  참조 표 자동 등록은 하지 않는다. 스키마가 없으면(마이그레이션 전) 경고만 남기고 0.
- 상주: 기동 시 참조 표가 비면 reference.refresh 1회(jobs.ensure_reference), APScheduler 시간표 시작,
  매 주기 degraded 복구 감지(degraded.check_recovery) → 큐 실행.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import argparse
import signal
import threading
import time
from collections.abc import Mapping, Sequence
from datetime import datetime
from types import FrameType
from typing import Any, Final

from sqlalchemy import inspect, select, update
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.core.logging import get_logger
from app.core.protocols import JudgeUnavailable
from app.core.redact import redact_obj, redact_text
from app.core.settings import get_settings
from app.models import JobRun
from app.scheduler.context import SchedulerContext, default_context
from app.scheduler.jobs import JobError

__all__ = [
    "claim",
    "execute",
    "main",
    "queued_ids",
    "recover_stale",
    "redact_stats",
    "run_once",
    "run_until_idle",
    "sweep_api_events",
]

log = get_logger("app.worker")
ERROR_TEXT_MAX = 500
RECOVERY_EVERY_S = 300.0
STALE_FACTOR: Final = 3.0
MAX_STALE_RECOVERIES: Final = 1
ERROR_KEYS: Final = frozenset({"error", "errors", "error_text", "store_errors", "skipped", "message"})


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


def redact_stats(stats: Mapping[str, Any], secrets: Sequence[str] | None = None) -> dict[str, Any]:
    """오류 문구 키(``ERROR_KEYS``) 아래 값만 가린다(다른 값 — sha256·경로 등 — 은 그대로). 중첩 dict 도 따라간다."""
    sec = list(secrets) if secrets is not None else get_settings().secret_values()

    def walk(obj: Any) -> Any:
        if isinstance(obj, Mapping):
            return {k: (redact_obj(v, sec) if str(k) in ERROR_KEYS else walk(v)) for k, v in obj.items()}
        if isinstance(obj, list):
            return [walk(v) for v in obj]
        return obj

    out: dict[str, Any] = walk(dict(stats))
    return out


# ---------------------------------------------------------------- 하트비트·멈춘 잡 회수


def _heartbeat_s() -> float:
    return float(get_settings().worker_heartbeat_s)


def _beat(ctx: SchedulerContext, job_id: int) -> None:
    try:
        with ctx.session_factory() as session:
            row = session.get(JobRun, job_id)
            if row is None or row.status != "running" or row.locked_by != ctx.worker_id[:64]:
                return
            row.stats = {**(row.stats or {}), "heartbeat_at": ctx.iso_now()}
            session.commit()
    except Exception:  # DB 잠김 등 — 다음 주기에 다시
        log.warning("worker.heartbeat.error", extra={"job_id": job_id})


class _Heartbeat:
    """실행 중 잡의 하트비트 스레드(``with`` 동안)."""

    def __init__(self, ctx: SchedulerContext, job_id: int, interval: float) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, args=(ctx, job_id, interval), name=f"heartbeat-{job_id}", daemon=True
        )

    def _run(self, ctx: SchedulerContext, job_id: int, interval: float) -> None:
        while not self._stop.wait(interval):
            _beat(ctx, job_id)

    def __enter__(self) -> _Heartbeat:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=5)


def _parse_iso(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def recover_stale(ctx: SchedulerContext, *, stale_after_s: float | None = None) -> list[int]:
    """running 인데 하트비트가 끊긴 잡 → queued(1회) / 또 멈추면 failed. 회수한 잡 id."""
    limit = stale_after_s if stale_after_s is not None else STALE_FACTOR * _heartbeat_s()
    now = ctx.now()
    out: list[int] = []
    with ctx.session_factory() as session:
        for row in session.scalars(select(JobRun).where(JobRun.status == "running").order_by(JobRun.id)):
            stats = dict(row.stats or {})
            last = _parse_iso(stats.get("heartbeat_at")) or _parse_iso(row.started_at)
            if last is None:
                continue
            try:
                age = (now - last).total_seconds()
            except TypeError:  # 시간대 표기가 섞인 옛 행 — 판단하지 않는다
                continue
            if age < limit:
                continue
            n = int(stats.get("stale_recoveries") or 0)
            who = row.locked_by
            if n < MAX_STALE_RECOVERIES:
                row.status, row.locked_by, row.started_at = "queued", None, None
                row.stats = {"stale_recoveries": n + 1, "stale_worker": who}
            else:
                row.status, row.finished_at = "failed", ctx.iso_now()
                row.error_text = f"stale: worker 응답 없음({int(age)}초, {who}) — 회수 {n}회 후 실패"
                row.stats = {**stats, "stale_recoveries": n}
            out.append(row.id)
            log.warning("worker.job.stale", extra={"job_id": row.id, "requeued": n < MAX_STALE_RECOVERIES})
        session.commit()
    return out


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
        with _Heartbeat(ctx, job_id, _heartbeat_s()):
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
        row.stats = redact_stats(_jsonable(stats))
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


def sweep_api_events(ctx: SchedulerContext) -> list[int]:
    """서버 쪽 알림(R3 m13): API 가 만든 critical 이벤트(사람 확인 접수·생활권 편집) 중 아직 재판정 잡에 실리지 않은 것 →
    rejudge 등록(그 잡이 웹훅을 보내고 stats 에 ``notified_event_ids`` 로 남긴다). 화면 토스트 클릭을 기다리지 않는다.
    등록한 잡 id(같은 스냅샷 queued 잡이 있으면 합쳐진다)."""
    from app.scheduler.notify import pending_api_events
    from app.scheduler.rejudge import enqueue_rejudge

    out: list[int] = []
    try:
        with ctx.session_factory() as session:
            for ev in pending_api_events(session, now=ctx.now(), sent=ctx.notifier.sent_ids):
                if ev.snapshot_id is None:
                    continue
                job = enqueue_rejudge(
                    session, ev.snapshot_id, [ev.complex_id] if ev.complex_id is not None else None,
                    f"서버 알림·재판정: {ev.entity}.{ev.field} 변경", change_event_ids=[ev.id], now=ctx.now(),
                )  # fmt: skip
                if job.id not in out:
                    out.append(job.id)
            session.commit()
    except (OperationalError, ProgrammingError):  # 스키마 전 — 다음 주기에
        log.warning("worker.sweep.no_schema")
    return out


def run_until_idle(ctx: SchedulerContext, max_jobs: int = 200) -> list[int]:
    recover_stale(ctx)
    sweep_api_events(ctx)
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

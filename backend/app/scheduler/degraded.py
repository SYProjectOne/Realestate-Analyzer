"""판정기 장애(degraded) 모드 (RA §10 runbook, T18, protocols.JudgeUnavailable).

- ``JudgeUnavailable`` 을 받으면 수집·정규화는 계속하고(이미 commit 됨) 스냅샷을 ``degraded=true`` 로 표시한다.
  점수는 계산하지 않는다(스냅샷 status 는 building 그대로 — publish 안 함). 플래그 위치 = ``snapshot.degraded``
  (계약 컬럼, API 의 Dashboard·JudgmentStats·health 가 읽는다).
- 복구 감지(``check_recovery``): degraded 스냅샷이 있으면 판정기를 시험 연결해 보고(``ctx.judge_available``),
  되면 그 스냅샷마다 미처리 rejudge 잡을 1개씩 자동 등록한다(이미 queued·running 이면 새로 넣지 않음).
  rejudge 가 판정까지 끝내면 degraded=false 로 돌아온다(pipeline.py).
"""

# ruff: noqa: E501  (한국어 docstring·로그 필드)

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import JobRun, Snapshot

if TYPE_CHECKING:
    from app.scheduler.context import SchedulerContext

__all__ = ["RECOVERY_REASON", "check_recovery", "clear_degraded", "degraded_snapshots", "mark_degraded"]

log = get_logger("app.scheduler.degraded")
RECOVERY_REASON = "판정기 복구: degraded 스냅샷 재판정"


def mark_degraded(session: Session, snapshot_id: int) -> None:
    snap = session.get(Snapshot, snapshot_id)
    if snap is not None and not snap.degraded:
        snap.degraded = True
        session.flush()
        log.warning("worker.degraded", extra={"snapshot_id": snapshot_id})


def clear_degraded(session: Session, snapshot_id: int) -> None:
    snap = session.get(Snapshot, snapshot_id)
    if snap is not None and snap.degraded:
        snap.degraded = False
        session.flush()
        log.info("worker.recovered", extra={"snapshot_id": snapshot_id})


def degraded_snapshots(session: Session) -> list[Snapshot]:
    return list(session.scalars(select(Snapshot).where(Snapshot.degraded.is_(True)).order_by(Snapshot.id)))


def _has_pending_rejudge(session: Session, snapshot_id: int) -> bool:
    for job in session.scalars(
        select(JobRun).where(JobRun.job_name == "rejudge", JobRun.status.in_(("queued", "running")))
    ):
        if (job.payload or {}).get("snapshot_id") == snapshot_id:
            return True
    return False


def check_recovery(ctx: SchedulerContext) -> list[int]:
    """판정기가 돌아왔으면 degraded 스냅샷마다 rejudge 1개 등록. 등록한 잡 id 목록."""
    from app.scheduler.rejudge import enqueue_rejudge

    with ctx.session_factory() as session:
        pending = [s.id for s in degraded_snapshots(session) if not _has_pending_rejudge(session, s.id)]
    if not pending:
        return []
    if not ctx.judge_available():
        return []
    ctx.reset_adapter()  # 끊겼던 연결은 버리고 새로
    ids: list[int] = []
    with ctx.session_factory() as session:
        for sid in pending:
            job = enqueue_rejudge(session, sid, None, RECOVERY_REASON, now=ctx.now())
            ids.append(job.id)
        session.commit()
    log.info("worker.recovery_enqueued", extra={"jobs": len(ids)})
    return ids

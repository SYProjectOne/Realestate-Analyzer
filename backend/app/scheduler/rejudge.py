"""재판정 (RA §4-4 rejudge, §5 WP7): 변경된 단지만 P1~P9 를 다시 돈다.

- 등록(``enqueue_rejudge``): 같은 스냅샷에 아직 queued 인 rejudge 가 있으면 새 잡을 만들지 않고 그 잡의
  complex_ids 에 합친다(None = 전부가 이긴다) — 변경 감지·사람 확인·복구가 겹쳐도 잡은 1개.
- 실행(``handle_rejudge``): ``pipeline.run_pipeline(complex_ids=…)``. 같은 입력은 판정기를 다시 부르지 않는다
  (judge/cache.py 의 input_hash — 두 번째 실행의 실제 호출 0, T17). 끝나면 snapshot.publish 잡을 등록한다.
- 판정기 장애면 잡은 failed(error_text='judge_unavailable …')이고 스냅샷은 degraded — 복구 시 degraded.py 가
  다시 등록한다(T18).
- 알림: payload ``change_event_ids`` 의 critical 이벤트를 웹훅으로 보낸다(사람 확인·생활권 편집처럼 API 가 만든
  이벤트도 알림이 가도록 — R3 minor 13). 수집 잡이 이미 보낸 이벤트는 Notifier 가 다시 보내지 않는다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ChangeEvent, Complex, JobRun
from app.scheduler.jobs import JobError, enqueue

if TYPE_CHECKING:
    from app.scheduler.context import SchedulerContext

__all__ = ["enqueue_rejudge", "handle_rejudge"]


def _merge(a: list[int] | None, b: Iterable[int] | None) -> list[int] | None:
    if a is None or b is None:
        return None
    return sorted(set(a) | set(b))


def enqueue_rejudge(
    session: Session,
    snapshot_id: int,
    complex_ids: Iterable[int] | None,
    reason: str,
    *,
    scenario_id: int | None = None,
    change_event_ids: Iterable[int] | None = None,
    now: datetime | None = None,
) -> JobRun:
    """rejudge 잡 1개(같은 스냅샷 queued 잡이 있으면 합친다). commit 은 호출자."""
    ids = None if complex_ids is None else sorted(set(complex_ids))
    events = sorted(set(change_event_ids)) if change_event_ids is not None else None
    for job in session.scalars(
        select(JobRun).where(JobRun.job_name == "rejudge", JobRun.status == "queued").order_by(JobRun.id)
    ):
        p = dict(job.payload or {})
        if p.get("snapshot_id") != snapshot_id or p.get("scenario_id") != scenario_id:
            continue
        p["complex_ids"] = _merge(p.get("complex_ids"), ids)
        if events:
            p["change_event_ids"] = sorted(set(p.get("change_event_ids") or []) | set(events))
        if reason not in str(p.get("reason", "")):
            p["reason"] = f"{p.get('reason', '')}; {reason}".strip("; ")[:200]
        job.payload = p
        session.flush()
        return job
    payload: dict[str, Any] = {
        "snapshot_id": snapshot_id,
        "scenario_id": scenario_id,
        "complex_ids": ids,
        "reason": reason[:200] or "재판정",
    }
    if events:
        payload["change_event_ids"] = events
    return enqueue(session, "rejudge", payload, kind="rejudge", now=now, dedupe=False)


def handle_rejudge(ctx: SchedulerContext, job: JobRun) -> dict[str, Any]:
    from app.scheduler.pipeline import run_pipeline

    p = job.payload or {}
    snapshot_id = int(p["snapshot_id"])
    ids = p.get("complex_ids")
    notified = _notify_events(ctx, [int(i) for i in p.get("change_event_ids") or []])
    result = run_pipeline(
        ctx,
        snapshot_id,
        complex_ids=None if ids is None else [int(i) for i in ids],
        scenario_id=p.get("scenario_id"),
        reason=str(p.get("reason") or "재판정"),
    )
    stats = result.stats()
    stats["notify"] = notified
    if result.degraded:
        raise JobError("judge_unavailable: 판정기 연결 실패 — degraded 모드(복구 후 재판정 자동 등록)", stats)
    with ctx.session_factory() as session:
        enqueue(
            session, "snapshot.publish", {"snapshot_id": result.snapshot_id}, kind="scheduled", now=ctx.now()
        )
        session.commit()
    return stats


def _notify_events(ctx: SchedulerContext, event_ids: list[int]) -> dict[str, Any]:
    """payload 의 change_event 중 critical 을 웹훅으로(건별 guard·중복 방지는 Notifier)."""
    if not event_ids:
        return {"sent": 0, "skipped": "no_events"}
    with ctx.session_factory() as session:
        events = list(session.scalars(select(ChangeEvent).where(ChangeEvent.id.in_(event_ids))))
        cids = sorted({e.complex_id for e in events if e.complex_id is not None})
        names = (
            {c.id: c.name for c in session.scalars(select(Complex).where(Complex.id.in_(cids)))}
            if cids
            else {}
        )
    return ctx.notifier.notify(events, names).stats()

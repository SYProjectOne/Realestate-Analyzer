"""판정기 버전·모델 변경 감지 (DECISIONS D6, RA §10 runbook '판정기 버전 변경').

adapter_version = ``<코드>+jev-mcp@<서버 버전>+<응답 model>`` 이 바뀌면 모든 input_hash 가 바뀐다. 그때
``change_event(entity=judge, field=version, severity=critical)`` 1건 + 지역마다 최신 스냅샷 **전체 재판정 1회**.

- 이전 버전 = 이번 실행 전 judgment_log 마지막 **정상 행**(ok·review·escaped)의 adapter_version.
  error·blocked 행은 판정기 응답 없이(모델을 모른 채) 쓰였을 수 있어 근거로 쓰지 않는다(R3 M12).
  행이 없으면(첫 실행·MockAdapter 는 DB에 쓰지 않음) 비교하지 않는다.
- 이전 버전에 모델 접미가 없고 새 버전이 거기에 모델만 붙인 것이면(처음 모델을 알게 됨) 변경이 아니다.
- 같은 (이전 → 새) 변경 이벤트가 이미 있으면 다시 만들지 않는다(1회).
"""

# ruff: noqa: E501  (한국어 docstring·로그 필드)

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.judge.cache import NOT_VERSION_EVIDENCE
from app.models import ChangeEvent, JudgmentLog, Region

if TYPE_CHECKING:
    from app.scheduler.context import SchedulerContext

__all__ = ["is_version_change", "last_logged", "record_version_change"]

log = get_logger("app.scheduler.judge_version")
REASON = "판정기 버전 변경"


def last_logged(session: Session) -> tuple[int, str | None]:
    """(마지막 정상 judgment_log seq, 그 행의 adapter_version). error·blocked 제외. 없으면 (0, None)."""
    row = session.scalars(
        select(JudgmentLog)
        .where(JudgmentLog.status.not_in(NOT_VERSION_EVIDENCE))
        .order_by(JudgmentLog.seq.desc())
        .limit(1)
    ).first()
    return (row.seq, row.adapter_version) if row is not None else (0, None)


def is_version_change(before: str | None, after: str | None) -> bool:
    """before → after 가 판정기 버전·모델 변경인가. 모델을 처음 알게 된 것(접미만 붙음)은 아니다."""
    if not before or not after or before == after:
        return False
    tail = after[len(before) + 1 :] if after.startswith(before + "+") else None
    return not (tail and "+" not in tail)


def record_version_change(
    ctx: SchedulerContext, session: Session, before: str | None, after: str | None, *, snapshot_id: int | None
) -> ChangeEvent | None:
    """before ≠ after 면 이벤트 + 전체 재판정 등록. commit 은 호출자."""
    from app.scheduler.rejudge import enqueue_rejudge
    from app.scheduler.snapshots import latest_for_region, mark_compare_base

    if not is_version_change(before, after):
        return None
    assert before is not None and after is not None
    dup = session.scalars(
        select(ChangeEvent).where(
            ChangeEvent.entity == "judge",
            ChangeEvent.field == "version",
            ChangeEvent.old_text == before,
            ChangeEvent.new_text == after,
        )
    ).first()
    if dup is not None:
        return None
    ev = ChangeEvent(
        snapshot_id=snapshot_id,
        entity="judge",
        entity_id=None,
        field="version",
        old_text=before,
        new_text=after,
        detected_at=ctx.iso_now(),
        severity="critical",
        triggers_rejudge=True,
        complex_id=None,
    )
    session.add(ev)
    session.flush()
    for region_id in list(session.scalars(select(Region.id).order_by(Region.id))):
        snap = latest_for_region(session, region_id)
        if snap is not None:
            # M-6: 최신이 미발행 리비전 1 이면 새 리비전이 생기지 않는다 — 직전 발행 스냅샷을 비교 기준으로 달아 delta 표
            mark_compare_base(session, snap, f"{REASON}: {after}")
            enqueue_rejudge(
                session, snap.id, None, f"{REASON}: {after}", change_event_ids=[ev.id], now=ctx.now()
            )
    log.warning("worker.judge_version_changed", extra={"event_id": ev.id})
    ctx.notifier.notify([ev])
    return ev

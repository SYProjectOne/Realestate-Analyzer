"""job_run 등록·표현 (RA §4-4, ADR-3, contracts/schemas/job_run.json).

api 는 판정기를 부르지 않는다 — 재판정·수집·보고서는 ``job_run`` 행(queued)으로 넣고 worker 가 집는다.
payload 는 job_name 별 스키마(contracts/schemas/job_payloads)로 검증한다(불일치 422).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.api.contract import check_schema
from app.core.time import now_kst
from app.models import JobRun

__all__ = ["PAYLOAD_SCHEMAS", "enqueue", "job_view", "now_iso"]

PAYLOAD_SCHEMAS: dict[str, str] = {
    "collect.daily": "CollectDailyPayload",
    "collect.weekly": "CollectWeeklyPayload",
    "rejudge": "RejudgePayload",
    "report": "ReportRequest",
    "snapshot.publish": "SnapshotPublishPayload",
    "reference.refresh": "ReferenceRefreshPayload",
    "region.bootstrap": "RegionBootstrapPayload",
    "claim.reverify": "ClaimReverifyPayload",  # 계약 2026-10-09.4 (PATCH /claims/{id})
    "backup": "BackupPayload",  # 계약 2026-10-09.8 (D11-8)
    "region.expand": "RegionExpandPayload",  # 계약 2026-10-09.8 (PATCH /regions/{id}, D11-7)
}


def now_iso() -> str:
    return now_kst().isoformat(timespec="seconds")


def enqueue(session: Session, job_name: str, payload: dict[str, Any], *, kind: str | None = None) -> JobRun:
    """payload 검증 후 queued 행 1개(flush, commit 은 호출자).

    kind 기본 = rejudge 잡이면 rejudge, 아니면 manual."""
    check_schema(PAYLOAD_SCHEMAS[job_name], payload, root="payload")
    row = JobRun(
        job_name=job_name,
        kind=kind or ("rejudge" if job_name == "rejudge" else "manual"),
        payload=dict(payload),
        scheduled_at=now_iso(),
        status="queued",
        stats={},
    )
    session.add(row)
    session.flush()
    return row


def job_view(row: JobRun) -> dict[str, Any]:
    progress = row.progress
    if isinstance(progress, dict) and not {"done", "total"} <= set(progress):
        progress = None
    return {
        "id": row.id,
        "job_name": row.job_name,
        "kind": row.kind,
        "payload": dict(row.payload or {}),
        "scheduled_at": row.scheduled_at,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "status": row.status,
        "stats": dict(row.stats or {}),
        "error_text": row.error_text,
        "progress": progress,
    }

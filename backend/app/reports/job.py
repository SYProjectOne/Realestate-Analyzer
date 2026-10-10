"""``report`` 잡 처리 함수 — WP7 runner 가 부른다(README '잡 규약').

payload = ``ReportRequest{snapshot_id, format: html|pdf, compare_snapshot_id?, scenario_id?}``(DECISIONS D4).
성공하면 job_run.stats 에 넣을 dict 를 돌려준다. 실패는 예외:
- ``ReportBlocked`` — contradicted 주장이 남음. runner 는 status=failed, error_text=``blocked: <reason>``,
  stats={"blocked_reason": reason} (API 의 Report.blocked_reason).
- ``ReportNotFound`` — 스냅샷·시나리오 없음(failed).
- ``ValueError`` — payload 형식 오류(pydantic ValidationError 포함, failed).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from sqlalchemy.orm import Session

from app.core.contracts_gen import ReportRequest
from app.core.db import get_session
from app.models import JobRun
from app.reports.export import GeneratedReport, generate

__all__ = ["JOB_NAME", "handle", "run_report_job"]

JOB_NAME: Final = "report"


def _stats(rep: GeneratedReport, req: ReportRequest) -> dict[str, Any]:
    return {
        "path": str(rep.path),
        "filename": rep.filename,
        "format": rep.format,
        "size_bytes": rep.size_bytes,
        "sha256": rep.sha256,
        "snapshot_id": req.snapshot_id,
        "compare_snapshot_id": req.compare_snapshot_id,
        "scenario_id": req.scenario_id,
        "scenario_code": rep.scenario_code,
        "charts": rep.charts,
        "charts_inlined": rep.charts_inlined,
        "blocked_reason": None,
    }


def run_report_job(
    payload: Mapping[str, Any],
    *,
    session: Session | None = None,
    out_dir: Path | None = None,
    job_id: int | None = None,
) -> dict[str, Any]:
    """payload 를 검증하고 보고서 파일을 ``REPORT_DIR``(또는 out_dir)에 만든다. 반환 = job_run.stats.
    ``job_id`` 는 파일 이름에 들어간다(같은 기준일·리비전 보고서끼리 덮어쓰지 않게 — R3 4차 C-4)."""
    req = ReportRequest.model_validate(dict(payload))
    kwargs: dict[str, Any] = {
        "compare_snapshot_id": req.compare_snapshot_id,
        "scenario_id": req.scenario_id,
        "out_dir": out_dir,
        "job_id": job_id,
    }
    if session is not None:
        rep = generate(session, req.snapshot_id, req.format, **kwargs)
    else:
        with get_session() as s:
            rep = generate(s, req.snapshot_id, req.format, **kwargs)
    return _stats(rep, req)


def handle(job: JobRun, session: Session) -> dict[str, Any]:
    """job_run 행 하나 처리(상태 전이는 runner 몫). ``job.job_name == 'report'`` 이어야 한다."""
    if job.job_name != JOB_NAME:
        raise ValueError(f"report 잡이 아님: {job.job_name}")
    return run_report_job(job.payload or {}, session=session, job_id=job.id)

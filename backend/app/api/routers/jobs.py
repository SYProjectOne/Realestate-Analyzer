"""잡 큐 (G5·G7·G8): api 는 job_run 행만 넣는다(판정기를 부르지 않는다).

claim.reverify 는 POST /jobs 로 넣을 수 없다(계약 2026-10-09.6 JobCreateName → 422) — PATCH /claims/{id} 의 같은 대상
검사·사실 강등(D10-3)을 건너뛰지 않게.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.contract import check_body
from app.api.deps import DB
from app.api.errors import not_found, validation_error
from app.api.jobs import enqueue, job_view
from app.models import JobRun
from app.models.enums import JOB_NAME

router = APIRouter(tags=["jobs"])

# 계약 JobName(enums.JOB_NAME — 2026-10-09.4 claim.reverify 포함)
JOB_NAMES = "^(" + "|".join(re.escape(n) for n in JOB_NAME) + ")$"


@router.get("/jobs")
def list_jobs(
    session: DB,
    status: Annotated[str | None, Query(pattern="^(queued|running|done|failed)$")] = None,
    job_name: Annotated[str | None, Query(pattern=JOB_NAMES)] = None,
    since: Annotated[str | None, Query(min_length=10, max_length=32)] = None,
    size: Annotated[int, Query(ge=1, le=1000)] = 50,
) -> JSONResponse:
    stmt = select(JobRun)
    if status:
        stmt = stmt.where(JobRun.status == status)
    if job_name:
        stmt = stmt.where(JobRun.job_name == job_name)
    if since:
        stmt = stmt.where(JobRun.scheduled_at >= since)
    rows = session.scalars(stmt.order_by(JobRun.id.desc()).limit(size))
    return JSONResponse([job_view(r) for r in rows])


@router.post("/jobs", status_code=202)
def create_job(session: DB, body: Annotated[Any, Body()] = None) -> JSONResponse:
    check_body("createJob", body)
    if body["job_name"] == "claim.reverify":  # 계약 JobCreateName 이 이미 막는다 — 이중 방어(D10-3)
        raise validation_error("claim.reverify 는 PATCH /claims/{id} 로만 등록한다", ("body", "job_name"))
    row = enqueue(session, body["job_name"], body["payload"])
    session.commit()
    return JSONResponse(job_view(row), status_code=202)


@router.get("/jobs/{id}")
def get_job(session: DB, id: int) -> JSONResponse:
    row = session.get(JobRun, id)
    if row is None:
        raise not_found(f"job {id}")
    return JSONResponse(job_view(row))

"""보고서 (G8, DECISIONS D4): POST → report 잡, 목록, 다운로드(html|pdf). id = job_run.id."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Annotated, Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select

from app.api.contract import check_body
from app.api.deps import DB, get_snapshot, in_db_range, settings_of
from app.api.errors import conflict, not_found
from app.api.jobs import enqueue, job_view
from app.models import JobRun

router = APIRouter(tags=["reports"])

_SHA = re.compile(r"^[0-9a-f]{64}$")


def report_view(row: JobRun) -> dict[str, Any]:
    p = row.payload or {}
    st = row.stats or {}
    done = row.status == "done"
    size = st.get("size_bytes")
    sha = st.get("sha256")
    return {
        "id": row.id,
        "snapshot_id": int(p.get("snapshot_id") or 0),
        "compare_snapshot_id": p.get("compare_snapshot_id"),
        "format": p.get("format") if p.get("format") in ("html", "pdf") else "html",
        "status": row.status,
        "created_at": row.scheduled_at,
        "finished_at": row.finished_at,
        "filename": st.get("filename") if done else None,
        "size_bytes": size if done and isinstance(size, int) and size >= 0 else None,
        "sha256": sha if done and isinstance(sha, str) and _SHA.match(sha) else None,
        "blocked_reason": row.error_text if row.status == "failed" else None,
    }


@router.get("/reports")
def list_reports(session: DB, snapshot_id: int | None = None) -> JSONResponse:
    if not in_db_range(snapshot_id):
        return JSONResponse([])
    rows = session.scalars(select(JobRun).where(JobRun.job_name == "report").order_by(JobRun.id.desc()))
    out = [
        report_view(r)
        for r in rows
        if snapshot_id is None or (r.payload or {}).get("snapshot_id") == snapshot_id
    ]
    return JSONResponse(out)


def contradicted(session: Any, snapshot_id: int) -> int:
    """남은 contradicted 수 — 분할 재검증 자식이 있는 주장은 막지 않는다(R3 M8, publish 검사와 같은 함수)."""
    from app.judge.claims import remaining_contradicted

    return len(remaining_contradicted(session, snapshot_id))


@router.post("/reports", status_code=202)
def create_report(session: DB, body: Annotated[Any, Body()] = None) -> JSONResponse:
    check_body("createReport", body)
    snap = get_snapshot(session, body["snapshot_id"])
    if body.get("compare_snapshot_id") is not None:
        get_snapshot(session, body["compare_snapshot_id"])
    n = contradicted(session, snap.id)
    if n:
        raise conflict(f"contradicted claim {n}건이 남아 있어 보고서를 만들 수 없다", code="publish_blocked")
    row = enqueue(session, "report", dict(body))
    session.commit()
    return JSONResponse(job_view(row), status_code=202)


def _report_path(base: Path, rel: str) -> Path | None:
    if not rel or PureWindowsPath(rel).drive or PurePosixPath(rel).is_absolute():
        candidate = Path(rel)
        try:
            candidate.resolve().relative_to(base.resolve())
        except (ValueError, OSError):
            return None
        return candidate
    parts = PurePosixPath(rel.replace("\\", "/")).parts
    if any(p in ("..", ".") for p in parts):
        return None
    return base.joinpath(*parts)


@router.get("/reports/{id}")
def download_report(session: DB, request: Request, id: int) -> Any:
    row = session.get(JobRun, id)
    if row is None or row.job_name != "report":
        raise not_found(f"report {id}")
    if row.status != "done":
        detail = f"report {id} is {row.status}"
        if row.status == "failed" and row.error_text:
            detail += f": {row.error_text}"[:300]
        raise conflict(detail)
    st = row.stats or {}
    base = settings_of(request).report_dir
    path = _report_path(base, str(st.get("path") or ""))
    if path is None or not path.is_file():
        raise not_found(f"report {id} file")
    fmt = (row.payload or {}).get("format")
    media = "application/pdf" if fmt == "pdf" or path.suffix.lower() == ".pdf" else "text/html; charset=utf-8"
    filename = str(st.get("filename") or path.name)
    return FileResponse(path, media_type=media, filename=filename)

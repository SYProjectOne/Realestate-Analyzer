"""보고서 (G8, DECISIONS D4): POST → report 잡, 목록, 다운로드(html|pdf). id = job_run.id."""

# ruff: noqa: E501  (한국어 docstring)

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
    if snap.status != "published":
        # R3 4차 M-16: 판정이 끝나지 않은(building) 리비전은 보고서를 만들지 않는다 — 파생 행이 반쯤 찬 상태
        raise conflict(f"snapshot {snap.id} 는 발행 전({snap.status})이라 보고서를 만들 수 없다")
    from app.api.errors import ApiError, validation_error

    if body.get("compare_snapshot_id") is not None:
        cmp = get_snapshot(session, body["compare_snapshot_id"])
        # R3 5차 M5: 비교 기준도 발행 리비전(저장본 — D13-1)·같은 지역만(지역끼리는 독립 분석, D11-10)
        if cmp.region_id != snap.region_id:
            raise validation_error(
                f"비교 스냅샷 {cmp.id} 은 다른 지역({cmp.region_id})이다", ("body", "compare_snapshot_id")
            )
        if cmp.status != "published":
            raise conflict(f"비교 스냅샷 {cmp.id} 는 발행 전({cmp.status})이라 비교할 수 없다")
        # R3 6차 m5: 비교 기준은 대상보다 **앞선** 리비전(같은 스냅샷·더 새 리비전은 '이전 → 현재' 표가 뒤집힌다)
        if (cmp.asof_date, int(cmp.revision or 1), cmp.id) >= (
            snap.asof_date,
            int(snap.revision or 1),
            snap.id,
        ):
            raise validation_error(
                f"비교 스냅샷 {cmp.id} 은 대상 {snap.id} 와 같거나 더 새 리비전이다 — 앞선 리비전을 고른다",
                ("body", "compare_snapshot_id"),
            )
    if body.get("scenario_id") is not None:
        from app.models import Scenario
        from app.reports.data import scenario_in_revision

        if session.get(Scenario, int(body["scenario_id"])) is None:
            raise validation_error(f"시나리오 {body['scenario_id']} 없음", ("body", "scenario_id"))
        if not scenario_in_revision(session, snap, int(body["scenario_id"])):
            # D14-3(R3 6차 N-M1): 그 리비전 발행 뒤 만든 시나리오 — 결과는 시나리오 실행이 만드는 새 리비전에 있다
            msg = (
                f"시나리오 {body['scenario_id']} 는 리비전 {snap.id} 에 없다(발행 뒤 만든 시나리오) — "
                "시나리오 실행으로 생긴 리비전을 고른다"
            )
            raise ApiError(
                422,
                "scenario_not_in_revision",
                msg,
                field_errors=[{"loc": ["body", "scenario_id"], "msg": msg}],
            )
    n = contradicted(session, snap.id)
    if n:
        raise conflict(f"contradicted claim {n}건이 남아 있어 보고서를 만들 수 없다", code="publish_blocked")
    row = enqueue(session, "report", dict(body))
    session.commit()
    return JSONResponse(job_view(row), status_code=202)


def _report_path(base: Path, rel: str) -> Path | None:
    """잡 stats 경로 → 파일. 저장은 ``REPORT_DIR`` 기준 상대 이름(``reports.job.stored_path``), 해석도 같은 기준(K3).
    절대 경로는 REPORT_DIR 안일 때만. 옛 잡(상대 REPORT_DIR 를 앞에 붙여 저장한 경로 — 예 'data/reports/x.html',
    '../r4/reports/x.html')은 그 앞부분을 떼고 읽는다. 그 밖의 '..'·'.' 는 거부."""
    if not rel:
        return None
    if PureWindowsPath(rel).drive or PurePosixPath(rel).is_absolute():
        candidate = Path(rel)
        try:
            candidate.resolve().relative_to(base.resolve())
        except (ValueError, OSError):
            return None
        return candidate
    norm = rel.replace("\\", "/")
    prefix = PurePosixPath(base.as_posix().replace("\\", "/")).as_posix()
    for head in (prefix, prefix.removeprefix("./")):
        if head not in ("", ".") and norm.startswith(head.rstrip("/") + "/"):
            norm = norm[len(head.rstrip("/")) + 1 :]
            break
    parts = PurePosixPath(norm).parts
    if not parts or any(p in ("..", ".") for p in parts):
        return None
    # R3 6차 m6: 'x/C:outside.txt' 같은 Windows 드라이브 상대 조각은 joinpath 가 base 를 버린다 — 조각에 드라이브·콜론 금지,
    # 이어 붙인 결과도 REPORT_DIR 안이어야 한다
    if any(":" in p or PureWindowsPath(p).drive or PureWindowsPath(p).root for p in parts):
        return None
    out = base.joinpath(*parts)
    try:
        out.resolve().relative_to(base.resolve())
    except (ValueError, OSError):
        return None
    return out


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

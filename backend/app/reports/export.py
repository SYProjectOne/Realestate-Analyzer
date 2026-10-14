"""보고서 생성 진입점: ``generate()``(세션 1개로 html|pdf 파일 1개) · ``ReportExporter``(Exporter Protocol).

순서: contradicted 검사·데이터 적재(``data.load_report``) → diff(비교 스냅샷이 있으면) → HTML 렌더
→ (pdf면) 인쇄.
거부·없음은 파일을 만들기 전에 예외로 끝난다. 쓰기는 임시 파일 → rename(원자적).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from app.core.contracts_gen import Snapshot as SnapshotDTO
from app.core.db import get_sessionmaker
from app.core.paths import report_dir
from app.core.protocols import ExportFormat
from app.reports.data import load_report
from app.reports.diff import diff_snapshots
from app.reports.pdf import html_to_pdf
from app.reports.render import render_html

__all__ = ["GeneratedReport", "ReportExporter", "default_compare", "generate", "report_filename"]

FORMATS: tuple[ExportFormat, ...] = ("html", "pdf")


@dataclass(frozen=True, slots=True)
class GeneratedReport:
    path: Path
    filename: str
    format: Literal["html", "pdf"]
    size_bytes: int
    sha256: str
    snapshot_id: int
    compare_snapshot_id: int | None
    scenario_code: str
    charts: int
    charts_inlined: bool


def report_filename(
    asof: str,
    fmt: str,
    *,
    compare_asof: str | None = None,
    scenario_code: str = "base",
    region_id: int | None = None,
    revision: int = 1,
    compare_revision: int | None = None,
    job_id: int | None = None,
) -> str:
    """``report_r1_2026-10-08-r2_vs_2026-10-08-r1_j57.pdf`` (계약 .9 Report 예시).

    R3 4차 C-4: 같은 기준일의 리비전·지역·잡끼리 파일이 겹치면 ``os.replace`` 가 앞 보고서를 덮어써 다운로드 내용과
    잡 stats 의 sha256 이 어긋났다 — 지역 id·리비전·(잡이면) 잡 id 를 이름에 넣는다. 기본 아닌 시나리오는 접미사."""
    name = "report"
    if region_id is not None:
        name += f"_r{region_id}"
    name += f"_{asof}-r{int(revision or 1)}"
    if compare_asof:
        name += f"_vs_{compare_asof}-r{int(compare_revision or 1)}"
    if scenario_code != "base":
        name += f"_{scenario_code}"
    if job_id is not None:
        name += f"_j{job_id}"
    return f"{name}.{fmt}"


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def default_compare(session: Session, snapshot_id: int) -> int | None:
    """비교 스냅샷을 주지 않았을 때의 비교 기준(D11-1): 리비전이면 바탕(revision_of) — 리비전 diff 표가 '판정기 버전 변경
    → 이전 run 과 delta 표'(RA §10)이고, 지역 확장 리비전이면 §12 '지역 추가' 장이 된다(D11-7). 리비전 1 이면 None."""
    from app.models import Snapshot

    snap_row = session.get(Snapshot, snapshot_id)
    return snap_row.revision_of if snap_row is not None else None


def generate(
    session: Session,
    snapshot_id: int,
    fmt: str,
    *,
    compare_snapshot_id: int | None = None,
    scenario_id: int | None = None,
    out_dir: Path | None = None,
    echarts_js: Path | None = None,
    job_id: int | None = None,
) -> GeneratedReport:
    """보고서 파일 1개를 만든다. ``job_id``(report 잡)는 파일 이름에 들어간다(C-4 — 잡끼리 덮어쓰지 않게).

    예외: ``ReportBlocked``(contradicted 남음) · ``ReportNotFound`` · ``ValueError``(형식).
    """
    if fmt not in FORMATS:
        raise ValueError(f"보고서 형식은 html|pdf: {fmt!r}")
    if compare_snapshot_id is None:
        compare_snapshot_id = default_compare(session, snapshot_id)
    data = load_report(session, snapshot_id, scenario_id=scenario_id, compare_snapshot_id=compare_snapshot_id)
    diff = (
        diff_snapshots(
            session,
            compare_snapshot_id,
            snapshot_id,
            scenario_code=data.scenario_code,
            scenario_id=scenario_id,
        )
        if compare_snapshot_id is not None
        else None
    )
    from app.models import Snapshot

    snap_row = session.get(Snapshot, snapshot_id)
    cmp_row = session.get(Snapshot, compare_snapshot_id) if compare_snapshot_id is not None else None
    rendered = render_html(
        data,
        diff=diff,
        echarts_js=echarts_js,
        revision=int(snap_row.revision or 1) if snap_row is not None else None,
        compare_revision=int(cmp_row.revision or 1) if cmp_row is not None else None,
    )
    target_dir = out_dir if out_dir is not None else report_dir()
    name = report_filename(
        data.asof_date,
        fmt,
        compare_asof=cmp_row.asof_date if cmp_row is not None else None,
        compare_revision=int(cmp_row.revision or 1) if cmp_row is not None else None,
        scenario_code=data.scenario_code,
        region_id=snap_row.region_id if snap_row is not None else None,
        revision=int(snap_row.revision or 1) if snap_row is not None else 1,
        job_id=job_id,
    )
    path = target_dir / name
    html_bytes = rendered.html.encode("utf-8")
    if fmt == "html":
        _atomic_write(path, html_bytes)
    else:
        target_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_html = tempfile.mkstemp(dir=target_dir, prefix=".tmp-", suffix=".html")
        tmp_pdf = Path(tmp_html).with_suffix(".pdf.part")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(html_bytes)
            html_to_pdf(Path(tmp_html), tmp_pdf)
            os.replace(tmp_pdf, path)
        finally:
            Path(tmp_html).unlink(missing_ok=True)
            tmp_pdf.unlink(missing_ok=True)
    content = path.read_bytes()
    return GeneratedReport(
        path=path,
        filename=name,
        format="html" if fmt == "html" else "pdf",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        snapshot_id=snapshot_id,
        compare_snapshot_id=compare_snapshot_id,
        scenario_code=data.scenario_code,
        charts=rendered.charts,
        charts_inlined=rendered.charts_inlined,
    )


class ReportExporter:
    """``app.core.protocols.Exporter`` 구현. 세션은 호출마다 새로 연다(기본 = ``get_sessionmaker()``)."""

    def __init__(
        self,
        session_factory: Callable[[], Session] | None = None,
        *,
        out_dir: Path | None = None,
        scenario_id: int | None = None,
    ) -> None:
        self._factory = session_factory
        self._out_dir = out_dir
        self._scenario_id = scenario_id

    def render(
        self, snapshot: SnapshotDTO, fmt: ExportFormat, compare_snapshot: SnapshotDTO | None = None
    ) -> Path:
        factory = self._factory or get_sessionmaker()
        with factory() as session:
            rep = generate(
                session,
                snapshot.id,
                fmt,
                compare_snapshot_id=compare_snapshot.id if compare_snapshot else None,
                scenario_id=self._scenario_id,
                out_dir=self._out_dir,
            )
        return rep.path

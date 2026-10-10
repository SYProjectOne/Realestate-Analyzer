"""CLI(`python -m app.reports.cli`)와 report 잡 처리 함수(WP7 runner가 부른다)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import Settings
from app.models import Claim
from app.reports import cli
from app.reports.errors import ReportBlocked
from app.reports.job import run_report_job

from ._seed import add_contradicted_claim


def test_cli_writes_html(
    report_settings: Settings, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(["--snapshot", "12", "--format", "html", "--compare", "11", "--out", str(tmp_path)])
    assert code == 0
    files = list(tmp_path.glob("*.html"))
    assert len(files) == 1
    assert str(files[0]) in capsys.readouterr().out


def test_cli_unknown_snapshot_returns_nonzero(report_settings: Settings, tmp_path: Path) -> None:
    assert cli.main(["--snapshot", "999", "--format", "html", "--out", str(tmp_path)]) == 2


def test_job_returns_stats_into_report_dir(report_settings: Settings) -> None:
    stats = run_report_job({"snapshot_id": 11, "format": "html"})
    # R3 5차 K3: stats.path = REPORT_DIR 기준 상대 이름(다운로드가 같은 기준으로 해석)
    assert stats["path"] == stats["filename"]
    path = report_settings.report_dir / stats["path"]
    assert path.is_file()
    assert stats["filename"] == path.name and stats["size_bytes"] == path.stat().st_size
    assert len(stats["sha256"]) == 64 and stats["format"] == "html"
    assert stats["snapshot_id"] == 11 and stats["compare_snapshot_id"] is None


def test_job_rejects_bad_payload(report_settings: Settings) -> None:
    with pytest.raises(ValueError):
        run_report_job({"snapshot_id": 11, "format": "docx"})
    with pytest.raises(ValueError):
        run_report_job({"format": "html"})


def test_job_blocked_by_contradicted_claim(report_settings: Settings, factory: sessionmaker[Session]) -> None:
    with factory() as s:
        cid = add_contradicted_claim(s, 11)
        s.commit()
    try:
        with pytest.raises(ReportBlocked) as exc:
            run_report_job({"snapshot_id": 11, "format": "html"})
        assert exc.value.reason and "contradicted" in exc.value.reason
    finally:
        from app.models import Snapshot

        with factory() as s:
            s.execute(delete(Claim).where(Claim.id == cid))
            snap = s.get(Snapshot, 11)
            assert snap is not None
            snap.status = "published"  # add_contradicted_claim 이 발행 전으로 둔 것을 되돌린다
            s.commit()

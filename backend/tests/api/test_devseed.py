"""devseed (DB 가 비어 있어도 화면 연결): CLI 적재 결과·판정기 호출 없음·재실행(--reset) 멱등."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.db import get_session, reset_engine
from app.core.settings import set_settings
from app.models import (
    Complex,
    FieldProvenance,
    JudgmentLog,
    LegalDong,
    Region,
    Scenario,
    ScoreRun,
    ScoreTotal,
    Snapshot,
)

from .conftest import make_settings


def _count(model: type) -> int:
    with get_session() as s:
        return int(s.scalar(select(func.count()).select_from(model)) or 0)


def test_cli_seeds_fixture_twice(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from app.api import devseed

    settings = make_settings(tmp_path / "cli.db", tmp_path / "raw", tmp_path / "reports")
    set_settings(settings)
    try:
        assert devseed.main(["--reference", "none"]) == 0
        out = capsys.readouterr().out
        assert "complexes=16" in out and "judgments=132" in out
        first = {
            m.__name__: _count(m) for m in (Region, Snapshot, Complex, FieldProvenance, JudgmentLog, ScoreRun)
        }
        assert first["Region"] == 1 and first["Snapshot"] == 2 and first["Complex"] == 16
        # 내장 시나리오 5개 × 스냅샷 2개(12 + 11 의 T7 인천 8단지 — R3 F4 요청)
        assert first["ScoreRun"] == 10
        assert _count(Scenario) == 5
        assert _count(LegalDong) == 0  # --reference none
        # 판정기를 부르지 않는다: judgment_log 는 녹화 132건 그대로(새 행 없음)
        with get_session() as s:
            seqs = list(s.scalars(select(JudgmentLog.seq).order_by(JudgmentLog.seq)))
            assert seqs == list(range(1, 133))
            totals = {
                t.complex_id: float(t.total)
                for t in s.scalars(select(ScoreTotal).where(ScoreTotal.score_run_id == 1))
                if t.total is not None
            }
            assert round(totals[1], 2) == 5.87 and round(totals[4], 3) == 4.995
        # 원문 파일이 RAW_DIR 로 복사된다
        assert (tmp_path / "raw" / "notice" / "01_n.txt").is_file()
        # --reset(기본) 재실행 = 같은 결과
        assert devseed.main(["--reference", "none"]) == 0
        again = {
            m.__name__: _count(m) for m in (Region, Snapshot, Complex, FieldProvenance, JudgmentLog, ScoreRun)
        }
        assert again == first
    finally:
        set_settings(None)
        reset_engine()


def test_seed_refuses_existing_region_without_reset(tmp_path: Path) -> None:
    from app.api import devseed

    settings = make_settings(tmp_path / "x.db", tmp_path / "raw", tmp_path / "reports")
    set_settings(settings)
    try:
        devseed.seed(settings, reference="none")
        with pytest.raises(RuntimeError, match="이미 있다"):
            devseed.seed(settings, reference="none", reset=False)
    finally:
        set_settings(None)
        reset_engine()

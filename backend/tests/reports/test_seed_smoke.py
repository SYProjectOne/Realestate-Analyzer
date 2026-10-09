"""픽스처 로더 자체 점검(파생 테이블이 채워졌는지)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Claim, Decision, FieldProvenance, JudgmentLog, Ladder, ScoreTotal

from ._seed import SeedInfo


def test_seed_fills_derived_tables(factory: sessionmaker[Session], seed_info: SeedInfo) -> None:
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(JudgmentLog)) == 132
        assert s.scalar(select(func.count()).select_from(ScoreTotal)) == 5 * (16 + 8)
        assert (s.scalar(select(func.count()).select_from(Ladder)) or 0) > 0
        assert (s.scalar(select(func.count()).select_from(Decision)) or 0) > 0
        assert (s.scalar(select(func.count()).select_from(Claim)) or 0) > 100
        assert (s.scalar(select(func.count()).select_from(FieldProvenance)) or 0) > 703
    assert len(seed_info.complex_ids[11]) == 8
    assert len(seed_info.complex_ids[12]) == 16

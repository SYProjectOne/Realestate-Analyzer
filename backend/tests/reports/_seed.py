"""WP8 테스트 fixture — 적재는 ``app.api.devseed.seed`` 하나(R3 F3 이후).

devseed 가 사실·출처·판정 로그·사다리·호재·시장·예시와 함께 스냅샷 12 점수·decide, 스냅샷 11(T7 인천 8단지)
점수·decide·접수 상태, verify 봉투 → claim(#131 contradicted 복합 주장의 분할 자식 포함)까지 넣는다.
여기서는 시험이 쓰는 id 를 모으고, 생성 거부 시험용 contradicted 주장 추가 함수만 둔다(판정기 호출 없음).

지역명은 픽스처에만 있다(코드에는 없음).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.scenarios import BUILTIN_SCENARIOS
from app.api import devseed
from app.core.settings import Settings
from app.models import Claim, ScoreRun, ScoreTotal

SNAP_PREV, SNAP_CUR = 11, 12


@dataclass
class SeedInfo:
    region_id: int = 1
    snapshots: tuple[int, int] = (SNAP_PREV, SNAP_CUR)
    score_runs: dict[tuple[int, str], int] = field(default_factory=dict)  # (snapshot, code) -> run id
    complex_ids: dict[int, list[int]] = field(default_factory=dict)  # snapshot -> 점수 행 단지 id


def seed(settings: Settings, session_factory: Any) -> SeedInfo:
    """devseed 전체 적재(스키마 재생성). 반환 = 시험이 쓰는 id 들."""
    devseed.seed(settings, reference="none", reset=True)
    info = SeedInfo()
    codes = {s.id: s.code or str(s.id) for s in BUILTIN_SCENARIOS}
    with session_factory() as session:
        for run in session.scalars(select(ScoreRun).order_by(ScoreRun.id)):
            info.score_runs[(run.snapshot_id, codes.get(run.scenario_id, str(run.scenario_id)))] = run.id
        for sid in info.snapshots:
            runs = select(ScoreRun.id).where(ScoreRun.snapshot_id == sid)
            info.complex_ids[sid] = sorted(
                set(session.scalars(select(ScoreTotal.complex_id).where(ScoreTotal.score_run_id.in_(runs))))
            )
    return info


def add_contradicted_claim(session: Session, snapshot_id: int) -> int:
    """T15: 분할되지 않은 contradicted 주장 1건(생성 거부 시험용)."""
    row = Claim(
        snapshot_id=snapshot_id,
        section="8-F1",
        text="시험용 contradicted 주장",
        verify_status="contradicted",
        ordinal=99,
    )
    session.add(row)
    session.flush()
    return row.id

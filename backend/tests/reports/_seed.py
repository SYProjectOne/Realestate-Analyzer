"""WP8 테스트 fixture — 적재는 ``app.api.devseed.seed`` 하나(R3 F3 이후).

devseed 가 사실·출처·판정 로그·사다리·호재·시장·예시와 함께 스냅샷 12 점수·decide, 스냅샷 11(T7 인천 8단지)
점수·decide·접수 상태, verify 봉투 → claim(#131 contradicted 복합 주장의 분할 자식 포함)까지 넣는다.
여기서는 시험이 쓰는 id 를 모으고, 생성 거부 시험용 contradicted 주장 추가 함수만 둔다(판정기 호출 없음).

지역명은 픽스처에만 있다(코드에는 없음).
"""

# ruff: noqa: E501  (한국어 docstring)

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


def live(session: Session, *snapshot_ids: int) -> None:
    """그 세션 안에서 발행 스냅샷(기본 11·12)을 '판정 끝·발행 전(ready)'으로 — ``load_report`` 가 지금 사실로 적재한다.

    D13-1(계약 .10): 발행 리비전 보고서는 발행 때 저장한 입력 데이터만 쓴다. 사실을 바꿔 보고서 계산 규칙을 보는 테스트는
    발행 전 리비전에서 본다(세션 rollback 으로 되돌린다)."""
    from app.models import Snapshot

    for sid in snapshot_ids or (11, 12):
        snap = session.get(Snapshot, sid)
        if snap is not None:
            snap.status = "ready"
    session.flush()


def add_contradicted_claim(session: Session, snapshot_id: int) -> int:
    """T15: 분할되지 않은 contradicted 주장 1건(생성 거부 시험용). 주장은 판정 중 리비전에 생긴다 — 그 스냅샷을 발행 전
    (ready)으로 둔다(발행 리비전은 발행 때 남은 contradicted 0 을 확인했고 저장본으로 렌더한다, D13-1)."""
    live(session, snapshot_id)
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

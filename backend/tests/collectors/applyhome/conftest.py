"""청약홈 수집기 테스트 공용 fixture — 지역·스냅샷은 테스트 데이터(지역명은 여기에만, AGENTS 규칙 15)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.core.contracts_gen import Region, Snapshot
from app.core.http import HttpClient

from .replay import Recording

FIXTURES = Path(__file__).parent / "fixtures"
RECORDING = FIXTURES / "applyhome_2026-10-09.zip"
TODAY = date(2026, 10, 9)  # 녹화일 — 목록 조회 창(2025-12 ~ 2026-11)이 녹화와 같아야 한다

# 녹화 지역(DECISIONS D3): 인천 연수구·서구·검단구·계양구 + 김포시.
# 검단구(2026-07 분구) 코드는 이 테스트용 값이다 — 사전 필터는 이름만 쓴다.
REGION_DICT: dict[str, Any] = {
    "id": 1,
    "name": "인천 송도·검단·계양 + 김포",
    "query_text": "송도, 검단, 계양구, 김포시",
    "selections": [
        {"kind": "legal_dong", "code": "2818510600", "full_name": "인천광역시 연수구 송도동"},
        {"kind": "sigungu", "code": "28260", "full_name": "인천광역시 서구"},
        {"kind": "sigungu", "code": "28265", "full_name": "인천광역시 검단구"},
        {"kind": "sigungu", "code": "28245", "full_name": "인천광역시 계양구"},
        {"kind": "sigungu", "code": "41570", "full_name": "경기도 김포시"},
    ],
    "sido_codes": ["28", "41"],
    "sigungu_codes": ["28185", "28245", "28260", "28265", "41570"],
    "legal_dong_codes": ["2818510600"],
    "living_areas": [],
    "age_premium_coef": {"c_per_year": 0.015, "cap_years": 8, "label": "추정"},
    "supply_ref_pct": 0.08,
    "applyhome_query": {},
    "status": "ready",
    "created_at": "2026-10-09T06:00:00+09:00",
}


class FakeClock:
    """sleep 이 시계를 민다 — 속도 제한(1 req/s)을 실제로 기다리지 않고 '실제라면 걸렸을 시간'을 잰다."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += max(0.0, seconds)


def make_region(**overrides: Any) -> Region:
    data = {**REGION_DICT, **overrides}
    return Region.model_validate(data)


def make_snapshot(region_id: int = 1, asof: str = "2026-10-09") -> Snapshot:
    return Snapshot(
        id=1,
        region_id=region_id,
        asof_date=asof,
        status="building",
        degraded=False,
        created_at=asof + "T06:00:00+09:00",
    )


@pytest.fixture
def region() -> Region:
    return make_region()


@pytest.fixture
def snapshot() -> Snapshot:
    return make_snapshot()


@pytest.fixture
def recording() -> Recording:
    return Recording.load(RECORDING)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def http(clock: FakeClock) -> Iterator[HttpClient]:
    client = HttpClient(
        rate_per_host=1.0, max_retries=0, jitter=0.0, sleep=clock.sleep, clock=clock.monotonic
    )
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def seeded_region(db_session: Session) -> Region:
    """region·snapshot 행(raw_document.region_id FK)."""
    from app.models import Region as RegionRow
    from app.models import Snapshot as SnapshotRow

    r = make_region()
    db_session.add(
        RegionRow(
            id=r.id,
            name=r.name,
            query_text=r.query_text,
            selections=[s.model_dump() for s in r.selections],
            sido_codes=r.sido_codes,
            sigungu_codes=r.sigungu_codes,
            legal_dong_codes=r.legal_dong_codes,
            living_areas=[],
            age_premium_coef=r.age_premium_coef.model_dump(),
            supply_ref_pct=r.supply_ref_pct,
            applyhome_query=r.applyhome_query,
            status=r.status,
            created_at=r.created_at,
        )
    )
    db_session.add(
        SnapshotRow(
            id=1,
            region_id=r.id,
            asof_date="2026-10-09",
            status="building",
            created_at="2026-10-09T06:00:00+09:00",
        )
    )
    db_session.flush()
    return r

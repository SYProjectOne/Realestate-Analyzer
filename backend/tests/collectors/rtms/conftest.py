"""WP1b 수집기 테스트 공용 fixture.

같은 내용이 official_site·rtms·stats·news·reference 테스트 디렉터리에 하나씩 있다
(``tests/collectors/conftest.py`` 는 WP1a 와 같이 쓰는 곳이라 만들지 않는다).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.contracts_gen import Region, Snapshot
from app.core.http import HttpClient
from app.models import Complex
from app.models import Region as RegionRow
from app.models import Snapshot as SnapshotRow

FIXTURES = Path(__file__).parent / "fixtures"
REFERENCE_COPY = Path(__file__).resolve().parents[4] / "contracts" / "fixtures" / "reference"
ASOF = "2026-10-08"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def reference_copy() -> Path:
    return REFERENCE_COPY


@pytest.fixture
def http() -> Iterator[HttpClient]:
    with HttpClient(sleep=lambda _s: None, max_retries=0, jitter=0) as client:
        yield client


@pytest.fixture
def count(db_engine: Engine) -> Callable[[type[Any]], int]:
    def _count(model: type[Any]) -> int:
        with Session(db_engine) as s:
            return int(s.scalar(select(func.count()).select_from(model)) or 0)

    return _count


@pytest.fixture
def region_ctx(db_engine: Engine, raw_dir: Path) -> tuple[Region, Snapshot]:
    """테스트용 지역 1개(픽스처 지역 코드) + 스냅샷 1개를 DB 에 넣고 DTO 로 돌려준다."""
    region = Region.model_validate(
        {
            "id": 1,
            "name": "테스트 지역",
            "query_text": "연수구, 김포시",
            "selections": [
                {"kind": "sigungu", "code": "28185", "full_name": "인천광역시 연수구"},
                {"kind": "sigungu", "code": "41570", "full_name": "경기도 김포시"},
            ],
            "sido_codes": ["28", "41"],
            "sigungu_codes": ["28185", "41570"],
            "legal_dong_codes": ["2818510600", "4157010100"],
            "living_areas": [
                {"id": "la_1", "name": "연수구", "legal_dong_codes": ["2818510600"], "households": None},
                {"id": "la_2", "name": "김포시", "legal_dong_codes": ["4157010100"], "households": None},
            ],
            "age_premium_coef": {"c_per_year": 0.015, "cap_years": 8, "label": "추정"},
            "supply_ref_pct": 0.08,
            "applyhome_query": {},
            "status": "ready",
            "created_at": "2026-10-08T06:00:00+09:00",
        }
    )
    snapshot = Snapshot.model_validate(
        {
            "id": 1,
            "region_id": 1,
            "asof_date": ASOF,
            "status": "building",
            "degraded": False,
            "created_at": "2026-10-08T06:00:00+09:00",
        }
    )
    with Session(db_engine) as s:
        s.add(
            RegionRow(
                id=region.id,
                name=region.name,
                query_text=region.query_text,
                selections=[x.model_dump() for x in region.selections],
                sido_codes=region.sido_codes,
                sigungu_codes=region.sigungu_codes,
                legal_dong_codes=region.legal_dong_codes,
                living_areas=[],
                age_premium_coef=region.age_premium_coef.model_dump(),
                applyhome_query={},
                status=region.status,
                created_at=region.created_at,
            )
        )
        s.flush()
        s.add(
            SnapshotRow(
                id=snapshot.id,
                region_id=region.id,
                asof_date=snapshot.asof_date,
                status=snapshot.status,
                created_at=snapshot.created_at,
            )
        )
        s.add(
            Complex(
                id=4,
                region_id=region.id,
                name="테스트 단지",
                former_names=[],
                apply_dates=[],
                contract_dates=[],
                official_site_url="https://site.example.test/",
            )
        )
        s.commit()
    return region, snapshot

"""stats: 입주물량 '추정 집계' 인터페이스 (공식 원천 없음 → 공고문 입주예정월 × 세대수, 라벨 추정)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.collectors.stats.supply import (
    NoticeMoveInEstimator,
    SupplyInput,
    SupplySource,
    aggregate_supply,
    estimate_supply,
    load_supply,
)
from app.core.contracts_gen import Region, Snapshot
from app.models import Supply

INPUTS = [
    SupplyInput(complex_id=4, living_area="la_1", move_in_ym="2029-03", units=501),
    SupplyInput(complex_id=5, living_area="la_1", move_in_ym=None, units=300),  # 입주월 없음 → 제외
    SupplyInput(complex_id=6, living_area="la_2", move_in_ym="2028-08", units=None),  # 세대수 없음 → 제외
]


def test_estimate_skips_unknowns_and_labels_estimate() -> None:
    records = estimate_supply(INPUTS)
    assert [(r.complex_id, r.year, r.ym, r.units) for r in records] == [(4, 2029, "2029-03", 501)]
    assert {(r.label, r.reason) for r in records} == {("추정", "추정 집계")}
    source: SupplySource = NoticeMoveInEstimator()
    assert source.supply(INPUTS) == records
    assert aggregate_supply(records) == {("la_1", 2029): 501}


def test_load_supply_upserts_per_complex(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], count: Callable[[type[Any]], int]
) -> None:
    region, _ = region_ctx
    records = estimate_supply(INPUTS)
    with Session(db_engine) as s:
        assert load_supply(s, region.id, records).inserted == 1
        assert load_supply(s, region.id, records).unchanged == 1
        moved = estimate_supply(
            [SupplyInput(complex_id=4, living_area="la_1", move_in_ym="2029-05", units=501)]
        )
        assert load_supply(s, region.id, moved).updated == 1
        s.commit()
        row = s.scalars(select(Supply)).one()
    assert (row.ym, row.year, row.label, row.reason) == ("2029-05", 2029, "추정", "추정 집계")
    assert count(Supply) == 1

"""stats: 입주물량 '추정 집계' 인터페이스 (공식 원천 없음 → 공고문 입주예정월 × 세대수, 라벨 추정)."""

from __future__ import annotations

import json
import zipfile
from collections.abc import Callable
from pathlib import Path
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
    supply_inputs_from_applyhome_api,
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


def _api_page(endpoint: str) -> bytes:
    """청약홈 API 녹화(collectors/applyhome/fixtures, 2026-10-09 실제 응답)에서 시도 목록 페이지 하나."""
    zpath = Path(__file__).parents[1] / "applyhome" / "fixtures" / "applyhome_api_2026-10-09.zip"
    with zipfile.ZipFile(zpath) as z:
        manifest = json.loads(z.read("manifest.json"))["entries"]
        entry = next(e for e in manifest if endpoint in e["url"] and "SUBSCRPT_AREA_CODE_NM" in e["url"])
        return z.read(entry["file"])


def test_supply_inputs_from_applyhome_api_feed_estimate() -> None:
    """청약홈 API 상세(입주예정월·공급세대수) → SupplyInput → 같은 추정 집계(라벨 추정)."""
    page = _api_page("getAPTLttotPblancDetail?")
    ids: dict[str, int] = {}

    def complex_id_for(hm: str) -> int | None:
        return ids.setdefault(hm, len(ids) + 1)

    inputs = supply_inputs_from_applyhome_api(page, complex_id_for=complex_id_for, raw_document_id=9)
    assert inputs and all(i.raw_document_id == 9 for i in inputs)
    assert all(i.move_in_ym is None or (len(i.move_in_ym) == 7 and i.move_in_ym[4] == "-") for i in inputs)
    records = estimate_supply(inputs)
    assert records and {(r.label, r.reason) for r in records} == {("추정", "추정 집계")}
    assert sum(r.units for r in records) == sum(i.units or 0 for i in inputs if i.move_in_ym)
    # 지역 밖(단지 행 없음) → 건너뜀
    assert supply_inputs_from_applyhome_api(page, complex_id_for=lambda _hm: None) == []
    # 잔여세대(무순위)·임의공급 행은 남은 세대 수라 입주물량이 아니다 → 쓰지 않는다
    remndr = _api_page("getRemndrLttotPblancDetail?")
    assert supply_inputs_from_applyhome_api(remndr, complex_id_for=complex_id_for) == []
    assert supply_inputs_from_applyhome_api(b"not json", complex_id_for=complex_id_for) == []

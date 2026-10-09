"""R3 W3: 입주물량 추정 행(supply)도 출처 행을 가진다 — 없으면 G1 대시보드가 dev 에서 500(contract_violation).

supply.units·year·ym 의 출처 = 그 단지의 채택 출처(complex.units_total·move_in_ym)를 가리키고, 라벨은 '추정'
(reason '추정 집계'). 단지 출처가 없으면 출처 행을 지어내지 않고 ``missing`` 으로 센다. 멱등.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.collectors.stats.supply import (
    SupplyInput,
    estimate_supply,
    load_supply,
    write_supply_provenance,
)
from app.core.contracts_gen import Region, Snapshot
from app.models import FieldProvenance, Supply


def _src(s: Session, field: str, value: str, url: str) -> None:
    s.add(
        FieldProvenance(
            entity="complex", entity_id=4, field=field, value_text=value, url=url, checked_at="2026-10-08",
            label="확인됨", source_rank=1, chosen=True, excerpt=f"{field} {value}",
        )
    )  # fmt: skip


def _prov(s: Session, supply_id: int) -> dict[str, FieldProvenance]:
    return {
        fp.field: fp
        for fp in s.scalars(
            select(FieldProvenance).where(
                FieldProvenance.entity == "supply",
                FieldProvenance.entity_id == supply_id,
                FieldProvenance.chosen.is_(True),
            )
        )
    }


def test_supply_rows_get_estimate_provenance_from_complex_sources(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot]
) -> None:
    region, _ = region_ctx
    with Session(db_engine) as s:
        _src(s, "units_total", "501", "https://www.applyhome.co.kr/detail?houseManageNo=4")
        _src(s, "move_in_ym", "2029-03", "https://www.applyhome.co.kr/detail?houseManageNo=4")
        load_supply(s, region.id, estimate_supply([SupplyInput(4, "la_1", "2029-03", 501)]))
        out = write_supply_provenance(s, region.id)
        row = s.scalars(select(Supply)).one()
        fps = _prov(s, row.id)
        assert set(fps) == {"units", "year", "ym"}
        for fp in fps.values():
            assert fp.label == "추정" and fp.reason and "추정 집계" in fp.reason
            assert fp.url and fp.checked_at == "2026-10-08"
        assert fps["units"].value_text == "501"
        assert (out.written, out.missing) == (3, 0)

        n = s.scalar(select(func.count()).select_from(FieldProvenance))
        again = write_supply_provenance(s, region.id)
        assert again.written == 0 and s.scalar(select(func.count()).select_from(FieldProvenance)) == n

        # 세대수가 바뀌면 새 출처 행이 채택되고 옛 행은 남는다(chosen=false)
        s.scalars(
            select(FieldProvenance).where(FieldProvenance.field == "units_total")
        ).one().value_text = "520"
        load_supply(s, region.id, estimate_supply([SupplyInput(4, "la_1", "2029-03", 520)]))
        write_supply_provenance(s, region.id)
        assert _prov(s, row.id)["units"].value_text == "520"
        assert (
            s.scalar(
                select(func.count())
                .select_from(FieldProvenance)
                .where(FieldProvenance.entity == "supply", FieldProvenance.field == "units")
            )
            == 2
        )


def test_missing_complex_source_is_counted_not_invented(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot]
) -> None:
    region, _ = region_ctx
    with Session(db_engine) as s:
        load_supply(s, region.id, estimate_supply([SupplyInput(4, "la_1", "2029-03", 501)]))
        out = write_supply_provenance(s, region.id)
        assert out.written == 0 and out.missing == 3
        assert s.scalar(select(func.count()).select_from(FieldProvenance)) == 0

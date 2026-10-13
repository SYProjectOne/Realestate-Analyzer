"""R6-DONG — 이미 저장된 단지의 법정동을 운영 수집(collect.daily·weekly)이 지금 규칙으로 다시 맞춘다.

운영 첫 실행(인천, 스냅샷 1)에서 옛 규칙으로 틀린 법정동(계양 테크노밸리 → 부천 대장동 4119610600)·NULL(간석1동)이 저장됐다.
주소가 바뀌지 않으면 저장 경로(``store_raw_document``)는 생활권을 다시 배정하지 않으므로, 수집 끝에 지역 단지 전체를 다시
맞춘다(``living_area.rederive_region_dongs``): 바뀐 단지마다 change_event(complex·legal_dong_code, critical → 재판정 대상),
같은 날 다시 수집하면 이벤트 0(D23-1). 첫 적재(bootstrap)면 이벤트 대신 first_load 요약 수(D18-7).
"""

# ruff: noqa: E501  (한국어 docstring·실제 주소)

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import ChangeEvent, Complex
from app.normalize.living_area import default_living_areas
from app.scheduler.collect import collect
from app.scheduler.context import SchedulerContext

from ..normalize.test_r6_dong import load_r6_reference
from .conftest import seed_region, seed_scenarios

ASOF = "2026-10-14"
GYEYANG = "인천광역시 계양구 귤현동, 동양동, 박촌동, 병방동, 상야동, 경기도 부천시 대장동, 서울특별시 강서구 오곡동 일원 인천계양 테크노밸리 공공주택지구 내 A17블록"
GANSEOK = "인천광역시 남동구 간석1동 311-1번지 일원"


def _setup(factory: sessionmaker[Session], *, status: str) -> tuple[int, int]:
    with factory() as s:
        seed_scenarios(s)
        ref = load_r6_reference(s)
        codes = sorted(
            r.code for r in ref.legal if r.active and r.code.startswith("28") and r.eupmyeondong_name
        )
        region = seed_region(
            s, status=status, legal_dong_codes=codes, sigungu_codes=sorted({c[:5] for c in codes}),
            living_areas=default_living_areas(codes, ref.legal),
        )  # fmt: skip
        common = {"region_id": region.id, "former_names": [], "apply_dates": [], "contract_dates": []}
        a = Complex(
            name="인천계양 A17블록",
            address=GYEYANG,
            legal_dong_code="4119610600",
            inclusion_class="범위 경계",
            **common,
        )
        b = Complex(name="포레나더샵 인천시청역", address=GANSEOK, inclusion_class="범위 경계", **common)
        s.add_all([a, b])
        s.commit()
        return a.id, b.id


def _dong_events(factory: sessionmaker[Session]) -> list[ChangeEvent]:
    with factory() as s:
        return list(
            s.scalars(
                select(ChangeEvent).where(
                    ChangeEvent.entity == "complex", ChangeEvent.field == "legal_dong_code"
                )
            )
        )


def test_daily_collect_corrects_stored_dong_with_event_then_idempotent(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session]
) -> None:
    a, b = _setup(factory, status="ready")
    res = collect(make_ctx(), 1, ["applyhome_list"], asof_date=ASOF)
    evs = {(e.complex_id, e.old_text, e.new_text, e.severity) for e in _dong_events(factory)}
    assert evs == {(a, "4119610600", "2824511100", "critical"), (b, None, "2820010200", "critical")}, evs
    assert {a, b} <= set(res.rejudge_complex_ids), "판정 범위가 바뀐 단지 → 재판정"
    with factory() as s:
        rows = {
            c.id: (c.legal_dong_code, c.inclusion_class, c.living_area is not None)
            for c in s.scalars(select(Complex))
        }
    assert rows == {a: ("2824511100", "미분류", True), b: ("2820010200", "미분류", True)}
    again = collect(make_ctx(), 1, ["applyhome_list"], asof_date=ASOF)
    assert again.change_event_ids == [] and len(_dong_events(factory)) == 2


def test_first_load_folds_into_summary(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session]
) -> None:
    _setup(factory, status="bootstrapping")
    collect(make_ctx(), 1, ["applyhome_list"], asof_date=ASOF)
    assert _dong_events(factory) == []
    with factory() as s:
        summary = list(s.scalars(select(ChangeEvent).where(ChangeEvent.field == "first_load")))
        assert {c.legal_dong_code for c in s.scalars(select(Complex))} == {"2824511100", "2820010200"}
    assert len(summary) == 1

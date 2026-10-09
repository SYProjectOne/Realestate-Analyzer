"""R3 C1 / D9-2: 벤치마크 생성 — 청약홈 과거 공고 분양가 + 입주 후 실거래(rtms) → benchmark 행 + 출처.

- 분양가 = 같은 공고의 84㎡에 가장 가까운 주택형 최고가(청약홈 공식 API, 라벨 확인됨)
- 실거래 = 입주월 이후 · 기준일 전 12개월 · 전용 80~85㎡ · 해제 제외 (low/median/high·건수), 고점 = 입주 후 전체
- 단지 매칭 = 정규화 단지명 + 법정동(모호하면 매칭 안 함 → '확인 불가(매칭 모호)')
- sale_period = 분양 연도 ≥ 기준연도−3 → 고가 분양기, 그 전 → 저가 분양기
- 생활권 표본 0 → 지역 전체로 대체(라벨 추정, '추정(대체: 지역 전체)'), 그래도 0 → 행 없음
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Benchmark, FieldProvenance, Region, RtmsTrade
from app.normalize.benchmark import (
    BENCHMARK_FIELDS,
    build_benchmarks,
    normalize_apt_name,
    sale_period,
)

from ._assemble_support import (
    ASOF,
    add_list,
    add_model,
    add_trade,
    notice_row,
    rtms_url,
)
from ._support import AddRaw

SONGDO = "2818510600"
JAKJEON = "2824511200"


def _la(region: Region, sgg: str) -> str:
    return next(a["id"] for a in region.living_areas if a["legal_dong_codes"][0].startswith(sgg))


def _seed(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    rid = region.id
    add_list(
        add_raw,
        rid,
        "인천",
        [
            # A: 송도 2021 분양 → 2024-06 입주 (저가 분양기)
            notice_row("2021000101", "힐스테이트 레이크 송도 2차", "인천광역시 연수구 송도동 1-1", "2021-03-10", "202406"),
            # C: 계양 — 같은 동에 이름이 겹치는 실거래 단지 둘 → 매칭 모호
            notice_row("2022000303", "푸르지오 작전", "인천광역시 계양구 작전동 5", "2022-01-05", "202503"),
            # D: 입주 전(2027-12) — 분양권 거래 없음 → 표본 아님
            notice_row("2024000404", "송도 미래 아파트", "인천광역시 연수구 송도동 9", "2024-02-01", "202712"),
            # E: 국민주택 — 민영 아님
            notice_row("2020000505", "공공 송도", "인천광역시 연수구 송도동 7", "2020-05-01", "202305", housing="국민"),
            # F: 지역 밖(부평구 = 지역 법정동 아님)
            notice_row("2021000606", "부평 래미안", "인천광역시 부평구 부평동 1", "2021-01-01", "202401"),
        ],
    )
    add_list(
        add_raw,
        rid,
        "경기",
        [
            # B: 김포 장기동 2023 분양 → 2026-01 입주 (고가 분양기)
            notice_row(
                "2023000202", "e편한세상 김포 장기 리버", "경기도 김포시 장기동 100", "2023-05-01", "202601", area="경기"
            ),
        ],
    )
    add_model(add_raw, rid, "2021000101", [("059.9876A", 50000, 100), ("084.9500A", 70000, 300), ("101.0000A", 90000, 50)])
    add_model(add_raw, rid, "2022000303", [("084.8000A", 55000, 200)])
    add_model(add_raw, rid, "2024000404", [("084.1000A", 99000, 200)])
    add_model(add_raw, rid, "2020000505", [("084.0000A", 30000, 200)])
    add_model(add_raw, rid, "2021000606", [("084.0000A", 40000, 200)])
    add_model(add_raw, rid, "2023000202", [("074.9000A", 50000, 100), ("084.9900A", 60000, 200)])

    # A 실거래(법정동 코드 있음)
    for price, day in ((80000, "2025-12-15"), (90000, "2026-03-02"), (100000, "2026-09-20")):
        add_trade(db_session, rid, "힐스테이트레이크송도2차", price, day, legal=SONGDO, built=2024)
    add_trade(db_session, rid, "힐스테이트레이크송도2차", 105000, "2025-03-10", legal=SONGDO, built=2024)  # 창 밖 고점
    add_trade(db_session, rid, "힐스테이트레이크송도2차", 200000, "2026-05-01", legal=SONGDO, cancelled=True)
    add_trade(db_session, rid, "힐스테이트레이크송도2차", 60000, "2026-04-01", legal=SONGDO, area="59.98")
    add_trade(db_session, rid, "힐스테이트레이크송도2차", 70000, "2026-04-01", legal="2818510500")  # 다른 동
    # B 실거래: 법정동 코드 없음 → 원문 URL 의 LAWD_CD + 동 이름으로 법정동을 찾는다
    doc = add_raw("<response/>", source_kind="rtms", url=rtms_url("41570", "202606"), region_id=rid, ext="xml")
    for price, day in ((50000, "2025-12-20"), (65000, "2026-02-10"), (70000, "2026-06-10")):
        add_trade(db_session, rid, "e편한세상김포장기리버", price, day, dong="장기동", built=2026, raw_document_id=doc.id)
    # C 실거래: 이름이 둘 다 '푸르지오작전'을 포함
    add_trade(db_session, rid, "푸르지오작전1단지", 60000, "2026-01-10", legal=JAKJEON, built=2025)
    add_trade(db_session, rid, "푸르지오작전2단지", 61000, "2026-01-11", legal=JAKJEON, built=2025)
    db_session.flush()


def _rows(db_session: Session) -> list[Benchmark]:
    return list(db_session.scalars(select(Benchmark).order_by(Benchmark.id)))


def test_normalize_apt_name_is_string_only() -> None:
    assert normalize_apt_name("힐스테이트 레이크 송도 2차") == normalize_apt_name("힐스테이트레이크송도2차")
    assert normalize_apt_name("더샵 송도마리나베이(조합원 자격상실세대 3회차)") == normalize_apt_name("더샵송도마리나베이")
    assert normalize_apt_name("e편한세상 김포") == normalize_apt_name("E편한세상김포")
    assert normalize_apt_name("검단신도시 AB12블록 우미린") == normalize_apt_name("검단신도시 우미린")


def test_sale_period_formula() -> None:
    assert sale_period(2023, 2026)[0] == "고가 분양기"
    assert sale_period(2022, 2026)[0] == "저가 분양기"
    assert "2026−3" in sale_period(2023, 2026)[1]


def test_build_benchmarks_from_history_and_trades(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    _seed(db_session, add_raw, region)
    res = build_benchmarks(db_session, region.id, asof_date=ASOF)

    own = [b for b in _rows(db_session) if b.note and "대체" not in b.note]
    by_name = {b.name: b for b in own}
    assert set(by_name) == {"힐스테이트 레이크 송도 2차", "e편한세상 김포 장기 리버"}

    a = by_name["힐스테이트 레이크 송도 2차"]
    assert a.living_area == _la(region, "28185")
    assert a.sale_price_84_won == 700_000_000  # 84㎡에 가장 가까운 084.9500A 최고가
    assert a.sale_price_label == "확인됨"
    assert (a.trade_low_won, a.trade_median_won, a.trade_high_won) == (800_000_000, 900_000_000, 1_000_000_000)
    assert a.n_trades == 3  # 해제·59㎡·다른 동·창 밖 거래 제외
    assert a.trade_window == "2025-11~2026-10"
    assert (a.peak_won, a.peak_ym) == (1_050_000_000, "2025-03")
    assert (a.sale_year, a.completed_year) == (2021, 2024)
    assert a.sale_period == "저가 분양기"
    assert a.is_presale is False

    b = by_name["e편한세상 김포 장기 리버"]
    assert b.living_area == _la(region, "41570")
    assert b.sale_price_84_won == 600_000_000
    assert b.trade_median_won == 675_000_000  # 입주(2026-01) 전 거래 제외 → 65000·70000
    assert b.n_trades == 2
    assert b.sale_period == "고가 분양기"

    assert res.samples == {
        _la(region, "28185"): 1,
        _la(region, "28245"): 0,
        _la(region, "28260"): 0,
        _la(region, "41570"): 1,
    }
    reasons = {u["name"]: u["reason"] for u in res.unmatched}
    assert reasons["푸르지오 작전"] == "확인 불가(매칭 모호)"


def test_every_numeric_field_has_provenance(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    _seed(db_session, add_raw, region)
    build_benchmarks(db_session, region.id, asof_date=ASOF)
    for row in _rows(db_session):
        for f in BENCHMARK_FIELDS:
            if getattr(row, f) is None:
                continue
            fp = db_session.scalars(
                select(FieldProvenance).where(
                    FieldProvenance.entity == "benchmark",
                    FieldProvenance.entity_id == row.id,
                    FieldProvenance.field == f,
                    FieldProvenance.chosen.is_(True),
                )
            ).one()
            assert fp.label.strip() and fp.url and fp.checked_at, (row.name, f)
            assert fp.raw_document_id is not None
    sale = db_session.scalars(
        select(FieldProvenance).where(
            FieldProvenance.entity == "benchmark", FieldProvenance.field == "sale_price_84_won"
        )
    ).first()
    assert sale is not None and "LTTOT_TOP_AMOUNT" in (sale.excerpt or "")


def test_living_area_without_sample_uses_region_wide_substitute(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    _seed(db_session, add_raw, region)
    res = build_benchmarks(db_session, region.id, asof_date=ASOF)
    gyeyang = _la(region, "28245")
    subs = [b for b in _rows(db_session) if b.living_area == gyeyang]
    assert {b.name for b in subs} == {"힐스테이트 레이크 송도 2차", "e편한세상 김포 장기 리버"}
    for b in subs:
        assert b.sale_price_label == "추정"
        assert b.note is not None and "추정(대체: 지역 전체)" in b.note
        fp = db_session.scalars(
            select(FieldProvenance).where(
                FieldProvenance.entity == "benchmark",
                FieldProvenance.entity_id == b.id,
                FieldProvenance.field == "trade_median_won",
            )
        ).one()
        assert fp.label == "추정" and "대체" in (fp.reason or "")
    assert set(res.substituted) == {gyeyang, _la(region, "28260")}


def test_no_sample_anywhere_creates_no_rows(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    add_list(add_raw, region.id, "인천", [notice_row("2021000101", "단지", "인천광역시 연수구 송도동 1", "2021-01-01", "202401")])
    add_model(add_raw, region.id, "2021000101", [("084.0000A", 50000, 10)])
    res = build_benchmarks(db_session, region.id, asof_date=ASOF)
    assert _rows(db_session) == []
    assert all(n == 0 for n in res.samples.values())
    assert res.substituted == []
    assert {u["reason"] for u in res.unmatched} == {"실거래 없음(매칭 단지 없음)"}


def test_rerun_is_idempotent(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    _seed(db_session, add_raw, region)
    first = build_benchmarks(db_session, region.id, asof_date=ASOF)
    n_rows = len(_rows(db_session))
    n_prov = db_session.scalar(select(func.count()).select_from(FieldProvenance))
    second = build_benchmarks(db_session, region.id, asof_date=ASOF)
    assert first.inserted == n_rows and first.changed
    assert (second.inserted, second.updated, second.removed) == (0, 0, 0)
    assert not second.changed
    assert len(_rows(db_session)) == n_rows
    assert db_session.scalar(select(func.count()).select_from(FieldProvenance)) == n_prov


def test_new_own_sample_replaces_substitute(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    _seed(db_session, add_raw, region)
    build_benchmarks(db_session, region.id, asof_date=ASOF)
    gyeyang = _la(region, "28245")
    # 모호했던 실거래 하나를 지우면(이름 정리) 계양구 자체 표본이 생긴다
    db_session.execute(RtmsTrade.__table__.delete().where(RtmsTrade.apt_name == "푸르지오작전2단지"))
    res = build_benchmarks(db_session, region.id, asof_date=ASOF)
    rows = [b for b in _rows(db_session) if b.living_area == gyeyang]
    assert [b.name for b in rows] == ["푸르지오 작전"]
    assert res.removed == 2 and gyeyang not in res.substituted


def test_presale_rows_are_marked(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    _seed(db_session, add_raw, region)
    add_trade(db_session, region.id, "송도미래아파트", 95000, "2026-08-01", legal=SONGDO, presale=True)
    build_benchmarks(db_session, region.id, asof_date=ASOF)
    pre = [b for b in _rows(db_session) if b.is_presale]
    assert [(b.name, b.trade_median_won) for b in pre] == [("송도 미래 아파트", 950_000_000)]


def test_untagged_rows_are_left_alone(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    seeded = Benchmark(region_id=region.id, living_area="la_1", name="수동 입력", sale_price_84_won=1, is_presale=False)
    db_session.add(seeded)
    db_session.flush()
    _seed(db_session, add_raw, region)
    build_benchmarks(db_session, region.id, asof_date=ASOF)
    build_benchmarks(db_session, region.id, asof_date=ASOF)
    assert db_session.get(Benchmark, seeded.id) is not None


@pytest.mark.parametrize("name", ["힐스테이트 레이크 송도 2차"])
def test_note_records_sources_and_formula(db_session: Session, add_raw: AddRaw, region: Region, name: str) -> None:
    _seed(db_session, add_raw, region)
    build_benchmarks(db_session, region.id, asof_date=ASOF)
    row = db_session.scalars(select(Benchmark).where(Benchmark.name == name)).first()
    assert row is not None and row.note is not None
    note: Any = row.note
    assert "청약홈" in note and "2021 < 2026−3" in note and "저가 분양기" in note

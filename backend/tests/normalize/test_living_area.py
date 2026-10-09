"""생활권 (D2): 기본값(시군구당 1개), 편집 검증(중복·누락 오류), 주소 → 법정동 배정, 세대수 집계 라벨."""

from __future__ import annotations

from fractions import Fraction

import pytest
from sqlalchemy.orm import Session

from app.core.contracts_gen import LivingArea
from app.models import Region
from app.normalize.living_area import (
    HouseholdInput,
    LivingAreaError,
    aggregate_households,
    apply_living_area_edit,
    assign_legal_dong,
    default_living_areas,
    household_facts,
    living_area_of,
    region_household_facts,
    validate_living_areas,
)
from app.normalize.region_resolve import ReferenceData

SEOGU = ["2826011600", "2826011700", "2826011800", "2826011900", "2826012000", "2826012100"]


def _codes(ref: ReferenceData, sgg: str) -> list[str]:
    return sorted(r.code for r in ref.legal if r.active and r.eupmyeondong_name and r.sigungu_code == sgg)


def test_default_one_area_per_sigungu(ref: ReferenceData) -> None:
    codes = _codes(ref, "28185") + _codes(ref, "41570")
    areas = default_living_areas(codes, ref.legal)
    assert [(a["id"], a["name"]) for a in areas] == [("la_1", "연수구"), ("la_2", "김포시")]
    assert areas[1]["legal_dong_codes"] == _codes(ref, "41570")
    for a in areas:
        LivingArea.model_validate(a)  # 계약 모양
    assert validate_living_areas(codes, areas) == []


def test_validation_reports_duplicate_and_missing(ref: ReferenceData) -> None:
    codes = _codes(ref, "28260")
    areas = [
        {"id": "la_1", "name": "검단 북", "legal_dong_codes": SEOGU[:4]},
        {
            "id": "la_2",
            "name": "검단 남",
            "legal_dong_codes": [SEOGU[3], SEOGU[4]],
        },  # 불로동 중복, 왕길동·백석동 누락
    ]
    issues = validate_living_areas(codes, areas)
    kinds = sorted((i.kind, i.code) for i in issues)
    assert ("duplicate", "2826011900") in kinds
    assert ("missing", "2826012100") in kinds and ("missing", "2826010100") in kinds
    dup = next(i for i in issues if i.kind == "duplicate")
    assert set(dup.areas) == {"la_1", "la_2"}


def test_validation_unknown_and_empty(ref: ReferenceData) -> None:
    codes = _codes(ref, "28185")
    issues = validate_living_areas(
        codes,
        [
            {"id": "la_1", "name": "연수", "legal_dong_codes": [*codes, "4157010700"]},
            {"id": "la_2", "name": "", "legal_dong_codes": []},
        ],
    )
    kinds = {i.kind for i in issues}
    assert {"unknown", "empty", "name"} <= kinds


def test_edit_split_keeps_ids_and_households(ref: ReferenceData) -> None:
    codes = _codes(ref, "28185") + _codes(ref, "28260")
    existing = default_living_areas(codes, ref.legal)
    existing[0]["households"] = {
        "v": 1,
        "label": "추정",
        "reason": "주민등록 세대",
        "prov": "rd_1",
        "checked_at": None,
    }
    seogu_all = existing[1]["legal_dong_codes"]
    new = apply_living_area_edit(
        codes,
        existing,
        [
            {"id": "la_1", "name": "연수구", "legal_dong_codes": existing[0]["legal_dong_codes"]},
            {"id": "la_2", "name": "서구(검단)", "legal_dong_codes": SEOGU},
            {"name": "서구(구도심)", "legal_dong_codes": [c for c in seogu_all if c not in SEOGU]},
        ],
    )
    assert [a["id"] for a in new] == ["la_1", "la_2", "la_3"]
    assert new[0]["households"] is not None  # 구성 그대로 → 유지
    assert new[1]["households"] is None and new[2]["households"] is None


def test_edit_rejects_dropping_nonempty_area(ref: ReferenceData) -> None:
    codes = _codes(ref, "28185") + _codes(ref, "28260")
    existing = default_living_areas(codes, ref.legal)
    with pytest.raises(LivingAreaError) as ei:
        apply_living_area_edit(codes, existing, [existing[0]])  # 서구 생활권을 빼면 그 법정동이 누락
    assert any(i.kind == "missing" for i in ei.value.issues)
    with pytest.raises(LivingAreaError) as e2:
        apply_living_area_edit(
            codes, existing, [*existing, {"id": "la_9", "name": "x", "legal_dong_codes": []}]
        )
    assert {"empty", "unknown_id"} <= {i.kind for i in e2.value.issues}


def test_address_to_legal_dong(ref: ReferenceData) -> None:
    legal = ref.legal
    assert assign_legal_dong("경기도 김포시 풍무동 483-7번지 일대", legal) == "4157010700"
    # 같은 동 이름이 다른 시군구에도 있으면 주소의 시군구로 좁힌다
    assert assign_legal_dong("풍무동 483-7", legal) is None
    # 괄호 안 법정동, 분구 전 코드(서구)
    assert assign_legal_dong("인천광역시 서구 검단신도시 AA32BL(마전동)", legal) == "2826011600"
    # 새 구 이름이면 새 코드
    assert assign_legal_dong("인천광역시 검단구 마전동 AA32블록", legal) == "2826510100"
    # 구 이름 없이 동만 → 지역 범위(scope)로 좁힌다
    assert assign_legal_dong("검단신도시 마전동", legal, scope={"2826011600"}) == "2826011600"
    # 리까지
    assert assign_legal_dong("경기도 김포시 고촌읍 향산리 588-45", legal) == "4157025022"
    assert assign_legal_dong("경기도 김포시 고촌읍 일대", legal) == "4157025000"
    assert assign_legal_dong("서울특별시 어딘가", legal) is None


def test_living_area_of() -> None:
    areas = [
        {"id": "la_1", "name": "a", "legal_dong_codes": ["1"]},
        {"id": "la_2", "name": "b", "legal_dong_codes": ["2"]},
    ]
    assert (
        living_area_of("2", areas) == "la_2"
        and living_area_of("3", areas) is None
        and living_area_of(None, areas) is None
    )


def test_households_equal_split_and_label(ref: ReferenceData) -> None:
    areas = [
        {"id": "la_1", "name": "마전", "legal_dong_codes": ["2826011600"]},
        {"id": "la_2", "name": "나머지", "legal_dong_codes": SEOGU[1:]},
    ]
    stats = [
        HouseholdInput("2826063000", 10_001, raw_document_id=7),  # 검단동 → 마전·당하·(폐지 검단동) 3분할
        HouseholdInput("2826065000", 7_000, raw_document_id=7),  # 오류왕길동 → 오류·왕길 2분할
        HouseholdInput("2826066000", 12_000, raw_document_id=7),  # 원당동 1:1
        HouseholdInput("2826064000", 8_000, raw_document_id=7),  # 불로대곡동 1:1
    ]
    aggs = aggregate_households(areas, stats, ref.admin_legal)
    assert aggs["la_1"].exact == Fraction(10_001, 3)
    assert aggs["la_1"].households == 3334  # 3333.67 → 사사오입
    assert aggs["la_2"].exact == Fraction(10_001, 3) + 7_000 + 12_000 + 8_000
    assert aggs["la_2"].households == 30_334
    assert aggs["la_1"].split_admin_codes == ["2826063000"]
    assert aggs["la_1"].label == "추정" and aggs["la_1"].reason == "주민등록 세대"
    facts = household_facts(aggs, checked_at="2026-09-05", supply_ref_pct=0.08)
    hf = facts["la_1"]["households"]
    assert (hf["v"], hf["label"], hf["reason"], hf["prov"]) == (3334, "추정", "주민등록 세대", "rd_7")
    ref_units = facts["la_2"]["supply_ref_units"]
    assert ref_units["v"] == 2427 and ref_units["label"] == "추정"  # 30,334 × 0.08 = 2,426.72


def test_households_without_stats_is_unknown_not_blank() -> None:
    aggs = aggregate_households([{"id": "la_1", "name": "x", "legal_dong_codes": ["9"]}], [], [])
    f = household_facts(aggs, checked_at=None)["la_1"]["households"]
    assert f["label"] == "확인 불가" and f["reason"]


def test_region_household_facts_db(db_session: Session, region: Region) -> None:
    facts = region_household_facts(db_session, region)
    by_name = {a["name"]: facts[a["id"]]["households"] for a in region.living_areas}
    # 김포시 = 풍무 25,000 + 사우 15,000 + 고촌읍 9,000(읍·리 3분할 합)
    assert by_name["김포시"]["v"] == 49_000
    assert by_name["김포시"]["label"] == "추정" and by_name["김포시"]["reason"] == "주민등록 세대"
    assert str(by_name["김포시"]["prov"]).startswith("rd_")
    # 연수구 = 송도1·2동 + 연수1동
    assert by_name["연수구"]["v"] == 59_001

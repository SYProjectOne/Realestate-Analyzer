"""region_resolve (D2-3): 자유 지명 → RegionCandidate[] — 공백·접미사 무시, exact > prefix > partial."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.contracts_gen import RegionCandidate
from app.normalize.region_resolve import (
    ReferenceData,
    expand_selections,
    normalize_name,
    resolve_region,
    resolve_region_db,
)


def kinds(cands: list[RegionCandidate]) -> list[tuple[str, str, str]]:
    return [(c.kind, c.full_name, c.match) for c in cands]


def test_normalize_name() -> None:
    assert normalize_name("김포시") == "김포"
    assert normalize_name("송도동") == "송도"
    assert normalize_name("송도") == "송도"  # 2자 미만으로 줄이지 않는다
    assert normalize_name("인천광역시", sido=True) == "인천"
    assert normalize_name(" 연 수 구 ") == "연수"


def test_songdo_is_songdo_dong_in_yeonsu(ref: ReferenceData) -> None:
    c = resolve_region("송도", ref)
    first = c[0]
    assert (first.kind, first.code, first.match) == ("legal_dong", "2818510600", "exact")
    assert first.full_name == "인천광역시 연수구 송도동"
    assert first.legal_dong_codes == ["2818510600"] and first.sigungu_code == "28185"
    # 행정동 송도1동·송도2동은 prefix로 뒤에
    assert [x.full_name for x in c if x.kind == "admin_dong"] == [
        "인천광역시 연수구 송도1동",
        "인천광역시 연수구 송도2동",
    ]
    assert all(x.match == "prefix" for x in c if x.kind == "admin_dong")


def test_geomdan_admin_dong_with_legal_codes_and_both_sigungu_codes(ref: ReferenceData) -> None:
    c = resolve_region("검단", ref)
    adm = [x for x in c if x.kind == "admin_dong"]
    assert len(adm) == 1 and adm[0].code == "2826063000" and adm[0].match == "exact"
    # 행정동 → 법정동 후보(폐지 코드 2826012200 제외)
    assert adm[0].legal_dong_codes == ["2826011600", "2826011700"]
    sgg = [x for x in c if x.kind == "sigungu"]
    assert [(x.code, x.match) for x in sgg] == [("28265", "exact")]
    assert sgg[0].legal_dong_codes == [
        "2826510100",
        "2826510200",
        "2826510300",
        "2826510400",
        "2826510500",
        "2826510600",
    ]
    # 폐지된 법정동 '검단동'은 후보가 아니다
    assert not [x for x in c if x.kind == "legal_dong"]
    # exact 안에서는 sigungu가 admin_dong보다 앞
    assert c[0].kind == "sigungu"


def test_gimpo_si_is_sigungu(ref: ReferenceData) -> None:
    c = resolve_region("김포시", ref)
    assert (c[0].kind, c[0].code, c[0].match) == ("sigungu", "41570", "exact")
    assert "4157025022" in c[0].legal_dong_codes and "4157000000" not in c[0].legal_dong_codes
    assert c[0].sido_code == "41"


def test_yeonsu_gu_exact_sigungu_first(ref: ReferenceData) -> None:
    c = resolve_region("연수구", ref)
    assert (c[0].kind, c[0].code, c[0].match) == ("sigungu", "28185", "exact")
    # 같은 이름의 법정동 '연수동'도 exact지만 sigungu 뒤, 행정동 '연수1동'은 prefix라 그 뒤
    assert [(x.kind, x.code, x.match) for x in c[1:3]] == [
        ("legal_dong", "2818510300", "exact"),
        ("admin_dong", "2818555000", "prefix"),
    ]


def test_multi_word_query_filters_by_ancestor(ref: ReferenceData) -> None:
    c = resolve_region("인천 연수구", ref)
    assert [x.code for x in c if x.kind == "sigungu"] == ["28185"]
    assert not resolve_region("경기 연수구", ref)
    ri = resolve_region("고촌 향산리", ref)
    assert [(x.kind, x.code) for x in ri] == [("legal_dong", "4157025022")]


def test_partial_and_sido(ref: ReferenceData) -> None:
    c = resolve_region("인천", ref)
    assert (c[0].kind, c[0].code, c[0].match) == ("sido", "28", "exact")
    p = resolve_region("오류왕", ref)
    assert [(x.kind, x.match) for x in p] == [("admin_dong", "prefix")]
    q = resolve_region("왕길", ref)
    assert ("admin_dong", "partial") in [(x.kind, x.match) for x in q]


def test_eupmyeondong_candidate_includes_ri(ref: ReferenceData) -> None:
    c = resolve_region("고촌읍", ref)
    leg = next(x for x in c if x.kind == "legal_dong")
    assert leg.legal_dong_codes == ["4157025000", "4157025021", "4157025022"]


def test_expand_selections(ref: ReferenceData) -> None:
    picks = [resolve_region("송도", ref)[0], resolve_region("김포시", ref)[0]]
    sido, sgg, legal = expand_selections(picks)
    assert sido == ["28", "41"] and sgg == ["28185", "41570"]
    assert "2818510600" in legal and "4157010700" in legal


def test_db_wrapper_same_as_pure(db_session: Session, reference_db: ReferenceData) -> None:
    assert resolve_region_db(db_session, "검단") == resolve_region("검단", reference_db)
    assert resolve_region_db(db_session, "") == []

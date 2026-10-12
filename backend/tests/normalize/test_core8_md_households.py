"""R4 재시험 m-d(minor, D21-7) — 보고서 §1-1 생활권 세대수는 세대 현황 집계 Fact(출처 = 세대 현황 원문 rd_)를 쓴다.

R4: ``region.living_areas[].households`` 가 null(지역 생성 때 집계 전)이라 보고서 §1-1 생활권 세대수 4칸이 '확인 불가(출처 누락)'
— API(``views.region_view``)는 세대 현황(household_stat) 집계로 같은 칸을 채우는데 보고서는 저장 json 만 읽었다(점수의 공급 성분
U_ref 에는 '추정'으로 쓰였다). D21-7: 보고서도 같은 집계(``living_area.region_household_facts``)로 출처를 연결한다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Region


def test_report_living_areas_link_household_source(db_session: Session, region: Region) -> None:
    from app.reports.data import report_living_areas

    assert all(a.get("households") is None for a in region.living_areas), (
        "R4 와 같은 상태(저장 json 세대수 null)"
    )
    areas = report_living_areas(db_session, region)
    assert [a["id"] for a in areas] == [a["id"] for a in region.living_areas]
    with_stats = [a for a in areas if a["households"] and a["households"]["label"] != "확인 불가"]
    assert with_stats, "세대 현황 집계가 있는 생활권은 값이 있다"
    for a in with_stats:
        h = a["households"]
        assert h["label"] == "추정" and str(h["prov"]).startswith("rd_") and isinstance(h["v"], int), h
    for a in areas:
        h = a["households"]
        assert h is None or h.get("reason") != "출처 누락", a

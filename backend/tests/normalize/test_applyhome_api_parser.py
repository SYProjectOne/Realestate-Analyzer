"""청약홈 공식 API JSON → 후보 (R2X).

픽스처 ``fixtures/applyhome_api/``: 2026-10-09 실제 API 응답 녹화(collectors 녹화 zip 에서 발췌,
serviceKey 없음)와 같은 날 웹 상세 HTML. 경쟁률(``get*LttotPblancCmpet_*.json``)도 실응답이다 —
경쟁률 서비스(data.go.kr 15098905) 활용신청 승인(2026-10-09) 뒤
``contracts/fixtures/tools/record_applyhome_cmpet.py`` 로 녹화한
``tests/collectors/applyhome/fixtures/applyhome_cmpet_2026-10-09/`` 의 발췌(WP9-후속, 합성 픽스처 교체).
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contracts_gen import FieldCandidate
from app.core.protocols import Parser
from app.models import Competition, Complex, ComplexType, Region
from app.normalize.applyhome_api_parser import (
    ApplyhomeApiParser,
    is_api_document,
    parse_applyhome_api_json,
)
from app.normalize.applyhome_parser import ApplyhomeParser, parse_applyhome_html
from app.normalize.store import store_raw_document

from ._support import FIX, AddRaw, dto

API = FIX / "applyhome_api"
URLS = {m["file"]: m["url"] for m in json.loads((API / "manifest.json").read_text(encoding="utf-8"))}
CMPET_URL = (
    "https://api.odcloud.kr/api/ApplyhomeInfoCmpetRtSvc/v1/getAPTLttotPblancCmpet"
    "?page=1&perPage=100&cond%5BHOUSE_MANAGE_NO%3A%3AEQ%5D=2026000367&cond%5BPBLANC_NO%3A%3AEQ%5D=2026000367"
)

RANK_AREA_KINDS = [
    "특별공급",
    "1순위 해당지역",
    "1순위 기타지역",
    "2순위 해당지역",
    "2순위 기타지역",
]  # R9-PARSE Q3


def _parse(name: str, url: str | None = None, source_kind: str = "applyhome_detail") -> list[FieldCandidate]:
    text = (API / name).read_text(encoding="utf-8")
    return parse_applyhome_api_json(text, dto(source_kind=source_kind, url=url or URLS[name]))


def _vals(cands: list[FieldCandidate], entity: str) -> dict[tuple[str, str], Any]:
    return {(str(c.entity_key), c.field): c.value for c in cands if c.entity == entity}


def test_parser_protocol_and_dispatch() -> None:
    assert isinstance(ApplyhomeApiParser(), Parser)
    name = "getAPTLttotPblancDetail_2026000367.json"
    raw = dto(source_kind="applyhome_detail", url=URLS[name])
    assert is_api_document(raw)
    assert not is_api_document(dto(source_kind="applyhome_detail", url=URLS["web_detail_2026000367.html"]))
    # ApplyhomeParser.parse 가 api.odcloud.kr 원문을 이 파서로 넘긴다
    text = (API / name).read_text(encoding="utf-8")
    assert ApplyhomeParser is not None and parse_applyhome_api_json(text, raw)


def test_apt_detail_and_model_fields() -> None:
    c = _parse("getAPTLttotPblancDetail_2026000367.json") + _parse("getAPTLttotPblancMdl_2026000367.json")
    cx = _vals(c, "complex")
    k = "2026000367"
    assert cx[(k, "name")] == "한강 푸르지오 리버프론트"
    assert cx[(k, "address")] == "경기도 김포시 고촌읍 향산리 588-45번지 일원"
    assert cx[(k, "units_total")] == 2432
    assert cx[(k, "notice_date")] == "2026-07-30" and cx[(k, "winner_date")] == "2026-08-20"
    assert cx[(k, "move_in_ym")] == "2031-01"
    assert json.loads(str(cx[(k, "contract_dates")])) == [{"from": "2026-09-01", "to": "2026-09-04"}]
    applies = json.loads(str(cx[(k, "apply_dates")]))
    # R9-PARSE Q3: 순위 × 거주지역마다 시작·끝(예전 '1순위'·'2순위' 시작일만)
    assert [a["kind"] for a in applies] == RANK_AREA_KINDS
    assert applies[0] == {"kind": "특별공급", "start": "2026-08-10", "end": "2026-08-10"}
    assert (cx[(k, "builder")], cx[(k, "housing_type")]) == ("(주)대우건설", "민영")
    types = _vals(c, "complex_type")
    assert any(
        f == "max_price_won" and isinstance(v, (int, float)) and v > 100_000_000
        for (_, f), v in types.items()
    )
    # 출처 규칙: 청약홈 상세와 같은 rank(가격 2, 나머지 1)·라벨 확인됨, observed_on = 모집공고일(상세 원문)
    for x in c:
        assert x.label == "확인됨" and x.source_kind == "applyhome_detail"
        assert x.source_rank == (2 if x.field == "max_price_won" else 1), x.field
        assert x.excerpt and x.excerpt_start is not None and x.excerpt_end is not None
    detail_text = (API / "getAPTLttotPblancDetail_2026000367.json").read_text(encoding="utf-8")
    for x in _parse("getAPTLttotPblancDetail_2026000367.json"):
        assert x.observed_on == "2026-07-30"
        assert detail_text[x.excerpt_start or 0 : x.excerpt_end] == x.excerpt  # 발췌 = 원문 조각


def test_api_matches_web_detail_for_same_complex() -> None:
    """같은 날 같은 단지: API(상세+주택형)와 웹 상세 HTML 의 공통 필드 값이 같다."""
    for hm, kind in (("2026000367", "APT"), ("2026910242", "Remndr"), ("2026940173", "OPT")):
        api = _parse(f"get{kind}LttotPblancDetail_{hm}.json") + _parse(f"get{kind}LttotPblancMdl_{hm}.json")
        html = (API / f"web_detail_{hm}.html").read_text(encoding="utf-8")
        web = parse_applyhome_html(
            html, dto(source_kind="applyhome_detail", url=URLS[f"web_detail_{hm}.html"])
        )
        a = {(c.entity, str(c.entity_key), c.field): c.value for c in api}
        w = {(c.entity, str(c.entity_key), c.field): c.value for c in web}
        # R9-PARSE Q3: 청약 일정(apply_dates)도 같은 값 — 웹 잔여세대 화면의 '청약접수' 칸도 읽는다
        common = a.keys() & w.keys()
        assert ("complex", hm, "apply_dates") in common, hm
        diff = {k: (a[k], w[k]) for k in common if a[k] != w[k]}
        assert len(common) >= 5, (hm, sorted(w))
        assert not diff, (hm, diff)


def test_remndr_and_opt() -> None:
    r = _vals(_parse("getRemndrLttotPblancDetail_2026910242.json"), "complex")
    assert r[("2026910242", "units_total")] == 1
    assert [a["kind"] for a in json.loads(str(r[("2026910242", "apply_dates")]))] == ["청약접수"]
    o = _parse("getOPTLttotPblancMdl_2026940173.json")
    prices = {str(c.entity_key): c.value for c in o if c.field == "max_price_won"}
    assert prices["2026940173:64A"] == 507_000_000  # '50,700'(만원, 쉼표) → 원
    od = _vals(_parse("getOPTLttotPblancDetail_2026940173.json"), "complex")
    notice = str(od[("2026940173", "notice_date")])
    assert len(notice) == 10 and notice[4] == "-"  # 임의공급 원문 YYYYMMDD → ISO


def test_list_page_and_failures_yield_nothing() -> None:
    name = "getAPTLttotPblancDetail_2026000367.json"
    assert _parse(name, source_kind="applyhome_list") == []
    assert parse_applyhome_api_json("not json", dto(source_kind="applyhome_detail", url=URLS[name])) == []
    assert (
        parse_applyhome_api_json('{"code":-401}', dto(source_kind="applyhome_detail", url=URLS[name])) == []
    )


def test_competition_keys_match_web_popup_format() -> None:
    """실응답(한강 푸르지오 리버프론트 본청약 2026000367): 키 = 웹 경쟁률 팝업 형식, 값 = 원문 그대로."""
    c = _parse("getAPTLttotPblancCmpet_2026000367.json", url=CMPET_URL)
    v = _vals(c, "competition")
    k = "2026000367:본청약:1순위 해당지역:84A"  # 웹 경쟁률 팝업과 같은 키 형식
    assert (v[(k, "supply")], v[(k, "applied")], v[(k, "ratio_or_shortfall_text")]) == (667, 216, "(△451)")
    assert v[("2026000367:본청약:2순위 기타지역:84A", "ratio_or_shortfall_text")] == "1.52"
    # 1순위 마감 → 2순위 미실시는 '-'
    assert v[("2026000367:본청약:2순위 해당지역:84E", "ratio_or_shortfall_text")] == "-"
    assert all(x.source_rank == 1 and x.observed_on is None for x in c)
    remndr = CMPET_URL.replace("getAPTLttotPblancCmpet", "getRemndrLttotPblancCmpet")
    rk = {str(x.entity_key) for x in _parse("getAPTLttotPblancCmpet_2026000367.json", url=remndr)}
    assert "2026000367:무순위:무순위 2026000367:84A" in rk


def test_store_creates_complex_types_and_competition(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    """정규화 저장(ApplyhomeParser 가 API 원문을 넘긴다): 단지·주택형·경쟁률 행 + 출처 행."""
    for name, url in (
        ("getAPTLttotPblancDetail_2026000367.json", None),
        ("getAPTLttotPblancMdl_2026000367.json", None),
        ("getAPTLttotPblancCmpet_2026000367.json", CMPET_URL),
    ):
        raw = add_raw(
            (API / name).read_text(encoding="utf-8"),
            source_kind="applyhome_detail",
            url=url or URLS[name],
            region_id=region.id,
            ext="json",
        )
        res = store_raw_document(db_session, raw)
        assert res.candidates
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2026000367")).one()
    assert (cx.units_total, cx.move_in_ym, cx.address) == (
        2432,
        "2031-01",
        "경기도 김포시 고촌읍 향산리 588-45번지 일원",
    )
    types = db_session.scalars(select(ComplexType).where(ComplexType.complex_id == cx.id)).all()
    assert types and all(t.notice_type_code for t in types)
    comps = db_session.scalars(select(Competition).where(Competition.complex_id == cx.id)).all()
    assert {(c.kind, c.round) for c in comps} >= {("본청약", "1순위 해당지역")}

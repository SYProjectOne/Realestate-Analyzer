"""청약홈 경쟁률 API 실응답(data.go.kr 15098905) → 경쟁률 파서 (WP9-후속, DECISIONS D1 #6a).

녹화: ``tests/collectors/applyhome/fixtures/applyhome_cmpet_2026-10-09/`` — 인천·김포 회귀 픽스처 단지 공고 10건
(APT 4·무순위 3·임의공급 3)을 ``contracts/fixtures/tools/record_applyhome_cmpet.py`` 로 2026-10-09 녹화(serviceKey 없음).
파서(``app.normalize.applyhome_api_parser`` 경쟁률 부분)는 읽기만 — 여기서는 실응답 필드
(``CMPET_RATE``·``REQ_CNT``·``SUPLY_HSHLDCO``·``HOUSE_TY``·``SUBSCRPT_RANK_CODE``·``RESIDE_SECD``/``RESIDE_SENM``·
``PBLANC_NO``)를 제대로 읽는지 행 단위로 본다.

실응답에서 본 모양(합성 픽스처와 다른 점):
- ``REQ_CNT`` 는 문자열("216", 쉼표 없음), ``SUPLY_HSHLDCO``·``SUBSCRPT_RANK_CODE`` 는 숫자.
- ``CMPET_RATE`` 는 "34.20"·"(△451)"(미달)·"-"(앞 순위 마감 → 미실시) 세 모양.
- 거주 구분은 코드 ``RESIDE_SECD``(01·02)와 이름 ``RESIDE_SENM``(해당지역·기타지역)이 같이 온다(파서는 이름을 쓴다).
- 무순위는 ``REMNDR_HSHLD_PBLANC_TYCD``, 순위·거주 필드 없음. 임의공급도 순위·거주 필드 없음.
- ``HOUSE_TY`` 에 문자 접미사가 없고 공백이 붙은 주택형이 있다('084.7529 ', '122.7490 ') → 약식 코드 '84.7529'.
"""

# ruff: noqa: E501
from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, Complex, ComplexType, Region
from app.normalize._text import normalize_type_code
from app.normalize.applyhome_api_parser import parse_applyhome_api_json
from app.normalize.store import store_raw_document

from ._support import FIX, AddRaw, dto

BACKEND = Path(__file__).resolve().parents[1].parent
REC = BACKEND / "tests" / "collectors" / "applyhome" / "fixtures" / "applyhome_cmpet_2026-10-09"
API_ZIP = BACKEND / "tests" / "collectors" / "applyhome" / "fixtures" / "applyhome_api_2026-10-09.zip"
NF = FIX / "applyhome_api"
MANIFEST: dict[str, Any] = json.loads((REC / "manifest.json").read_text(encoding="utf-8"))
ENTRIES: list[dict[str, Any]] = MANIFEST["entries"]
KIND = {"apt": "본청약", "remndr": "무순위", "opt": "임의"}
RESIDE = {"01": "해당지역", "02": "기타지역"}


def _text(e: dict[str, Any]) -> str:
    return (REC / e["file"]).read_text(encoding="utf-8")


def _rows(e: dict[str, Any]) -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads(_text(e))["data"]
    return data


def _round(e: dict[str, Any], row: dict[str, Any]) -> str:
    if e["kind"] == "apt":
        return f"{row['SUBSCRPT_RANK_CODE']}순위 {row['RESIDE_SENM']}"
    return f"{KIND[e['kind']]} {row['PBLANC_NO']}"


def test_recording_has_no_key_and_covers_three_services() -> None:
    assert {e["kind"] for e in ENTRIES} == {"apt", "remndr", "opt"}
    assert all(e["status"] == 200 and e["rows"] > 0 and e["error"] is None for e in ENTRIES)
    for e in ENTRIES:
        assert "serviceKey" not in e["url"] and "ApplyhomeInfoCmpetRtSvc/v1/get" in e["url"]
        assert "serviceKey" not in _text(e)
    assert sum(1 for e in ENTRIES if e["kind"] == "apt") >= 3


@pytest.mark.parametrize("e", ENTRIES, ids=[e["file"] for e in ENTRIES])
def test_every_row_three_fields_exact(e: dict[str, Any]) -> None:
    """행마다 supply = SUPLY_HSHLDCO, applied = REQ_CNT(정수), 비율 문구 = CMPET_RATE — 키는 웹 팝업 형식, 발췌·오프셋 = 원문."""
    text = _text(e)
    cands = parse_applyhome_api_json(text, dto(source_kind="applyhome_detail", url=e["url"]))
    got = {(str(c.entity_key), c.field): c for c in cands}
    rows = _rows(e)
    assert len(cands) == 3 * len(rows), "행마다 3필드(빠진 값 없음)"
    assert len(got) == len(cands), "키 중복 없음"
    for row in rows:
        key = f"{row['HOUSE_MANAGE_NO']}:{KIND[e['kind']]}:{_round(e, row)}:{normalize_type_code(row['HOUSE_TY'])}"
        sup, app, ratio = got[(key, "supply")], got[(key, "applied")], got[(key, "ratio_or_shortfall_text")]
        assert sup.value == row["SUPLY_HSHLDCO"] and isinstance(row["SUPLY_HSHLDCO"], int)
        assert app.value == int(str(row["REQ_CNT"]).replace(",", "")) and app.value_text == row["REQ_CNT"]
        assert ratio.value == str(row["CMPET_RATE"]).strip()
        if e["kind"] == "apt":
            assert RESIDE[row["RESIDE_SECD"]] == row["RESIDE_SENM"], "거주 코드·이름 일치(파서는 이름으로 round 를 만든다)"
            assert isinstance(row["SUBSCRPT_RANK_CODE"], int)
        else:
            assert "SUBSCRPT_RANK_CODE" not in row and "RESIDE_SECD" not in row
    for c in cands:
        assert c.entity == "competition" and c.source_rank == 1 and c.observed_on is None
        assert c.excerpt and c.excerpt_start is not None and c.excerpt_end is not None
        assert text[c.excerpt_start : c.excerpt_end] == c.excerpt


def test_ratio_text_shapes_seen_in_real_responses() -> None:
    seen = {str(r["CMPET_RATE"]) for e in ENTRIES for r in _rows(e)}
    assert "-" in seen and any(s.startswith("(△") for s in seen) and any(s.replace(".", "").isdigit() for s in seen)


def test_report_values_match_recording() -> None:
    """보고서 수치와 대조: 마리나베이 무순위 3회차 1세대 173건(173:1), 한내들 임의공급 전 타입 1.18~4.25:1."""
    by = {e["house_manage_no"]: _rows(e) for e in ENTRIES}
    mb = by["2026910242"]
    assert [(r["SUPLY_HSHLDCO"], r["REQ_CNT"], r["CMPET_RATE"]) for r in mb] == [(1, "173", "173.00")]
    rates = sorted(float(r["CMPET_RATE"]) for r in by["2026940088"])
    assert (rates[0], rates[-1]) == (1.18, 4.25)


def test_store_competition_rows_and_type_codes(db_session: Session, region: Region, add_raw: AddRaw) -> None:
    """정규화 저장: 임의공급(엘리프 3차 2026940173) 상세·주택형·경쟁률 실응답 → competition 행 7개, 타입 = 주택형 약식 코드."""
    urls = {m["file"]: m["url"] for m in json.loads((NF / "manifest.json").read_text(encoding="utf-8"))}
    for name in ("getOPTLttotPblancDetail_2026940173.json", "getOPTLttotPblancMdl_2026940173.json",
                 "getOPTLttotPblancCmpet_2026940173.json"):  # fmt: skip
        raw = add_raw((NF / name).read_text(encoding="utf-8"), source_kind="applyhome_detail", url=urls[name],
                      region_id=region.id, ext="json")  # fmt: skip
        assert store_raw_document(db_session, raw).candidates
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2026940173")).one()
    comps = db_session.scalars(select(Competition).where(Competition.complex_id == cx.id)).all()
    types = {t.type_code for t in db_session.scalars(select(ComplexType).where(ComplexType.complex_id == cx.id))}
    assert len(comps) == 7 and {c.kind for c in comps} == {"임의"} and {c.round for c in comps} == {"임의 2026940173"}
    assert {c.type_code for c in comps} <= types, ({c.type_code for c in comps}, types)
    c84a = next(c for c in comps if c.type_code == "84A")
    assert (c84a.supply, c84a.applied, c84a.ratio_or_shortfall_text) == (2, 15, "7.50")


def _zip_entry(z: zipfile.ZipFile, needle: str) -> tuple[str, str]:
    m = json.loads(z.read("manifest.json"))["entries"]
    e = next(x for x in m if needle in x["url"] and x["status"] == 200)
    return e["url"], z.read(e["file"]).decode("utf-8")


def test_letterless_house_ty_competition_matches_complex_types(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    """칸타빌 임의공급 2차(2026940116): 공고문 주택형 84A(84.9582㎡)·84B(84.7529㎡)가 이미 있는 단지에 API 상세·주택형·경쟁률
    실응답을 저장하면, 경쟁률 행의 type_code 도 그 주택형(84B 등)이어야 화면(C8 경쟁률·타입별 표)이 맞는다."""
    with zipfile.ZipFile(API_ZIP) as z:
        detail = _zip_entry(z, "getOPTLttotPblancDetail?page=1&perPage=100&cond%5BHOUSE_MANAGE_NO%3A%3AEQ%5D=2026940116")
        model = _zip_entry(z, "getOPTLttotPblancMdl?page=1&perPage=100&cond%5BHOUSE_MANAGE_NO%3A%3AEQ%5D=2026940116")
    cmpet = next(e for e in ENTRIES if e["house_manage_no"] == "2026940116")
    store_raw_document(db_session, add_raw(detail[1], source_kind="applyhome_detail", url=detail[0], region_id=region.id, ext="json"))
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2026940116")).one()
    # 공고문(웹·PDF) 파서가 만든 것과 같은 약식 주택형이 이미 있는 상태(픽스처 complexes.json 칸타빌: 84A·84B)
    db_session.add_all([ComplexType(complex_id=cx.id, type_code="84A", area_m2=84.9582),
                        ComplexType(complex_id=cx.id, type_code="84B", area_m2=84.7529)])  # fmt: skip
    db_session.flush()
    for url, text in (model, (cmpet["url"], _text(cmpet))):
        store_raw_document(db_session, add_raw(text, source_kind="applyhome_detail", url=url, region_id=region.id, ext="json"))
    types = {t.type_code for t in db_session.scalars(select(ComplexType).where(ComplexType.complex_id == cx.id))}
    # 주택형(Mdl)은 저장 단계가 전용면적으로 기존 약식 타입(84A·84B)에 맞춘다 — 새 '84.xxxx' 행이 생기지 않는다
    assert not {t for t in types if t.startswith("84.")}, sorted(types)
    comps = db_session.scalars(select(Competition).where(Competition.complex_id == cx.id)).all()
    assert comps
    eighty_four = {c.type_code for c in comps if c.type_code.startswith("84")}
    assert eighty_four <= {"84A", "84B"}, (eighty_four, sorted(types))  # R3 마무리 전: {'84.7529', '84.9582'}


def test_letterless_house_ty_ambiguous_area_is_not_matched(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    """같은 전용면적(소수 4자리)의 단지 주택형이 둘이면(84A·84B 모두 84.7529) 면적 코드 경쟁률은 어느 쪽에도 붙이지 않고
    type_code '확인 불가(타입 모호)'로 남긴다 — 다른 면적(84.9582 → 하나)은 그대로 맞춘다."""
    from app.normalize.store import TYPE_AMBIGUOUS

    with zipfile.ZipFile(API_ZIP) as z:
        detail = _zip_entry(z, "getOPTLttotPblancDetail?page=1&perPage=100&cond%5BHOUSE_MANAGE_NO%3A%3AEQ%5D=2026940116")
    cmpet = next(e for e in ENTRIES if e["house_manage_no"] == "2026940116")
    store_raw_document(db_session, add_raw(detail[1], source_kind="applyhome_detail", url=detail[0], region_id=region.id, ext="json"))
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2026940116")).one()
    db_session.add_all([ComplexType(complex_id=cx.id, type_code="84A", area_m2=84.75, notice_type_code="084.7529A"),
                        ComplexType(complex_id=cx.id, type_code="84B", area_m2=84.75, notice_type_code="084.7529B"),
                        ComplexType(complex_id=cx.id, type_code="84C", area_m2=84.96, notice_type_code="084.9582C")])  # fmt: skip
    db_session.flush()
    store_raw_document(db_session, add_raw(_text(cmpet), source_kind="applyhome_detail", url=cmpet["url"], region_id=region.id, ext="json"))
    codes = {c.type_code for c in db_session.scalars(select(Competition).where(Competition.complex_id == cx.id))}
    assert TYPE_AMBIGUOUS in codes and "84C" in codes, codes
    assert not codes & {"84A", "84B"}, codes


@pytest.mark.live
def test_live_competition_api_matches_recording() -> None:
    """실제 호출 1회(APT 리버프론트 2026000367): 200·48행, 녹화와 같은 행(마감 공고라 값이 변하지 않는다), 주소에 키 없음.

    실행: ``ENV_FILE=<메인 체크아웃>/.env uv run pytest -m live tests/normalize/test_applyhome_cmpet_real.py``
    """
    from app.collectors.applyhome import api
    from app.core.http import HttpClient
    from app.core.settings import load_settings

    s = load_settings()
    key = s.data_go_kr_key.get_secret_value() if s.data_go_kr_key else os.environ.get("DATA_GO_KR_KEY")
    if not key:
        pytest.skip("DATA_GO_KR_KEY 없음 (ENV_FILE 로 .env 경로를 준다)")
    e = next(x for x in ENTRIES if x["house_manage_no"] == "2026000367")
    with HttpClient(max_retries=1) as http:
        r = api.ApplyhomeApi(http, key).get(api.ENDPOINTS["apt"].competition, api.item_params("2026000367", "2026000367"))
    assert r.status == 200 and key not in r.url and "serviceKey" not in r.url
    page = api.parse_page(r)
    assert page.ok and len(page.rows) == e["rows"] == 48
    key_of = lambda x: (x["HOUSE_TY"], x["SUBSCRPT_RANK_CODE"], x["RESIDE_SECD"])  # noqa: E731
    assert sorted(page.rows, key=key_of) == sorted(_rows(e), key=key_of)
    cands = parse_applyhome_api_json((r.content or b"").decode("utf-8"), dto(source_kind="applyhome_detail", url=r.url))
    assert len(cands) == 3 * 48

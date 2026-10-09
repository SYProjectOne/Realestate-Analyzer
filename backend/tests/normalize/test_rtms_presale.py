"""R3b F1a: 분양권 전매 실거래 원문(``RTMSDataSvcSilvTrade``) → rtms_trade 후보 is_presale=True.

픽스처는 수집기 테스트의 합성 응답(``tests/collectors/rtms/fixtures/openapi_presale_synthetic.xml`` — 키가 서비스에
활용신청되지 않아 실녹화 불가, 파일 주석)을 같이 쓴다.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Region, RtmsTrade
from app.normalize.rtms_parser import is_presale_url, parse_rtms_xml
from app.normalize.store import store_raw_document

from ._support import AddRaw, dto

PRESALE_XML = (
    Path(__file__).resolve().parents[1] / "collectors" / "rtms" / "fixtures" / "openapi_presale_synthetic.xml"
)
PRESALE_URL = (
    "https://apis.data.go.kr/1613000/RTMSDataSvcSilvTrade/getRTMSDataSvcSilvTrade"
    "?LAWD_CD=28185&DEAL_YMD=202609&numOfRows=1000&pageNo=1"
)
TRADE_URL = (
    "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"
    "?LAWD_CD=28185&DEAL_YMD=202609&numOfRows=1000&pageNo=1"
)


def test_presale_url_detection() -> None:
    assert is_presale_url(PRESALE_URL)
    assert not is_presale_url(TRADE_URL)
    assert not is_presale_url("https://example-reprocessed.kr/SilvTrade")  # Open API 가 아니면 아니다


def test_presale_candidates_have_is_presale_true() -> None:
    xml = PRESALE_XML.read_text(encoding="utf-8")
    c = parse_rtms_xml(xml, dto(source_kind="rtms", url=PRESALE_URL))
    keys = sorted({str(x.entity_key) for x in c})
    assert len(keys) == 2
    for k in keys:
        f = {x.field: x for x in c if x.entity_key == k}
        assert f["is_presale"].value is True
        assert f["is_presale"].label == "확인됨" and f["is_presale"].source_rank == 1
        assert f["is_presale"].value_text in ("분", "입")  # 원문 구분(분양권/입주권)
        assert f["source"].value == "openapi"
    p = {x.field: x.value for x in c if "테스트분양권아파트P" in str(x.entity_key)}
    assert p["price_won"] == 624_500_000 and p["deal_date"] == "2026-09-21" and p["floor"] == 17
    assert "legal_dong_code" not in p  # 분양권 응답에는 umdCd 가 없다(합성 픽스처 가정)
    # 같은 원문을 매매 URL 로 읽으면 is_presale 후보가 없고 키도 다르다(같은 값의 매매와 섞이지 않게)
    t = parse_rtms_xml(xml, dto(source_kind="rtms", url=TRADE_URL))
    assert not any(x.field == "is_presale" for x in t)
    assert not ({str(x.entity_key) for x in t} & set(keys))


def test_store_writes_is_presale(db_session: Session, region: Region, add_raw: AddRaw) -> None:
    raw = add_raw(
        PRESALE_XML.read_text(encoding="utf-8"),
        source_kind="rtms",
        url=PRESALE_URL,
        region_id=region.id,
        ext="xml",
    )
    store_raw_document(db_session, raw)
    store_raw_document(db_session, raw)  # 멱등
    rows = db_session.scalars(select(RtmsTrade).order_by(RtmsTrade.apt_name)).all()
    assert [(r.apt_name, r.is_presale, r.cancelled) for r in rows] == [
        ("테스트분양권아파트P", True, False),
        ("테스트분양권아파트Q", True, True),
    ]

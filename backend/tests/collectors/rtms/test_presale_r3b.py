"""R3b F1a: 분양권 전매 실거래(``RTMSDataSvcSilvTrade``) 수집 → ``rtms_trade.is_presale=True``.

- 매매 API 와 같은 키·같은 LAWD_CD/DEAL_YMD, 같은 raw_document 흐름(source_kind 'rtms'), URL 경로로 구별.
- 픽스처 ``openapi_presale_synthetic.xml`` 은 합성(파일 주석 — 키가 서비스에 활용신청되지 않아 실녹화 불가).
- 서비스 미신청(403 SERVICE_KEY_IS_NOT_REGISTERED_ERROR)이면 실패 행 1개만 남기고 그 실행의 나머지 분양권
  호출은 하지 않는다(매매 수집은 그대로).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import respx
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.collectors.rtms import PRESALE_API_URL, RTMS_API_URL, RtmsCollector, parse_trade_xml
from app.core.contracts_gen import Region, Snapshot
from app.core.http import HttpClient
from app.models import RawDocument, RtmsTrade

FAKE_KEY = "TEST%2BKEY%3D%3D"
PRESALE = "openapi_presale_synthetic.xml"


def _xml(fixtures_dir: Path, name: str) -> Callable[[httpx.Request], httpx.Response]:
    body = (fixtures_dir / name).read_bytes()
    empty = (fixtures_dir / "openapi_trade_empty.xml").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.params
        content = body if p["LAWD_CD"] == "28185" else empty
        # 실제 응답은 API·시군구·월마다 다르다(같은 sha 면 원문 1행) — 표시만 달리한다
        tag = f"<resultMsg>OK</resultMsg><!-- {request.url.path} {p['LAWD_CD']} {p['DEAL_YMD']} -->"
        content = content.replace(b"<resultMsg>OK</resultMsg>", tag.encode())
        return httpx.Response(200, content=content, headers={"content-type": "application/xml"})

    return handler


def test_presale_endpoint_shape() -> None:
    assert PRESALE_API_URL == (
        "https://apis.data.go.kr/1613000/RTMSDataSvcSilvTrade/getRTMSDataSvcSilvTrade"
    )
    assert PRESALE_API_URL != RTMS_API_URL


def test_parse_presale_fixture(fixtures_dir: Path) -> None:
    page = parse_trade_xml((fixtures_dir / PRESALE).read_bytes(), is_presale=True)
    assert page.ok and page.total_count == 2 and len(page.items) == 2
    assert all(t.is_presale for t in page.items)
    p = next(t for t in page.items if t.apt_name == "테스트분양권아파트P")
    assert p.price_won == 624_500_000 and p.legal_dong_code is None and p.completed_year is None
    q = next(t for t in page.items if t.apt_name == "테스트분양권아파트Q")
    assert q.cancelled is True and q.cancel_date == "2026-10-01"
    # 매매 응답은 기본값 그대로(is_presale False)
    assert not any(
        t.is_presale for t in parse_trade_xml((fixtures_dir / "openapi_trade_sample.xml").read_bytes()).items
    )


def test_collects_presale_and_marks_is_presale(
    db_engine: Engine,
    region_ctx: tuple[Region, Snapshot],
    fixtures_dir: Path,
    http: HttpClient,
    count: Callable[[type[Any]], int],
) -> None:
    region, snapshot = region_ctx
    with respx.mock(assert_all_called=False) as router:
        router.get("https://apis.data.go.kr/robots.txt").respond(400)
        trade = router.get(RTMS_API_URL).mock(side_effect=_xml(fixtures_dir, "openapi_trade_sample.xml"))
        presale = router.get(PRESALE_API_URL).mock(side_effect=_xml(fixtures_dir, PRESALE))
        col = RtmsCollector(service_key=FAKE_KEY, http=http, months=1)
        docs = col.fetch(region, snapshot, None)
        assert trade.call_count == 2 and presale.call_count == 2  # 시군구 2 × 1개월, API 2종
        sent = presale.calls[0].request.url.params
        assert (sent["serviceKey"], sent["LAWD_CD"], sent["DEAL_YMD"]) == ("TEST+KEY==", "28185", "202610")
        assert len(docs) == 4 and {d.source_kind for d in docs} == {"rtms"}
        assert sum("RTMSDataSvcSilvTrade" in d.url for d in docs) == 2
        assert col.load_stats is not None and col.load_stats.inserted == 5  # 매매 3 + 분양권 2
        n_raw, n_trade = count(RawDocument), count(RtmsTrade)
        RtmsCollector(service_key=FAKE_KEY, http=http, months=1).fetch(region, snapshot, None)
        assert (count(RawDocument), count(RtmsTrade)) == (n_raw, n_trade)  # 멱등
    with Session(db_engine) as s:
        rows = {t.apt_name: t for t in s.scalars(select(RtmsTrade))}
        urls = [d.url for d in s.scalars(select(RawDocument))]
        presale_doc_ids = {
            d.id for d in s.scalars(select(RawDocument)) if "RTMSDataSvcSilvTrade" in d.url
        }
    assert {n for n, t in rows.items() if t.is_presale} == {"테스트분양권아파트P", "테스트분양권아파트Q"}
    assert not any(rows[n].is_presale for n in ("테스트아파트A", "테스트아파트B", "테스트아파트C"))
    assert rows["테스트분양권아파트P"].raw_document_id in presale_doc_ids
    assert rows["테스트분양권아파트Q"].cancelled is True
    assert all("serviceKey" not in u and "TEST" not in u for u in urls)


def test_presale_not_registered_leaves_one_row_and_stops(
    region_ctx: tuple[Region, Snapshot],
    fixtures_dir: Path,
    http: HttpClient,
    count: Callable[[type[Any]], int],
) -> None:
    """실제 2026-10-09 응답(403 SERVICE_KEY_IS_NOT_REGISTERED_ERROR) — 매매는 그대로, 분양권은 1회만."""
    region, snapshot = region_ctx
    with respx.mock(assert_all_called=False) as router:
        router.get("https://apis.data.go.kr/robots.txt").respond(400)
        trade = router.get(RTMS_API_URL).mock(side_effect=_xml(fixtures_dir, "openapi_trade_sample.xml"))
        presale = router.get(PRESALE_API_URL).respond(
            403,
            content=(fixtures_dir / "openapi_403_not_registered.xml").read_bytes(),
            headers={"content-type": "application/xml"},
        )
        col = RtmsCollector(service_key=FAKE_KEY, http=http, months=2)
        docs = col.fetch(region, snapshot, None)
    assert trade.call_count == 4 and presale.call_count == 1  # 시군구 2 × 2개월
    failed = [d for d in docs if "RTMSDataSvcSilvTrade" in d.url]
    assert [(d.http_status, d.error_text) for d in failed] == [(403, "SERVICE_KEY_IS_NOT_REGISTERED_ERROR")]
    assert col.presale_disabled_reason == "403: SERVICE_KEY_IS_NOT_REGISTERED_ERROR"
    assert col.trades and not any(t.is_presale for _, t in col.trades)
    assert col.load_stats is not None and col.load_stats.inserted == len(col.trades)


def test_presale_can_be_turned_off(
    region_ctx: tuple[Region, Snapshot], fixtures_dir: Path, http: HttpClient
) -> None:
    region, snapshot = region_ctx
    with respx.mock(assert_all_called=False) as router:
        router.get("https://apis.data.go.kr/robots.txt").respond(400)
        router.get(RTMS_API_URL).mock(side_effect=_xml(fixtures_dir, "openapi_trade_sample.xml"))
        presale = router.get(PRESALE_API_URL).mock(side_effect=_xml(fixtures_dir, PRESALE))
        RtmsCollector(service_key=FAKE_KEY, http=http, months=1, presale=False).fetch(region, snapshot, None)
    assert presale.call_count == 0


def test_backfill_includes_presale_months(
    region_ctx: tuple[Region, Snapshot], fixtures_dir: Path, http: HttpClient
) -> None:
    region, snapshot = region_ctx
    with respx.mock(assert_all_called=False) as router:
        router.get("https://apis.data.go.kr/robots.txt").respond(400)
        router.get(RTMS_API_URL).mock(side_effect=_xml(fixtures_dir, "openapi_trade_sample.xml"))
        presale = router.get(PRESALE_API_URL).mock(side_effect=_xml(fixtures_dir, PRESALE))
        RtmsCollector(service_key=FAKE_KEY, http=http, months=1).fetch(region, snapshot, None)
        assert presale.call_count == 2
        col = RtmsCollector(service_key=FAKE_KEY, http=http, months=1)
        col.backfill(region, snapshot, months=2)  # 202609 만 새로(202610 은 이미 받음)
        new = sorted(
            (c.request.url.params["LAWD_CD"], c.request.url.params["DEAL_YMD"]) for c in presale.calls[2:]
        )
        assert new == [("28185", "202609"), ("41570", "202609")]

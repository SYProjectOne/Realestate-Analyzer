"""rtms: Open API XML 파싱(해제 플래그 보존) + 키 없는 경로(비활성 / 재가공 폴백 인터페이스) + 멱등."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.collectors.rtms import (
    DISABLED_NO_KEY,
    RTMS_API_URL,
    RtmsCollector,
    TradeRecord,
    api_error_message,
    load_trades,
    month_range,
    parse_trade_xml,
)
from app.core.contracts_gen import Region, Snapshot
from app.core.http import FetchResult, HttpClient
from app.models import RawDocument, RtmsTrade

FAKE_KEY = "TEST%2BKEY%3D%3D"  # 인코딩 키 형태(가짜)
# 분양권 전매 API 는 test_presale_r3b.py — 여기서는 매매 API 만(presale=False)


def test_parse_openapi_xml_keeps_cancelled_flag(fixtures_dir: Path) -> None:
    page = parse_trade_xml((fixtures_dir / "openapi_trade_sample.xml").read_bytes())
    assert page.ok and page.total_count == 3 and page.skipped == 0
    a, b, c = page.items
    assert (a.apt_name, a.price_won, a.area_m2, a.floor, a.deal_date) == (
        "테스트아파트A",
        1_050_000_000,
        Decimal("84.81"),
        45,
        "2026-09-30",
    )
    assert (a.legal_dong_code, a.dong, a.completed_year, a.apt_dong) == ("2818510600", "송도동", 2025, "101")
    assert (a.cancelled, a.cancel_date, a.source, a.label) == (False, None, "openapi", "확인됨")
    assert (b.cancelled, b.cancel_date, b.area_m2, b.apt_dong) == (True, "2026-10-02", Decimal("84.34"), None)
    assert c.dealing_type == "직거래"


def test_parse_recorded_error_responses(fixtures_dir: Path) -> None:
    for name, msg in [
        ("openapi_403_not_registered.xml", "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"),
        ("openapi_401_key_null.xml", "SERVICE_KEY_IS_NULL"),
    ]:
        content = (fixtures_dir / name).read_bytes()
        page = parse_trade_xml(content)
        assert not page.ok and page.result_msg == msg
        assert api_error_message(content) == msg
    assert not parse_trade_xml(b"not xml").ok


def test_month_range() -> None:
    assert month_range("2025-11", "2026-02") == ["202511", "202512", "202601", "202602"]


def test_no_key_is_disabled_without_network(
    region_ctx: tuple[Region, Snapshot], count: Callable[[type[Any]], int]
) -> None:
    region, snapshot = region_ctx
    collector = RtmsCollector()  # test_settings: DATA_GO_KR_KEY 없음
    assert (collector.enabled, collector.disabled_reason, collector.mode) == (
        False,
        DISABLED_NO_KEY,
        "disabled",
    )
    with respx.mock(assert_all_called=False) as router:
        assert collector.fetch(region, snapshot, None) == []
        assert router.calls.call_count == 0
    assert count(RawDocument) == 0


def _xml_by_lawd(fx: Path) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        name = (
            "openapi_trade_sample.xml"
            if request.url.params["LAWD_CD"] == "28185"
            else "openapi_trade_empty.xml"
        )
        return httpx.Response(
            200, content=(fx / name).read_bytes(), headers={"content-type": "application/xml"}
        )

    return handler


def test_openapi_collects_loads_and_is_idempotent(
    db_engine: Engine,
    region_ctx: tuple[Region, Snapshot],
    fixtures_dir: Path,
    http: HttpClient,
    count: Callable[[type[Any]], int],
) -> None:
    region, snapshot = region_ctx
    with respx.mock(assert_all_called=False) as router:
        router.get("https://apis.data.go.kr/robots.txt").respond(400)  # 실제 응답도 400 → 제한 없음
        route = router.get(RTMS_API_URL).mock(side_effect=_xml_by_lawd(fixtures_dir))
        collector = RtmsCollector(service_key=FAKE_KEY, http=http, months=1, presale=False)
        docs = collector.fetch(region, snapshot, None)
        assert route.call_count == 2  # 시군구 2 × 1개월
        sent = route.calls[0].request.url.params
        assert (sent["serviceKey"], sent["DEAL_YMD"], sent["LAWD_CD"]) == ("TEST+KEY==", "202610", "28185")
        assert len(docs) == 2 and all(d.http_status == 200 for d in docs)
        assert collector.load_stats is not None and collector.load_stats.inserted == 3
        n_raw, n_trade = count(RawDocument), count(RtmsTrade)

        again = RtmsCollector(service_key=FAKE_KEY, http=http, months=1, presale=False)
        again.fetch(region, snapshot, None)
        assert (count(RawDocument), count(RtmsTrade)) == (n_raw, n_trade)  # T17

    with Session(db_engine) as s:
        urls = [d.url for d in s.scalars(select(RawDocument))]
        trades = s.scalars(select(RtmsTrade).order_by(RtmsTrade.deal_date)).all()
    assert all("serviceKey" not in u and "TEST" not in u for u in urls)  # 키는 DB 에 남기지 않는다
    assert all("LAWD_CD=" in u for u in urls)
    assert [(t.apt_name, t.cancelled, t.source) for t in trades] == [
        ("테스트아파트C", False, "openapi"),
        ("테스트아파트B", True, "openapi"),
        ("테스트아파트A", False, "openapi"),
    ]


def test_invalid_key_leaves_403_row(
    region_ctx: tuple[Region, Snapshot],
    fixtures_dir: Path,
    http: HttpClient,
    count: Callable[[type[Any]], int],
) -> None:
    region, snapshot = region_ctx
    with respx.mock(assert_all_called=False) as router:
        router.get("https://apis.data.go.kr/robots.txt").respond(400)
        router.get(RTMS_API_URL).respond(
            403,
            content=(fixtures_dir / "openapi_403_not_registered.xml").read_bytes(),
            headers={"content-type": "application/xml"},
        )
        docs = RtmsCollector(service_key="INVALID", http=http, months=1, presale=False).fetch(
            region, snapshot, None
        )
    assert [d.http_status for d in docs] == [403, 403]
    assert all(d.path is None and d.error_text == "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" for d in docs)
    assert count(RtmsTrade) == 0


class FakeReprocessed:
    """재가공 원천 인터페이스 구현 예(테스트용) — 실제 원천은 정하지 않았다(RA: 인터페이스만)."""

    name = "fake-reprocessed"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def fetch_month(self, lawd_cd: str, deal_ym: str) -> FetchResult:
        self.calls.append((lawd_cd, deal_ym))
        body = f"{lawd_cd},{deal_ym},재가공아파트,84.9,10,500000000,2026-10-01".encode()
        return FetchResult(
            url=f"https://reprocessed.example.test/{lawd_cd}/{deal_ym}",
            status=200,
            headers={"content-type": "text/csv"},
            content=body,
            error=None,
            elapsed_ms=1,
            attempts=1,
            fetched_at=datetime(2026, 10, 8, 0, 0, tzinfo=UTC),
        )

    def parse(self, content: bytes) -> list[TradeRecord]:
        _lawd, _ym, name, area, floor, price, day = content.decode().split(",")
        return [
            TradeRecord(
                apt_name=name,
                dong=None,
                legal_dong_code=None,
                completed_year=None,
                area_m2=Decimal(area),
                floor=int(floor),
                price_won=int(price),
                deal_date=day,
                cancelled=False,
            )
        ]


def test_no_key_with_reprocessed_fallback(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], count: Callable[[type[Any]], int]
) -> None:
    region, snapshot = region_ctx
    source = FakeReprocessed()
    collector = RtmsCollector(service_key=None, fallback=source, months=1)
    assert (collector.enabled, collector.mode, collector.disabled_reason) == (True, "reprocessed", None)
    docs = collector.fetch(region, snapshot, None)
    assert source.calls == [("28185", "202610"), ("41570", "202610")]
    assert len(docs) == 2
    assert {t.label for _, t in collector.trades} == {"재가공"}
    with Session(db_engine) as s:
        rows = s.scalars(select(RtmsTrade)).all()
    assert {r.source for r in rows} == {"reprocessed"} and len(rows) == 2
    RtmsCollector(service_key=None, fallback=FakeReprocessed(), months=1).fetch(region, snapshot, None)
    assert count(RtmsTrade) == 2


def test_load_trades_updates_cancellation_without_duplicates(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], fixtures_dir: Path
) -> None:
    region, _ = region_ctx
    items = parse_trade_xml((fixtures_dir / "openapi_trade_sample.xml").read_bytes()).items
    with Session(db_engine) as s:
        assert load_trades(s, region.id, [(None, t) for t in items]).inserted == 3
        # 다음 날 같은 월을 다시 받았더니 A 가 해제됨 → 행은 그대로, 해제 플래그만 갱신
        later = [replace(t, cancelled=True) if t.apt_name == "테스트아파트A" else t for t in items]
        stats = load_trades(s, region.id, [(None, t) for t in later])
        assert (stats.inserted, stats.updated, stats.unchanged) == (0, 1, 2)
        s.commit()
        rows = {r.apt_name: r.cancelled for r in s.scalars(select(RtmsTrade))}
    assert rows == {"테스트아파트A": True, "테스트아파트B": True, "테스트아파트C": False}


REAL = "openapi_trade_28185_202609.xml"  # 2026-10-09 실제 응답 녹화(연수구 28185, 202609, numOfRows 1000)


def test_parse_recorded_real_response(fixtures_dir: Path) -> None:
    """실제 녹화(합성 아님): 333건, 해제 2건 보존, 키는 녹화본에 없다(키는 쿼리로만 가고 응답에 안 나온다)."""
    content = (fixtures_dir / REAL).read_bytes()
    assert b"serviceKey" not in content
    page = parse_trade_xml(content)
    assert page.ok and page.total_count == 333 and len(page.items) == 333 and page.skipped == 0
    assert sum(t.cancelled for t in page.items) == 2
    assert all(t.source == "openapi" and t.label == "확인됨" for t in page.items)
    assert all(t.deal_date.startswith("2026-09-") and t.price_won > 0 for t in page.items)
    # 실제 응답에는 umdCd 가 없다(sggCd·umdNm 만) → 법정동 코드는 비우고 동 이름은 남긴다
    assert all(t.dong for t in page.items)


def test_openapi_path_with_real_recording(
    db_engine: Engine,
    region_ctx: tuple[Region, Snapshot],
    fixtures_dir: Path,
    http: HttpClient,
    count: Callable[[type[Any]], int],
) -> None:
    """source=openapi 경로를 실제 녹화로: 연수구 202609 → rtms_trade 333행(해제 2 포함), 재실행 증가 0."""
    region, snapshot = region_ctx
    snap = snapshot.model_copy(update={"asof_date": "2026-09-30"})
    body = (fixtures_dir / REAL).read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["LAWD_CD"] == "28185":
            return httpx.Response(
                200, content=body, headers={"content-type": "application/xml;charset=utf-8"}
            )
        return httpx.Response(
            200,
            content=(fixtures_dir / "openapi_trade_empty.xml").read_bytes(),
            headers={"content-type": "application/xml"},
        )

    with respx.mock(assert_all_called=False) as router:
        route = router.get(RTMS_API_URL).mock(side_effect=handler)
        collector = RtmsCollector(service_key=FAKE_KEY, http=http, months=1, presale=False)
        assert collector.mode == "openapi"
        docs = collector.fetch(region, snap, None)
        assert route.call_count == 2 and len(docs) == 2
        assert collector.load_stats is not None and collector.load_stats.inserted == 333
        RtmsCollector(service_key=FAKE_KEY, http=http, months=1, presale=False).fetch(region, snap, None)
    assert count(RtmsTrade) == 333
    with Session(db_engine) as s:
        rows = s.scalars(select(RtmsTrade)).all()
        urls = [d.url for d in s.scalars(select(RawDocument))]
    assert {r.source for r in rows} == {"openapi"} and sum(r.cancelled for r in rows) == 2
    assert all("serviceKey" not in u for u in urls)


def _live_key(name: str) -> str | None:
    """실제 키: ``ENV_FILE``(worktree 에서는 메인 체크아웃의 .env)을 읽은 설정 → 없으면 환경변수."""
    from app.core.settings import load_settings

    secret = getattr(load_settings(), name.lower())
    value = secret.get_secret_value() if secret is not None else None
    return value or os.environ.get(name)


@pytest.mark.live
def test_live_openapi_with_real_key(region_ctx: tuple[Region, Snapshot]) -> None:
    """실제 키로 연수구(28185) 2026-09 1회.

    실행: ``ENV_FILE=<메인 체크아웃>/.env uv run pytest -m live tests/collectors/rtms``
    """
    key = _live_key("DATA_GO_KR_KEY")
    if not key:
        pytest.skip("DATA_GO_KR_KEY 없음 (ENV_FILE 로 .env 경로를 준다)")
    region, snapshot = region_ctx
    yeonsu = region.model_copy(update={"sigungu_codes": ["28185"]})
    snap = snapshot.model_copy(update={"asof_date": "2026-09-30"})
    c = RtmsCollector(service_key=key, months=1, presale=False)
    docs = c.fetch(yeonsu, snap, None)
    assert docs and all(d.http_status == 200 for d in docs), [(d.http_status, d.error_text) for d in docs]
    assert c.pages and all(p.result_code in {"00", "000"} for p in c.pages)
    assert len(c.trades) >= 100  # 녹화 시점 333건 — 신고가 늘어도 줄지 않는다(해제는 플래그로 남음)
    assert all(key not in (d.url or "") for d in docs)

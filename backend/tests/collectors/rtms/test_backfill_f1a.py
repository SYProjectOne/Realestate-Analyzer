"""R3 C1: 벤치마크용 과거 월 실거래 채우기 — ``RtmsCollector.backfill``.

기준월 − (N−1) ~ 기준월 중 아직 성공 원문이 없는 (시군구, 월)만 받는다(입주 후 실거래·고점의 원천). 멱등.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import respx

from app.collectors.rtms import RTMS_API_URL, RtmsCollector
from app.core.contracts_gen import Region, Snapshot
from app.core.http import HttpClient
from app.models import RawDocument, RtmsTrade

FAKE_KEY = "TEST%2BKEY%3D%3D"


def _handler(fixtures_dir: Path) -> Callable[[httpx.Request], httpx.Response]:
    body = (fixtures_dir / "openapi_trade_sample.xml").read_bytes()
    empty = (fixtures_dir / "openapi_trade_empty.xml").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.params
        # 실제 응답은 시군구·월마다 내용이 다르다(같은 sha 면 원문 1행) — 표시만 달리한다
        tag = f"<resultMsg>OK</resultMsg><!-- {p['LAWD_CD']} {p['DEAL_YMD']} -->".encode()
        content = body if p["DEAL_YMD"] == "202609" else empty
        return httpx.Response(200, content=content.replace(b"<resultMsg>OK</resultMsg>", tag))

    return handler


def test_backfill_fetches_only_missing_months(
    region_ctx: tuple[Region, Snapshot],
    fixtures_dir: Path,
    http: HttpClient,
    count: Callable[[type[Any]], int],
) -> None:
    region, snapshot = region_ctx  # 기준일 2026-10-08, 시군구 2개
    with respx.mock(assert_all_called=False) as router:
        router.get("https://apis.data.go.kr/robots.txt").respond(400)
        route = router.get(RTMS_API_URL).mock(side_effect=_handler(fixtures_dir))
        # 평소 수집(최근 1개월)이 먼저 돌았다
        RtmsCollector(service_key=FAKE_KEY, http=http, months=1).fetch(region, snapshot, None)
        assert route.call_count == 2
        col = RtmsCollector(service_key=FAKE_KEY, http=http, months=1)
        docs = col.backfill(region, snapshot, months=3)
        months = sorted(
            {(c.request.url.params["LAWD_CD"], c.request.url.params["DEAL_YMD"]) for c in route.calls[2:]}
        )
        assert months == [("28185", "202608"), ("28185", "202609"), ("41570", "202608"), ("41570", "202609")]
        assert len(docs) == 4
        assert col.load_stats is not None and col.load_stats.inserted > 0
        n_raw, n_trade = count(RawDocument), count(RtmsTrade)

        again = RtmsCollector(service_key=FAKE_KEY, http=http, months=1).backfill(region, snapshot, months=3)
        assert again == [] and route.call_count == 6  # 채울 달 없음
        assert (count(RawDocument), count(RtmsTrade)) == (n_raw, n_trade)


def test_backfill_disabled_without_key(region_ctx: tuple[Region, Snapshot]) -> None:
    region, snapshot = region_ctx
    assert RtmsCollector(service_key=None).backfill(region, snapshot, months=36) == []

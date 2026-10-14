"""R9-PARSE Q12(20-gap §2-2, D28-5): 실거래 수집기는 공공데이터포털 Open API(apis.data.go.kr)만 쓴다.

국토부 실거래가 공개시스템(rt.molit.go.kr)은 이용 조건이 자동 수집을 금지한다(collector 모듈 설명·10-molit 노트). 수집기가 그 호스트
페이지를 요청하지 않음을 **요청 기록**으로 고정한다: 모든 HTTP 요청을 잡아 호스트를 모으고, 매매·분양권 API·과거 월 채우기
(backfill) 경로 어디에서도 ``apis.data.go.kr`` 밖으로 나가지 않는지 본다. 코드에 rt.molit.go.kr 주소가 URL 로 들어가지 않는지도 본다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import respx

from app.collectors import rtms as rtms_pkg
from app.collectors.rtms import PRESALE_API_URL, RTMS_API_URL, RtmsCollector
from app.core.contracts_gen import Region, Snapshot
from app.core.http import HttpClient

FAKE_KEY = "TEST%2BKEY%3D%3D"
ALLOWED = {"apis.data.go.kr"}
FORBIDDEN_RE = re.compile(r"(?:^|\.)molit\.go\.kr$")


def _record_all(fixtures_dir: Path, seen: list[str]) -> respx.MockRouter:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        host = request.url.host
        if host == "apis.data.go.kr" and request.url.path == "/robots.txt":
            return httpx.Response(400)
        if host == "apis.data.go.kr":
            return httpx.Response(
                200,
                content=(fixtures_dir / "openapi_trade_empty.xml").read_bytes(),
                headers={"content-type": "application/xml"},
            )
        return httpx.Response(599)  # 다른 호스트로 가면 기록만 하고 실패 응답(아래 단언이 잡는다)

    router = respx.mock(assert_all_called=False, assert_all_mocked=True)
    router.route().mock(side_effect=handler)
    return router


def test_api_endpoints_are_data_go_kr() -> None:
    for url in (RTMS_API_URL, PRESALE_API_URL):
        assert urlsplit(url).hostname in ALLOWED, url


def test_fetch_and_backfill_never_leave_open_api_host(
    region_ctx: tuple[Region, Snapshot], fixtures_dir: Path, http: HttpClient
) -> None:
    region, snapshot = region_ctx
    seen: list[str] = []
    with _record_all(fixtures_dir, seen):
        collector = RtmsCollector(service_key=FAKE_KEY, http=http, months=2, presale=True)
        collector.fetch(region, snapshot, None)
        RtmsCollector(service_key=FAKE_KEY, http=http, presale=True).backfill(region, snapshot, months=3)
    hosts = {urlsplit(u).hostname for u in seen}
    assert seen, "요청이 하나도 없다 — 시험이 수집 경로를 타지 않았다"
    assert hosts <= ALLOWED, f"Open API 밖 호스트 요청: {sorted(h or '' for h in hosts - ALLOWED)}"
    assert not any(FORBIDDEN_RE.search(h or "") for h in hosts)


def test_no_rt_molit_url_in_collector_code() -> None:
    """rt.molit.go.kr 은 모듈 설명(왜 쓰지 않는가)에만 나온다 — 'http(s)://…molit…' URL 리터럴이 없다."""
    pkg = Path(rtms_pkg.__file__).parent
    hits = [
        f"{p.name}:{n}"
        for p in sorted(pkg.glob("*.py"))
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r"https?://[^\s\"']*rt\.molit\.go\.kr", line)
    ]
    assert hits == []

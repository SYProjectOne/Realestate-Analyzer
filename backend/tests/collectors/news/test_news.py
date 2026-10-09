"""news: 키 없으면 비활성(빈 결과 + '비활성(키 없음)'), 키가 있으면 URL·제목·발췌만.

제공자: ncp(NAVER Cloud API HUB, 기본) / naver_developers(레거시 개발자센터).
``ncp_news_20261009.json`` = 2026-10-09 실제 API HUB 응답 녹화(질의 '연수구 분양', display 5; 키는 헤더로만
가므로 본문에 없음). ``naver_news_sample.json`` = 레거시 형식 합성 픽스처.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import respx
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.collectors.news import (
    DISABLED_NO_KEY,
    NAVER_NEWS_URL,
    NCP_NEWS_URL,
    NewsCollector,
    parse_credentials,
    parse_news_json,
)
from app.core.contracts_gen import Region, Snapshot
from app.core.http import HttpClient
from app.core.settings import load_settings
from app.models import RawDocument

KEY = "test-client-id:test-client-secret"  # 가짜


def test_no_key_is_disabled_and_returns_nothing(
    region_ctx: tuple[Region, Snapshot], count: Callable[[type[Any]], int]
) -> None:
    region, snapshot = region_ctx
    collector = NewsCollector()  # test_settings: NEWS_API_KEY 없음
    assert (collector.enabled, collector.disabled_reason) == (False, DISABLED_NO_KEY)
    assert DISABLED_NO_KEY == "비활성(키 없음)"
    with respx.mock(assert_all_called=False) as router:
        assert collector.fetch(region, snapshot, None) == []
        assert router.calls.call_count == 0
    assert collector.items == []
    assert count(RawDocument) == 0


def test_malformed_key_is_disabled_too() -> None:
    collector = NewsCollector(api_key="only-one-part")
    assert not collector.enabled
    assert collector.disabled_reason is not None and "키 형식" in collector.disabled_reason
    assert parse_credentials(KEY) == ("test-client-id", "test-client-secret")
    assert parse_credentials(None) is None


def test_parse_keeps_url_title_excerpt_only(fixtures_dir: Path) -> None:
    items = parse_news_json((fixtures_dir / "naver_news_sample.json").read_bytes(), raw_document_id=7)
    assert [(i.title, i.url) for i in items] == [
        ('테스트 지역 분양 단지 선착순 계약 "진행"', "https://news.example.test/article/1"),
        ("링크만 있는 기사", "https://n.news.example.test/mnews/article/2"),
    ]
    assert items[0].excerpt == "테스트 지역 분양 단지가 잔여 세대 선착순 계약을 진행한다고 밝혔다."
    assert items[0].raw_document_id == 7
    assert parse_news_json(b"{}") == [] and parse_news_json(b"not json") == []


def test_with_key_collects_and_is_idempotent(
    db_engine: Engine,
    region_ctx: tuple[Region, Snapshot],
    fixtures_dir: Path,
    http: HttpClient,
    count: Callable[[type[Any]], int],
) -> None:
    region, snapshot = region_ctx
    with respx.mock(assert_all_called=False) as router:
        router.get("https://openapi.naver.com/robots.txt").respond(404)
        route = router.get(NAVER_NEWS_URL).respond(
            200,
            content=(fixtures_dir / "naver_news_sample.json").read_bytes(),
            headers={"content-type": "application/json"},
        )
        collector = NewsCollector(api_key=KEY, provider="naver_developers", http=http)
        docs = collector.fetch(region, snapshot, None)
        req = route.calls[0].request
        assert req.headers["X-Naver-Client-Id"] == "test-client-id"
        assert req.url.params["query"] == "테스트 지역 분양"  # 지역명은 region 행에서
        assert len(docs) == 1 and len(collector.items) == 2
        n = count(RawDocument)
        NewsCollector(api_key=KEY, provider="naver_developers", http=http).fetch(region, snapshot, None)
        assert count(RawDocument) == n
    with Session(db_engine) as s:
        doc = s.scalars(select(RawDocument)).one()
    assert doc.source_kind == "news" and "secret" not in doc.url and "test-client" not in doc.url


def test_with_key_robots_exempt_api_is_called(
    db_engine: Engine,
    region_ctx: tuple[Region, Snapshot],
    fixtures_dir: Path,
    http: HttpClient,
) -> None:
    """openapi.naver.com/robots.txt 실제 녹화(Disallow: /)여도 키 인증 API 는 robots 예외
    (HTTP_ROBOTS_EXEMPT_HOSTS, 계약 2026-10-09.2) — robots.txt 를 받지 않고 API 를 부른다."""
    region, snapshot = region_ctx
    robots = (fixtures_dir / "naver_openapi_robots.txt").read_bytes()
    assert b"Disallow: /" in robots
    with respx.mock(assert_all_called=False) as router:
        robots_route = router.get("https://openapi.naver.com/robots.txt").respond(200, content=robots)
        api = router.get(NAVER_NEWS_URL).respond(200, json={"items": []})
        docs = NewsCollector(api_key=KEY, provider="naver_developers", http=http).fetch(
            region, snapshot, None
        )
        assert api.call_count == 1 and robots_route.call_count == 0
    assert [(d.http_status, d.error_text) for d in docs] == [(200, None)]


def test_with_key_but_robots_disallow_leaves_failure_row(
    db_engine: Engine,
    region_ctx: tuple[Region, Snapshot],
    fixtures_dir: Path,
) -> None:
    """robots 예외를 끄면(빈 목록) core.http 가 막고, 실패 행이 남는다."""
    region, snapshot = region_ctx
    robots = (fixtures_dir / "naver_openapi_robots.txt").read_bytes()
    with (
        respx.mock(assert_all_called=False) as router,
        HttpClient(sleep=lambda _s: None, max_retries=0, jitter=0, robots_exempt_hosts=()) as strict,
    ):
        router.get("https://openapi.naver.com/robots.txt").respond(200, content=robots)
        api = router.get(NAVER_NEWS_URL).respond(200, json={"items": []})
        docs = NewsCollector(api_key=KEY, provider="naver_developers", http=strict).fetch(
            region, snapshot, None
        )
        assert api.call_count == 0
    assert [(d.http_status, d.error_text, d.path) for d in docs] == [(None, "robots", None)]


def test_default_provider_is_ncp_api_hub() -> None:
    c = NewsCollector(api_key=KEY)  # test_settings: NEWS_API_PROVIDER 기본값
    assert c.provider.name == "ncp" and c.provider.url == NCP_NEWS_URL
    assert NCP_NEWS_URL == "https://naverapihub.apigw.ntruss.com/search/v1/news"
    assert NewsCollector(api_key=KEY, provider="naver_developers").provider.url == NAVER_NEWS_URL


def test_parse_recorded_ncp_response(fixtures_dir: Path) -> None:
    """API HUB 실제 응답(녹화) — 필드가 개발자센터 형식과 같아 같은 파서로 읽힌다."""
    content = (fixtures_dir / "ncp_news_20261009.json").read_bytes()
    items = parse_news_json(content, raw_document_id=3)
    assert len(items) == 5
    assert all(i.url.startswith("http") and i.title and "<b>" not in i.title for i in items)
    assert all(i.published_at and i.published_at.endswith("+0900") for i in items)
    assert all("<b>" not in i.excerpt and len(i.excerpt) <= 300 for i in items)


def test_ncp_provider_headers_url_and_idempotent(
    db_engine: Engine,
    region_ctx: tuple[Region, Snapshot],
    fixtures_dir: Path,
    http: HttpClient,
    count: Callable[[type[Any]], int],
) -> None:
    """ncp: API HUB 호스트·NCP 헤더로 부르고(robots.txt 요청 없음 — 예외 호스트), 녹화 응답을 저장·파싱."""
    region, snapshot = region_ctx
    body = (fixtures_dir / "ncp_news_20261009.json").read_bytes()
    with respx.mock(assert_all_called=False) as router:
        robots = router.get("https://naverapihub.apigw.ntruss.com/robots.txt").respond(404)
        route = router.get(NCP_NEWS_URL).respond(
            200, content=body, headers={"content-type": "text/plain;charset=UTF-8"}
        )
        collector = NewsCollector(api_key=KEY, provider="ncp", http=http)
        docs = collector.fetch(region, snapshot, None)
        req = route.calls[0].request
        assert req.headers["X-NCP-APIGW-API-KEY-ID"] == "test-client-id"
        assert req.headers["X-NCP-APIGW-API-KEY"] == "test-client-secret"
        assert "X-Naver-Client-Id" not in req.headers
        assert req.url.params["sort"] == "date" and req.url.params["query"] == "테스트 지역 분양"
        assert robots.call_count == 0
        assert [(d.http_status, d.source_kind) for d in docs] == [(200, "news")] and len(collector.items) == 5
        n = count(RawDocument)
        NewsCollector(api_key=KEY, provider="ncp", http=http).fetch(region, snapshot, None)
        assert count(RawDocument) == n
    with Session(db_engine) as s:
        doc = s.scalars(select(RawDocument)).one()
    assert doc.url.startswith(NCP_NEWS_URL) and "test-client" not in doc.url


def test_ncp_wrong_path_404_is_failure_row(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], http: HttpClient
) -> None:
    """키·경로가 틀리면(예: naveropenapi.apigw.ntruss.com/search/v1/news → 404) 실패 행, 예외 없음."""
    region, snapshot = region_ctx
    with respx.mock(assert_all_called=False) as router:
        router.get(NCP_NEWS_URL).respond(
            401, json={"error": {"errorCode": "200", "message": "Authentication Failed"}}
        )
        docs = NewsCollector(api_key=KEY, provider="ncp", http=http).fetch(region, snapshot, None)
    assert [(d.http_status, d.path) for d in docs] == [(401, None)]


@pytest.mark.live
def test_live_news_with_real_key(region_ctx: tuple[Region, Snapshot]) -> None:
    """실제 키(ENV_FILE 또는 환경의 NEWS_API_KEY·NEWS_API_PROVIDER)로 1회 호출.

    실행: ``ENV_FILE=<메인 체크아웃>/.env uv run pytest -m live tests/collectors/news``
    """
    live = load_settings()
    key = live.news_api_key.get_secret_value() if live.news_api_key else os.environ.get("NEWS_API_KEY")
    if not key:
        pytest.skip("NEWS_API_KEY 없음 (ENV_FILE 로 .env 경로를 준다)")
    region, snapshot = region_ctx
    collector = NewsCollector(api_key=key, provider=live.news_api_provider)
    docs = collector.fetch(region, snapshot, None)
    assert [d.http_status for d in docs] == [200], [(d.http_status, d.error_text) for d in docs]
    assert collector.items and all(i.url.startswith("http") for i in collector.items)
    secret = key.split(":", 1)
    assert all(part not in (d.url or "") for d in docs for part in secret)

"""news: 키 없으면 비활성(빈 결과 + '비활성(키 없음)'), 키가 있으면 URL·제목·발췌만."""

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
    NewsCollector,
    parse_credentials,
    parse_news_json,
)
from app.core.contracts_gen import Region, Snapshot
from app.core.http import HttpClient
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
        collector = NewsCollector(api_key=KEY, http=http)
        docs = collector.fetch(region, snapshot, None)
        req = route.calls[0].request
        assert req.headers["X-Naver-Client-Id"] == "test-client-id"
        assert req.url.params["query"] == "테스트 지역 분양"  # 지역명은 region 행에서
        assert len(docs) == 1 and len(collector.items) == 2
        n = count(RawDocument)
        NewsCollector(api_key=KEY, http=http).fetch(region, snapshot, None)
        assert count(RawDocument) == n
    with Session(db_engine) as s:
        doc = s.scalars(select(RawDocument)).one()
    assert doc.source_kind == "news" and "secret" not in doc.url and "test-client" not in doc.url


def test_with_key_but_robots_disallow_leaves_failure_row(
    db_engine: Engine,
    region_ctx: tuple[Region, Snapshot],
    fixtures_dir: Path,
    http: HttpClient,
) -> None:
    """openapi.naver.com/robots.txt 실제 녹화(Disallow: /) — core.http 가 막고, 실패 행이 남는다."""
    region, snapshot = region_ctx
    robots = (fixtures_dir / "naver_openapi_robots.txt").read_bytes()
    assert b"Disallow: /" in robots
    with respx.mock(assert_all_called=False) as router:
        router.get("https://openapi.naver.com/robots.txt").respond(200, content=robots)
        api = router.get(NAVER_NEWS_URL).respond(200, json={"items": []})
        docs = NewsCollector(api_key=KEY, http=http).fetch(region, snapshot, None)
        assert api.call_count == 0
    assert [(d.http_status, d.error_text, d.path) for d in docs] == [(None, "robots", None)]


@pytest.mark.live
def test_live_news_with_real_key(region_ctx: tuple[Region, Snapshot]) -> None:
    """NEWS_API_KEY 가 환경에 있을 때만(지금은 키 없음 — D1 #6)."""
    key = os.environ.get("NEWS_API_KEY")
    if not key:
        pytest.skip("NEWS_API_KEY 없음")
    region, snapshot = region_ctx
    NewsCollector(api_key=key).fetch(region, snapshot, None)

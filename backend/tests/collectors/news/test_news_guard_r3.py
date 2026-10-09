"""R3 M10: 뉴스 질의어도 guard(판정기 payload 와 같은 공용 필터)를 통과해야 보낸다.

거부 시 요청 없음 + 실패 행."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import respx
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.collectors.news import NAVER_NEWS_URL, NewsCollector
from app.collectors.news.collector import GUARD_FAILURE
from app.core.contracts_gen import Region, Snapshot
from app.core.http import HttpClient
from app.models import RawDocument

KEY = "test-client-id:test-client-secret"  # 가짜


def test_m10_sensitive_query_is_not_sent_and_leaves_failure_row(
    db_engine: Engine,
    region_ctx: tuple[Region, Snapshot],
    http: HttpClient,
    count: Callable[[type[Any]], int],
) -> None:
    region, snapshot = region_ctx
    queries = ["홍길동 010-1234-5678 분양", "테스트 지역 분양"]
    with respx.mock(assert_all_called=False) as router:
        route = router.get(NAVER_NEWS_URL).respond(200, json={"items": []})
        collector = NewsCollector(
            api_key=KEY, provider="naver_developers", http=http, queries=queries, secrets=[]
        )
        docs = collector.fetch(region, snapshot, None)
        sent = [c.request.url.params["query"] for c in route.calls]
    assert sent == ["테스트 지역 분양"]  # 걸린 질의는 보내지 않았다
    assert collector.blocked_queries == 1
    failed = [d for d in docs if d.http_status is None]
    assert len(failed) == 1 and (failed[0].error_text or "").startswith(f"{GUARD_FAILURE}: phone")
    with Session(db_engine) as s:
        urls = [r.url for r in s.scalars(select(RawDocument))]
    assert all("010" not in u and "1234-5678" not in u for u in urls)
    assert any("REDACTED" in u for u in urls)
    assert count(RawDocument) == 2


def test_m10_secret_in_query_is_blocked_too(region_ctx: tuple[Region, Snapshot], http: HttpClient) -> None:
    region, snapshot = region_ctx
    with respx.mock(assert_all_called=False) as router:
        route = router.get(NAVER_NEWS_URL).respond(200, json={"items": []})
        collector = NewsCollector(
            api_key=KEY, provider="naver_developers", http=http, queries=["분양 SeCrEt-Token-99"],
            secrets=["SeCrEt-Token-99"],
        )  # fmt: skip
        docs = collector.fetch(region, snapshot, None)
        assert route.call_count == 0
    assert [d.error_text for d in docs] == [f"{GUARD_FAILURE}: secret"]

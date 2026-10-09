"""R3b F1a (news): NCP 키(``ID:Secret``)는 헤더로만 간다 — 응답 본문·오류 문구가 키를 되돌려 줘도 원문 행·저장
본문에 원문·퍼센트 인코딩(quote·quote_plus) 어느 형태로도 남지 않는다."""

from __future__ import annotations

import json
from urllib.parse import quote, quote_plus

import httpx
import respx
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.collectors.news import NCP_NEWS_URL, NewsCollector
from app.core.contracts_gen import Region, Snapshot
from app.core.http import HttpClient
from app.core.paths import resolve_raw_path
from app.models import RawDocument

CID, SECRET = "ncp-test-id-0001", "s3cr+t/value=="
KEY = f"{CID}:{SECRET}"
FORMS = {s for v in (CID, SECRET) for s in (v, quote(v, safe=""), quote(v), quote_plus(v))}


def _leaks(text: str | None) -> list[str]:
    return sorted(f for f in FORMS if text and f in text)


def test_echoed_credentials_are_masked(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], http: HttpClient
) -> None:
    region, snapshot = region_ctx

    def handler(request: httpx.Request) -> httpx.Response:
        q = request.url.params["query"]
        echo = f"id={request.headers['X-NCP-APIGW-API-KEY-ID']} key={quote_plus(SECRET)} raw={SECRET}"
        if q.endswith("오류"):
            return httpx.Response(401, json={"error": {"errorCode": "200", "message": echo}})
        if q.endswith("끊김"):
            raise httpx.ConnectError(f"refused {echo}", request=request)
        item = {"title": "기사", "originallink": "https://news.example.test/1", "description": echo}
        return httpx.Response(200, content=json.dumps({"items": [item]}).encode())

    with respx.mock(assert_all_called=False) as router:
        router.get(NCP_NEWS_URL).mock(side_effect=handler)
        col = NewsCollector(
            api_key=KEY,
            provider="ncp",
            http=http,
            queries=["테스트 분양", "테스트 오류", "테스트 끊김"],
            secrets=[],
        )
        docs = col.fetch(region, snapshot, None)
    assert [d.http_status for d in docs] == [200, 401, None]
    for it in col.items:
        assert _leaks(it.excerpt) == [] and _leaks(it.title) == []
    with Session(db_engine) as s:
        rows = list(s.scalars(select(RawDocument)))
    for row in rows:
        assert _leaks(row.url) == [] and _leaks(row.error_text) == []
        if row.path:
            assert _leaks(resolve_raw_path(row.path).read_bytes().decode("utf-8")) == []

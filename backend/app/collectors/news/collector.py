"""뉴스 수집기 — 네이버 검색 API(뉴스) 형식 (source_kind='news', DECISIONS D1 #6).

- ``NEWS_API_KEY`` 가 없으면 비활성: ``enabled=False``, ``disabled_reason='비활성(키 없음)'``, fetch 는
  네트워크 없이 [].
  호재는 사람이 URL 로 입력할 수 있다(D1 #6).
- 키 형식: ``<Client ID>:<Client Secret>`` (네이버는 두 값을 헤더 X-Naver-Client-Id / X-Naver-Client-Secret
  로 받는다).
- 요청: ``GET https://openapi.naver.com/v1/search/news.json?query=…&display=…&start=1&sort=date``.
- 남기는 것: 응답 JSON 원문(raw_document) + ``items`` = URL·제목·발췌(+게시일)만. 본문 기사는 받지 않는다.
- openapi.naver.com/robots.txt 는 ``Disallow: /`` 이지만 키 인증 API 라 core.http 의 robots 예외
  (``HTTP_ROBOTS_EXEMPT_HOSTS``, 계약 2026-10-09.2)다. 예외 목록에서 빼면 실패 행
  (error_text='robots')만 남는다.
- 질의어: ``queries`` 를 주면 그것, 아니면 ``"<region.name> 분양"`` 1개(지역명은 region 행에서 온다).
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from app.collectors.reference.rawstore import RawStore, fetch_failure
from app.core.contracts_gen import RawDocument, Region, Snapshot
from app.core.db import get_session
from app.core.http import HttpClient
from app.core.settings import get_settings

__all__ = [
    "DISABLED_NO_KEY",
    "NAVER_NEWS_URL",
    "NewsCollector",
    "NewsItem",
    "parse_credentials",
    "parse_news_json",
]

NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"
DISABLED_NO_KEY = "비활성(키 없음)"
SessionFactory = Callable[[], AbstractContextManager[Session]]
_TAG_RE = re.compile(r"<[^>]+>")
_UNSET = object()


@dataclass(frozen=True, slots=True)
class NewsItem:
    title: str
    url: str
    excerpt: str
    published_at: str | None
    raw_document_id: int | None = None


def _clean(text: str) -> str:
    return " ".join(html.unescape(_TAG_RE.sub("", text)).split())


def parse_credentials(key: str | None) -> tuple[str, str] | None:
    if not key or ":" not in key:
        return None
    cid, secret = key.split(":", 1)
    cid, secret = cid.strip(), secret.strip()
    return (cid, secret) if cid and secret else None


def parse_news_json(content: bytes, *, raw_document_id: int | None = None) -> list[NewsItem]:
    try:
        data = json.loads(content.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return []
    items = data.get("items") if isinstance(data, dict) else None
    out: list[NewsItem] = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        url = str(it.get("originallink") or it.get("link") or "").strip()
        title = _clean(str(it.get("title", "")))
        if not url or not title:
            continue
        out.append(
            NewsItem(
                title=title,
                url=url,
                excerpt=_clean(str(it.get("description", "")))[:300],
                published_at=str(it["pubDate"]) if it.get("pubDate") else None,
                raw_document_id=raw_document_id,
            )
        )
    return out


class NewsCollector:
    source_kind = "news"

    def __init__(
        self,
        *,
        api_key: str | object | None = _UNSET,
        http: HttpClient | None = None,
        queries: Sequence[str] | None = None,
        display: int = 20,
        session_factory: SessionFactory = get_session,
        raw_dir: Path | None = None,
    ) -> None:
        if api_key is _UNSET:
            secret = get_settings().news_api_key
            key = secret.get_secret_value() if secret is not None else None
        else:
            key = api_key if isinstance(api_key, str) else None
        self._credentials = parse_credentials(key)
        self._key_present = bool(key)
        self._http = http
        self._queries = list(queries) if queries is not None else None
        self._display = max(1, min(100, display))
        self._session_factory = session_factory
        self._raw_dir = raw_dir
        self.items: list[NewsItem] = []

    @property
    def enabled(self) -> bool:
        return self._credentials is not None

    @property
    def disabled_reason(self) -> str | None:
        if self.enabled:
            return None
        return DISABLED_NO_KEY if not self._key_present else "비활성(키 형식 오류: 'ID:Secret')"

    def queries_for(self, region: Region) -> list[str]:
        return self._queries if self._queries is not None else [f"{region.name} 분양"]

    def fetch(self, region: Region, snapshot: Snapshot, since: str | None) -> list[RawDocument]:
        self.items = []
        if self._credentials is None:
            return []
        cid, secret = self._credentials
        headers = {"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": secret}
        http = self._http or HttpClient()
        docs: list[RawDocument] = []
        try:
            with self._session_factory() as session:
                store = RawStore(session, raw_dir=self._raw_dir)
                for q in self.queries_for(region):
                    params = {"query": q, "display": str(self._display), "start": "1", "sort": "date"}
                    shown = f"{NAVER_NEWS_URL}?{urlencode(params)}"
                    r = http.get(NAVER_NEWS_URL, params=params, headers=headers)
                    if not r.ok:
                        docs.append(
                            store.save_result(
                                r,
                                source_kind="news",
                                ext="json",
                                url=shown,
                                region_id=region.id,
                                failure=fetch_failure(r),
                            )
                        )
                        continue
                    doc = store.save_result(
                        r,
                        source_kind="news",
                        ext="json",
                        url=shown,
                        content_type="application/json",
                        region_id=region.id,
                    )
                    docs.append(doc)
                    self.items.extend(parse_news_json(r.content, raw_document_id=doc.id))
        finally:
            if self._http is None:
                http.close()
        return docs

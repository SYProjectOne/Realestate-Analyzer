"""뉴스 수집기 — 네이버 검색(뉴스) API (source_kind='news', DECISIONS D1 #6).

제공자 (``NEWS_API_PROVIDER``, 기본 ``ncp``)
- ``ncp``: NAVER Cloud Platform **NAVER API HUB** "NAVER 검색"(개발자센터 검색 API 의 이관처).
  ``GET https://naverapihub.apigw.ntruss.com/search/v1/news?query=&display=(1~100)&start=(1~1000)&sort=sim|date``,
  헤더 ``X-NCP-APIGW-API-KEY-ID`` / ``X-NCP-APIGW-API-KEY`` (NCP 콘솔 API HUB Application 인증 정보).
  문서: api.ncloud-docs.com/docs/naver-api-hub-search-news (2026-10-09 확인, 실제 호출 200 확인).
  응답 필드는 개발자센터와 같다: lastBuildDate·total·start·display·items[title·originallink·link·description·
  pubDate]. 응답 content-type 이 ``text/plain`` 이어도 본문은 JSON 이다.
- ``naver_developers``(레거시): ``GET https://openapi.naver.com/v1/search/news.json``,
  헤더 ``X-Naver-Client-Id`` / ``X-Naver-Client-Secret``.

공통
- ``NEWS_API_KEY`` 가 없으면 비활성: ``enabled=False``, ``disabled_reason='비활성(키 없음)'``, fetch 는
  네트워크 없이 []. 호재는 사람이 URL 로 입력할 수 있다(D1 #6).
- 키 형식: ``<ID>:<Secret>`` (두 값을 위 헤더로 보낸다). 키는 헤더로만 가고 URL·원문 행에 남지 않는다.
  응답 본문·오류 문구가 키를 되돌려 줘도 원문·퍼센트 인코딩 형태 모두 가린 뒤 저장한다(R3b F1a,
  ``reference.rawstore.scrub_result``).
- 남기는 것: 응답 JSON 원문(raw_document) + ``items`` = URL·제목·발췌(+게시일)만. 본문 기사는 받지 않는다.
- 두 호스트 모두 키 인증 API 라 core.http 의 robots 예외(``HTTP_ROBOTS_EXEMPT_HOSTS``)다.
  openapi.naver.com/robots.txt 는 ``Disallow: /`` — 예외 목록에서 빼면 실패 행(error_text='robots')만 남는다.
- 질의어: ``queries`` 를 주면 그것, 아니면 ``"<region.name> 분양"`` 1개(지역명은 region 행에서 온다).
- 질의어도 외부로 나가는 값이다(RA §10 보안 1, R3 M10): 보내기 전에 판정기 payload 와 같은 공용 필터
  ``app.judge.guard.check_payload``(전화·주민번호·이메일·설정 비밀값·URL 키)를 통과해야 한다. 걸리면 요청하지
  않고 실패 행(error_text ``guard: <종류>``, URL 의 질의는 ``[REDACTED]``)만 남긴다 — 실패도 데이터.
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

from app.collectors.reference.rawstore import Failure, RawStore, fetch_failure, scrub_result
from app.core.contracts_gen import RawDocument, Region, Snapshot
from app.core.db import get_session
from app.core.http import HttpClient
from app.core.settings import NewsApiProvider, get_settings
from app.judge.guard import check_payload, default_secrets

__all__ = [
    "DISABLED_NO_KEY",
    "GUARD_FAILURE",
    "NAVER_NEWS_URL",
    "NCP_NEWS_URL",
    "PROVIDERS",
    "NewsCollector",
    "NewsItem",
    "Provider",
    "parse_credentials",
    "parse_news_json",
]

NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"  # 레거시 개발자센터
NCP_NEWS_URL = "https://naverapihub.apigw.ntruss.com/search/v1/news"  # NAVER Cloud API HUB


@dataclass(frozen=True, slots=True)
class Provider:
    name: NewsApiProvider
    url: str
    id_header: str
    secret_header: str


PROVIDERS: dict[str, Provider] = {
    "ncp": Provider("ncp", NCP_NEWS_URL, "X-NCP-APIGW-API-KEY-ID", "X-NCP-APIGW-API-KEY"),
    "naver_developers": Provider(
        "naver_developers", NAVER_NEWS_URL, "X-Naver-Client-Id", "X-Naver-Client-Secret"
    ),
}
DISABLED_NO_KEY = "비활성(키 없음)"
GUARD_FAILURE = "guard"
"""질의어가 guard 에 걸려 보내지 않은 실패 행의 error_text 머리."""
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
        provider: NewsApiProvider | None = None,
        http: HttpClient | None = None,
        queries: Sequence[str] | None = None,
        display: int = 20,
        session_factory: SessionFactory = get_session,
        raw_dir: Path | None = None,
        secrets: Sequence[str] | None = None,
    ) -> None:
        if api_key is _UNSET:
            secret = get_settings().news_api_key
            key = secret.get_secret_value() if secret is not None else None
        else:
            key = api_key if isinstance(api_key, str) else None
        self.provider = PROVIDERS[provider or get_settings().news_api_provider]
        self._credentials = parse_credentials(key)
        self._key_present = bool(key)
        self._http = http
        self._queries = list(queries) if queries is not None else None
        self._display = max(1, min(100, display))
        self._session_factory = session_factory
        self._raw_dir = raw_dir
        self._secrets = list(secrets) if secrets is not None else None
        self.items: list[NewsItem] = []
        self.blocked_queries = 0

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
        self.blocked_queries = 0
        if self._credentials is None:
            return []
        secrets = self._secrets if self._secrets is not None else default_secrets()
        cid, secret = self._credentials
        prov = self.provider
        headers = {prov.id_header: cid, prov.secret_header: secret}
        http = self._http or HttpClient()
        docs: list[RawDocument] = []
        try:
            with self._session_factory() as session:
                store = RawStore(session, raw_dir=self._raw_dir)
                for i, q in enumerate(self.queries_for(region)):
                    checked = check_payload({"query": q}, secrets=secrets)
                    if not checked.ok:
                        self.blocked_queries += 1
                        docs.append(
                            store.save_failure(
                                source_kind="news",
                                url=f"{prov.url}?query=[REDACTED]&q={i}",
                                failure=Failure(None, GUARD_FAILURE),
                                region_id=region.id,
                                detail=",".join(checked.kinds()),
                            )
                        )
                        continue
                    params = {"query": q, "display": str(self._display), "start": "1", "sort": "date"}
                    shown = f"{prov.url}?{urlencode(params)}"
                    r = scrub_result(
                        http.get(prov.url, params=params, headers=headers), (cid, secret), url=shown
                    )
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

"""실거래 수집기 (source_kind='rtms', DECISIONS D1 #5).

경로
1. ``DATA_GO_KR_KEY`` 가 있으면 국토부 Open API(``openapi``, 라벨 확인됨): region.sigungu_codes × 월 × 페이지.
2. 키가 없고 ``fallback``(재가공 원천)이 주어지면 그것으로(``reprocessed``, 라벨 재가공). **인터페이스만**
  있다(RA).
3. 둘 다 없으면 비활성: ``enabled=False``, ``disabled_reason='비활성(키 없음)'``, 네트워크 호출 0.

키 없는 공식 경로 조사(2026-10-09): 국토부 실거래가 공개시스템(rt.molit.go.kr)의 '자료제공'은 시군구·기간별
CSV 를
키 없이 내려받게 해 주지만, 같은 사이트 공개안내의 이용 제한이 "기술적 수단(스크래핑·크롤러 등 자동화
수단)으로
콘텐츠에 접근하거나 자료를 수집하는 행위"를 금지하고 공공데이터포털 API 이용을 안내한다. robots.txt 는
없음(404).
그래서 ``official_web`` 경로는 구현하지 않는다.

저장: 페이지 응답 XML 1개 = raw_document 1행(URL 에 serviceKey 없음). 파싱한 거래는 ``trades`` 에 모으고
``load=True`` 면 ``rtms_trade`` 에 적재한다(같은 raw_document 는 한 번만 — 멱등).

분양권 전매(R3b F1a): Open API 경로에서는 같은 키·같은 LAWD_CD/DEAL_YMD 로 ``PRESALE_API_URL``
(국토교통부_아파트 분양권전매 실거래가 자료, ``RTMSDataSvcSilvTrade``)도 받는다(``presale=True`` 기본). 같은
raw_document 흐름(source_kind 'rtms')이고 URL 경로로 구별한다. 그 거래는 ``is_presale=True`` 로 적재한다
(분양권·입주권 모두 — 입주 전 권리 거래, 매매 갭·벤치마크 점수에서 빠진다). 키가 이 서비스에 활용신청되지
않았으면(401·403·포털 오류 코드) 실패 행 1개만 남기고 그 실행의 나머지 분양권 호출은 하지 않는다
(``presale_disabled_reason``). 매매 수집은 영향 없다.

키 마스킹(R3b F1a): 응답은 ``reference.rawstore.scrub_result`` 로 오류 문구·본문에서 키(원문·인코딩 형태)를
가린 뒤 저장·파싱한다(포털 오류 문구가 키를 되돌려 주면 error_text 상세로 DB 에 남던 경로).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote, urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.reference.load import LoadStats
from app.collectors.reference.rawstore import RawStore, fetch_failure, scrub_result
from app.collectors.rtms.parse import TradeRecord, api_error_message, parse_trade_xml
from app.core.contracts_gen import RawDocument, Region, Snapshot
from app.core.db import get_session
from app.core.http import FetchResult, HttpClient
from app.core.settings import get_settings
from app.models import RawDocument as RtmsRaw
from app.models import RtmsTrade

__all__ = [
    "DISABLED_NO_KEY",
    "PRESALE_API_URL",
    "RTMS_API_URL",
    "ReprocessedTradeSource",
    "RtmsCollector",
    "load_trades",
    "month_range",
]

RTMS_API_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"
PRESALE_API_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcSilvTrade/getRTMSDataSvcSilvTrade"
_AUTH_STATUSES = frozenset({401, 403})
# 포털 공통 오류 returnReasonCode: 20 접근 거부·22 한도 초과·30 미등록 키·31 기한 만료·32 미등록 IP
_AUTH_CODES = frozenset({"20", "22", "30", "31", "32"})
DISABLED_NO_KEY = "비활성(키 없음)"
SessionFactory = Callable[[], AbstractContextManager[Session]]
_UNSET = object()


class ReprocessedTradeSource(Protocol):
    """재가공 실거래 원천(키가 없을 때 폴백) — RA: 인터페이스만. 구현체는 사람이 고른 원천에 맞춰 만든다.

    - ``fetch_month``: 시군구(5자리)·월(YYYYMM) 원문을 core.http 로 받아 FetchResult 로 돌려준다.
    - ``parse``: 원문 → TradeRecord(source='reprocessed', label='재가공'). 해제 거래는 cancelled=True 로 보존.
    """

    name: str

    def fetch_month(self, lawd_cd: str, deal_ym: str) -> FetchResult: ...

    def parse(self, content: bytes) -> list[TradeRecord]: ...


def month_range(start_ym: str, end_ym: str) -> list[str]:
    """'2026-01'..'2026-03' → ['202601', '202602', '202603'] (API 형식)."""
    y, m = (int(x) for x in start_ym.split("-"))
    ey, em = (int(x) for x in end_ym.split("-"))
    out: list[str] = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _shift(ym: str, months: int) -> str:
    y, m = (int(x) for x in ym.split("-"))
    total = y * 12 + (m - 1) + months
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


@dataclass(frozen=True, slots=True)
class PageOutcome:
    lawd_cd: str
    deal_ym: str
    page_no: int
    document: RawDocument
    result_code: str | None
    result_msg: str | None
    n_items: int
    is_presale: bool = False


class RtmsCollector:
    source_kind = "rtms"

    def __init__(
        self,
        *,
        service_key: str | object | None = _UNSET,
        http: HttpClient | None = None,
        fallback: ReprocessedTradeSource | None = None,
        months: int = 12,
        num_rows: int = 1000,
        max_pages: int = 20,
        load: bool = True,
        session_factory: SessionFactory = get_session,
        raw_dir: Path | None = None,
        presale: bool = True,
    ) -> None:
        """``presale``: Open API 경로에서 분양권 전매 API 도 받는다(모듈 설명)."""
        if service_key is _UNSET:
            secret = get_settings().data_go_kr_key
            key = secret.get_secret_value() if secret is not None else None
        else:
            key = service_key if isinstance(service_key, str) else None
        # 공공데이터포털은 '인코딩 키'(%2B 등)와 '디코딩 키'를 준다. httpx 가 다시 인코딩하므로 디코딩
        # 형태로 맞춘다.
        self._key = unquote(key) if key else None
        self._secrets = (key, self._key)
        self._presale = presale
        self._http = http
        self._fallback = fallback
        self._months = max(1, months)
        self._num_rows = num_rows
        self._max_pages = max_pages
        self._load = load
        self._session_factory = session_factory
        self._raw_dir = raw_dir
        self.trades: list[tuple[int | None, TradeRecord]] = []
        self.pages: list[PageOutcome] = []
        self.load_stats: LoadStats | None = None
        self._seen_docs: set[int | None] = set()
        # 이번 실행에서 분양권 API 를 멈춘 사유('403: SERVICE_KEY_IS_NOT_REGISTERED_ERROR' 등) — 없으면 None
        self.presale_disabled_reason: str | None = None

    @property
    def mode(self) -> str:
        if self._key:
            return "openapi"
        if self._fallback is not None:
            return "reprocessed"
        return "disabled"

    @property
    def enabled(self) -> bool:
        return self.mode != "disabled"

    @property
    def disabled_reason(self) -> str | None:
        return None if self.enabled else DISABLED_NO_KEY

    def months_for(self, snapshot: Snapshot, since: str | None) -> list[str]:
        end = snapshot.asof_date[:7]
        start = _shift(end, -(self._months - 1))
        if since:
            since_ym = since[:7]
            start = max(start, since_ym) if since_ym <= end else end
        return month_range(start, end)

    def _apis(self) -> list[tuple[str, bool]]:
        """(엔드포인트, is_presale) — 매매 먼저, 분양권은 켜져 있고 이번 실행에서 멈추지 않았을 때."""
        apis = [(RTMS_API_URL, False)]
        if self._presale and self.presale_disabled_reason is None:
            apis.append((PRESALE_API_URL, True))
        return apis

    def get(self, url: str, params: dict[str, str], *, http: HttpClient | None = None) -> FetchResult:
        """키를 붙여 요청하고, 키를 모든 표기로 지운 결과를 돌려준다(url = 키 없는 조회 주소)."""
        client = http or self._http
        if client is None:
            with HttpClient() as own:
                return self.get(url, params, http=own)
        r = client.get(url, params={"serviceKey": self._key or "", **params})
        return scrub_result(r, self._secrets, url=f"{url}?{urlencode(params)}")

    def fetch(self, region: Region, snapshot: Snapshot, since: str | None) -> list[RawDocument]:
        self.trades, self.pages, self.load_stats = [], [], None
        self.presale_disabled_reason = None
        self._seen_docs = set()  # 같은 원문(같은 sha256)이 두 번 오면 거래를 한 번만
        if not self.enabled:
            return []
        months = self.months_for(snapshot, since)
        http = self._http or HttpClient()
        docs: list[RawDocument] = []
        try:
            with self._session_factory() as session:
                store = RawStore(session, raw_dir=self._raw_dir)
                for lawd in region.sigungu_codes:
                    for ym in months:
                        if self.mode == "openapi":
                            for api_url, presale in self._apis():
                                docs.extend(
                                    self._openapi_month(http, store, region.id, lawd, ym, api_url, presale)
                                )
                        else:
                            docs.extend(self._fallback_month(store, region.id, lawd, ym))
                if self._load:
                    self.load_stats = load_trades(session, region.id, self.trades)
        finally:
            if self._http is None:
                http.close()
        return docs

    def backfill(self, region: Region, snapshot: Snapshot, *, months: int) -> list[RawDocument]:
        """벤치마크용 과거 월 채우기(R3 C1, D9-2 '입주 후 실거래'): 기준월 − (months−1) ~ 기준월 중 아직 성공
        원문이 없는 (시군구, 월)만 Open API 로 받아 적재한다. 멱등 — 채울 달이 없으면 호출 0.

        '받은 적 있음' = 같은 조회 주소(1쪽)의 성공 원문 행. 거래 0건 달의 응답은 시군구·월이 달라도 본문이
        같을 수 있어(같은 sha256 → 원문 1행) 다음 실행에서 다시 받을 수 있다(비용 작음, 정확성 영향 없음).
        키가 없으면(재가공 폴백 포함) 하지 않는다 — 재가공 원천은 인터페이스만 있다.
        """
        self.trades, self.pages, self.load_stats = [], [], None
        self.presale_disabled_reason = None
        self._seen_docs = set()
        if self.mode != "openapi":
            return []
        end = snapshot.asof_date[:7]
        wanted = month_range(_shift(end, -(max(1, months) - 1)), end)
        http = self._http or HttpClient()
        docs: list[RawDocument] = []
        try:
            with self._session_factory() as session:
                have = {
                    url
                    for url in session.scalars(
                        select(RtmsRaw.url).where(
                            RtmsRaw.source_kind == "rtms",
                            RtmsRaw.path.is_not(None),
                            RtmsRaw.http_status == 200,
                            RtmsRaw.error_text.is_(None),
                        )
                    )
                }
                store = RawStore(session, raw_dir=self._raw_dir)
                for lawd in region.sigungu_codes:
                    for ym in wanted:
                        for api_url, presale in self._apis():
                            if self._shown_url(lawd, ym, 1, api_url) in have:
                                continue
                            docs.extend(
                                self._openapi_month(http, store, region.id, lawd, ym, api_url, presale)
                            )
                if self._load and self.trades:
                    self.load_stats = load_trades(session, region.id, self.trades)
        finally:
            if self._http is None:
                http.close()
        return docs

    def _params(self, lawd: str, ym: str, page: int) -> dict[str, str]:
        return {"LAWD_CD": lawd, "DEAL_YMD": ym, "numOfRows": str(self._num_rows), "pageNo": str(page)}

    def _shown_url(self, lawd: str, ym: str, page: int, api_url: str = RTMS_API_URL) -> str:
        return f"{api_url}?{urlencode(self._params(lawd, ym, page))}"

    def _openapi_month(
        self,
        http: HttpClient,
        store: RawStore,
        region_id: int,
        lawd: str,
        ym: str,
        api_url: str = RTMS_API_URL,
        presale: bool = False,
    ) -> list[RawDocument]:
        docs: list[RawDocument] = []
        page_no = 1
        while page_no <= self._max_pages:
            r = self.get(api_url, self._params(lawd, ym, page_no), http=http)
            shown = r.url
            if not r.ok:
                failure = fetch_failure(r)
                doc = store.save_result(
                    r,
                    source_kind="rtms",
                    ext="xml",
                    url=shown,
                    region_id=region_id,
                    failure=failure,
                    detail=api_error_message(r.content),
                )
                docs.append(doc)
                self.pages.append(PageOutcome(lawd, ym, page_no, doc, None, doc.error_text, 0, presale))
                if presale and r.status in _AUTH_STATUSES:
                    self.presale_disabled_reason = f"{r.status}: {doc.error_text or ''}".rstrip(": ")
                break
            doc = store.save_result(
                r,
                source_kind="rtms",
                ext="xml",
                url=shown,
                content_type="application/xml",
                region_id=region_id,
            )
            docs.append(doc)
            page = parse_trade_xml(r.content, is_presale=presale)
            self.pages.append(
                PageOutcome(
                    lawd, ym, page_no, doc, page.result_code, page.result_msg, len(page.items), presale
                )
            )
            if not page.ok:
                if presale and page.result_code in _AUTH_CODES:  # 200 + 포털 인증 오류(미신청 등)
                    self.presale_disabled_reason = f"{page.result_code}: {page.result_msg or ''}".rstrip(": ")
                break
            if doc.id not in self._seen_docs:
                self._seen_docs.add(doc.id)
                self.trades.extend((doc.id, t) for t in page.items)
            if page.num_rows <= 0 or page_no * page.num_rows >= page.total_count:
                break
            page_no += 1
        return docs

    def _fallback_month(self, store: RawStore, region_id: int, lawd: str, ym: str) -> list[RawDocument]:
        assert self._fallback is not None
        r = self._fallback.fetch_month(lawd, ym)
        if not r.ok:
            doc = store.save_result(
                r, source_kind="rtms", ext="bin", region_id=region_id, failure=fetch_failure(r)
            )
            self.pages.append(PageOutcome(lawd, ym, 1, doc, None, doc.error_text, 0))
            return [doc]
        ctype = r.headers.get("content-type", "application/octet-stream")
        ext = "json" if "json" in ctype else "html" if "html" in ctype else "csv" if "csv" in ctype else "bin"
        doc = store.save_result(r, source_kind="rtms", ext=ext, content_type=ctype, region_id=region_id)
        records = [replace(t, source="reprocessed", label="재가공") for t in self._fallback.parse(r.content)]
        if doc.id not in self._seen_docs:
            self._seen_docs.add(doc.id)
            self.trades.extend((doc.id, t) for t in records)
        self.pages.append(PageOutcome(lawd, ym, 1, doc, "fallback", self._fallback.name, len(records)))
        return [doc]


TradeKey = tuple[str, str | None, Decimal, int | None, int, str, str, bool]


def _key(
    apt_name: str,
    place: str | None,
    area: Decimal,
    floor: int | None,
    price: int,
    day: str,
    src: str,
    presale: bool,
) -> TradeKey:
    return (apt_name, place, Decimal(area).quantize(Decimal("0.01")), floor, price, day, src, bool(presale))


def load_trades(
    session: Session, region_id: int, trades: Iterable[tuple[int | None, TradeRecord]]
) -> LoadStats:
    """rtms_trade 적재(멱등).

    같은 거래가 날마다 받은 다른 원문(같은 월 재조회)에 또 나오므로 원문 단위가 아니라 거래 키
    (단지명, 법정동 코드|동, 면적, 층, 금액, 계약일, source, 분양권 여부)로 맞춘다. 키가 같은 기존 행은
    해제 여부만 갱신하고, 같은 키가 여러 건이면 건수만큼 둔다.
    """
    stats = LoadStats()
    items = list(trades)
    if not items:
        return stats
    days = [t.deal_date for _, t in items]
    existing: dict[TradeKey, list[RtmsTrade]] = {}
    rows = session.scalars(
        select(RtmsTrade).where(
            RtmsTrade.region_id == region_id,
            RtmsTrade.deal_date >= min(days),
            RtmsTrade.deal_date <= max(days),
        )
    )
    for row in rows:
        k = _key(
            row.apt_name,
            row.legal_dong_code or row.dong,
            row.area_m2,
            row.floor,
            row.price_won,
            row.deal_date,
            row.source,
            row.is_presale,
        )
        existing.setdefault(k, []).append(row)
    for doc_id, t in items:
        k = _key(
            t.apt_name,
            t.legal_dong_code or t.dong,
            t.area_m2,
            t.floor,
            t.price_won,
            t.deal_date,
            t.source,
            t.is_presale,
        )
        pool = existing.get(k)
        if pool:
            row = pool.pop(0)
            if row.cancelled != t.cancelled:
                row.cancelled = t.cancelled
                row.raw_document_id = doc_id
                stats.updated += 1
            else:
                stats.unchanged += 1
            continue
        session.add(
            RtmsTrade(
                region_id=region_id,
                apt_name=t.apt_name,
                dong=t.dong,
                legal_dong_code=t.legal_dong_code,
                completed_year=t.completed_year,
                area_m2=t.area_m2,
                floor=t.floor,
                price_won=t.price_won,
                deal_date=t.deal_date,
                cancelled=t.cancelled,
                is_presale=t.is_presale,
                source=t.source,
                raw_document_id=doc_id,
            )
        )
        stats.inserted += 1
    session.flush()
    return stats

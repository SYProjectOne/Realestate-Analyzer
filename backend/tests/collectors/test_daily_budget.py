"""R3b m4: 지역 1개 일일 수집 10분 이내 — **모든 수집기**를 가짜 시계 1개로 합산(RA §5 WP1 완료 기준).

이전에는 청약홈만 FakeClock 으로 쟀다(``applyhome/test_applyhome_collector.py``). 여기서는 운영 수집
순서(``app.scheduler.collect.STEP_ORDER``: 청약홈 → 공고문 → 공식 홈페이지 → 실거래 → 통계 → 뉴스)대로
6개 수집기를 같은 시계·녹화/오프라인 픽스처로 돌리고 걸린 시간을 더한다.

시계 모델(전부 가짜 시계 위에서 계산 — 실제로 기다리지 않는다)
- 속도 제한: ``core.http.HttpClient`` 호스트당 1 req/s(운영 기본값), 재시도 0, jitter 0.
  robots.txt 요청도 센다.
- 응답 지연: 요청마다 ``LATENCY_S``(녹화 재생은 지연이 없으므로 일부러 더한다). 근거: 2026-10-09
  실측 — 공식 홈페이지 5곳 robots.txt + 첫 화면 2요청이 1.0~1.1 s.
- 렌더: 공식 홈페이지는 ``render='always'``(운영 기본 'auto' 보다 보수적) + 렌더 1회 ``RENDER_S``.
  근거: 2026-10-09 ``PlaywrightRenderer`` 실측 5곳 5.2~8.4 s(브라우저 기동·load·networkidle·settle·
  스크린샷) → 10 s.
- 처리 시간: 수집기 코드가 실제로 쓴 시간(perf_counter)도 더한다(PDF 추출·DB 저장 등).

시나리오(운영 잡과 같은 ``since``)
- 1회차 = 부트스트랩(region.bootstrap, since 없음): 상태를 만든다. 시간은 출력만 한다.
- 2회차 = 일일 수집: collect.daily(청약홈·공고문·공식 홈페이지, since = 어제 수집) +
  collect.weekly(실거래·통계·뉴스, since = 지난주 수집)가 **같은 날 겹친 최악의 날**을 한 번에 잰다
  → 합계 ≤ 600 s.

픽스처
- 청약홈: 2026-10-09 실녹화(웹 + 공식 API, ``applyhome/fixtures``). 녹화에 없는 요청은 실패로 세고
  0이어야 한다.
- 공고문: 실제 공고문 PDF(``notice_pdf/fixtures`` 스캔 PDF — 추출이 빠르다) — 링크마다 내용이 다르게
  꼬리표를 붙인다.
- 공식 홈페이지: 실녹화 HTML(``official_site/fixtures/hndapt_index.html``) — 대상 = 녹화의 지역 안
  공고(12개월 창)의 홈페이지(HMPG_ADRES) 주소마다 단지 행 1개(같은 단지의 무순위·임의공급 재공고는 같은
  주소 → 한 단지).
- 실거래: 매매 합성 응답 + 분양권 합성 응답(``rtms/fixtures``, 파일 주석), 통계·뉴스: 실녹화 JSON.
"""

from __future__ import annotations

import json
import time
import zipfile
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.collectors.applyhome import ApplyhomeCollector
from app.collectors.news import NCP_NEWS_URL, NewsCollector
from app.collectors.notice_pdf import NoticePdfCollector
from app.collectors.official_site import OfficialSiteCollector, PopupShot, RenderResult
from app.collectors.rtms import PRESALE_API_URL, RTMS_API_URL, RtmsCollector
from app.collectors.stats import UnsoldCollector
from app.collectors.stats.unsold import MOLIT_DATA_URL
from app.core.contracts_gen import RawDocument as RawDTO
from app.core.contracts_gen import Region, Snapshot
from app.core.http import HttpClient
from app.core.paths import resolve_raw_path
from app.models import Complex
from app.models import RawDocument as RawRow
from app.models import Region as RegionRow
from app.models import Snapshot as SnapshotRow
from app.scheduler.collect import STEP_ORDER

HERE = Path(__file__).parent
WEB_ZIP = HERE / "applyhome" / "fixtures" / "applyhome_2026-10-09.zip"
API_ZIP = HERE / "applyhome" / "fixtures" / "applyhome_api_2026-10-09.zip"
PDF = HERE / "notice_pdf" / "fixtures" / "scan_2026940062_p1p3.pdf"
SITE_HTML = HERE / "official_site" / "fixtures" / "hndapt_index.html"
RTMS_FX = HERE / "rtms" / "fixtures"
STATS_FX = HERE / "stats" / "fixtures"
NEWS_JSON = HERE / "news" / "fixtures" / "ncp_news_20261009.json"

DAILY_LIMIT_S = 600.0
RATE_PER_HOST = 1.0  # 운영 기본(Settings.http_rate_per_host)
LATENCY_S = 0.5  # 응답 1회 지연(실측 robots + 첫 화면 1.0~1.1 s / 2요청)
RENDER_S = 10.0  # Playwright 렌더 1회(실측 5.2~8.4 s → 올려 잡음)
TODAY = date(2026, 10, 9)  # 녹화일
ASOF = "2026-10-09"
SINCE_DAILY = "2026-10-08T06:00:00+09:00"  # 어제 collect.daily
SINCE_WEEKLY = "2026-10-02T06:00:00+09:00"  # 지난주 collect.weekly
FAKE_KEY = "TEST%2BKEY%3D%3D"  # 가짜(인코딩 키 형태)
NEWS_KEY = "test-client-id:test-client-secret"  # 가짜
SECRET_PARAMS = frozenset({"serviceKey"})
KEY_FORM_FIELDS = ("beginPd", "endPd", "suplyAreaCode", "pageIndex")

REGION: dict[str, Any] = {  # 녹화 지역(테스트 데이터 — 지역명은 테스트에만, AGENTS 규칙 15)
    "id": 1,
    "name": "인천 송도·검단·계양 + 김포",
    "query_text": "송도, 검단, 계양구, 김포시",
    "selections": [
        {"kind": "legal_dong", "code": "2818510600", "full_name": "인천광역시 연수구 송도동"},
        {"kind": "sigungu", "code": "28260", "full_name": "인천광역시 서구"},
        {"kind": "sigungu", "code": "28265", "full_name": "인천광역시 검단구"},
        {"kind": "sigungu", "code": "28245", "full_name": "인천광역시 계양구"},
        {"kind": "sigungu", "code": "41570", "full_name": "경기도 김포시"},
    ],
    "sido_codes": ["28", "41"],
    "sigungu_codes": ["28185", "28245", "28260", "28265", "41570"],
    "legal_dong_codes": ["2818510600"],
    "living_areas": [],
    "age_premium_coef": {"c_per_year": 0.015, "cap_years": 8, "label": "추정"},
    "supply_ref_pct": 0.08,
    "applyhome_query": {},
    "status": "ready",
    "created_at": "2026-10-09T06:00:00+09:00",
}


class FakeClock:
    """sleep 이 시계를 민다 — 기다리지 않고 '실제라면 걸렸을 시간'을 잰다(applyhome conftest 와 같은 모양)."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += max(0.0, seconds)


Key = tuple[str, str, tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]


def _key(method: str, url: str, form: dict[str, str] | None = None) -> Key:
    parts = urlsplit(url)
    query = tuple(
        sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in SECRET_PARAMS)
    )
    body = tuple(sorted((k, v) for k, v in (form or {}).items() if k in KEY_FORM_FIELDS))
    return (method.upper(), f"{parts.scheme}://{parts.netloc}{parts.path}", query, body)


@dataclass
class Replay:
    """모든 수집기의 HTTP 를 녹화·픽스처로 돌려주는 전송 1개. 요청마다 가짜 시계에 응답 지연을 더한다."""

    clock: FakeClock
    site_hosts: set[str] = field(default_factory=set)
    calls: Counter[str] = field(default_factory=Counter)
    misses: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._zips: dict[Key, tuple[zipfile.ZipFile, dict[str, Any]]] = {}
        for path in (WEB_ZIP, API_ZIP):
            z = zipfile.ZipFile(path)
            for e in json.loads(z.read("manifest.json"))["entries"]:
                self._zips[_key(e["method"], e["url"], e.get("form"))] = (z, e)
        self._pdf = PDF.read_bytes()
        self._site = SITE_HTML.read_bytes()
        self._news = NEWS_JSON.read_bytes()

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.clock.sleep(LATENCY_S)
        url, host, path = request.url, request.url.host, request.url.path
        self.calls[host] += 1
        if path == "/robots.txt":
            return httpx.Response(404, text="not found")
        if host in ("www.applyhome.co.kr", "api.odcloud.kr"):
            form = None
            if request.method == "POST":
                form = dict(parse_qsl(request.content.decode("utf-8"), keep_blank_values=True))
            found = self._zips.get(_key(request.method, str(url), form))
            if found is None:
                return self._miss(request)
            z, e = found
            body = z.read(e["file"]) if e.get("file") else b""
            return httpx.Response(e["status"], content=body, headers={"content-type": e["content_type"]})
        if (
            host == "static.applyhome.co.kr"
        ):  # 공고문마다 다른 원문(같은 sha 면 한 행이 되어 매일 다시 받는다)
            return httpx.Response(
                200,
                content=self._pdf + f"\n%{url}\n".encode(),
                headers={"content-type": "application/pdf"},
            )
        if f"{url.scheme}://{host}{path}" in (RTMS_API_URL, PRESALE_API_URL):
            name = "openapi_presale_synthetic.xml" if "SilvTrade" in path else "openapi_trade_sample.xml"
            tag = f"<resultMsg>OK</resultMsg><!-- {path} {url.params['LAWD_CD']} {url.params['DEAL_YMD']} -->"
            body = (RTMS_FX / name).read_bytes().replace(b"<resultMsg>OK</resultMsg>", tag.encode())
            return httpx.Response(200, content=body, headers={"content-type": "application/xml"})
        if f"{url.scheme}://{host}{path}" == MOLIT_DATA_URL:
            name = (
                "molit_unsold_2082_202609.json"
                if url.params["formId"] == "2082"
                else "molit_unsold_5328_202608.json"
            )
            return httpx.Response(
                200, content=(STATS_FX / name).read_bytes(), headers={"content-type": "application/json"}
            )
        if f"{url.scheme}://{host}{path}" == NCP_NEWS_URL:
            return httpx.Response(200, content=self._news, headers={"content-type": "text/plain"})
        if host in self.site_hosts:
            return httpx.Response(
                200, content=self._site, headers={"content-type": "text/html; charset=utf-8"}
            )
        return self._miss(request)

    def _miss(self, request: httpx.Request) -> httpx.Response:
        self.misses.append(f"{request.method} {request.url.host}{request.url.path}")
        raise httpx.ConnectError("[replay] 녹화에 없는 요청", request=request)


class ClockRenderer:
    """Playwright 대신: 렌더 1회 = 가짜 시계 RENDER_S."""

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.calls = 0

    def render(self, url: str) -> RenderResult:
        self.clock.sleep(RENDER_S)
        self.calls += 1
        return RenderResult(
            url=url,
            final_url=url,
            status=200,
            screenshot_png=b"\x89PNG\r\n\x1a\n" + url.encode(),
            dom_text="분양 안내",
            popups=(PopupShot(selector="#layer_popup", sha256="a" * 64, width=300, height=200),),
        )


@dataclass
class Step:
    name: str
    fake_s: float
    real_s: float
    docs: int
    requests: int

    @property
    def total_s(self) -> float:
        return self.fake_s + self.real_s


@pytest.fixture
def world(db_engine: Engine, raw_dir: Path) -> Iterator[tuple[Region, Snapshot]]:
    region = Region.model_validate(REGION)
    snapshot = Snapshot(
        id=1,
        region_id=1,
        asof_date=ASOF,
        status="building",
        degraded=False,
        created_at=ASOF + "T06:00:00+09:00",
    )
    with Session(db_engine) as s:
        s.add(
            RegionRow(
                id=region.id,
                name=region.name,
                query_text=region.query_text,
                selections=[x.model_dump() for x in region.selections],
                sido_codes=region.sido_codes,
                sigungu_codes=region.sigungu_codes,
                legal_dong_codes=region.legal_dong_codes,
                living_areas=[],
                age_premium_coef=region.age_premium_coef.model_dump(),
                supply_ref_pct=region.supply_ref_pct,
                applyhome_query={},
                status=region.status,
                created_at=region.created_at,
            )
        )
        s.flush()
        s.add(
            SnapshotRow(id=1, region_id=1, asof_date=ASOF, status="building", created_at=snapshot.created_at)
        )
        s.commit()
    yield region, snapshot


def _homepages(engine: Engine) -> dict[str, str]:
    """1회차 청약홈이 받은 지역 안 API 상세 원문의 홈페이지(URL → 첫 주택관리번호). 주소 1개 = 단지 1개."""
    out: dict[str, str] = {}
    with Session(engine) as s:
        rows = s.scalars(
            select(RawRow).where(
                RawRow.source_kind == "applyhome_detail",
                RawRow.region_id.is_not(None),
                RawRow.path.is_not(None),
                RawRow.url.like("https://api.odcloud.kr/%LttotPblancDetail%"),
            )
        )
        for row in rows:
            assert row.path is not None
            for d in json.loads(resolve_raw_path(row.path).read_bytes()).get("data", []):
                url = str(d.get("HMPG_ADRES") or "").strip()
                if url.startswith(("http://", "https://")):
                    hm = str(d["HOUSE_MANAGE_NO"])
                    out[url] = min(out.get(url, hm), hm)
    return out


def _seed_complexes(engine: Engine, homepages: dict[str, str]) -> None:
    with Session(engine) as s:
        for i, (url, hm) in enumerate(sorted(homepages.items()), start=1):
            s.add(
                Complex(
                    id=i,
                    region_id=1,
                    name=f"단지 {hm}",
                    applyhome_id=hm,
                    former_names=[],
                    apply_dates=[],
                    contract_dates=[],
                    official_site_url=url,
                )
            )
        s.commit()


def _run_all(
    region: Region,
    snapshot: Snapshot,
    replay: Replay,
    clock: FakeClock,
    *,
    daily: bool,
    names: tuple[str, ...] = STEP_ORDER,
) -> list[Step]:
    def http() -> HttpClient:
        # 수집기마다 자기 HttpClient(운영과 같다) — 시계는 하나
        return HttpClient(
            rate_per_host=RATE_PER_HOST,
            max_retries=0,
            jitter=0.0,
            sleep=clock.sleep,
            clock=clock.monotonic,
            transport=replay.transport(),
        )

    renderer = ClockRenderer(clock)
    factories: dict[str, Callable[[HttpClient], Any]] = {
        "applyhome": lambda h: ApplyhomeCollector(
            http=h, today=lambda: TODAY, service_key=FAKE_KEY, window=("2025-12", "2026-11")
        ),
        "notice_pdf": lambda h: NoticePdfCollector(http=h, ocr=None),
        "official_site": lambda h: OfficialSiteCollector(http=h, renderer=renderer, render="always"),
        "rtms": lambda h: RtmsCollector(http=h, service_key=FAKE_KEY),
        "stats": lambda h: UnsoldCollector(http=h),
        "news": lambda h: NewsCollector(http=h, api_key=NEWS_KEY, provider="ncp", secrets=[]),
    }
    since = {
        "applyhome": SINCE_DAILY,
        "notice_pdf": SINCE_DAILY,
        "official_site": SINCE_DAILY,
        "rtms": SINCE_WEEKLY,
        "stats": SINCE_WEEKLY,
        "news": SINCE_WEEKLY,
    }
    steps: list[Step] = []
    for name in (n for n in STEP_ORDER if n in names):  # 운영 순서 그대로
        with http() as client:
            collector = factories[name](client)
            n0, t0, r0 = sum(replay.calls.values()), clock.now, time.perf_counter()
            docs: list[RawDTO] = collector.fetch(region, snapshot, since[name] if daily else None)
            steps.append(
                Step(
                    name=name,
                    fake_s=clock.now - t0,
                    real_s=time.perf_counter() - r0,
                    docs=len(docs),
                    requests=sum(replay.calls.values()) - n0,
                )
            )
    return steps


def _table(title: str, steps: list[Step]) -> str:
    lines = [f"[timing] {title}"]
    for s in steps:
        lines.append(
            f"  {s.name:<14} 요청 {s.requests:>4}  원문 {s.docs:>4}"
            f"  가짜 {s.fake_s:7.1f}s  처리 {s.real_s:6.2f}s"
        )
    lines.append(
        f"  {'합계':<14} {'':>24}  {sum(s.total_s for s in steps):7.1f}s (한도 {DAILY_LIMIT_S:.0f}s)"
    )
    return "\n".join(lines)


def test_all_collectors_daily_budget_one_clock(world: tuple[Region, Snapshot], db_engine: Engine) -> None:
    region, snapshot = world
    clock = FakeClock()
    replay = Replay(clock)

    # 1회차(부트스트랩) — 공식 홈페이지 대상은 청약홈 원문의 홈페이지로 단지 행을 만든 뒤
    boot = _run_all(region, snapshot, replay, clock, daily=False)
    homepages = _homepages(db_engine)
    assert len(homepages) >= 10  # 녹화 규모(지역 안 공고 중 홈페이지가 있는 것)
    _seed_complexes(db_engine, homepages)
    replay.site_hosts = {httpx.URL(u).host for u in homepages}  # 한글 도메인은 punycode
    (boot_site,) = _run_all(region, snapshot, replay, clock, daily=False, names=("official_site",))
    print("\n" + _table("1회차(부트스트랩, 공식 홈페이지 대상 0)", boot))
    print(f"  official_site(대상 {len(homepages)}) 1회 {boot_site.total_s:.1f}s")
    assert replay.misses == [], replay.misses[:10]

    # 2회차 = 일일 수집(collect.daily + collect.weekly 가 겹친 날)
    replay.calls.clear()
    steps = _run_all(region, snapshot, replay, clock, daily=True)
    print(_table("일일(daily+weekly 같은 날, 가짜 시계 1개)", steps))
    assert replay.misses == [], replay.misses[:10]
    by = {s.name: s for s in steps}
    assert [s.name for s in steps] == list(STEP_ORDER)
    # 모든 수집기가 실제로 돌았다(요청·원문이 있다) — 공고문은 새 공고가 없으면 요청 0 이 정상
    for name in ("applyhome", "official_site", "rtms", "stats", "news"):
        assert by[name].requests > 0 and by[name].docs > 0, by[name]
    assert by["official_site"].docs >= len(homepages)  # HTML(+ 스크린샷)
    assert by["rtms"].requests >= 2 * len(region.sigungu_codes)  # 매매 + 분양권

    total = sum(s.total_s for s in steps)
    daily_only = sum(by[n].total_s for n in ("applyhome", "notice_pdf", "official_site"))
    assert daily_only <= total <= DAILY_LIMIT_S, _table("초과", steps)

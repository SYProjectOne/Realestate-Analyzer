"""청약홈 수집기 (RA §5 WP1, Collector 프로토콜, DECISIONS D2-6).

경로 선택 (시도마다)
- **공식 API 1순위** (``DATA_GO_KR_KEY`` 가 있으면, ``api.py``): 시도 약칭 + 모집공고일 범위로 APT·잔여세대·
  임의공급 상세 목록을 받는다(목록에 공급위치가 있어 지역 밖 단지는 상세를 더 받지 않는다). 목록 페이지 =
  ``applyhome_list``(JSON). 지역 안 공고마다 상세(1건 조회)·주택형별·경쟁률 = ``applyhome_detail``(JSON).
  - 목록이 하나라도 실패(401·5xx·네트워크·JSON 아님)하면 **그 시도는 웹 경로**로 전부 다시 받는다.
  - 공고 단위 폴백: API 상세·주택형 실패 → 웹 상세, API 경쟁률 실패(예: 경쟁률 서비스 미신청 401) → 웹 경쟁률.
  - 웹 상세는 API 가 성공해도 받는다(``web_detail=True`` 기본): 모집공고문 PDF 링크는 웹 상세에만 있어
    notice_pdf 수집기가 그것을 읽는다(API 에 첨부 링크 필드 없음).
- **웹 경로** (키 없음·API 목록 실패): 아래 1~3.

웹 흐름 (지역 1개)
1. ``region.sido_codes`` 마다 시도 약칭으로 **APT 분양정보 목록**과 **APT 잔여세대(무순위·임의) 목록**을
   조회한다.
   기간은 ``region.applyhome_query['from_ym']``(없으면 기준월 −10개월) ~ 기준월 +1개월을 12개월 창으로 나눠
   모든 페이지를 받는다. 페이지마다 ``RawDocument(source_kind='applyhome_list')``.
2. 목록에는 주소가 없으므로 행마다 상세 팝업을 받아 '공급위치'를 읽고, region 의 시군구·읍면동 이름이 있는
   행만 남긴다(사전 필터 — 정밀 법정동 배정·범위 경계는 WP2). 남은 행은 경쟁률 팝업까지 받는다.
   상세·경쟁률 = ``applyhome_detail``. 필터 밖 상세도 원문으로 저장하되(region_id=None) 반환하지 않고,
   다음 실행부터는 저장된 원문의 공급위치로 판단해 다시 받지 않는다.
3. ``since``(ISO)가 주어지면 이미 받은 적 있는 행 중 행의 마지막 날짜(청약 마감·당첨자 발표)가 since 이전인
   것은 상세·경쟁률을 다시 받지 않고 기존 행을 돌려준다.

멱등: 같은 원문이면 행을 만들지 않는다(``RawStore``). 실패(403·5xx·DNS·timeout·robots)도 행으로 돌려준다.
HTTP 는 ``app.core.http.HttpClient`` 만 쓴다(속도 제한·robots·재시도).
"""

from __future__ import annotations

import calendar
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.applyhome import api as ah_api
from app.collectors.applyhome import parse, site
from app.collectors.applyhome.area import AreaFilter, build_region_areas
from app.collectors.applyhome.raw import RawStore, Stored, to_contract
from app.core.contracts_gen import RawDocument, Region, Snapshot
from app.core.db import get_sessionmaker
from app.core.http import FetchResult, HttpClient
from app.core.paths import resolve_raw_path
from app.core.settings import get_settings
from app.core.time import today_kst
from app.models import Complex

__all__ = ["ApplyhomeCollector", "month_windows"]

MAX_PAGES = 200  # 창 하나에 2,000행 — 형식이 바뀌어 total 을 못 읽을 때의 안전장치
_UNSET = object()


def _ym(d: date) -> tuple[int, int]:
    return d.year, d.month


def _add_months(ym: tuple[int, int], n: int) -> tuple[int, int]:
    total = ym[0] * 12 + (ym[1] - 1) + n
    return total // 12, total % 12 + 1


def _parse_ym(value: object) -> tuple[int, int] | None:
    if not isinstance(value, str):
        return None
    digits = value.replace("-", "").replace(".", "").strip()
    if len(digits) != 6 or not digits.isdigit():
        return None
    year, month = int(digits[:4]), int(digits[4:])
    return (year, month) if 1 <= month <= 12 else None


def month_windows(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[str, str]]:
    """[start, end] 을 12개월 이하 창으로 나눈다 → [('YYYYMM', 'YYYYMM'), ...] (오래된 것부터)."""
    out: list[tuple[str, str]] = []
    cur = start
    while cur <= end:
        stop = min(_add_months(cur, site.MAX_WINDOW_MONTHS - 1), end)
        out.append((f"{cur[0]:04d}{cur[1]:02d}", f"{stop[0]:04d}{stop[1]:02d}"))
        cur = _add_months(stop, 1)
    return out


def _since_date(since: str | None) -> date | None:
    if not since:
        return None
    try:
        return datetime.fromisoformat(since).date()
    except ValueError:
        try:
            return date.fromisoformat(since[:10])
        except ValueError:
            return None


@dataclass(slots=True)
class _Run:
    region: Region
    store: RawStore
    out: list[RawDocument]
    seen: set[int]

    def emit(self, stored: Stored) -> None:
        if stored.row.id not in self.seen:
            self.seen.add(stored.row.id)
            self.out.append(to_contract(stored.row))


class ApplyhomeCollector:
    """``fetch(region, snapshot, since) -> list[RawDocument]`` (app.core.protocols.Collector)."""

    source_kinds = ("applyhome_list", "applyhome_detail")

    def __init__(
        self,
        *,
        http: HttpClient | None = None,
        session: Session | None = None,
        today: Callable[[], date] = today_kst,
        max_pages: int = MAX_PAGES,
        service_key: str | object | None = _UNSET,
        web_detail: bool = True,
    ) -> None:
        """``service_key``: 공공데이터포털 키(기본 = 설정 ``DATA_GO_KR_KEY``). None/빈 값이면 웹 경로만.
        ``web_detail``: API 경로에서도 지역 안 공고의 웹 상세를 받는다(공고문 PDF 링크용)."""
        self._http = http
        self._session = session
        self._today = today
        self._max_pages = max_pages
        if service_key is _UNSET:
            secret = get_settings().data_go_kr_key
            key = secret.get_secret_value() if secret is not None else None
        else:
            key = service_key if isinstance(service_key, str) else None
        self._key = key or None
        self._web_detail = web_detail
        # 마지막 fetch 의 시도별 경로: {sido_code: 'api' | 'web' | 'web(api 실패: <사유>)'}
        self.paths: dict[str, str] = {}

    @property
    def api_enabled(self) -> bool:
        return self._key is not None

    # --- 자원
    @contextmanager
    def _resources(self) -> Iterator[tuple[HttpClient, Session, bool]]:
        http = self._http or HttpClient()
        own_session = self._session is None
        session = self._session or get_sessionmaker()()
        try:
            yield http, session, own_session
            if own_session:
                session.commit()
            else:
                session.flush()
        except BaseException:
            if own_session:
                session.rollback()
            raise
        finally:
            if own_session:
                session.close()
            if self._http is None:
                http.close()

    # --- 프로토콜
    def fetch(self, region: Region, snapshot: Snapshot, since: str | None) -> list[RawDocument]:
        with self._resources() as (http, session, own):
            run = _Run(region=region, store=RawStore(session), out=[], seen=set())

            def checkpoint() -> None:
                # 긴 수집 동안 SQLite 쓰기 잠금을 오래 잡지 않도록 문서마다 커밋(세션을 받은 경우는 flush)
                if own:
                    session.commit()
                else:
                    session.flush()

            areas = build_region_areas(region, session)
            windows = self._windows(region)
            since_day = _since_date(since)
            self.paths = {}
            api = ah_api.ApplyhomeApi(http, self._key) if self._key else None
            for flt in areas.filters.values():
                if api is not None:
                    failed = self._collect_api(api, http, run, session, flt, windows, since_day, checkpoint)
                    if failed is None:
                        self.paths[flt.sido_code] = "api"
                        continue
                    self.paths[flt.sido_code] = f"web(api 실패: {failed})"
                else:
                    self.paths[flt.sido_code] = "web"
                for kind in site.LIST_KINDS:
                    rows = self._collect_list(http, run, flt, kind, windows, checkpoint)
                    for row in rows:
                        self._collect_row(http, run, session, flt, row, since_day, checkpoint)
            return run.out

    # --- 공식 API
    def _collect_api(
        self,
        api: ah_api.ApplyhomeApi,
        http: HttpClient,
        run: _Run,
        session: Session,
        flt: AreaFilter,
        windows: list[tuple[str, str]],
        since_day: date | None,
        checkpoint: Callable[[], None],
    ) -> str | None:
        """시도 하나를 API 로. 목록이 실패하면 사유 문자열(호출자가 웹 경로로), 성공이면 None."""
        begin = date(int(windows[0][0][:4]), int(windows[0][0][4:]), 1)
        end_y, end_m = int(windows[-1][1][:4]), int(windows[-1][1][4:])
        end = date(end_y, end_m, calendar.monthrange(end_y, end_m)[1])
        rows: dict[tuple[str, str], ah_api.ApiRow] = {}
        for kind in ah_api.API_KINDS:
            path = ah_api.ENDPOINTS[kind].detail
            got = 0
            for page_no in range(1, self._max_pages + 1):
                result = api.get(path, ah_api.list_params(kind, flt.area, begin, end, page_no))
                stored = run.store.save(
                    result, source_kind="applyhome_list", ext="json", region_id=run.region.id
                )
                run.emit(stored)
                checkpoint()
                page = ah_api.parse_page(result)
                if not page.ok:
                    return f"{kind} 목록 {page.error}"
                for d in page.rows:
                    row = ah_api.to_row(kind, d)
                    if row is not None:
                        rows.setdefault((row.house_manage_no, row.pblanc_no), row)
                got += len(page.rows)
                if not page.rows or page.match_count is None or got >= page.match_count:
                    break
        for row in rows.values():
            if row.area_name not in (None, flt.area) or not flt.matches(row.address):
                continue  # 목록에 공급위치가 있으므로 지역 밖은 더 받지 않는다(원문은 목록 페이지에 있다)
            self._collect_api_row(api, http, run, session, row, since_day, checkpoint)
        return None

    def _collect_api_row(
        self,
        api: ah_api.ApplyhomeApi,
        http: HttpClient,
        run: _Run,
        session: Session,
        row: ah_api.ApiRow,
        since_day: date | None,
        checkpoint: Callable[[], None],
    ) -> None:
        hm, pb = row.house_manage_no, row.pblanc_no
        ep = ah_api.ENDPOINTS[row.kind]
        params = ah_api.item_params(hm, pb)
        api_urls = [ah_api.doc_url(p, params) for p in (ep.detail, ep.model, ep.competition)]
        web_urls = [site.detail_url(ep.web_kind, hm, pb), site.competition_url(ep.web_kind, hm, pb)]
        if since_day is not None and row.last_date is not None and row.last_date < since_day.isoformat():
            known = [run.store.latest_ok("applyhome_detail", u) for u in api_urls + web_urls]
            if known[0] is not None:  # 일정이 끝난 공고 — 받아 둔 원문을 그대로 돌려준다
                for k in known:
                    if k is not None:
                        run.emit(Stored(k, created=False))
                return

        complex_id = _complex_id(session, run.region.id, hm)

        def save(result: FetchResult, ext: str) -> Stored:
            stored = run.store.save(
                result,
                source_kind="applyhome_detail",
                ext=ext,
                region_id=run.region.id,
                complex_id=complex_id,
            )
            run.emit(stored)
            checkpoint()
            return stored

        ok: list[bool] = []
        for path in (ep.detail, ep.model, ep.competition):
            result = api.get(path, params)
            save(result, "json")
            page = ah_api.parse_page(result)
            ok.append(page.ok and (bool(page.rows) or path == ep.competition))
        detail_ok, model_ok, comp_ok = ok
        if self._web_detail or not (detail_ok and model_ok):
            save(http.get(web_urls[0]), "html")  # 공고문 링크(notice_pdf) + API 상세 실패 폴백
        if not comp_ok:
            save(http.get(web_urls[1]), "html")  # 경쟁률 API 실패(401 등) → 웹 경쟁률

    # --- 목록
    def _windows(self, region: Region) -> list[tuple[str, str]]:
        today = self._today()
        end = _add_months(_ym(today), 1)
        start = _parse_ym(region.applyhome_query.get("from_ym")) or _add_months(_ym(today), -10)
        return month_windows(min(start, end), end)

    def _collect_list(
        self,
        http: HttpClient,
        run: _Run,
        flt: AreaFilter,
        kind: site.ListKind,
        windows: list[tuple[str, str]],
        checkpoint: Callable[[], None],
    ) -> list[parse.ListRow]:
        rows: dict[tuple[str, str], parse.ListRow] = {}
        for begin, end in windows:
            got = 0
            for page in range(1, self._max_pages + 1):
                form = site.list_form(flt.area, begin, end, page)
                result = http.post(site.list_url(kind), data=form)
                result = _with_url(result, site.list_doc_url(kind, form))
                stored = run.store.save(
                    result, source_kind="applyhome_list", ext="html", region_id=run.region.id
                )
                run.emit(stored)
                checkpoint()
                if not stored.ok:
                    break
                listing = parse.parse_list(result.text(), kind)
                for row in listing.rows:
                    rows.setdefault((row.house_manage_no, row.pblanc_no), row)
                got += len(listing.rows)
                if not listing.rows or (listing.total is not None and got >= listing.total):
                    break
        return list(rows.values())

    # --- 상세·경쟁률
    def _collect_row(
        self,
        http: HttpClient,
        run: _Run,
        session: Session,
        flt: AreaFilter,
        row: parse.ListRow,
        since_day: date | None,
        checkpoint: Callable[[], None],
    ) -> None:
        hm, pb = row.house_manage_no, row.pblanc_no
        d_url = site.detail_url(row.kind, hm, pb)
        c_url = site.competition_url(row.kind, hm, pb)
        known = run.store.latest_ok("applyhome_detail", d_url)
        known_text = _read_text(known.path) if known is not None else ""
        if known is not None and known_text:  # 원문 파일이 없으면 모르는 것으로 보고 다시 받는다
            address = parse.detail_supply_address(known_text)
            if not flt.matches(address):
                return  # 이전에 받은 원문으로 지역 밖임을 안다 — 다시 받지 않는다
            if since_day is not None and row.last_date is not None and row.last_date < since_day.isoformat():
                run.emit(Stored(known, created=False))
                comp = run.store.latest_ok("applyhome_detail", c_url)
                if comp is not None:
                    run.emit(Stored(comp, created=False))
                return

        complex_id = _complex_id(session, run.region.id, hm)
        result = http.get(d_url)
        if not result.ok:
            run.emit(
                run.store.save(
                    result,
                    source_kind="applyhome_detail",
                    ext="html",
                    region_id=run.region.id,
                    complex_id=complex_id,
                )
            )
            checkpoint()
            return
        address = parse.detail_supply_address(result.text())
        in_region = flt.matches(address)
        stored = run.store.save(
            result,
            source_kind="applyhome_detail",
            ext="html",
            region_id=run.region.id if in_region else None,
            complex_id=complex_id if in_region else None,
        )
        checkpoint()
        if not in_region:
            return
        run.emit(stored)
        comp_result = http.get(c_url)
        run.emit(
            run.store.save(
                comp_result,
                source_kind="applyhome_detail",
                ext="html",
                region_id=run.region.id,
                complex_id=complex_id,
            )
        )
        checkpoint()


def _with_url(result: FetchResult, url: str) -> FetchResult:
    """POST 목록은 본문을 쿼리로 붙인 주소로 남긴다(같은 날 실패 행 sha 가 조회 조건마다 다르게)."""
    from dataclasses import replace

    return replace(result, url=url)


def _read_text(relpath: str | None) -> str:
    if not relpath:
        return ""
    try:
        return resolve_raw_path(relpath).read_bytes().decode("utf-8", errors="replace")
    except (OSError, ValueError):
        return ""


def _complex_id(session: Session, region_id: int, house_manage_no: str) -> int | None:
    stmt = select(Complex.id).where(Complex.applyhome_id == house_manage_no, Complex.region_id == region_id)
    return session.scalars(stmt).first()

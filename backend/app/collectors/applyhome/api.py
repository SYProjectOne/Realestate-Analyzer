"""청약홈 공식 API (공공데이터포털 → api.odcloud.kr) 요청 형식 — 2026-10-09 swagger·실제 호출로 확인.

서비스 두 개 (키 = ``DATA_GO_KR_KEY`` 하나, 서비스마다 data.go.kr '활용신청'이 따로 필요)

1. 한국부동산원_청약홈 분양정보 조회 서비스 (data.go.kr 15098547, swagger
   ``infuser.odcloud.kr/api/stages/37000/api-docs``) ``/ApplyhomeInfoDetailSvc/v1/…``
   - ``getAPTLttotPblancDetail`` APT 분양정보 상세(주택관리번호·공고번호·주택명·공급위치·공급규모·청약일정·
     당첨자발표일·계약일·입주예정월·시행사·시공사 …), ``getAPTLttotPblancMdl`` 주택형별(주택형·공급면적·
     일반/특별 세대수·분양최고금액(만원))
   - ``getRemndrLttotPblancDetail``/``…Mdl`` APT 잔여세대(무순위 04·불법행위 재공급 06)
   - ``getOPTLttotPblancDetail``/``…Mdl`` 임의공급(11)
   조건: ``cond[필드::연산]`` 쿼리 — ``SUBSCRPT_AREA_CODE::EQ``(공급지역코드 '400'…), ``HSSPLY_ADRES::LIKE``,
   ``RCRIT_PBLANC_DE::GTE/LTE``(모집공고일), ``HOUSE_MANAGE_NO::EQ``·``PBLANC_NO::EQ``.
   ``SUBSCRPT_AREA_CODE_NM::EQ``(공급지역명 = 시도 약칭 '인천'·'경기')는 APT 상세 swagger 에만 적혀 있지만
   잔여세대·임의공급에도 동작한다(실제 호출로 확인). 이름을 쓰므로 지역 코드 표가 필요 없다 —
   웹 목록의 ``suplyAreaCode`` 와 같은 값(area.py ``sido_short_name``).
   모집공고일 값 형식: APT·잔여세대 'YYYY-MM-DD', 임의공급 'YYYYMMDD' → 조건도 그 형식으로 보낸다.
2. 한국부동산원_청약홈 청약접수 경쟁률 및 특별공급 신청현황 조회 서비스 (data.go.kr 15098905, swagger
   ``infuser.odcloud.kr/api/stages/36148/api-docs``) ``/ApplyhomeInfoCmpetRtSvc/v1/…``
   - ``getAPTLttotPblancCmpet`` APT 경쟁률(주택형·공급세대수·순위·거주지역·접수건수·경쟁률),
     ``getRemndrLttotPblancCmpet``, ``getOPTLttotPblancCmpet``
   이 서비스는 '청약 신청·당첨자 정보 조회 서비스'(15110812, ``ApplyhomeStatSvc`` — 지역·월 단위 통계)와
   **다른 서비스**다. 키가 15098905 에 활용신청되지 않았으면 odcloud 는 401
   ``{"code":-401,"msg":"유효하지 않은 인증키 입니다."}`` 를 준다 → 웹 경쟁률 팝업으로 폴백.

응답(JSON): ``{"page","perPage","totalCount","currentCount","matchCount","data":[…]}``. 오류는 4xx +
``{"code":-401,"msg":…}``. 인증: 쿼리 ``serviceKey``(디코딩 키) — **raw_document.url 에는 남기지 않는다**.
robots.txt: api.odcloud.kr 는 404(키 인증 API 라 core.http 예외 호스트에도 넣었다).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date
from typing import Any, Final, Literal
from urllib.parse import unquote, urlencode

from app.collectors.applyhome.site import ListKind
from app.core.http import FetchResult, HttpClient

__all__ = [
    "API_KINDS",
    "BASE",
    "ENDPOINTS",
    "PER_PAGE",
    "ApiKind",
    "ApiPage",
    "ApiRow",
    "ApplyhomeApi",
    "doc_url",
    "item_params",
    "list_params",
    "parse_page",
    "to_row",
]

BASE: Final = "https://api.odcloud.kr/api"
HOST: Final = "api.odcloud.kr"
DETAIL_SVC: Final = "/ApplyhomeInfoDetailSvc/v1"
CMPET_SVC: Final = "/ApplyhomeInfoCmpetRtSvc/v1"
PER_PAGE: Final = 100

ApiKind = Literal["apt", "remndr", "opt"]
API_KINDS: Final[tuple[ApiKind, ...]] = ("apt", "remndr", "opt")


@dataclass(frozen=True, slots=True)
class ApiEndpoints:
    detail: str
    model: str
    competition: str
    date_format: str  # 모집공고일 조건 값 형식
    web_kind: ListKind  # 같은 공고의 청약홈 웹 화면(폴백·공고문 링크)


ENDPOINTS: Final[dict[ApiKind, ApiEndpoints]] = {
    "apt": ApiEndpoints(
        f"{DETAIL_SVC}/getAPTLttotPblancDetail",
        f"{DETAIL_SVC}/getAPTLttotPblancMdl",
        f"{CMPET_SVC}/getAPTLttotPblancCmpet",
        "%Y-%m-%d",
        "apt",
    ),
    "remndr": ApiEndpoints(
        f"{DETAIL_SVC}/getRemndrLttotPblancDetail",
        f"{DETAIL_SVC}/getRemndrLttotPblancMdl",
        f"{CMPET_SVC}/getRemndrLttotPblancCmpet",
        "%Y-%m-%d",
        "remndr",
    ),
    # 임의공급은 웹에서 잔여세대 화면(selectAPTRemndrLttotPblancDetailView)으로 열린다(PBLANC_URL 도 같다)
    "opt": ApiEndpoints(
        f"{DETAIL_SVC}/getOPTLttotPblancDetail",
        f"{DETAIL_SVC}/getOPTLttotPblancMdl",
        f"{CMPET_SVC}/getOPTLttotPblancCmpet",
        "%Y%m%d",
        "remndr",
    ),
}


def list_params(kind: ApiKind, area: str, begin: date, end: date, page: int) -> dict[str, str]:
    """시도(약칭) 하나·모집공고일 [begin, end] 의 상세 목록 한 페이지."""
    fmt = ENDPOINTS[kind].date_format
    return {
        "page": str(page),
        "perPage": str(PER_PAGE),
        "cond[SUBSCRPT_AREA_CODE_NM::EQ]": area,
        "cond[RCRIT_PBLANC_DE::GTE]": begin.strftime(fmt),
        "cond[RCRIT_PBLANC_DE::LTE]": end.strftime(fmt),
    }


def item_params(house_manage_no: str, pblanc_no: str) -> dict[str, str]:
    """공고 1건(주택관리번호 + 공고번호)의 상세·주택형·경쟁률."""
    return {
        "page": "1",
        "perPage": str(PER_PAGE),
        "cond[HOUSE_MANAGE_NO::EQ]": house_manage_no,
        "cond[PBLANC_NO::EQ]": pblanc_no,
    }


def doc_url(path: str, params: dict[str, str]) -> str:
    """raw_document.url — 무엇을 조회했는지(경로 + 조건), 키 없음."""
    return f"{BASE}{path}?{urlencode(params)}"


@dataclass(frozen=True, slots=True)
class ApiPage:
    ok: bool  # 2xx 이고 data 배열이 있다
    rows: list[dict[str, Any]]
    match_count: int | None
    error: str | None  # 실패 사유('401', 'api: <msg>', 'json' …)


def parse_page(result: FetchResult) -> ApiPage:
    if not result.ok:
        msg = _error_msg(result.content)
        reason = str(result.status) if result.status is not None else (result.error_kind or "network")
        return ApiPage(False, [], None, f"{reason}: {msg}" if msg else reason)
    try:
        data = json.loads(result.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ApiPage(False, [], None, "json")
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        msg = data.get("msg") if isinstance(data, dict) else None
        return ApiPage(False, [], None, f"api: {msg}" if msg else "api")
    rows = [r for r in data["data"] if isinstance(r, dict)]
    match = data.get("matchCount")
    return ApiPage(True, rows, match if isinstance(match, int) else None, None)


def _error_msg(content: bytes) -> str | None:
    try:
        data = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    msg = data.get("msg") if isinstance(data, dict) else None
    return str(msg) if msg else None


def iso_date(value: object) -> str | None:
    """'2026-10-08' · '20261008' → '2026-10-08'. 아니면 None."""
    if not isinstance(value, str):
        return None
    digits = value.replace("-", "").replace(".", "").strip()
    if len(digits) != 8 or not digits.isdigit():
        return None
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"


@dataclass(frozen=True, slots=True)
class ApiRow:
    kind: ApiKind
    house_manage_no: str
    pblanc_no: str
    name: str
    address: str | None
    area_name: str | None  # SUBSCRPT_AREA_CODE_NM (시도 약칭)
    notice_date: str | None  # 모집공고일 ISO
    last_date: str | None  # 청약 마감·당첨자 발표 중 늦은 것 — since 판단용(웹 목록과 같은 뜻)


def to_row(kind: ApiKind, d: dict[str, Any]) -> ApiRow | None:
    hm, pb = str(d.get("HOUSE_MANAGE_NO") or "").strip(), str(d.get("PBLANC_NO") or "").strip()
    if not hm or not pb:
        return None
    dates = [
        x
        for x in (
            iso_date(d.get("PRZWNER_PRESNATN_DE")),
            iso_date(d.get("RCEPT_ENDDE")),
            iso_date(d.get("SUBSCRPT_RCEPT_ENDDE")),
        )
        if x
    ]
    address = d.get("HSSPLY_ADRES")
    area = d.get("SUBSCRPT_AREA_CODE_NM")
    return ApiRow(
        kind=kind,
        house_manage_no=hm,
        pblanc_no=pb,
        name=str(d.get("HOUSE_NM") or ""),
        address=str(address) if address else None,
        area_name=str(area) if area else None,
        notice_date=iso_date(d.get("RCRIT_PBLANC_DE")),
        last_date=max(dates) if dates else None,
    )


class ApplyhomeApi:
    """odcloud 호출. 키는 쿼리로만 보내고 돌려주는 ``FetchResult.url`` 은 키 없는 조회 주소다."""

    def __init__(self, http: HttpClient, service_key: str) -> None:
        self._http = http
        # 포털은 인코딩 키(%2B…)와 디코딩 키를 준다 — httpx 가 다시 인코딩하므로 디코딩 형태로
        self._key = unquote(service_key)

    def get(self, path: str, params: dict[str, str]) -> FetchResult:
        result = self._http.get(BASE + path, params={**params, "serviceKey": self._key})
        # final_url 에는 serviceKey 가 들어 있다 — 저장·로그로 새지 않게 지운다(오류 문구도 혹시 몰라 가린다)
        error = result.error.replace(self._key, "***") if result.error else None
        return replace(result, url=doc_url(path, params), final_url=None, error=error)

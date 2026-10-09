"""청약홈(www.applyhome.co.kr) 요청 형식 — 2026-10-09 실제 사이트에서 확인.

목록 2종은 ``POST application/x-www-form-urlencoded`` 로 조회하는 서버 렌더 HTML 이다(페이지당 10행).

- 폼 필드: ``beginPd``/``endPd`` (YYYYMM, 끝-시작 ≤ 11개월 — 사이트가 12개월 넘는 조회를 막는다),
  ``suplyAreaCode`` (시도 약칭 '서울'·'경기'… — 코드가 아니라 이름), ``houseNm``, ``pageIndex``.
- 행: ``<tr data-pbno data-hmno [data-hsecd] data-honm>`` — 공고번호·주택관리번호·(잔여) 공급 구분·주택명.
  목록에는 공급위치(주소)가 없다. 주소는 상세 팝업의 '공급위치' 칸에만 있다.

상세·경쟁률 팝업은 ``GET ?houseManageNo=&pblancNo=`` 로도 같은 HTML 을 준다(브라우저는 POST).
모집공고문 PDF 는 상세 팝업의 ``https://static.applyhome.co.kr/ai/aia/getAtchmnfl.do?...`` 링크다.
robots.txt 는 두 호스트 모두 404(= 제한 없음, RFC 9309).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal
from urllib.parse import urlencode

BASE: Final = "https://www.applyhome.co.kr"
STATIC_HOST: Final = "static.applyhome.co.kr"

ListKind = Literal["apt", "remndr"]
LIST_KINDS: Final[tuple[ListKind, ...]] = ("apt", "remndr")
MAX_WINDOW_MONTHS: Final = 12  # 사이트 제한: endPd - beginPd ≤ 11


@dataclass(frozen=True, slots=True)
class Endpoints:
    list_path: str
    detail_path: str
    competition_path: str


ENDPOINTS: Final[dict[ListKind, Endpoints]] = {
    # APT 분양정보/경쟁률
    "apt": Endpoints(
        "/ai/aia/selectAPTLttotPblancListView.do",
        "/ai/aia/selectAPTLttotPblancDetail.do",
        "/ai/aia/selectAPTCompetitionPopup.do",
    ),
    # APT 잔여세대(무순위·임의공급·불법행위 재공급)
    "remndr": Endpoints(
        "/ai/aia/selectAPTRemndrLttotPblancListView.do",
        "/ai/aia/selectAPTRemndrLttotPblancDetailView.do",
        "/ai/aia/selectAPTRemndrCompetitionPopup.do",
    ),
}


def list_url(kind: ListKind) -> str:
    return BASE + ENDPOINTS[kind].list_path


def list_form(area: str, begin_ym: str, end_ym: str, page: int) -> dict[str, str]:
    """목록 POST 본문. ym 은 'YYYYMM'."""
    return {
        "beginPd": begin_ym,
        "endPd": end_ym,
        "houseDetailSecd": "",
        "suplyAreaCode": area,
        "houseNm": "",
        "pageIndex": str(page),
    }


def list_doc_url(kind: ListKind, form: dict[str, str]) -> str:
    """raw_document.url 로 남기는 목록 주소 — POST 본문을 쿼리 문자열로 붙여 무엇을 조회했는지 남긴다."""
    return f"{list_url(kind)}?{urlencode(form)}"


def detail_url(kind: ListKind, house_manage_no: str, pblanc_no: str) -> str:
    q = urlencode({"houseManageNo": house_manage_no, "pblancNo": pblanc_no})
    return f"{BASE}{ENDPOINTS[kind].detail_path}?{q}"


def competition_url(kind: ListKind, house_manage_no: str, pblanc_no: str) -> str:
    q = urlencode({"houseManageNo": house_manage_no, "pblancNo": pblanc_no})
    return f"{BASE}{ENDPOINTS[kind].competition_path}?{q}"

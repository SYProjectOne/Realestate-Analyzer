"""청약홈 HTML 에서 수집에 필요한 최소 정보만 읽는다(목록 행·공급위치·공고문 링크).

필드 정규화(세대수·가격·일정 등)는 WP2 ``normalize/applyhome_parser.py`` 몫이다. 여기서는 다음 요청을 정하는
데 필요한 것만 꺼낸다 — 판단 없음, 문자열 처리만.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Tag

from app.collectors.applyhome.site import STATIC_HOST, ListKind

__all__ = [
    "ListPage",
    "ListRow",
    "detail_house_name",
    "detail_supply_address",
    "notice_pdf_links",
    "parse_list",
]

_TOTAL_RE = re.compile(r"총게시물\s*:\s*<b[^>]*>\s*([\d,]+)")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class ListRow:
    kind: ListKind
    house_manage_no: str
    pblanc_no: str
    name: str
    area: str  # 목록 '지역' 칸(시도 약칭)
    house_secd: str | None  # 잔여세대 목록의 공급 구분 코드(04 무순위, 06 불법행위 재공급, 11 임의공급)
    notice_date: str | None  # 모집공고일 YYYY-MM-DD
    last_date: str | None  # 행에 적힌 날짜 중 가장 늦은 것(청약 마감·당첨자 발표) — since 판단용


@dataclass(frozen=True, slots=True)
class ListPage:
    total: int | None  # '총게시물' 숫자. 페이지 형식이 바뀌어 못 읽으면 None
    rows: list[ListRow]


def _text(node: Tag) -> str:
    return _WS_RE.sub(" ", node.get_text(" ", strip=True)).strip()


def parse_list(html: str, kind: ListKind) -> ListPage:
    m = _TOTAL_RE.search(html)
    total = int(m.group(1).replace(",", "")) if m else None
    soup = BeautifulSoup(html, "lxml")
    rows: list[ListRow] = []
    for tr in soup.select("tr[data-hmno]"):
        hm = str(tr.get("data-hmno") or "").strip()
        pb = str(tr.get("data-pbno") or "").strip() or hm
        if not hm.isdigit():
            continue
        cells = [_text(td) for td in tr.find_all("td", recursive=False)]
        dates = sorted({d for c in cells for d in _DATE_RE.findall(c)})
        notice = next((c for c in cells if _DATE_RE.fullmatch(c)), None)
        secd = tr.get("data-hsecd")
        rows.append(
            ListRow(
                kind=kind,
                house_manage_no=hm,
                pblanc_no=pb,
                name=str(tr.get("data-honm") or "").strip(),
                area=cells[0] if cells else "",
                house_secd=str(secd).strip() if secd is not None else None,
                notice_date=notice,
                last_date=dates[-1] if dates else None,
            )
        )
    return ListPage(total=total, rows=rows)


def _label_value(soup: BeautifulSoup, label: str) -> str | None:
    """``<td>라벨</td><td>값</td>`` (또는 th) 모양의 값 칸."""
    for cell in soup.find_all(["td", "th"]):
        if _text(cell) == label:
            nxt = cell.find_next_sibling(["td", "th"])
            if isinstance(nxt, Tag):
                value = _text(nxt)
                return value or None
    return None


def detail_supply_address(html: str) -> str | None:
    """상세 팝업의 '공급위치'. 없으면 None."""
    return _label_value(BeautifulSoup(html, "lxml"), "공급위치")


def detail_house_name(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    node = soup.select_one("#houseNmBanner")
    return _text(node) if node is not None else None


def notice_pdf_links(html: str) -> list[str]:
    """상세 팝업의 모집공고문 첨부 링크(static.applyhome.co.kr ``getAtchmnfl.do``), 문서 순서·중복 제거.

    호스트는 **정확히** ``STATIC_HOST`` 여야 한다(R3 minor 17: 부분 문자열 비교는
    ``static.applyhome.co.kr.evil.example``·``evil.example/?static.applyhome.co.kr`` 를 통과시킨다).
    scheme 은 http·https 만.
    """
    soup = BeautifulSoup(html, "lxml")
    out: list[str] = []
    for a in soup.find_all("a", href=True):
        href = str(a["href"]).strip().replace("&amp;", "&")
        try:
            parts = urlsplit(href)
            host = (parts.hostname or "").lower()
        except ValueError:
            continue
        if (
            parts.scheme in ("http", "https")
            and host == STATIC_HOST
            and parts.path.endswith("getAtchmnfl.do")
            and href not in out
        ):
            out.append(href)
    return out

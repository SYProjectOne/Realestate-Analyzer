"""청약홈 HTML(목록·상세·경쟁률) → 필드 후보 (WP2).

- applyhome_list: APT 분양정보 목록 표의 ``tr[data-hmno]`` → 단지 이름·시공사·공고일·당첨자발표일
- applyhome_detail(상세 팝업 ``selectAPTLttotPblancDetail``): 주요정보·청약일정·공급대상·
  공급금액(최고가, 만원)·입주예정월·시행사/시공사·홈페이지(당첨자 발표 칸 링크 → official_site_url)
- applyhome_detail(경쟁률 팝업 ``selectAPTCompetitionPopup``): 주택형·공급세대수·순위·지역·
  접수건수·경쟁률(미달), 당첨가점 최저·최고·평균(R9-PARSE Q4 — competition.winning_score_*, 회차 '1순위 <거주지역>' 행)

source_rank는 RA §3 표(app.normalize.fields): 세대수·면적·일정·경쟁률은 청약홈 1, 가격은 청약홈 2.
청약홈 상세 화면에는 층별 가격이 없으므로 가격은 '최고가 기준' 하나만 낸다(max_price_won).
complex_type.notice_type_code = 청약홈 주택형 원문('084.9582').
observed_on = 그 단지의 모집공고일(계약 2026-10-09.2).

같은 source_kind 의 청약홈 공식 API JSON(호스트 api.odcloud.kr)은 ``applyhome_api_parser`` 로 넘긴다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import re
from bisect import bisect_right
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from app.core.contracts_gen import FieldCandidate, RawDocument
from app.normalize._text import (
    CandidateBuilder,
    area_from_long_code,
    canonical_json,
    normalize_site_url,
    normalize_type_code,
    parse_date,
    parse_won,
    read_raw_text,
    stamp_observed_on,
)
from app.normalize.applyhome_api_parser import (
    apply_items,
    apply_text,
    is_api_document,
    parse_applyhome_api_json,
)
from app.normalize.fields import WINNING_SCORE_FIELDS

__all__ = ["ApplyhomeParser", "parse_applyhome_html"]

_LONG_RE = re.compile(r"^0?\d{2,3}\.\d{4}[A-Z]?\d?$")
_MGMT_RE = re.compile(r"(\d{10})\(\d+\)")
_HOUSE_NO_RE = re.compile(r"(?:houseManageNo|pblancNo)=(\d{10})")
_DATE_ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


class ApplyhomeParser:
    """``Parser`` 구현 — source_kind ∈ {applyhome_list, applyhome_detail}."""

    def __init__(self, *, raw_dir: Path | None = None) -> None:
        self._raw_dir = raw_dir

    def parse(self, raw: RawDocument) -> list[FieldCandidate]:
        if raw.http_status not in (None, 200):
            return []
        html = read_raw_text(raw, raw_dir=self._raw_dir)
        if html is None:
            return []
        if is_api_document(raw):
            return parse_applyhome_api_json(html, raw)
        return parse_applyhome_html(html, raw)


class _Pos:
    """bs4(html.parser) 태그의 (sourceline, sourcepos) → 원문 문자 오프셋."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.starts = [0]
        for m in re.finditer("\n", text):
            self.starts.append(m.end())

    def at(self, tag: Tag) -> int:
        line = tag.sourceline or 1
        col = tag.sourcepos or 0
        return self.starts[min(line - 1, len(self.starts) - 1)] + col

    def span(self, tag: Tag) -> tuple[int, int]:
        start = self.at(tag)
        close = f"</{tag.name}>"
        end = self.text.find(close, start)
        return (start, end + len(close) if end >= 0 else start + 1)

    def line_of(self, pos: int) -> int:
        return bisect_right(self.starts, pos) - 1


def _cells(tr: Tag) -> list[Tag]:
    return [c for c in tr.find_all(["td", "th"], recursive=False) if isinstance(c, Tag)]


def _txt(t: Tag) -> str:
    return " ".join(t.get_text(" ", strip=True).split())


def _table(soup: BeautifulSoup, caption: str) -> Tag | None:
    for cap in soup.find_all("caption"):
        if caption in _txt(cap):
            parent = cap.parent
            if isinstance(parent, Tag):
                return parent
    return None


def parse_applyhome_html(html: str, raw: RawDocument) -> list[FieldCandidate]:
    """청약홈 HTML → 후보 (순수 함수)."""
    soup = BeautifulSoup(html, "html.parser")
    b = CandidateBuilder(raw, html)
    pos = _Pos(html)
    if soup.select("tr[data-hmno]"):
        _list(soup, b, pos)
    elif soup.find("td", class_="cpHouseTy") is not None:
        _competition(soup, b, pos, raw)
    else:
        _detail(soup, b, pos, raw)
    # 원문 시점 = 그 단지(주택관리번호)의 모집공고일. 경쟁률 화면처럼 공고일이 없으면 None.
    days = {
        str(c.entity_key): c.value
        for c in b.out
        if c.entity == "complex" and c.field == "notice_date" and isinstance(c.value, str)
    }
    return stamp_observed_on(b.out, lambda c: days.get(str(c.entity_key or "").split(":")[0]))


# ---------------------------------------------------------------- 목록


def _list(soup: BeautifulSoup, b: CandidateBuilder, pos: _Pos) -> None:
    for tr in soup.select("tr[data-hmno]"):
        key = str(tr.get("data-hmno") or "")
        cells = _cells(tr)
        if not key or len(cells) < 9:
            continue
        span = pos.span(tr)
        row_text = " | ".join(_txt(c) for c in cells[:9])
        name = _txt(cells[3])
        b.add("complex", key, "name", name, name, span, excerpt=row_text)
        if _txt(cells[1]) in ("민영", "국민"):
            b.add("complex", key, "housing_type", _txt(cells[1]), _txt(cells[1]), span, excerpt=row_text)
        builder = _txt(cells[4])
        if builder:
            b.add("complex", key, "builder", builder, builder, span, excerpt=row_text)
        for idx, fname in ((6, "notice_date"), (8, "winner_date")):
            d = parse_date(_txt(cells[idx]))
            if d:
                b.add("complex", key, fname, d, _txt(cells[idx]), span, excerpt=row_text)


# ---------------------------------------------------------------- 상세


def _detail_key(soup: BeautifulSoup, raw: RawDocument) -> str:
    m = _HOUSE_NO_RE.search(raw.url)
    if m:
        return m.group(1)
    for td in soup.find_all("td"):
        mm = _MGMT_RE.search(_txt(td))
        if mm:
            return mm.group(1)
    a = soup.find("a", href=_HOUSE_NO_RE)
    if isinstance(a, Tag):
        m2 = _HOUSE_NO_RE.search(str(a.get("href")))
        if m2:
            return m2.group(1)
    return ""


def _detail(soup: BeautifulSoup, b: CandidateBuilder, pos: _Pos, raw: RawDocument) -> None:
    key = _detail_key(soup, raw)
    if not key:
        return
    info = _table(soup, "주요정보")
    if info is not None:
        th = info.find("th")
        if isinstance(th, Tag):
            name = _txt(th)
            b.add("complex", key, "name", name, name, pos.span(th), excerpt=name)
        for tr in info.find_all("tr"):
            cells = _cells(tr)
            if len(cells) != 2:
                continue
            label, value = _txt(cells[0]), _txt(cells[1])
            ex = f"{label} {value}"
            if label.startswith("공급위치"):
                b.add("complex", key, "address", value, value, pos.span(tr), excerpt=ex)
            elif label.startswith("공급규모"):
                m = re.search(r"([\d,]+)\s*세대", value)
                if m:
                    b.add(
                        "complex",
                        key,
                        "units_total",
                        int(m.group(1).replace(",", "")),
                        value,
                        pos.span(tr),
                        excerpt=ex,
                    )
    sched = _table(soup, "청약일정")
    if sched is not None:
        _schedule(sched, b, pos, key)
    supply = _table(soup, "입주자모집공고 공급대상")
    if supply is not None:
        _supply(supply, b, pos, key)
    price = _table(soup, "공급금액")
    if price is not None:
        for tr in price.find_all("tr"):
            cells = _cells(tr)
            if len(cells) < 2 or not _LONG_RE.match(_txt(cells[0])):
                continue
            long_code, v = _txt(cells[0]), _txt(cells[1])
            if not re.fullmatch(r"[\d,]+", v):
                continue
            tkey = f"{key}:{normalize_type_code(long_code)}"
            ex = f"{long_code} 공급금액(최고가 기준, 만원) {v}"
            b.add(
                "complex_type",
                tkey,
                "max_price_won",
                parse_won(v, unit="만원"),
                f"{v}만원",
                pos.span(tr),
                excerpt=ex,
            )
    for li in soup.find_all("li"):
        t = _txt(li)
        m = re.search(r"입주예정월\s*:\s*(\d{4})\.(\d{1,2})", t)
        if m:
            ym = f"{m.group(1)}-{int(m.group(2)):02d}"
            b.add("complex", key, "move_in_ym", ym, f"{m.group(1)}.{m.group(2)}", pos.span(li), excerpt=t)
    etc = _table(soup, "기타사항")
    if etc is not None:
        heads = [_txt(h) for h in etc.find_all("th")]
        body = etc.find("tbody")
        row = body.find("tr") if isinstance(body, Tag) else None
        if isinstance(row, Tag):
            vals = [_txt(c) for c in _cells(row)]
            for h, v in zip(heads, vals, strict=False):
                field = {"시행사": "developer", "시공사": "builder"}.get(h)
                if field and v:
                    b.add("complex", key, field, v, v, pos.span(row), excerpt=f"{h} {v}")


_AREA_HEADS = ("해당지역", "기타경기", "기타지역")


def _schedule(tbl: Tag, b: CandidateBuilder, pos: _Pos, key: str) -> None:
    """청약일정 표. 접수 일정(R9-PARSE Q3)은 API 원문과 같은 모양(``apply_items``): 특별공급 = 지역 칸 전체의 처음~끝,
    1·2순위 = 지역 칸(머리 '해당지역'·'기타경기'·'기타지역')마다 처음~끝, 잔여세대·임의공급 '청약접수' 한 칸 = 처음~끝."""
    found: dict[str, tuple[str, str]] = {}
    apply_span: tuple[int, int] | None = None
    apply_ex: list[str] = []
    areas: list[str] = []
    for tr in tbl.find_all("tr"):
        cells = _cells(tr)
        if not cells:
            continue
        texts = [_txt(c) for c in cells]
        if "구분" in texts:  # 접수 표 머리: '구분 해당지역 [기타경기] 기타지역 접수장소'
            i = texts.index("구분")
            areas = texts[i + 1 :]
            continue
        head = texts[0]
        if head == "청약접수" and len(cells) == 2:  # 잔여세대·임의공급: 칸 하나에 기간
            dates = _DATE_ISO_RE.findall(texts[1])
            if dates:
                found["청약접수"] = (dates[0], dates[-1])
                apply_ex.append(" ".join(texts))
                span = pos.span(tr)
                apply_span = (apply_span[0], span[1]) if apply_span else span
            continue
        if head == "청약접수" and len(cells) > 2:
            cells, texts = cells[1:], texts[1:]  # 첫 접수 행에 rowspan 머리가 붙은 경우
            head = texts[0]
        span = pos.span(tr)
        ex = " ".join(texts)
        if head == "모집공고일" and len(cells) > 1:
            d = parse_date(_txt(cells[1]))
            if d:
                b.add("complex", key, "notice_date", d, _txt(cells[1]), span, excerpt=ex)
        elif head.replace(" ", "") == "당첨자발표일" and len(cells) > 1:
            d = parse_date(_txt(cells[1]))
            if d:
                b.add(
                    "complex", key, "winner_date", d, _txt(cells[1]).split("(")[0].strip(), span, excerpt=ex
                )
            # 당첨자 발표 칸의 '( 홈페이지 링크 )' = 단지 공식 홈페이지(R3b 마무리) → official_site_url
            link = cells[1].find("a", href=True)
            site = normalize_site_url(str(link.get("href"))) if isinstance(link, Tag) else None
            if site and isinstance(link, Tag):
                b.add(
                    "complex", key, "official_site_url", site, str(link.get("href")), pos.span(link),
                    excerpt=f"{head} 홈페이지 {link.get('href')}",
                )  # fmt: skip
        elif head == "계약일" and len(cells) > 1:
            dates = _DATE_ISO_RE.findall(_txt(cells[1]))
            if dates:
                val = [{"from": dates[0], "to": dates[-1]}]
                b.add("complex", key, "contract_dates", canonical_json(val), _txt(cells[1]), span, excerpt=ex)
        elif head in ("특별공급", "일반공급", "1순위", "2순위") and len(cells) > 1:
            per_area = [
                (areas[i] if i < len(areas) else "", _DATE_ISO_RE.findall(t)) for i, t in enumerate(texts[1:])
            ]
            if head in ("특별공급", "일반공급"):
                every = sorted(d for _, ds in per_area for d in ds)
                if every:
                    found[head] = (every[0], every[-1])
            else:
                for area, ds in per_area:
                    if ds and area in _AREA_HEADS:
                        found[f"{head} {area}"] = (ds[0], ds[-1])
                    elif ds and not areas:  # 머리 행이 없는 옛 표: 첫 칸 = 해당지역
                        found.setdefault(f"{head} 해당지역", (ds[0], ds[-1]))
            if any(ds for _, ds in per_area):
                apply_ex.append(ex)
                apply_span = (apply_span[0], span[1]) if apply_span else span
    applies = apply_items(found)
    if applies and apply_span:
        b.add(
            "complex",
            key,
            "apply_dates",
            canonical_json(applies),
            apply_text(applies),
            apply_span,
            excerpt=" / ".join(apply_ex),
        )


def _supply(tbl: Tag, b: CandidateBuilder, pos: _Pos, key: str) -> None:
    for tr in tbl.find_all("tr"):
        cells = _cells(tr)
        texts = [_txt(c) for c in cells]
        span = pos.span(tr)
        ex = " ".join(texts)
        if texts and texts[0] in ("민영", "국민"):
            b.add("complex", key, "housing_type", texts[0], texts[0], span, excerpt=ex)
            texts = texts[1:]
        if len(texts) >= 5 and _LONG_RE.match(texts[0]):
            long_code = texts[0]
            tkey = f"{key}:{normalize_type_code(long_code)}"
            area = area_from_long_code(long_code)
            if area is not None:
                b.add("complex_type", tkey, "area_m2", area, long_code, span, excerpt=ex)
            b.add("complex_type", tkey, "notice_type_code", long_code, long_code, span, excerpt=ex)
            if texts[4].isdigit():
                b.add("complex_type", tkey, "units", int(texts[4]), texts[4], span, excerpt=ex)
        elif texts and texts[0] == "계" and len(texts) >= 4:
            gen, spc = texts[1], texts[2]
            if gen.isdigit():
                b.add("complex", key, "units_general", int(gen), gen, span, excerpt=ex)
            if spc.isdigit():
                b.add("complex", key, "units_special", int(spc), spc, span, excerpt=ex)


# ---------------------------------------------------------------- 경쟁률


def _competition(soup: BeautifulSoup, b: CandidateBuilder, pos: _Pos, raw: RawDocument) -> None:
    key = _detail_key(soup, raw)
    if not key:
        return
    for td in soup.find_all("td", class_="cpHouseTy"):
        tr = td.parent
        if not isinstance(tr, Tag):
            continue
        cells = _cells(tr)
        if len(cells) < 7:
            continue
        long_code, supply, rank, area_kind, applied, ratio = (_txt(c) for c in cells[:6])
        type_code = normalize_type_code(long_code)
        rnd = f"{rank} {area_kind}".strip()
        ckey = f"{key}:본청약:{rnd}:{type_code}"
        span = pos.span(tr)
        ex = " ".join(_txt(c) for c in cells[:7])
        if supply.isdigit():
            b.add("competition", ckey, "supply", int(supply), supply, span, excerpt=ex)
        if applied.replace(",", "").isdigit():
            b.add("competition", ckey, "applied", int(applied.replace(",", "")), applied, span, excerpt=ex)
        if ratio:
            b.add("competition", ckey, "ratio_or_shortfall_text", ratio, ratio, span, excerpt=ex)
        _winning_scores(tr, cells, b, pos, key, type_code, long_code)


_SCORE_RE = re.compile(r"^\d{1,2}(?:\.\d{1,2})?$")


def _winning_scores(
    tr: Tag, cells: list[Tag], b: CandidateBuilder, pos: _Pos, key: str, type_code: str, long_code: str
) -> None:
    """당첨가점 칸(R9-PARSE Q4): ``td.cpResideSenm``(거주지역) 뒤 세 칸 = 최저·최고·평균(가점제 당첨자만 — 1순위). 팝업은 이 묶음을
    1·2순위 행 옆에 지역마다 rowspan 으로 붙인다 — 칸에 적힌 지역의 '1순위 <지역>' 경쟁률 행에 단다. '-'(발표 전·가점 당첨자
    없음)·숫자 아닌 칸은 후보를 내지 않는다(값 없음). 숫자는 원문 그대로(0 포함)."""
    for i, c in enumerate(cells):
        if "cpResideSenm" not in (c.get("class") or []):
            continue
        area = _txt(c)
        vals = [_txt(x) for x in cells[i + 1 : i + 4]]
        if not area or len(vals) != 3:
            return
        ckey = f"{key}:본청약:1순위 {area}:{type_code}"
        ex = f"{long_code} 당첨가점 {area} 최저 {vals[0]} 최고 {vals[1]} 평균 {vals[2]}"
        span = pos.span(tr)
        for fname, v in zip(WINNING_SCORE_FIELDS, vals, strict=True):
            if _SCORE_RE.match(v):
                b.add("competition", ckey, fname, float(v), v, span, excerpt=ex)
        return

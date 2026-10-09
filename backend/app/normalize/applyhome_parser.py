"""청약홈 HTML(목록·상세·경쟁률) → 필드 후보 (WP2).

- applyhome_list: APT 분양정보 목록 표의 ``tr[data-hmno]`` → 단지 이름·시공사·공고일·당첨자발표일
- applyhome_detail(상세 팝업 ``selectAPTLttotPblancDetail``): 주요정보·청약일정·공급대상·
  공급금액(최고가, 만원)·입주예정월·시행사/시공사
- applyhome_detail(경쟁률 팝업 ``selectAPTCompetitionPopup``): 주택형·공급세대수·순위·지역·
  접수건수·경쟁률(미달)

source_rank는 RA §3 표(app.normalize.fields): 세대수·면적·일정·경쟁률은 청약홈 1, 가격은 청약홈 2.
청약홈 상세 화면에는 층별 가격이 없으므로 가격은 '최고가 기준' 하나만 낸다(max_price_won).
"""

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
    normalize_type_code,
    parse_date,
    parse_won,
    read_raw_text,
)

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
    return b.out


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


def _schedule(tbl: Tag, b: CandidateBuilder, pos: _Pos, key: str) -> None:
    applies: list[dict[str, str]] = []
    apply_span: tuple[int, int] | None = None
    apply_ex: list[str] = []
    for tr in tbl.find_all("tr"):
        cells = _cells(tr)
        if not cells:
            continue
        head = _txt(cells[0])
        span = pos.span(tr)
        ex = " ".join(_txt(c) for c in cells)
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
        elif head == "계약일" and len(cells) > 1:
            dates = _DATE_ISO_RE.findall(_txt(cells[1]))
            if dates:
                val = [{"from": dates[0], "to": dates[-1]}]
                b.add("complex", key, "contract_dates", canonical_json(val), _txt(cells[1]), span, excerpt=ex)
        elif head in ("특별공급", "1순위", "2순위") and len(cells) > 1:
            dates = _DATE_ISO_RE.findall(_txt(cells[1]))
            if dates:
                applies.append({"kind": head, "date": dates[0]})
                apply_ex.append(ex)
                apply_span = (apply_span[0], span[1]) if apply_span else span
    if applies and apply_span:
        b.add(
            "complex",
            key,
            "apply_dates",
            canonical_json(applies),
            "; ".join(f"{a['kind']} {a['date']}" for a in applies),
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

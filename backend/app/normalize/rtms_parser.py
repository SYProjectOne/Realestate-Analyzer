"""국토교통부 아파트 매매 실거래가 응답(XML) → rtms_trade 후보 (WP2).

Open API(apis.data.go.kr …/RTMSDataSvcAptTrade) 응답의 ``<item>``마다 후보를 만든다.
영문 태그(신규 API: aptNm, umdNm, sggCd, umdCd, excluUseAr, floor, dealAmount(만원),
dealYear/Month/Day, buildYear, cdealType)와 한글 태그(구 API: 아파트, 법정동, 지역코드,
법정동읍면동코드, 전용면적, 층, 거래금액, 년/월/일, 건축년도, 해제여부)를 둘 다 읽는다.

- Open API URL이면 label '확인됨'·source 'openapi'·rank 1, 그 밖(재가공 사이트 사본)은
  label '재가공'·source 'reprocessed'·rank 2(2차 자료). 둘 중 무엇을 점수에 쓸지는 WP4(RA §3).
- entity_key = '<시군구코드>:<아파트>:<거래일>:<층>:<면적>:<금액>:<동>'
  (같은 거래 = 같은 키 → 재수집해도 행이 늘지 않는다).
"""

from __future__ import annotations

import re
from pathlib import Path
from xml.etree import ElementTree as ET

from app.core.contracts_gen import FieldCandidate, RawDocument
from app.normalize._text import CandidateBuilder, parse_won, read_raw_text, round_area, stamp_observed_on

__all__ = ["RtmsParser", "is_openapi_url", "parse_rtms_xml"]

_TAGS: dict[str, tuple[str, ...]] = {
    "apt": ("aptNm", "아파트"),
    "umd": ("umdNm", "법정동"),
    "sgg": ("sggCd", "지역코드"),
    "umd_cd": ("umdCd", "법정동읍면동코드"),
    "area": ("excluUseAr", "전용면적"),
    "floor": ("floor", "층"),
    "amount": ("dealAmount", "거래금액"),
    "y": ("dealYear", "년"),
    "m": ("dealMonth", "월"),
    "d": ("dealDay", "일"),
    "built": ("buildYear", "건축년도"),
    "cancel": ("cdealType", "해제여부"),
    "apt_dong": ("aptDong", "동"),
}


def is_openapi_url(url: str) -> bool:
    return bool(re.search(r"apis\.data\.go\.kr|openapi\.molit\.go\.kr", url))


class RtmsParser:
    """``Parser`` 구현 — source_kind='rtms'."""

    def __init__(self, *, raw_dir: Path | None = None) -> None:
        self._raw_dir = raw_dir

    def parse(self, raw: RawDocument) -> list[FieldCandidate]:
        if raw.http_status not in (None, 200):
            return []
        text = read_raw_text(raw, raw_dir=self._raw_dir)
        return [] if text is None else parse_rtms_xml(text, raw)


def _get(item: ET.Element, key: str) -> str:
    for tag in _TAGS[key]:
        el = item.find(tag)
        if el is not None and el.text is not None and el.text.strip():
            return el.text.strip()
    return ""


def parse_rtms_xml(text: str, raw: RawDocument) -> list[FieldCandidate]:
    b = CandidateBuilder(raw, text)
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    openapi = is_openapi_url(raw.url)
    label = "확인됨" if openapi else "재가공"
    source = "openapi" if openapi else "reprocessed"
    search_from = 0
    for item in root.iter("item"):
        apt, amount = _get(item, "apt"), _get(item, "amount")
        y, m, d = _get(item, "y"), _get(item, "m"), _get(item, "d")
        area_t, floor_t = _get(item, "area"), _get(item, "floor")
        if not (apt and amount and y and m and d and area_t):
            continue
        deal_date = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        price = parse_won(amount, unit="만원")
        area = round_area(area_t)
        sgg, umd_cd = _get(item, "sgg"), _get(item, "umd_cd")
        apt_dong = _get(item, "apt_dong")
        key = f"{sgg}:{apt}:{deal_date}:{floor_t}:{area}:{price}:{apt_dong}"
        # 원문 위치: 이 item의 아파트 이름이 처음 나오는 곳부터 다음 </item>까지
        start = text.find(apt, search_from)
        if start < 0:
            start = search_from
        end = text.find("</item>", start)
        end = len(text) if end < 0 else end + len("</item>")
        search_from = end
        span = (start, end)
        ex = f"{apt} {_get(item, 'umd')} {area_t}㎡ {floor_t}층 {amount}만원 {deal_date}"
        cancelled = _get(item, "cancel") in ("O", "o", "Y", "y")
        umd = _get(item, "umd") or None
        built = _get(item, "built")
        fields: list[tuple[str, float | int | str | bool | None, str | None]] = [
            ("apt_name", apt, apt),
            ("dong", umd, umd),
        ]
        if sgg and umd_cd and len(sgg + umd_cd) == 10:
            fields.append(("legal_dong_code", sgg + umd_cd, sgg + umd_cd))
        if built.isdigit():
            fields.append(("completed_year", int(built), built))
        fields.append(("area_m2", area, area_t))
        if re.fullmatch(r"-?\d+", floor_t):
            fields.append(("floor", int(floor_t), floor_t))
        fields += [
            ("price_won", price, f"{amount}만원"),
            ("deal_date", deal_date, f"{y}.{m}.{d}"),
            ("cancelled", cancelled, _get(item, "cancel") or ""),
            ("source", source, source),
        ]
        for fname, value, vt in fields:
            # RA §3 실거래: Open API(1) > 재가공 사이트(2, 2차 자료)
            b.add(
                "rtms_trade",
                key,
                fname,
                value,
                vt,
                span,
                label=label,
                excerpt=ex,
                rank=1 if openapi else 2,
                primary=openapi,
            )
    # 원문 시점 = 거래일(계약 2026-10-09.2 observed_on)
    deals = {str(c.entity_key): c.value for c in b.out if c.field == "deal_date" and isinstance(c.value, str)}
    return stamp_observed_on(b.out, lambda c: deals.get(str(c.entity_key)))

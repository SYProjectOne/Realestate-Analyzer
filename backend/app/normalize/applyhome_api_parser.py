"""청약홈 공식 API JSON(api.odcloud.kr) → 필드 후보 (R2X, ``collectors/applyhome/api.py`` 가 받은 원문).

source_kind 는 HTML 과 같다(``applyhome_list``·``applyhome_detail``) — 그래서 출처 rank·라벨도 청약홈 상세와
같다(RA §3 표: 세대수·면적·일정·경쟁률 1, 가격 2, 라벨 '확인됨'). 엔드포인트는 URL 경로로 가린다.

- ``applyhome_list``(시도 단위 목록 페이지): 후보를 내지 않는다. 지역 밖 단지까지 들어 있고, 지역 안 단지는
  수집기가 공고 1건 조회(상세)로 다시 받아 그 원문이 후보를 낸다(목록에서 단지 행을 만들지 않기 위해).
- ``…LttotPblancDetail``(APT·잔여세대·임의공급 상세): complex — name·address·units_total·housing_type·
  builder·developer·notice_date·winner_date·move_in_ym·contract_dates·apply_dates·official_site_url(HMPG_ADRES,
  ``_text.normalize_site_url``).
- ``…LttotPblancMdl``(주택형별): complex_type — area_m2·notice_type_code·units(일반+특별)·max_price_won(만원),
  complex — units_general·units_special(페이지에 모든 주택형이 있을 때만 합계).
- ``…LttotPblancCmpet``(경쟁률): competition — supply·applied·ratio_or_shortfall_text.
  APT = kind '본청약', round '<순위>순위 <거주지역>'(웹 경쟁률 팝업과 같은 키). 잔여세대 = '무순위',
  임의공급 = '임의'(round = '<kind> <공고번호>').

observed_on = 모집공고일(상세 원문의 RCRIT_PBLANC_DE). 주택형·경쟁률 원문에는 공고일이 없어 None
(HTML 경쟁률과 같다).
발췌 = 원문 JSON 의 ``"필드":값`` 조각, 오프셋은 원문 텍스트 위치.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.core.contracts_gen import FieldCandidate, RawDocument
from app.normalize._text import (
    CandidateBuilder,
    area_from_long_code,
    canonical_json,
    normalize_site_url,
    normalize_type_code,
    parse_won,
    read_raw_text,
    stamp_observed_on,
)

__all__ = ["API_HOST", "ApplyhomeApiParser", "is_api_document", "parse_applyhome_api_json"]

API_HOST = "api.odcloud.kr"
_YM_RE = re.compile(r"^(\d{4})(\d{2})$")
_KIND_BY_PATH = (("Remndr", "무순위"), ("OPT", "임의"))


def is_api_document(raw: RawDocument) -> bool:
    """청약홈 공식 API 원문인가(URL 호스트)."""
    return urlsplit(raw.url).hostname == API_HOST


class ApplyhomeApiParser:
    """``Parser`` 구현 — 청약홈 공식 API JSON."""

    def __init__(self, *, raw_dir: Path | None = None) -> None:
        self._raw_dir = raw_dir

    def parse(self, raw: RawDocument) -> list[FieldCandidate]:
        if raw.http_status not in (None, 200):
            return []
        text = read_raw_text(raw, raw_dir=self._raw_dir)
        if text is None:
            return []
        return parse_applyhome_api_json(text, raw)


# ---------------------------------------------------------------- JSON 위치


def _row_spans(text: str) -> list[tuple[int, int]]:
    """``"data":[ {...}, {...} ]`` 안 객체들의 [시작, 끝) 오프셋(값에 중첩 객체 없음 — 평평한 행)."""
    start = text.find('"data"')
    if start < 0:
        return []
    i = text.find("[", start)
    spans: list[tuple[int, int]] = []
    depth, in_str, esc, obj_start = 0, False, False, -1
    while 0 <= i < len(text):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and obj_start >= 0:
                spans.append((obj_start, i + 1))
        elif ch == "]" and depth == 0:
            break
        i += 1
    return spans


def _field_span(text: str, row: tuple[int, int], name: str) -> tuple[int, int]:
    """행 안 ``"name":값`` 의 [시작, 끝). 못 찾으면 행 전체."""
    key = f'"{name}":'
    s = text.find(key, row[0], row[1])
    if s < 0:
        return row
    j = s + len(key)
    in_str = text[j : j + 1] == '"'
    j += 1 if in_str else 0
    while j < row[1]:
        ch = text[j]
        if in_str:
            if ch == "\\":
                j += 2
                continue
            if ch == '"':
                return s, j + 1
        elif ch in ",}":
            return s, j
        j += 1
    return s, row[1]


def _rows(text: str) -> Iterator[tuple[dict[str, Any], tuple[int, int]]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return
    rows = data.get("data") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return
    spans = _row_spans(text)
    for i, row in enumerate(rows):
        if isinstance(row, dict):
            yield row, spans[i] if i < len(spans) else (0, len(text))


# ---------------------------------------------------------------- 값


def _str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _int(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    s = _str(v)
    if s is None:
        return None
    s = s.replace(",", "")
    return int(s) if s.isdigit() else None


def _iso(v: Any) -> str | None:
    s = _str(v)
    if s is None:
        return None
    digits = s.replace("-", "").replace(".", "")
    if len(digits) != 8 or not digits.isdigit():
        return None
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"


def _ym(v: Any) -> str | None:
    s = _str(v)
    m = _YM_RE.match(s.replace("-", "").replace(".", "")) if s else None
    if m is None or not 1 <= int(m.group(2)) <= 12:
        return None
    return f"{m.group(1)}-{m.group(2)}"


# ---------------------------------------------------------------- 파서


def parse_applyhome_api_json(text: str, raw: RawDocument) -> list[FieldCandidate]:
    """청약홈 API JSON → 후보 (순수 함수)."""
    if raw.source_kind != "applyhome_detail":
        return []  # 목록 페이지: 위 모듈 설명
    path = urlsplit(raw.url).path
    b = CandidateBuilder(raw, text)
    if path.endswith("Detail"):
        _detail(text, b)
    elif path.endswith("Mdl"):
        _model(text, b)
    elif path.endswith("Cmpet"):
        _competition(text, b, path)
    days = {
        str(c.entity_key): c.value
        for c in b.out
        if c.entity == "complex" and c.field == "notice_date" and isinstance(c.value, str)
    }
    return stamp_observed_on(b.out, lambda c: days.get(str(c.entity_key or "").split(":")[0]))


def _add(
    b: CandidateBuilder,
    text: str,
    span: tuple[int, int],
    entity: str,
    key: str,
    field: str,
    name: str,
    value: float | int | str | None,
    value_text: str | None = None,
) -> None:
    if value is None:
        return
    s = _field_span(text, span, name)
    b.add(
        entity,
        key,
        field,
        value,
        value_text if value_text is not None else str(value),
        s,
        excerpt=text[s[0] : s[1]],
    )


def _detail(text: str, b: CandidateBuilder) -> None:
    for row, span in _rows(text):
        key = _str(row.get("HOUSE_MANAGE_NO"))
        if key:
            _detail_row(text, b, row, span, key)


def _detail_row(text: str, b: CandidateBuilder, row: dict[str, Any], span: tuple[int, int], key: str) -> None:
    def add(field: str, name: str, value: float | int | str | None, vt: str | None = None) -> None:
        _add(b, text, span, "complex", key, field, name, value, vt)

    add("name", "HOUSE_NM", _str(row.get("HOUSE_NM")))
    add("address", "HSSPLY_ADRES", _str(row.get("HSSPLY_ADRES")))
    add("units_total", "TOT_SUPLY_HSHLDCO", _int(row.get("TOT_SUPLY_HSHLDCO")))
    htype = _str(row.get("HOUSE_DTL_SECD_NM"))
    if htype in ("민영", "국민"):
        add("housing_type", "HOUSE_DTL_SECD_NM", htype)
    add("builder", "CNSTRCT_ENTRPS_NM", _str(row.get("CNSTRCT_ENTRPS_NM")))
    # 단지 공식 홈페이지(R3b 마무리) → complex.official_site_url — official_site 수집기의 대상
    site = normalize_site_url(_str(row.get("HMPG_ADRES")))
    add("official_site_url", "HMPG_ADRES", site, _str(row.get("HMPG_ADRES")))
    add("developer", "BSNS_MBY_NM", _str(row.get("BSNS_MBY_NM")))
    add(
        "notice_date",
        "RCRIT_PBLANC_DE",
        _iso(row.get("RCRIT_PBLANC_DE")),
        _str(row.get("RCRIT_PBLANC_DE")),
    )
    add(
        "winner_date",
        "PRZWNER_PRESNATN_DE",
        _iso(row.get("PRZWNER_PRESNATN_DE")),
        _str(row.get("PRZWNER_PRESNATN_DE")),
    )
    add("move_in_ym", "MVN_PREARNGE_YM", _ym(row.get("MVN_PREARNGE_YM")), _str(row.get("MVN_PREARNGE_YM")))
    c_from, c_to = _iso(row.get("CNTRCT_CNCLS_BGNDE")), _iso(row.get("CNTRCT_CNCLS_ENDDE"))
    if c_from:
        val = [{"from": c_from, "to": c_to or c_from}]
        add("contract_dates", "CNTRCT_CNCLS_BGNDE", canonical_json(val), f"{c_from} ~ {c_to or c_from}")
    # 청약 일정: 웹 상세와 같은 종류 이름(특별공급·1순위·2순위), 잔여세대·임의공급은 '청약접수'
    applies: list[dict[str, str]] = []
    first_field: str | None = None
    for kind, name in (
        ("특별공급", "SPSPLY_RCEPT_BGNDE"),
        ("1순위", "GNRL_RNK1_CRSPAREA_RCPTDE"),
        ("2순위", "GNRL_RNK2_CRSPAREA_RCPTDE"),
        ("일반공급", "GNRL_RCEPT_BGNDE"),
        ("청약접수", "SUBSCRPT_RCEPT_BGNDE"),
    ):
        d = _iso(row.get(name))
        if d:
            applies.append({"kind": kind, "date": d})
            first_field = first_field or name
    if applies and first_field:
        add(
            "apply_dates",
            first_field,
            canonical_json(applies),
            "; ".join(f"{a['kind']} {a['date']}" for a in applies),
        )


def _model(text: str, b: CandidateBuilder) -> None:
    rows = list(_rows(text))
    general = special = 0
    complete = True
    key = ""
    for row, span in rows:
        key = _str(row.get("HOUSE_MANAGE_NO")) or key
        long_code = _str(row.get("HOUSE_TY"))
        if not key or not long_code:
            complete = False
            continue
        tkey = f"{key}:{normalize_type_code(long_code)}"
        area = area_from_long_code(long_code)
        if area is not None:
            _add(b, text, span, "complex_type", tkey, "area_m2", "HOUSE_TY", area, long_code)
        _add(b, text, span, "complex_type", tkey, "notice_type_code", "HOUSE_TY", long_code)
        gen, spc = _int(row.get("SUPLY_HSHLDCO")), _int(row.get("SPSPLY_HSHLDCO"))
        if gen is not None:
            units = gen + (spc or 0)
            _add(b, text, span, "complex_type", tkey, "units", "SUPLY_HSHLDCO", units, str(units))
            general += gen
            special += spc or 0
        else:
            complete = False
        amount = _str(row.get("LTTOT_TOP_AMOUNT"))
        if amount and re.fullmatch(r"[\d,]+", amount):
            won = parse_won(amount, unit="만원")
            _add(
                b,
                text,
                span,
                "complex_type",
                tkey,
                "max_price_won",
                "LTTOT_TOP_AMOUNT",
                won,
                f"{won // 10_000:,}만원",
            )
    match = _match_count(text)
    if key and rows and complete and match == len(rows):
        whole = (0, len(text))
        s = _field_span(text, whole, "matchCount")
        b.add(
            "complex",
            key,
            "units_general",
            general,
            str(general),
            s,
            excerpt=f"주택형 {len(rows)}개 일반공급 합계 {general}",
        )
        if any("SPSPLY_HSHLDCO" in r for r, _ in rows):
            b.add(
                "complex",
                key,
                "units_special",
                special,
                str(special),
                s,
                excerpt=f"주택형 {len(rows)}개 특별공급 합계 {special}",
            )


def _match_count(text: str) -> int | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    m = data.get("matchCount") if isinstance(data, dict) else None
    return m if isinstance(m, int) else None


def _competition(text: str, b: CandidateBuilder, path: str) -> None:
    kind = next((k for marker, k in _KIND_BY_PATH if marker in path), "본청약")
    for row, span in _rows(text):
        key = _str(row.get("HOUSE_MANAGE_NO"))
        long_code = _str(row.get("HOUSE_TY"))
        if not key or not long_code:
            continue
        if kind == "본청약":
            rank = _str(row.get("SUBSCRPT_RANK_CODE"))
            reside = _str(row.get("RESIDE_SENM")) or ""
            rnd = f"{rank}순위 {reside}".strip() if rank else reside
        else:
            rnd = f"{kind} {_str(row.get('PBLANC_NO')) or ''}".strip()
        ckey = f"{key}:{kind}:{rnd}:{normalize_type_code(long_code)}"
        _add(b, text, span, "competition", ckey, "supply", "SUPLY_HSHLDCO", _int(row.get("SUPLY_HSHLDCO")))
        applied = _int(row.get("REQ_CNT"))
        _add(b, text, span, "competition", ckey, "applied", "REQ_CNT", applied, _str(row.get("REQ_CNT")))
        _add(
            b,
            text,
            span,
            "competition",
            ckey,
            "ratio_or_shortfall_text",
            "CMPET_RATE",
            _str(row.get("CMPET_RATE")),
        )

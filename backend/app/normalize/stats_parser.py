"""미분양 통계 표(CSV) → unsold 후보 (WP2).

국토교통 통계누리 '미분양주택현황보고'를 내려받은 CSV(UTF-8 또는 CP949)를 읽는다. 열 이름으로 열을 찾는다:
지역(시군구·구분·지역) · 지역코드(선택) · 연월(시점·기간·연월) · 미분양(합계·미분양 호수) · 준공후 미분양.
연월 표기 '2026.08' · '2026-08' · '202608' · '2026년 8월'을 'YYYY-MM'으로 바꾼다.
entity_key = '<지역코드 또는 지역명>:<YYYY-MM>'. 라벨은 '확인됨'(공식 통계 원문). observed_on = 기준월 말일.
입주물량(supply) 집계는 공고문 입주예정월 합산(추정)이라 여기서 하지 않는다.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from app.core.contracts_gen import FieldCandidate, RawDocument
from app.normalize._text import CandidateBuilder, month_end, read_raw_text, stamp_observed_on

__all__ = ["StatsParser", "parse_unsold_csv"]

_COLS: dict[str, tuple[str, ...]] = {
    "name": ("시군구", "지역", "구분", "시도"),
    "code": ("지역코드", "시군구코드", "코드"),
    "ym": ("연월", "시점", "기간", "월"),
    "post": ("준공후", "준공 후"),
    "total": ("미분양", "합계", "전체"),
}


def _ym(text: str) -> str | None:
    m = re.search(r"(\d{4})\D{0,3}(\d{1,2})", text)
    if not m:
        return None
    mo = int(m.group(2))
    return f"{m.group(1)}-{mo:02d}" if 1 <= mo <= 12 else None


def _int(text: str) -> int | None:
    s = text.replace(",", "").strip()
    return int(s) if re.fullmatch(r"-?\d+", s) else None


class StatsParser:
    """``Parser`` 구현 — source_kind='stats'."""

    def __init__(self, *, raw_dir: Path | None = None) -> None:
        self._raw_dir = raw_dir

    def parse(self, raw: RawDocument) -> list[FieldCandidate]:
        if raw.http_status not in (None, 200):
            return []
        text = read_raw_text(raw, raw_dir=self._raw_dir)
        return [] if text is None else parse_unsold_csv(text, raw)


def _find_cols(header: list[str]) -> dict[str, int]:
    """열 이름 → 열 번호. 키마다 우선순위 높은 이름부터 찾고, 한 열은 한 키에만 쓴다(준공후 미분양 먼저)."""
    norm = [h.replace(" ", "") for h in header]
    used: set[int] = set()
    found: dict[str, int] = {}
    for key in ("post", "code", "ym", "total", "name"):
        for pat in _COLS[key]:
            p = pat.replace(" ", "")
            idx = next((i for i, h in enumerate(norm) if p in h and i not in used), None)
            if idx is not None:
                found[key] = idx
                used.add(idx)
                break
    return found


def parse_unsold_csv(text: str, raw: RawDocument) -> list[FieldCandidate]:
    b = CandidateBuilder(raw, text)
    lines = text.splitlines(keepends=True)
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    cols = _find_cols(rows[0])
    if not {"ym", "total"} <= cols.keys() or not ({"name", "code"} & cols.keys()):
        return []
    offset = len(lines[0]) if lines else 0
    for i, row in enumerate(rows[1:], start=1):
        line = lines[i] if i < len(lines) else ""
        span = (offset, offset + max(1, len(line.rstrip("\r\n"))))
        offset += len(line)
        if len(row) <= max(cols.values()):
            continue
        ym = _ym(row[cols["ym"]])
        name = row[cols["name"]].strip() if "name" in cols else ""
        code = row[cols["code"]].strip() if "code" in cols else ""
        total = _int(row[cols["total"]])
        if ym is None or total is None or not (name or code):
            continue
        key = f"{code or name}:{ym}"
        ex = ", ".join(row)
        b.add("unsold", key, "ym", ym, row[cols["ym"]], span, excerpt=ex)
        if name:
            b.add("unsold", key, "scope_name", name, name, span, excerpt=ex)
        if code:
            b.add("unsold", key, "scope_code", code, code, span, excerpt=ex)
        b.add("unsold", key, "total", total, row[cols["total"]], span, excerpt=ex)
        if "post" in cols:
            post = _int(row[cols["post"]])
            if post is not None:
                b.add("unsold", key, "post_completion", post, row[cols["post"]], span, excerpt=ex)
    # 원문 시점 = 기준월의 말일(계약 2026-10-09.2 observed_on)
    yms = {str(c.entity_key): c.value for c in b.out if c.field == "ym" and isinstance(c.value, str)}
    return stamp_observed_on(b.out, lambda c: month_end(str(yms.get(str(c.entity_key), ""))))

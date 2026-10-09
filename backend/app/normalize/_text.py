"""파서 공용 도구: 원문 읽기, 금액·날짜 정규화, 발췌(오프셋) 붙은 후보 만들기.

정규식은 판단이 아니다(AGENTS 규칙 3). 여기 함수는 표기를 바꾸기만 하고 값을 고르지 않는다.
"""

from __future__ import annotations

import calendar
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from app.core.contracts_gen import FieldCandidate, RawDocument
from app.core.paths import resolve_raw_path
from app.normalize.fields import LABEL_BY_SOURCE, PRIMARY_SOURCES, source_rank

__all__ = [
    "AMOUNT_RE",
    "CandidateBuilder",
    "amounts_in",
    "area_from_long_code",
    "canonical_json",
    "checked_on",
    "line_span",
    "month_end",
    "normalize_type_code",
    "parse_date",
    "parse_won",
    "read_raw_text",
    "round_area",
    "stamp_observed_on",
]

AMOUNT_RE = re.compile(r"\d{1,3}(?:,\d{3})+")
_DATE_RE = re.compile(r"(?<!\d)(\d{2}|\d{4})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})(?!\d)")


def read_raw_text(raw: RawDocument, *, raw_dir: Path | None = None) -> str | None:
    """raw의 추출 텍스트(text_path) 또는 원문(path)을 UTF-8로 읽는다. 실패 행·파일 없음이면 None."""
    for rel in (raw.text_path, raw.path):
        if not rel:
            continue
        p = resolve_raw_path(rel, raw_dir=raw_dir)
        if p.exists():
            data = p.read_bytes()
            for enc in ("utf-8", "cp949"):
                try:
                    return data.decode(enc)
                except UnicodeDecodeError:
                    continue
            return data.decode("utf-8", errors="replace")
    return None


def checked_on(raw: RawDocument) -> str:
    """확인일 = fetched_at의 날짜(YYYY-MM-DD)."""
    return raw.fetched_at[:10]


def parse_won(text: str, *, unit: str = "원") -> int:
    """'770,000,000' → 770000000. unit='만원'이면 ×10,000. '-'·빈칸은 0."""
    s = text.strip().replace(",", "").replace(" ", "")
    if s in {"", "-", "−", "–"}:
        return 0
    n = int(Decimal(s))
    return n * 10_000 if unit == "만원" else n


def amounts_in(line: str) -> list[tuple[int, int, int]]:
    """줄 안의 금액 토큰(3자리 콤마) → [(값, 시작, 끝)]. 붙어 나온 금액('166,127,212315,872,788')도 나눈다."""
    return [(parse_won(m.group(0)), m.start(), m.end()) for m in AMOUNT_RE.finditer(line)]


def parse_date(text: str) -> str | None:
    """'25.07.04.' · '2025.07.04' · '2025-07-04' · '2025년 7월 4일' → '2025-07-04'. 못 읽으면 None."""
    m = _DATE_RE.search(text)
    if not m:
        return None
    y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
    year = int(y) + 2000 if len(y) == 2 else int(y)
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{year:04d}-{mo:02d}-{d:02d}"


def round_area(text: str) -> float:
    """전용면적 '84.7531' → 84.75 (㎡ 소수 2자리, 사사오입)."""
    return float(Decimal(text).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


_LONG_TYPE_RE = re.compile(r"^0*(\d+)\.(\d+)([A-Z]*\d*)$")


def normalize_type_code(code: str) -> str:
    """공고상 주택형 → 약식 type_code. '084.7531A' → '84A', '110.0000P' → '110P'.

    문자 접미사가 없는 '084.9582'는 같은 평형의 다른 타입과 겹칠 수 있어 '84.9582'(앞 0만 제거)로 둔다 —
    저장 단계(store)가 전용면적으로 약식 타입과 맞춘다. 이미 약식이면 그대로.
    """
    c = code.strip()
    m = _LONG_TYPE_RE.match(c)
    if m is None:
        return c
    whole, frac, suffix = m.groups()
    return f"{int(whole)}{suffix}" if suffix and suffix[0].isalpha() else f"{int(whole)}.{frac}"


def area_from_long_code(code: str) -> float | None:
    """'084.7531A' → 84.75 (주택형 = 주거전용면적)."""
    m = _LONG_TYPE_RE.match(code.strip())
    return round_area(f"{int(m.group(1))}.{m.group(2)}") if m else None


def month_end(ym: str) -> str | None:
    """'2026-08' → '2026-08-31' (통계 기준월의 원문 시점). 형식이 아니면 None."""
    m = re.fullmatch(r"(\d{4})-(\d{2})", ym.strip())
    if m is None:
        return None
    y, mo = int(m.group(1)), int(m.group(2))
    if not 1 <= mo <= 12:
        return None
    return f"{y:04d}-{mo:02d}-{calendar.monthrange(y, mo)[1]:02d}"


def stamp_observed_on(
    cands: list[FieldCandidate], observed: str | Callable[[FieldCandidate], str | None] | None
) -> list[FieldCandidate]:
    """후보에 observed_on(원문 시점, 계약 2026-10-09.2)을 붙인 새 목록. 값 또는 후보별 함수."""
    out: list[FieldCandidate] = []
    for c in cands:
        d = observed(c) if callable(observed) else observed
        out.append(c if c.observed_on == d else c.model_copy(update={"observed_on": d}))
    return out


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def line_span(text: str, pos: int) -> tuple[int, int]:
    """pos를 포함하는 줄의 [시작, 끝) 오프셋(개행 제외)."""
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    return start, (len(text) if end < 0 else end)


@dataclass
class CandidateBuilder:
    """raw 한 건에서 나오는 후보를 같은 출처 정보(url·확인일·라벨·rank)로 만든다."""

    raw: RawDocument
    text: str
    url: str | None = None
    out: list[FieldCandidate] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.url is None:
            self.url = self.raw.url

    @property
    def source_kind(self) -> str:
        return self.raw.source_kind

    def add(
        self,
        entity: str,
        key: str | None,
        field_name: str,
        value: float | int | str | bool | None,
        value_text: str | None,
        span: tuple[int, int],
        *,
        label: str | None = None,
        reason: str | None = None,
        needs_extract: bool = False,
        entity_id: int | None = None,
        excerpt: str | None = None,
        rank: int | None = None,
        primary: bool | None = None,
    ) -> FieldCandidate:
        """span = 원문 텍스트 안 발췌 [시작, 끝). 발췌는 그 구간을 포함하는 줄 전체(최소 1자).

        HTML처럼 줄 단위 발췌가 읽기 어려운 원문은 ``excerpt``(셀 텍스트 등)를 직접 주고
        span은 원문 위치로 둔다.
        """
        start, end = span
        if excerpt is not None:
            ls, le = start, end
            excerpt = excerpt.strip() or (value_text or field_name)
        else:
            ls, _ = line_span(self.text, start)
            _, le = line_span(self.text, max(start, end - 1))
            excerpt = self.text[ls:le].strip() or (value_text or field_name)
        kind = self.source_kind
        cand = FieldCandidate(
            entity=entity,
            entity_id=entity_id,
            entity_key=key,
            field=field_name,
            value_text=value_text,
            value=value,
            source_rank=rank if rank is not None else source_rank(entity, field_name, kind),
            source_kind=kind,
            primary=primary if primary is not None else kind in PRIMARY_SOURCES,
            label=(label or LABEL_BY_SOURCE.get(kind, "비공식")),
            reason=reason,
            excerpt=excerpt,
            excerpt_start=ls,
            excerpt_end=le,
            raw_document_id=self.raw.id,
            url=self.url,
            checked_at=checked_on(self.raw),
            needs_extract=needs_extract,
        )
        self.out.append(cand)
        return cand

    def missing(
        self,
        entity: str,
        key: str | None,
        field_name: str,
        span: tuple[int, int],
        reason: str = "파싱 실패",
    ) -> FieldCandidate:
        """정규식·표 파서가 못 읽은 필드: label '확인 불가' + needs_extract=True (판정기 extract로 넘김)."""
        return self.add(
            entity,
            key,
            field_name,
            None,
            None,
            span,
            label="확인 불가",
            reason=reason,
            needs_extract=True,
        )

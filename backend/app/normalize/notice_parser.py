"""입주자모집공고문 텍스트(pdfplumber 추출) → 필드 후보 (WP2, RA §5 WP2 카드).

읽는 것
- 제목 줄('… 입주자모집공고'): 공고 종류(본청약·무순위·임의·선착순)만. **단지 이름 후보는 내지 않는다**
  (R4 C3·D18-4·D11-4: 제목 줄·본문 줄이 '불법행위'·'(임의공급 4차)'·'민영 비규제지역' 같은 이름으로 채택됐다 —
  단지 이름은 청약홈(API·상세)만). 제목 줄에 종류 낱말이 없어도 '최초 주택관리번호'가 이 공고 번호와 다르면 최초
  공고가 아니므로 무순위로 본다(파싱 규칙).
- 머리 표: 주택유형·규제지역·재당첨제한·전매제한·거주의무기간·분양가상한제·택지유형,
  청약 일정(공고일·당첨자발표일)
- 단지 유의사항: 최초 주택관리번호·최초 공고일(임의공급·무순위 공고), 전매제한 문장
- 공급대상 표: 주택형(공고 표기·약식 표기)·전용면적·공급세대수
- 공급금액 표: 층별 행(대지비+건축비[+부가세]=공급금액) → 타입별 최고가·최저층 공급금액,
  계약금·중도금·잔금 비율, 1차 계약금 정액, 중도금 회차 날짜.
  **금액 단위(R4 재시험 N1, D21-1)**: 표 머리·근처의 단위 표기('(단위: 세대, 천원)'·'만원'·'원')를 읽어 원으로 환산한다.
  원이 아닌 단위로 환산한 가격 후보는 출처 발췌에 그 단위 줄을 덧붙인다(단위 근거). 단위가 없으면 원으로 보고 reason
  ``UNIT_ASSUMED``('단위 표기 없음 — 원으로 봄') — 다른 1차 출처와 10배 이상 다르면 resolver 가 compare 로 보낸다
- 발코니 확장 금액 표, 중도금 이자 조건 문장, 선택품목 문장, 입주시기, 공급위치·공급규모

규칙(app.core.protocols.Parser)
- 모든 후보에 원문 발췌(줄 단위)와 오프셋을 붙인다. 금액은 원 단위 정수, 면적 ㎡ 소수 2자리, 날짜 ISO.
- 표 파서가 못 읽은 필드는 label='확인 불가' + needs_extract=True 후보로 낸다(판정기 extract 요청은
  ``app.normalize.extract_request``가 만든다 — 여기서는 판정기를 부르지 않는다).
- 행 → 타입 배정은 공급대상 표의 타입별 공급세대수 합계로 검증한다(행 세대수 합 = 타입 세대수).
  합이 맞지 않으면 추측하지 않고 해당 타입 가격을 needs_extract로 넘긴다.
- 임의공급·무순위·선착순 공고는 잔여 세대 일부만 싣기 때문에 complex_type 의 면적·세대수는 내지 않는다.
  가격(최고가·최저층 공급금액)은 낸다 — 현재 구매가(complex_type 가격) = 현재 조건(최신 공고)의 값
  (계약 2026-10-09.2 payment_terms.price_by_type). 같은 rank 의 공고문끼리는 observed_on(공고일) 최신이
  채택된다.
- 공고별 타입 가격(계약 2026-10-09.2): payment_terms 후보 field='price_by_type.<type_code>.<항목>'
  (max_price_won·floor_sample_price_won·floor_sample_text·units·notice_type_code).
  행 배정이 검증된 타입만 낸다.
  complex_type.notice_type_code = 공고상 주택형 원문('084.7800A').
- observed_on = 이 공고의 공고일(임의공급이면 임의공급 공고일) — 모든 후보에 같다.
- OCR 원문(R3 C3, DECISIONS D5-4): raw.error_text 가 ``ocr``(전 페이지 OCR)·``ocr_partial:<p,…>``(그 페이지만
  OCR, 1부터 센 번호; 텍스트 파일은 페이지마다 ``\f`` 로 나뉜다)이면 OCR 로 읽은 구간에서 나온 값 후보를
  label '추정' + reason 'OCR'(표시 '추정(OCR)')로 내고, 수치·날짜 필드는 모두 needs_extract=True 로 표시한다
  (판정기 extract/audit 를 반드시 거친다 — 반영은 ``normalize.judged.apply_extracted``). 파서가 못 읽은
  필드('확인 불가')는 그대로. ``scan``(전 페이지 텍스트 없음)은 후보가 없다(확인 불가(스캔)).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final
from urllib.parse import parse_qs, urlsplit

from app.core.contracts_gen import FieldCandidate, RawDocument
from app.normalize._text import (
    AMOUNT_RE,
    CandidateBuilder,
    amounts_in,
    canonical_json,
    line_span,
    parse_date,
    parse_won,
    read_raw_text,
    round_area,
    stamp_observed_on,
)
from app.normalize.fields import (
    OCR_LABEL,
    OCR_REASON,
    UNIT_ASSUMED,
    discount_field,
    is_numeric_field,
    price_by_type_field,
)

__all__ = [
    "NoticeParser",
    "PriceRow",
    "TypeSpec",
    "mark_ocr",
    "notice_numbers",
    "ocr_spans",
    "parse_notice_text",
]

_TITLE_LINE_RE = re.compile(r"^.*입주자\s*모집\s*공고.*$", re.M)
_KIND_WORD_RE = re.compile(r"임의\s*공급|무순위|선착순|계약\s*취소|재공급|잔여\s*세대")
# 주택관리번호 10자리. 공고문은 '2025000302'·'2025-000302'·'2025 - 000302'(하이픈·공백)으로 적는다(R4 재시험 N3, D21-3)
_NO_PAT = r"(\d{4})\s*[-‐‑–—]?\s*(\d{6})(?!\d)"
_ORIG_NO_RE = re.compile(r"최초\s*주택관리번호는\s*" + _NO_PAT)
_THIS_NO_RE = re.compile(r"주택관리번호는\s*" + _NO_PAT)


def _no(m: re.Match[str]) -> str:
    """주택관리번호 매치 → 10자리(하이픈·공백 뗌)."""
    return m.group(1) + m.group(2)


_ORIG_DATE_RE = re.compile(r"최초\s*입주자모집공고일은\s*([0-9.\s]+)")
_THIS_DATE_RE = re.compile(r"(?:임의공급|무순위[^\s]*|선착순)\s*입주자모집공고일은\s*([0-9.\s]+)")
_HOUSE_NO_URL_RE = re.compile(r"houseManageNo=(\d{10})")

_SECTION3_RE = re.compile(r"^\d\s+공급(?:대상|내역)\s*및\s*공급금액", re.M)
_PRICE_HEAD_RE = re.compile(r"^■\s*공급\s*금액", re.M)
_BALCONY_HEAD_RE = re.compile(
    r"^■?\s*(?:\(\d\)|\d\.)?\s*발코니\s*확장\s*(?:공사비|공급금액|금액|대금|공사\s*금액)", re.M
)
_LOCATION_RE = re.compile(r"■\s*공급위치\s*:\s*(.+)")
_SCALE_RE = re.compile(r"■\s*공급규모\s*:\s*(.+)")
_MOVE_IN_RE = re.compile(r"■\s*입주(?:시기|예정월?|예정일)\s*:\s*(\d{4})\s*년\s*(\d{1,2})\s*월")
_SPECIAL_RE = re.compile(r"\[\s*특별공급\s*([\d,]+)\s*세대")
_DP_RE = re.compile(r"계약금\s*\(?\s*(\d+(?:\.\d+)?)\s*%\s*\)?")
_INTERIM_RE = re.compile(r"중도금\s*\(?\s*(\d+(?:\.\d+)?)\s*%\s*\)?")
_BALANCE_RE = re.compile(r"잔금\s*\(?\s*(\d+(?:\.\d+)?)\s*%\s*\)?")
_INSTALL_RE = re.compile(r"(\d)\s*(?:회|차)\s*\(\s*(\d+(?:\.\d+)?)\s*%\s*\)")
_DATE_TOKEN_RE = re.compile(r"(?<![\d.])(\d{4}[.\-]\d{1,2}[.\-]\d{1,2}|\d{2}\.\d{1,2}\.\d{1,2})\.?(?![\d])")
_INTEREST_RE = re.compile(r"^.*중도금.*(?:이자후불|무이자|이자\s*대납|이자를\s*대납).*$", re.M)
_OPTIONS_RE = re.compile(r"^.*선택\s*품목.*(?:미포함|포함되지|포함되어\s*있지).*$", re.M)
_BULLET_RE = re.compile(r"^[\s•\-Ÿ⦁※•]+")

# 공급대상 표 행: '04 084.7531A 84A 84.7531 28.0364 ... 50.1011 266 27 ...'
# 하위 타입 행: '84C 84.8600 ... 59.1353 8'
_TYPE_ROW_RE = re.compile(
    r"(?:^|\s)(?:\d{2}\s+)?(?P<long>0?\d{2,3}\.\d{4}[A-Z]?)\s+(?P<short>\d{2,3}[A-Z]{0,2}\d?)\s+"
    r"(?P<area>0?\d{2,3}\.\d{2,4})(?P<areas>(?:\s+\d+\.\d+){3,6})\s+(?P<units>[\d,]+)(?=\s|$)"
)
_SUBTYPE_ROW_RE = re.compile(
    r"^(?P<short>\d{2,3}[A-Z]{1,2}\d?)\s+(?P<area>\d{2,3}\.\d{2,4})(?P<areas>(?:\s+\d+\.\d+){3,6})\s+(?P<units>[\d,]+)(?=\s|$)"
)
# 잔여 세대 공고(임의·무순위)의 공급대상 표: 면적 없이 '01 084.9766C 84C 1 119 3204'(잔여 세대수 + 동·호)
_REMAIN_TYPE_ROW_RE = re.compile(
    r"(?:^|\s)(?:\d{2}\s+)?(?P<long>0?\d{2,3}\.\d{4}[A-Z]?)\s+(?P<short>\d{2,3}[A-Z]{0,2}\d?)\s+(?P<units>\d{1,4})(?=\s|$)"
)
# 잔여 세대 공고: 면적 열은 있고 세대수 열이 동·호 목록으로 갈라진 행(세대수 없음)
_NOUNITS_TYPE_ROW_RE = re.compile(
    r"(?:^|\s)(?:\d{2}\s+)?(?P<long>0?\d{2,3}\.\d{4}[A-Z]?)\s+(?P<short>\d{2,3}[A-Z]{0,2}\d?)\s+"
    r"(?P<area>0?\d{2,3}\.\d{2,4})(?P<areas>(?:\s+\d+\.\d+){3,6})\s*$"
)
_TOTAL_ROW_RE = re.compile(r"^합\s*계\s+([\d,]+)", re.M)
_LEADING_TYPE_RE = re.compile(r"^\s*(?:0?\d{2,3}\.\d{4}[A-Z]?\s+)?(\d{2,3}[A-Z]{0,2}\d?)\s")
_FLOOR_RE = re.compile(
    r"(\d+\s*층?\s*[~\-]\s*\d+\s*층|\d+\s*층\s*이상|\d+층|\d+\s*~\s*\d+|기준층|최상층|최하층|\d+F)"
)

# 머리 표 열 이름 → (필드, 값 패턴)
_HEADER_VALUE = {
    "재당첨제한": r"없음|\d+\s*년",
    "전매제한": r"없음|\d+\s*(?:개월|년)(?:\s*\([^)]*\))?",
    "거주의무기간": r"없음|\d+\s*(?:개월|년)",
    "분양가상한제": r"미적용|적용",
    "택지유형": r"(?:민간택지|공공택지)(?:\s*,\s*[^\s]+)?",
}


@dataclass
class TypeSpec:
    short: str
    long: str
    area_text: str
    units: int | None  # 잔여 세대 공고에서 세대수 열이 없으면 None
    span: tuple[int, int]


@dataclass
class PriceRow:
    total: int
    units: int
    floor_text: str
    after_total: list[int]
    span: tuple[int, int]


@dataclass(frozen=True)
class _Unit:
    """공급금액 표의 금액 단위(D21-1). ``line`` = 단위 표기가 있는 원문 줄(없으면 None — 원으로 봄)."""

    scale: int = 1
    line: str | None = None

    @property
    def found(self) -> bool:
        return self.line is not None


@dataclass
class _Ctx:
    text: str
    raw: RawDocument
    b: CandidateBuilder
    complex_key: str
    notice_no: str
    notice_kind: str
    head_span: tuple[int, int] = (0, 1)
    types: list[TypeSpec] = field(default_factory=list)
    assigned: dict[str, list[PriceRow]] = field(default_factory=dict)
    unit: _Unit = field(default_factory=_Unit)


def _months(token: str) -> int | None:
    m = re.search(r"(\d+)\s*(개월|년)", token)
    if m is None:
        return 0 if "없음" in token else None
    n = int(m.group(1))
    return n if m.group(2) == "개월" else n * 12


def _years(token: str) -> int | None:
    m = re.search(r"(\d+)\s*년", token)
    if m is None:
        return 0 if "없음" in token else None
    return int(m.group(1))


def _line_spans(text: str, start: int, end: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    pos = start
    while pos < end:
        nl = text.find("\n", pos, end)
        stop = end if nl < 0 else nl
        out.append((pos, stop))
        pos = stop + 1
    return out


class NoticeParser:
    """``Parser`` 구현 — source_kind='notice_pdf'."""

    source_kind = "notice_pdf"

    def __init__(self, *, raw_dir: Path | None = None) -> None:
        self._raw_dir = raw_dir

    def parse(self, raw: RawDocument) -> list[FieldCandidate]:
        if raw.http_status not in (None, 200) or (raw.error_text or "").lower() == "scan":
            return _failed(raw)
        text = read_raw_text(raw, raw_dir=self._raw_dir)
        if text is None:
            return _failed(raw)
        return mark_ocr(parse_notice_text(text, raw), ocr_spans(raw.error_text, text))


def ocr_spans(error_text: str | None, text: str) -> list[tuple[int, int]]:
    """OCR 로 읽은 텍스트 구간 [시작, 끝) 목록. OCR 원문이 아니면 [].

    ``ocr`` → 전체. ``ocr_partial:3,4`` → 3·4쪽(``\f`` 로 나뉜 페이지). 페이지 번호를 못 읽으면 전체로 본다
    (보수적으로: OCR 값이 '확인됨'으로 남는 것보다 낫다).
    """
    et = (error_text or "").strip().lower()
    if et == "ocr":
        return [(0, len(text))]
    if not et.startswith("ocr_partial:"):
        return []
    try:
        pages = {int(p) for p in et.split(":", 1)[1].split(",") if p.strip()}
    except ValueError:
        return [(0, len(text))]
    spans: list[tuple[int, int]] = []
    pos = 0
    for no, page in enumerate(text.split("\f"), start=1):
        end = pos + len(page)
        if no in pages:
            spans.append((pos, end))
        pos = end + 1
    return spans or [(0, len(text))]


def mark_ocr(cands: list[FieldCandidate], spans: list[tuple[int, int]]) -> list[FieldCandidate]:
    """OCR 구간에서 나온 값 후보 → label '추정' + reason 'OCR'; 수치·날짜 필드는 needs_extract=True."""
    if not spans:
        return cands
    out: list[FieldCandidate] = []
    for c in cands:
        start = c.excerpt_start or 0
        end = max(start + 1, c.excerpt_end or start + 1)
        in_ocr = any(start < e and s < end for s, e in spans)
        if not in_ocr or c.label == "확인 불가":
            out.append(c)
            continue
        numeric = is_numeric_field(c.entity, c.field, c.value)
        out.append(
            c.model_copy(
                update={
                    "label": OCR_LABEL,
                    "reason": OCR_REASON,
                    "needs_extract": bool(c.needs_extract) or numeric,
                }
            )
        )
    return out


def _failed(raw: RawDocument) -> list[FieldCandidate]:
    """실패 원문(403·스캔 등)은 후보를 내지 않는다.

    실패 자체는 raw_document 행(http_status·error_text)에 남아 있다.
    """
    del raw
    return []


def notice_numbers(raw: RawDocument, *, raw_dir: Path | None = None) -> tuple[str, str | None]:
    """(이 공고의 주택관리번호, 인용한 최초 주택관리번호 — 같거나 없으면 None). 수집 단계가 저장 순서를 정할 때 쓴다
    (D18-4 — 원 번호를 인용한 잔여 공고문을 그 공고의 청약홈 원문보다 먼저). 파싱 규칙(판단 아님)."""
    text = read_raw_text(raw, raw_dir=raw_dir) or ""
    own = _house_no(raw, text)
    orig = _ORIG_NO_RE.search(text)
    cited = _no(orig) if orig and _no(orig) != own else None
    return own, cited


def _house_no(raw: RawDocument, text: str) -> str:
    m = _HOUSE_NO_URL_RE.search(raw.url)
    if m:
        return m.group(1)
    qs = parse_qs(urlsplit(raw.url).query)
    if "pblancNo" in qs:
        return qs["pblancNo"][0]
    return _this_no(text)


def _this_no(text: str) -> str:
    """이 공고의 주택관리번호: '…주택관리번호는 N' 중 '최초 주택관리번호는' 이 아닌 첫 것 — R3 5차 minor: 두 줄의 순서가
    바뀌면('최초' 줄이 먼저) 원 단지 번호를 이 공고 번호로 읽었다."""
    for m in _THIS_NO_RE.finditer(text):
        if re.search(r"최초\s*$", text[max(0, m.start() - 8) : m.start()]):
            continue
        return _no(m)
    return ""


def parse_notice_text(text: str, raw: RawDocument) -> list[FieldCandidate]:
    """공고문 텍스트 → 후보 목록 (순수 함수: 파일·DB 접근 없음)."""
    b = CandidateBuilder(raw, text)
    notice_no = _house_no(raw, text)
    orig = _ORIG_NO_RE.search(text)
    complex_key = _no(orig) if orig else notice_no
    title = _TITLE_LINE_RE.search(text[:2000])
    kind_m = _KIND_WORD_RE.search(title.group(0)) if title else None
    kind_text = kind_m.group(0).replace(" ", "") if kind_m else ""
    notice_kind = (
        "임의"
        if kind_text.startswith("임의")
        else "무순위"  # '재공급'(계약취소 주택 재공급)·잔여세대도 무순위 공급 — R3 5차 minor: '본청약'으로 분류됐다
        if kind_text.startswith(("무순위", "계약취소", "재공급", "잔여"))
        else "선착순"
        if kind_text.startswith("선착순")
        else "무순위"  # 최초 주택관리번호가 따로 있으면 최초 공고가 아니다(R4: '불법행위재공급' 제목이 본청약으로)
        if orig is not None and notice_no and _no(orig) != notice_no
        else "본청약"
    )
    head_end = text.find("\n1 공통")
    ctx = _Ctx(
        text=text,
        raw=raw,
        b=b,
        complex_key=complex_key,
        notice_no=notice_no or complex_key,
        notice_kind=notice_kind,
        head_span=(0, head_end if head_end > 0 else min(len(text), 2000)),
    )
    # D18-4·D11-4: 제목 줄은 단지 이름 후보가 아니다(공고 종류만 읽는다)
    _header(ctx)
    _section3(ctx)
    ctx.types = _type_table(ctx)
    _price_table(ctx)
    if notice_kind == "본청약":
        _balcony(ctx)
        _options(ctx)
    return stamp_observed_on(b.out, _notice_day(b.out, notice_kind))


def _notice_day(cands: list[FieldCandidate], notice_kind: str) -> str | None:
    """이 공고의 공고일(원문 시점) = payment_terms.effective_from. 없으면 본청약만 단지 공고일."""
    for c in cands:
        if c.entity == "payment_terms" and c.field == "effective_from" and isinstance(c.value, str):
            return c.value
    if notice_kind == "본청약":
        for c in cands:
            if c.entity == "complex" and c.field == "notice_date" and isinstance(c.value, str):
                return c.value
    return None


# ---------------------------------------------------------------- 머리 표


def _header(ctx: _Ctx) -> None:
    text, b, key = ctx.text, ctx.b, ctx.complex_key
    hs, he = ctx.head_span
    head = text[hs:he]

    m = re.search(r"(?<![가-힣])(민영|국민)(?![가-힣])", head)
    if m:
        b.add("complex", key, "housing_type", m.group(1), m.group(1), (hs + m.start(), hs + m.end()))
    m = re.search(r"(비규제지역|투기과열지구|조정대상지역|규제지역)(?!\s*여부)", head)
    if m:
        v = "비규제" if m.group(1) == "비규제지역" else "규제"
        b.add("complex", key, "regulated", v, m.group(1), (hs + m.start(), hs + m.end()))

    found: set[str] = set()
    for hm in re.finditer(r"^.*(?:재당첨제한|전매제한|분양가상한제).*$", head, re.M):
        cols = [
            c
            for c in re.findall(
                r"재당첨제한|전매제한|거주의무기간|분양가상한제|택지유형|주택유형|규제지역여부", hm.group(0)
            )
        ]
        cols = [c for c in cols if c in _HEADER_VALUE]
        if len(cols) < 2:
            continue
        line_end = hs + hm.end()
        nl = text.find("\n", line_end + 1)
        vline_start = line_end + 1
        vline = text[vline_start : nl if nl > 0 else len(text)]
        pos = 0
        ok_cols: list[tuple[str, str, tuple[int, int]]] = []
        for col in cols:
            vm = re.compile(r"\s*(" + _HEADER_VALUE[col] + r")").match(vline, pos)
            if vm is None:
                break
            ok_cols.append((col, vm.group(1), (vline_start + vm.start(1), vline_start + vm.end(1))))
            pos = vm.end()
        for col, val, span in ok_cols:
            found.add(col)
            _header_value(ctx, col, val, span)
        if ok_cols:
            break

    _trustee_officetel(ctx)
    if "전매제한" not in found:
        rm = re.search(r"전매제한은[^\n]*?(\d+\s*(?:개월|년))[^\n]*", text)
        if rm:
            _header_value(ctx, "전매제한", rm.group(0), (rm.start(), rm.end()))
        else:
            b.missing("complex", key, "resale_months", ctx.head_span)
    if "거주의무기간" not in found and ctx.notice_kind == "본청약":
        b.missing("complex", key, "residency_months", ctx.head_span)
    _schedule(ctx)


# 신탁(수탁자)·오피스텔 실 수(RA complex.trustee·officetel_units — R3 3차 RA 부분). 표에 이름표가 붙은 값만
# 읽는다: '수탁자(사업주체) 한국자산신탁(주)'·'신탁사: 우리자산신탁 주식회사', '오피스텔 250실'. 납부 계좌
# 예금주처럼 이름표 없는 신탁사 이름은 신탁 관계를 단정할 수 없어 읽지 않는다(추측 금지).
_TRUSTEE_RE = re.compile(
    r"(?:수탁자|신탁사|신탁회사)(?:\s*\([^)\r\n]{0,20}\))?\s*[:：]?\s*"
    r"((?:주식회사\s*)?[가-힣A-Za-z]{2,20}신탁(?:\s*주식회사|\s*\(주\)|\s*㈜)?)"
)
_OFFICETEL_RE = re.compile(r"오피스텔\s*(?:총\s*)?(\d{1,3}(?:,\d{3})*|\d+)\s*실")


def _trustee_officetel(ctx: _Ctx) -> None:
    text, b, key = ctx.text, ctx.b, ctx.complex_key
    m = _TRUSTEE_RE.search(text)
    if m:
        name = " ".join(m.group(1).split())
        b.add("complex", key, "trustee", name, name, m.span(1))
    o = _OFFICETEL_RE.search(text)
    if o:
        units = int(o.group(1).replace(",", ""))
        b.add("complex", key, "officetel_units", units, o.group(0), o.span())


def _header_value(ctx: _Ctx, col: str, val: str, span: tuple[int, int]) -> None:
    b, key = ctx.b, ctx.complex_key
    if col == "재당첨제한":
        b.add("complex", key, "rewin_restriction_years", _years(val), val, span)
    elif col == "전매제한":
        b.add("complex", key, "resale_months", _months(val), val, span)
        release = "소유권이전등기" in val.replace(" ", "")
        if not release:
            # 머리 표 값 바로 아래 줄의 '(단, 기간 내 소유권이전등기 시 해제)' 같은 보충 문장
            nxt = ctx.text[span[1] : ctx.text.find("\n", ctx.text.find("\n", span[1]) + 1)]
            release = "소유권이전등기" in nxt.replace(" ", "") and "해제" in nxt
        b.add(
            "complex",
            key,
            "resale_release_on_registration",
            release,
            "등기 시 해제" if release else "해당 없음",
            span,
        )
    elif col == "거주의무기간":
        b.add("complex", key, "residency_months", _months(val), val, span)
    elif col == "분양가상한제":
        b.add("complex", key, "price_cap", val, val, span)
    elif col == "택지유형":
        v = "공공택지" if val.startswith("공공") else "민간택지"
        b.add("complex", key, "land_type", v, val, span)


def _schedule(ctx: _Ctx) -> None:
    """머리 일정 표: '구분 입주자모집공고일 … 당첨자발표일 …' / '일정 25.07.04.(금) …'."""
    text, b, key = ctx.text, ctx.b, ctx.complex_key
    hs, he = ctx.head_span
    od = _ORIG_DATE_RE.search(text)
    if od and ctx.notice_kind != "본청약":
        d = parse_date(od.group(1))
        if d:
            b.add("complex", key, "notice_date", d, od.group(1).strip(), od.span(1))
        return
    hm = re.search(r"^구분\s+입주자모집공고일.*$", text[hs:he], re.M)
    vm = re.search(r"^일\s*정\s+(.*)$", text[hs:he], re.M)
    if hm is None or vm is None:
        return
    cols = re.findall(r"입주자모집공고일|특별공급|1순위|2순위|당첨자발표일|서류접수|계약체결", hm.group(0))
    vstart = hs + vm.start(1)
    tokens = list(
        re.finditer(
            r"(\d{2,4}\.\s*\d{1,2}\.\s*\d{1,2}\.?(?:\s*\([^)]*\))?)"
            r"(?:\s*~\s*(\d{2,4}\.\s*\d{1,2}\.\s*\d{1,2}\.?(?:\s*\([^)]*\))?))?",
            vm.group(1),
        )
    )
    if not tokens:
        return
    first = tokens[0]
    d0 = parse_date(first.group(1))
    if d0:
        b.add(
            "complex", key, "notice_date", d0, first.group(0), (vstart + first.start(), vstart + first.end())
        )
    if len(tokens) == len(cols) and "당첨자발표일" in cols:
        t = tokens[cols.index("당첨자발표일")]
        dw = parse_date(t.group(1))
        if dw:
            b.add("complex", key, "winner_date", dw, t.group(0), (vstart + t.start(), vstart + t.end()))


# ---------------------------------------------------------------- 공급 개요


def _section3(ctx: _Ctx) -> None:
    text, b, key = ctx.text, ctx.b, ctx.complex_key
    m = _LOCATION_RE.search(text)
    if m:
        addr = m.group(1).strip()
        b.add("complex", key, "address", addr, addr, m.span(1))
    m = _SCALE_RE.search(text)
    if m:
        scale = m.group(1)
        gm = re.search(r"일반\s*분양\s*([\d,]+)\s*세대", scale) or re.search(r"총\s*([\d,]+)\s*세대", scale)
        if gm:
            s = m.start(1) + gm.start(1)
            b.add(
                "complex",
                key,
                "units_total",
                int(gm.group(1).replace(",", "")),
                gm.group(0),
                (s, s + len(gm.group(1))),
            )
        else:
            b.missing("complex", key, "units_total", m.span())
        sm = _SPECIAL_RE.search(text, m.end(), m.end() + 400)
        if sm and ctx.notice_kind == "본청약":
            b.add("complex", key, "units_special", int(sm.group(1).replace(",", "")), sm.group(0), sm.span())
    m = _MOVE_IN_RE.search(text)
    if m:
        ym = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
        b.add("complex", key, "move_in_ym", ym, m.group(0).replace("■", "").strip(), m.span())
    else:
        b.missing("complex", key, "move_in_ym", ctx.head_span)


def _type_table(ctx: _Ctx) -> list[TypeSpec]:
    text = ctx.text
    s3 = _SECTION3_RE.search(text)
    p = _PRICE_HEAD_RE.search(text, s3.end() if s3 else 0)
    start = s3.end() if s3 else 0
    end = p.start() if p else len(text)
    out: list[TypeSpec] = []
    seen: set[str] = set()
    main = ctx.notice_kind == "본청약"
    for ls, le in _line_spans(text, start, end):
        line = text[ls:le]
        m = _TYPE_ROW_RE.search(line) or _SUBTYPE_ROW_RE.search(line)
        if m is None and not main:
            m = _NOUNITS_TYPE_ROW_RE.search(line) or _REMAIN_TYPE_ROW_RE.search(line)
        if m is None:
            continue
        short = m.group("short")
        if short in seen:
            continue
        seen.add(short)
        groups = m.groupdict()
        long = groups.get("long") or ""
        area = groups.get("area") or long
        units = groups.get("units")
        out.append(
            TypeSpec(
                short=short,
                long=long,
                area_text=area.lstrip("0") or area,
                units=int(units.replace(",", "")) if units else None,
                span=(ls, le),
            )
        )
    return out


# ---------------------------------------------------------------- 공급금액 표


def _price_rows(text: str, start: int, end: int) -> list[PriceRow]:
    rows: list[PriceRow] = []
    for ls, le in _line_spans(text, start, end):
        row = _price_row(text[ls:le], (ls, le))
        if row is not None:
            rows.append(row)
    return rows


def _price_row(line: str, span: tuple[int, int]) -> PriceRow | None:
    amts = amounts_in(line)
    if len(amts) < 3:
        return None
    # '-'(부가세 없음)를 0으로 끼워 넣은 금액 열 (값, 원문 시작 위치)
    cols: list[tuple[int, int]] = []
    prev_end = amts[0][1]
    for v, s, e in amts:
        if cols and re.fullmatch(r"\s*[-−–]\s*", line[prev_end:s]):
            cols.append((0, prev_end))
        cols.append((v, s))
        prev_end = e
    values = [v for v, _ in cols]
    # 공급금액 열 = 앞 열(대지비+건축비[+부가세])의 합. 공고 표의 원 단위 끝수(±10원)는 허용한다.
    # 동·호 표기('401,405동')가 금액처럼 보일 수 있어 시작 열도 0~2 중에서 찾는다.
    found: tuple[int, int] | None = None
    for s0 in range(0, 3):
        for k in range(s0 + 2, min(len(values), s0 + 4)):
            if (
                values[k] > 0
                and values[s0] > 0
                and values[k] == max(values)  # 공급금액은 행에서 가장 큰 금액(납부 회차는 그 일부)
                and abs(values[k] - sum(values[s0:k])) <= 10
            ):
                found = (s0, k)
                break
        if found:
            break
    if found is None:
        return None
    s0, k = found
    before = line[: cols[s0][1]]
    # 타입 표기('84A')의 숫자는 세대수·층이 아니다 → 뒤에 영문자가 붙은 숫자는 제외
    ints = list(re.finditer(r"(?<![\d,~\-.])(\d{1,4})(?![\d,층F~\-.A-Z])", before))
    if not ints:
        return None
    units_m = ints[-1]
    floors = [
        fm for fm in _FLOOR_RE.finditer(before) if fm.end() <= units_m.start() or fm.start() >= units_m.end()
    ]
    if floors:
        floor_text = floors[-1].group(0).replace(" ", "")
    elif len(ints) >= 2 and len(before[ints[-2].start() :].split()) == 2:
        # '1 6 …'처럼 층 번호만 있는 표: 세대수 바로 앞 정수가 층
        floor_text = ints[-2].group(1) + "층"
    else:
        floor_text = ""
    return PriceRow(
        total=values[k],
        units=int(units_m.group(1)),
        floor_text=floor_text,
        after_total=values[k + 1 :],
        span=span,
    )


_UNIT_NOTE_RE: Final = re.compile(r"단위\s*[:：]?\s*([^)\]\n]*)")
_MONEY_UNIT_RE: Final = re.compile(r"(?<![가-힣])(백만원|천원|만원|원)(?![가-힣])")
_UNIT_SCALE: Final = {"원": 1, "천원": 1_000, "만원": 10_000, "백만원": 1_000_000}


def _price_unit(text: str, start: int, end: int) -> _Unit:
    """공급금액 표 머리(표 제목 줄 ~ 첫 금액 행)의 단위 표기 → 금액 단위(D21-1). '(단위: ㎡, 세대)'처럼 금액 단위가 없는
    표기는 건너뛴다. 없으면 원으로 본다(``_Unit()`` — 후보 reason ``UNIT_ASSUMED``). 파싱 규칙이다(판단 아님)."""
    for m in _UNIT_NOTE_RE.finditer(text, start, end):
        um = _MONEY_UNIT_RE.search(m.group(1))
        if um is None:
            continue
        ls, le = line_span(text, m.start())
        return _Unit(_UNIT_SCALE[um.group(1)], " ".join(text[ls:le].split()))
    return _Unit()


def _scaled(row: PriceRow, scale: int) -> PriceRow:
    return PriceRow(
        total=row.total * scale,
        units=row.units,
        floor_text=row.floor_text,
        after_total=[v * scale for v in row.after_total],
        span=row.span,
    )


def _unit_kw(ctx: _Ctx, span: tuple[int, int]) -> dict[str, str]:
    """가격 후보의 단위 근거: 원이 아닌 단위로 환산했으면 발췌 = 금액 행 + 단위 표기 줄, 단위 표기가 없으면 reason
    ``UNIT_ASSUMED``. 원 단위 표는 그대로(발췌 = 금액 행)."""
    unit = ctx.unit
    if not unit.found:
        return {"reason": UNIT_ASSUMED}
    if unit.scale == 1:
        return {}
    ls, le = line_span(ctx.text, span[0])
    row_text = ctx.text[ls : max(le, min(span[1], len(ctx.text)))].strip()
    return {"excerpt": f"{row_text}\n[단위 근거] {unit.line}"}


def _assign(rows: list[PriceRow], types: list[TypeSpec]) -> dict[str, list[PriceRow]]:
    """행을 공급대상 표 순서대로 타입에 배정한다. 타입의 행 세대수 합 = 공급세대수일 때만 배정하고,
    처음 어긋난 타입부터는 배정하지 않는다(뒤 타입의 행 경계를 알 수 없으므로)."""
    out: dict[str, list[PriceRow]] = {}
    i = 0
    for t in types:
        if t.units is None:
            break
        acc = 0
        group: list[PriceRow] = []
        while i < len(rows) and acc < t.units:
            group.append(rows[i])
            acc += rows[i].units
            i += 1
        if acc != t.units or not group:
            break
        out[t.short] = group
    return out


def _assign_by_label(
    text: str, rows: list[PriceRow], types: list[TypeSpec], total: int | None
) -> dict[str, list[PriceRow]]:
    """잔여 세대 공고에서 공급대상 표에 세대수가 없을 때: 공급금액 행이 **행 머리에 타입을 적은 경우만**
    그 타입에 배정한다(표를 읽는 것이지 추측이 아니다). 모든 행에 타입 표기가 있어야 하고, 공급대상 표의
    '합 계' 세대수가 있으면 행 세대수 합과 같아야 한다. 하나라도 어긋나면 배정하지 않는다(needs_extract)."""
    shorts = {t.short for t in types}
    out: dict[str, list[PriceRow]] = {}
    for r in rows:
        m = _LEADING_TYPE_RE.match(text[r.span[0] : r.span[1]])
        if m is None or m.group(1) not in shorts:
            return {}
        out.setdefault(m.group(1), []).append(r)
    if not out or (total is not None and sum(r.units for r in rows) != total):
        return {}
    return out


def _price_table(ctx: _Ctx) -> None:
    text, b = ctx.text, ctx.b
    s3 = _SECTION3_RE.search(text)
    p = _PRICE_HEAD_RE.search(text, s3.end() if s3 else 0)
    pay_key = f"{ctx.complex_key}:{ctx.notice_no}"
    if p is None:
        b.missing("payment_terms", pay_key, "down_payment_pct", ctx.head_span, reason="공급금액 표 없음")
        if ctx.notice_kind == "본청약":
            for t in ctx.types:
                b.missing(
                    "complex_type",
                    f"{ctx.complex_key}:{t.short}",
                    "max_price_won",
                    t.span,
                    reason="공급금액 표 없음",
                )
        return
    end = _price_section_end(text, p.end())
    rows = _price_rows(text, p.end(), end)
    head_end = rows[0].span[0] if rows else min(len(text), p.end() + 800)
    ctx.unit = _price_unit(text, p.start(), max(head_end, p.end()))
    if ctx.unit.scale != 1:
        rows = [_scaled(r, ctx.unit.scale) for r in rows]
    _payment_terms(ctx, (p.start(), head_end), rows, pay_key)
    main = ctx.notice_kind == "본청약"
    groups = _assign(rows, ctx.types)
    if not main and any(t.units is None for t in ctx.types):
        s3 = _SECTION3_RE.search(text)
        tm = _TOTAL_ROW_RE.search(text, s3.end() if s3 else 0, p.start())
        total = int(tm.group(1).replace(",", "")) if tm else None
        groups = _assign_by_label(text, rows, ctx.types, total)
    for t in ctx.types:
        tkey = f"{ctx.complex_key}:{t.short}"
        if main and t.units is not None:
            b.add("complex_type", tkey, "area_m2", round_area(t.area_text), t.long or t.area_text, t.span)
            b.add("complex_type", tkey, "units", t.units, str(t.units), t.span)
        if t.long:
            b.add("complex_type", tkey, "notice_type_code", t.long, t.long, t.span)
        g = groups.get(t.short)
        ctx.assigned = groups
        if not g:
            # 표를 못 읽은 타입 — 본청약·잔여 세대 공고 모두 판정기 extract 로 넘긴다(추측 금지, R3 minor 3)
            why = "공급금액 표 행 배정 실패"
            b.missing("complex_type", tkey, "max_price_won", p.span(), reason=why)
            b.missing("complex_type", tkey, "floor_sample_price_won", p.span(), reason=why)
            continue
        top = max(g, key=lambda r: r.total)
        low = min(g, key=lambda r: r.total)
        b.add(
            "complex_type",
            tkey,
            "max_price_won",
            top.total,
            f"{top.total:,}",
            top.span,
            **_unit_kw(ctx, top.span),
        )
        b.add(
            "complex_type", tkey, "floor_sample_price_won", low.total, f"{low.total:,}", low.span,
            **_unit_kw(ctx, low.span),
        )  # fmt: skip
        b.add(
            "complex_type",
            tkey,
            "floor_sample_text",
            low.floor_text or None,
            low.floor_text or None,
            low.span,
        )
        _price_by_type(ctx, pay_key, t, top, low)
    if main and not ctx.types:
        b.missing(
            "complex_type", f"{ctx.complex_key}:?", "max_price_won", p.span(), reason="공급대상 표 없음"
        )


def _price_by_type(ctx: _Ctx, pay_key: str, t: TypeSpec, top: PriceRow, low: PriceRow) -> None:
    """이 공고의 타입 1개 공급가 → payment_terms 후보 'price_by_type.<type>.<항목>' (계약 2026-10-09.2)."""
    b = ctx.b

    def f(item: str) -> str:
        return price_by_type_field(t.short, item)

    b.add(
        "payment_terms",
        pay_key,
        f("max_price_won"),
        top.total,
        f"{top.total:,}",
        top.span,
        **_unit_kw(ctx, top.span),
    )
    b.add(
        "payment_terms", pay_key, f("floor_sample_price_won"), low.total, f"{low.total:,}", low.span,
        **_unit_kw(ctx, low.span),
    )  # fmt: skip
    b.add(
        "payment_terms",
        pay_key,
        f("floor_sample_text"),
        low.floor_text or None,
        low.floor_text or None,
        low.span,
    )
    units = t.units if t.units is not None else sum(r.units for r in _rows_of(ctx, t))
    b.add("payment_terms", pay_key, f("units"), units, str(units), t.span)
    if t.long:
        b.add("payment_terms", pay_key, f("notice_type_code"), t.long, t.long, t.span)
    disc = _discount_line(ctx.text, t)
    if disc is not None and 0 < disc.won < top.total:  # 0·음수·공급가 이상 할인은 후보가 아니다(R3 4차 minor)
        # D16-1(R3 8차 N-C1, D14-2·D15-1 대체): 자동 파싱 할인은 언제나 '추정'(표시만 — 구매가에서 빼지 않는다, D11-6·D12-3).
        # 구매가 차감은 사람 확인(의미 단위 ``discount``)이 '확인됨'으로 만든 할인뿐이다
        b.add(
            "payment_terms", pay_key, discount_field(t.short), disc.won, f"{disc.won:,}", disc.span,
            label="추정", reason=disc.reason,
        )  # fmt: skip


# 공고문에 적힌 할인(D11-6, 계약 .8) — **D16-1**(R3 8차 N-C1): 파서는 할인 후보를 찾아 표시만 한다('추정'). 조건 문구는
# 앞뒤 줄·떨어진 각주·표 머리에 흩어져 있어 줄 단위 규칙으로 '조건 없음'을 증명할 수 없다(7·8차 누출) — 허용 목록·금지
# 낱말로 '확인됨'을 가리지 않는다. 할인 아닌 금액(경품·지원 등)·'할인 없음' 줄·0원은 할인 후보가 아니다(표시할 할인이 없다).
# 파싱 규칙이며 판단 대체가 아니다(AGENTS 규칙 3).

DISCOUNT_REASON: Final = "공고문 자동 추출 — 조건 확인 필요"
"""파서 할인 후보의 '추정' 사유(D16-1). 화면은 '사람 확인 시 구매가에 반영' 안내와 G7 사람 확인 링크를 둔다."""

_NON_DISCOUNT_RE: Final = re.compile(
    r"경품|사은품|선물|상품권|캐시백|축하금|지원|무상|대납|대출|취득세|관리비|이자|옵션|발코니|확장|계약금|중도금|선납"
)
"""할인 아닌 금액(경품·지원·세금·관리비·옵션·발코니·계약금·중도금·선납 등)이 같은 줄에 있으면 그 줄은 분양가 할인 후보를
만들지 않는다(R3 4차 M-12) — '84A 분양가 할인 0원, 경품 10,000,000원' 의 금액은 할인이 아니다."""
_NO_DISCOUNT_RE: Final = re.compile(
    r"할인\s*(?:금액|액|혜택)?\s*[:：]?\s*(?:해당\s*(?:사항\s*)?)?(?:없음|없습니다|없다|無)"
    r"|미적용|비적용|적용\s*(?:되지|하지)\s*않|적용\s*없음"
)
"""'할인 없음'·'미적용'이 붙은 줄은 할인 후보를 만들지 않는다(그 줄의 다른 금액은 할인이 아니다)."""
_PRICE_DISCOUNT_RE: Final = re.compile(r"(?:분양가|분양\s*가격|공급\s*금액|공급가(?:격)?)\s*할인")
"""'추정' 사유 구분용 — 분양가·공급금액 할인을 명시한 줄인가."""
_AMOUNT_AFTER_RE: Final = re.compile(r"(?<![0-9,.])([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)[ \t]*원")
"""'할인' 뒤 첫 원 단위 금액(ASCII 숫자) — 후보 금액. 0원이면 할인 후보가 아니다."""
_TYPE_TOKEN_RE: Final = re.compile(r"(?<![0-9A-Za-z.])(\d{2,3}(?:\.\d+)?[A-Z]{0,3})(?:㎡|m2)?(?![0-9A-Za-z])")


def _mark_re(mark: str) -> re.Pattern[str]:
    """타입 표기를 **토큰 전체**로 찾는다('84A' 가 '184A'·'84AB' 안에서 맞지 않게)."""
    return re.compile(rf"(?<![0-9A-Za-z.]){re.escape(mark)}(?![0-9A-Za-z])")


@dataclass(frozen=True, slots=True)
class DiscountLine:
    """공고문 할인 줄 1개: 금액·원문 위치·'추정' 사유(D16-1 — '확인됨' 여부는 없다)."""

    won: int
    span: tuple[int, int]
    reason: str = DISCOUNT_REASON


_COUNT_SUFFIX_RE: Final = re.compile(r"\s*(?:세대|층|동|호|개|명|%|년|월|일)")


def _discount_line(text: str, t: TypeSpec) -> DiscountLine | None:
    """타입 표기(약식 '84A'·공고 주택형 '084.9582A'·면적 '84㎡')와 할인 금액이 같은 줄에 있는 첫 줄 → 할인 후보.

    후보 줄: '할인'이 있고, 타입 표기가 토큰 전체로 있고(R3 4차 M-12: '184A' 아님), 금액 앞에 다른 타입 표기가 없고(모호),
    '할인 없음/미적용'·할인 아닌 금액(``_NON_DISCOUNT_RE``)이 없고, '할인' 뒤 첫 금액이 0원이 아닌 줄. 후보는 언제나
    '추정'이다(D16-1) — ``reason`` 은 사람 확인 안내(분양가 할인을 명시하지 않은 줄이면 그 사실을 덧붙인다)."""
    short_area = t.short.rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    marks = [*(m for m in (t.short, t.long) if m), f"{short_area}㎡"]
    pats = [_mark_re(m) for m in marks]
    mine = {t.short, short_area, *marks}
    for ls, le in _line_spans(text, 0, len(text)):
        line = text[ls:le]
        off = line.find("할인")
        if off < 0 or _NON_DISCOUNT_RE.search(line) or _NO_DISCOUNT_RE.search(line):
            continue
        if not any(p.search(line) for p in pats):
            continue
        m = _AMOUNT_AFTER_RE.search(line, off)
        if m is None:
            continue
        before = line[: m.start()]
        others = {
            tok.group(1)
            for tok in _TYPE_TOKEN_RE.finditer(before)
            if tok.group(1) not in mine
            and tok.group(1).lstrip("0") not in mine
            and not _COUNT_SUFFIX_RE.match(before, tok.end())  # '30세대'·'10층'·'101동' 은 타입 표기가 아니다
        }
        if any(o[:1].isdigit() and len(o.rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")) >= 2 for o in others):
            continue  # 다른 타입 표기도 같은 줄에 있다 — 모호
        won = int(m.group(1).replace(",", ""))
        if won == 0:
            continue  # 0원은 할인 사실이 아니다
        reason = (
            DISCOUNT_REASON
            if _PRICE_DISCOUNT_RE.search(line)
            else f"{DISCOUNT_REASON}, 분양가 할인 명시 아님"
        )
        return DiscountLine(won, (ls + m.start(1), ls + m.end(1)), reason)
    return None


def _rows_of(ctx: _Ctx, t: TypeSpec) -> list[PriceRow]:
    return ctx.assigned.get(t.short, [])


def _price_section_end(text: str, start: int) -> int:
    seen_amount = False
    for ls, le in _line_spans(text, start, len(text)):
        line = text[ls:le]
        if AMOUNT_RE.search(line):
            seen_amount = True
        if (
            seen_amount
            and re.match(r"^(■|•|Ÿ|⦁|\[…\]|※\s*상기|발코니)", line)
            and not _PRICE_HEAD_RE.match(line)
        ):
            return ls
    return len(text)


def _payment_terms(ctx: _Ctx, head: tuple[int, int], rows: list[PriceRow], key: str) -> None:
    text, b = ctx.text, ctx.b
    hs, he = head
    kind_span = head
    b.add("payment_terms", key, "notice_kind", ctx.notice_kind, ctx.notice_kind, kind_span)
    # effective_from: 이 공고의 공고일
    eff: tuple[str, str, tuple[int, int]] | None = None
    tm = _THIS_DATE_RE.search(text)
    if tm and ctx.notice_kind != "본청약":
        d = parse_date(tm.group(1))
        if d:
            eff = (d, tm.group(1).strip(), tm.span(1))
    if eff is None:
        for c in reversed(b.out):
            if c.entity == "complex" and c.field == "notice_date" and isinstance(c.value, str):
                eff = (c.value, c.value_text or c.value, (c.excerpt_start or 0, c.excerpt_end or 1))
                break
    if eff is None:
        b.missing("payment_terms", key, "effective_from", ctx.head_span)
    else:
        b.add("payment_terms", key, "effective_from", eff[0], eff[1], eff[2])

    dpm = _DP_RE.search(text, hs, he)
    itm = _INTERIM_RE.search(text, hs, he)
    blm = _BALANCE_RE.search(text, hs, he)
    if dpm is None:
        for f in ("down_payment_pct", "interim_pct", "balance_pct"):
            b.missing("payment_terms", key, f, head)
        return
    dp = float(dpm.group(1))
    b.add("payment_terms", key, "down_payment_pct", dp, dpm.group(0), dpm.span())
    if blm is not None:
        b.add("payment_terms", key, "balance_pct", float(blm.group(1)), blm.group(0), blm.span())
    else:
        b.missing("payment_terms", key, "balance_pct", head, reason="잔금 비율 표기 해석 실패")
    no_interim = itm is None and blm is not None and dp + float(blm.group(1)) == 100.0
    if itm is not None:
        b.add("payment_terms", key, "interim_pct", float(itm.group(1)), itm.group(0), itm.span())
    elif no_interim and blm is not None:
        b.add("payment_terms", key, "interim_pct", 0.0, "중도금 없음", (dpm.start(), blm.end()))
    else:
        b.missing("payment_terms", key, "interim_pct", head)

    # 1차 계약금 정액: 공급금액 다음 두 열의 합 = 계약금이고 첫 열이 모든 행에서 같으면 정액
    if rows:
        firsts = {r.after_total[0] for r in rows if len(r.after_total) >= 2}
        r0 = rows[0]
        due = round(r0.total * dp / 100)
        if (
            len(firsts) == 1
            and len(r0.after_total) >= 2
            and r0.after_total[0] + r0.after_total[1] == due
            and r0.after_total[0] != r0.after_total[1]
        ):
            fixed = r0.after_total[0]
            b.add(
                "payment_terms",
                key,
                "down_payment_first_won",
                fixed,
                f"{fixed:,}",
                r0.span,
                **_unit_kw(ctx, r0.span),
            )
        else:
            b.add(
                "payment_terms",
                key,
                "down_payment_first_won",
                None,
                None,
                r0.span,
                label="확인 불가",
                reason="정액 표기 없음",
            )

    # 중도금 회차·날짜
    installs = [(int(m.group(1)), float(m.group(2))) for m in _INSTALL_RE.finditer(text, hs, he)]
    installs = sorted(dict(installs).items())
    dates = [m for m in _DATE_TOKEN_RE.finditer(text, hs, he)]
    if installs and len(dates) >= len(installs):
        use = dates[len(dates) - len(installs) :]
        sched: list[dict[str, object]] = []
        for (seq, pct), dm in zip(installs, use, strict=True):
            d = parse_date(dm.group(1))
            if d is None:
                sched = []
                break
            sched.append({"seq": seq, "due_date": d, "pct": pct})
        if sched:
            span = (use[0].start(), use[-1].end())
            b.add(
                "payment_terms", key, "interim_schedule", canonical_json(sched), text[span[0] : span[1]], span
            )
        else:
            b.missing("payment_terms", key, "interim_schedule", head, reason="중도금 날짜 해석 실패")
    elif installs or itm is not None:
        b.missing("payment_terms", key, "interim_schedule", head, reason="중도금 회차·날짜 해석 실패")
    elif no_interim:
        b.add("payment_terms", key, "interim_schedule", "[]", "중도금 없음", dpm.span())

    im = _INTEREST_RE.search(text)
    if im:
        line = _BULLET_RE.sub("", im.group(0)).strip()
        b.add("payment_terms", key, "interim_terms_text", line, line, im.span())


# ---------------------------------------------------------------- 발코니·옵션


def _balcony(ctx: _Ctx) -> None:
    text, b = ctx.text, ctx.b
    shorts = [t.short for t in ctx.types]
    if not shorts:
        return
    m = _BALCONY_HEAD_RE.search(text)
    found: dict[str, tuple[int, str, tuple[int, int]]] = {}
    if m is not None:
        spans = _line_spans(text, m.start(), min(len(text), m.end() + 2000))[:24]
        type_alt = "|".join(sorted((re.escape(s) for s in shorts), key=len, reverse=True))
        row_re = re.compile(rf"^((?:{type_alt})(?:\s*[·,]\s*(?:{type_alt}))*)\s+({AMOUNT_RE.pattern})")
        for ls, le in spans:
            rm = row_re.match(text[ls:le])
            if rm:
                for s in re.split(r"\s*[·,]\s*", rm.group(1)):
                    found.setdefault(s, (parse_won(rm.group(2)), rm.group(2), (ls, le)))
        if not found:
            # 가로 표: '구분 84A 84B …' 다음 줄들 중 금액 개수가 타입 수와 같은 줄
            for i, (ls, le) in enumerate(spans):
                hdr = re.findall(rf"(?<![\w])({type_alt})(?![\w])", text[ls:le])
                if len(hdr) < 2:
                    continue
                for ls2, le2 in spans[i + 1 : i + 4]:
                    amts = amounts_in(text[ls2:le2])
                    if len(amts) == len(hdr):
                        for s, (v, _, _) in zip(hdr, amts, strict=True):
                            found.setdefault(s, (v, f"{v:,}", (ls2, le2)))
                        break
                if found:
                    break
    for t in ctx.types:
        tkey = f"{ctx.complex_key}:{t.short}"
        if t.short in found:
            v, vt, span = found[t.short]
            b.add("complex_type", tkey, "balcony_won", v, vt, span)
        else:
            b.missing(
                "complex_type",
                tkey,
                "balcony_won",
                m.span() if m else ctx.head_span,
                reason="발코니 표 해석 실패",
            )


def _options(ctx: _Ctx) -> None:
    """'상기 공급금액은 추가 선택품목 비용이 포함되지 아니한 가격' → 필수 옵션 0원(선택품목은 별도 계약)."""
    text, b = ctx.text, ctx.b
    m = _OPTIONS_RE.search(text)
    for t in ctx.types:
        tkey = f"{ctx.complex_key}:{t.short}"
        if m:
            line = _BULLET_RE.sub("", m.group(0)).strip()
            b.add("complex_type", tkey, "options_required_won", 0, line, m.span())
            # 옵션 설명 원문(RA complex_type.options_text — R3 3차 RA 부분): 선택품목 안내 문장 그대로
            b.add("complex_type", tkey, "options_text", line[:500], line[:500], m.span())
        else:
            b.missing(
                "complex_type", tkey, "options_required_won", ctx.head_span, reason="선택품목 문장 없음"
            )

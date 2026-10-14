"""필드 레지스트리: 출처 우선순위(RA §3 표), 수치 필드 목록, 변경 심각도.

파싱·해결·저장·변경 감지가 같은 표를 보도록 한 곳에 둔다. 판단(포함 여부·상충 판정)은 여기 없다 — 표는
RA §3의 우선순위 규칙을 옮긴 것뿐이다.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Final, Literal

__all__ = [
    "AUDIT_FLAG_REASON",
    "BALANCE_DERIVED_REASON",
    "BOOL_FIELDS",
    "COMPARE_ADOPTED",
    "COMPARE_SIDE",
    "CONFLICT_HOLD",
    "CRITICAL_FIELDS",
    "DECIMAL_FIELDS",
    "EXPLICIT_NULL_FIELDS",
    "EXTRACT_REASON",
    "FIELD_GROUP",
    "INT_FIELDS",
    "JSON_FIELDS",
    "LABEL_BY_SOURCE",
    "MAGNITUDE_RATIO",
    "NUMERIC_FIELDS",
    "OCR_LABEL",
    "OCR_REASON",
    "PRICE_BY_TYPE_ITEMS",
    "PRIMARY_SOURCES",
    "QUIET_FIRST_FIELDS",
    "RULE_TEXT",
    "UNIT_ASSUMED",
    "WINNING_SCORE_DASH_REASON",
    "WINNING_SCORE_FIELDS",
    "SourceKind",
    "compare_mark",
    "discount_field",
    "field_group",
    "has_tag",
    "is_numeric_field",
    "is_ocr",
    "is_price_amount",
    "is_provisional",
    "magnitude_apart",
    "norm_value",
    "price_by_type_field",
    "rule_text",
    "source_rank",
    "split_discount",
    "split_price_by_type",
    "strip_tags",
    "value_from_norm",
    "with_mark",
    "with_tag",
]

SourceKind = Literal[
    "applyhome_list",
    "applyhome_detail",
    "notice_pdf",
    "official_site",
    "rtms",
    "stats",
    "news",
    "reference",
]

FieldGroup = Literal["schedule", "price", "other"]

# RA §3: 세대수·면적·일정·경쟁률 = 청약홈 상세(1) > 공고문(2) > 언론(3)
#        가격·발코니·옵션·납부·전매·거주의무 = 공고문 최신(1) > 청약홈(2) > 언론(3)
_SCHEDULE_FIELDS: Final = frozenset(
    {
        ("complex", "units_total"),
        ("complex", "units_general"),
        ("complex", "units_special"),
        ("complex", "officetel_units"),
        ("complex", "notice_date"),
        ("complex", "apply_dates"),
        ("complex", "winner_date"),
        ("complex", "contract_dates"),
        ("complex", "move_in_ym"),
        ("complex_type", "area_m2"),
        ("complex_type", "units"),
    }
)
_PRICE_FIELDS: Final = frozenset(
    {
        ("complex_type", "max_price_won"),
        ("complex_type", "floor_sample_price_won"),
        ("complex_type", "floor_sample_text"),
        ("complex_type", "balcony_won"),
        ("complex_type", "options_required_won"),
        ("complex_type", "options_text"),
        ("complex", "resale_months"),
        ("complex", "resale_release_on_registration"),
        ("complex", "residency_months"),
        ("complex", "rewin_restriction_years"),
        ("complex", "price_cap"),
    }
)

_RANKS: Final[dict[FieldGroup, dict[str, int]]] = {
    "schedule": {"applyhome_detail": 1, "applyhome_list": 1, "notice_pdf": 2, "news": 3},
    "price": {"notice_pdf": 1, "applyhome_detail": 2, "applyhome_list": 2, "news": 3},
    # 표에 없는 필드(이름·주소·시행·시공 등)는 세대수 군과 같은 순서로 둔다(가정, 보고서에 기록)
    "other": {
        "applyhome_detail": 1,
        "applyhome_list": 1,
        "notice_pdf": 2,
        "rtms": 1,
        "stats": 1,
        "reference": 1,
        "official_site": 2,
        "news": 3,
    },
}

RULE_TEXT: Final[dict[FieldGroup, str]] = {
    "schedule": "세대수·면적·일정·경쟁률: 청약홈 상세(1) > 공고문(2) > 언론(3) — rank 1 채택, compare 미호출",
    "price": "가격·발코니·옵션·납부·전매·거주의무: 공고문 최신(1) > 청약홈(2) > 언론(3) — rank 1 채택",
    "other": "기타 공고 항목: 청약홈(1) > 공고문(2) > 언론(3) — rank 1 채택",
}

PRIMARY_SOURCES: Final = frozenset(
    {"applyhome_list", "applyhome_detail", "notice_pdf", "official_site", "rtms", "stats", "reference"}
)

LABEL_BY_SOURCE: Final[dict[str, str]] = {
    "applyhome_list": "확인됨",
    "applyhome_detail": "확인됨",
    "notice_pdf": "확인됨",
    "official_site": "확인됨",
    "rtms": "확인됨",
    "stats": "확인됨",
    "reference": "확인됨",
    "news": "비공식",
}

# 저장 대상 수치 컬럼(provenance 전수 검사 대상). 날짜·연월도 Fact이므로 포함한다.
NUMERIC_FIELDS: Final[dict[str, tuple[str, ...]]] = {
    "complex": (
        "units_total",
        "units_general",
        "units_special",
        "officetel_units",
        "notice_date",
        "winner_date",
        "move_in_ym",
        "resale_months",
        "residency_months",
        "rewin_restriction_years",
    ),
    "complex_type": (
        "area_m2",
        "units",
        "max_price_won",
        "floor_sample_price_won",
        "balcony_won",
        "options_required_won",
    ),
    "payment_terms": (
        "effective_from",
        "down_payment_pct",
        "down_payment_first_won",
        "interim_pct",
        "balance_pct",
    ),
    "competition": ("supply", "applied"),
}

EXPLICIT_NULL_FIELDS: Final = frozenset({("complex_type", "options_text")})
"""값 없음(None) + 라벨 확인됨 후보가 저장 값을 지우는 필드(R9-PARSE Q2).

공고문의 '추가 선택품목 비용 미포함' 고지문은 필수 옵션 설명이 아니다 — 옛 파서가 넣은 고지문을
재정규화가 비운다. 다른 필드의 값 없음 후보는 그대로 저장 값을 지우지 않는다."""

WINNING_SCORE_FIELDS: Final = ("winning_score_min", "winning_score_max", "winning_score_avg")
WINNING_SCORE_DASH_REASON: Final = "가점 당첨자 없음(청약홈 '-')"
"""청약홈 경쟁률 팝업 당첨가점 칸이 '-' — 값 없는 '확인 불가' 후보의 사유(R10).
팝업을 못 받은 '가점 미수집'과 구별한다. '-' 는 그 지역 가점제 당첨자가 없다는 표기다
(미달·추첨제·해당지역에서 마감 …) — 미달인지·발표 전인지는 읽을 때 경쟁률 행 원문('△')·
당첨자 발표일로 나눈다(``app.api.views.winning_score_fact``)."""
QUIET_FIRST_FIELDS: Final = frozenset(("competition", f) for f in WINNING_SCORE_FIELDS)
"""빈 값 → 값(처음 관측)을 change_event 로 남기지 않는 필드(R9-PARSE Q4).

당첨가점은 발표 뒤 웹 팝업으로 처음 수집하는 지난 결과라 '바뀐 사실'이 아니다 — 배포 뒤 첫 수집이
경쟁률 행마다 이벤트를 쏟지 않게. 값 → 다른 값은 그대로 이벤트(severity info — 점수 입력 아님)."""

INT_FIELDS: Final = frozenset(
    {
        "units_total",
        "units_general",
        "units_special",
        "officetel_units",
        "resale_months",
        "residency_months",
        "rewin_restriction_years",
        "units",
        "max_price_won",
        "floor_sample_price_won",
        "balcony_won",
        "options_required_won",
        "down_payment_first_won",
        "supply",
        "applied",
    }
)

# value가 JSON 문자열(canonical)로 오는 필드
JSON_FIELDS: Final = frozenset({"apply_dates", "contract_dates", "interim_schedule"})

# RA §3 change_event: 새 공고·팝업 변경·중도금일·가격 변경은 critical
CRITICAL_FIELDS: Final = frozenset(
    {
        ("complex_type", "max_price_won"),
        ("complex_type", "floor_sample_price_won"),
        ("complex_type", "balcony_won"),
        ("complex_type", "options_required_won"),
        ("payment_terms", "down_payment_pct"),
        ("payment_terms", "down_payment_first_won"),
        ("payment_terms", "interim_pct"),
        ("payment_terms", "balance_pct"),
        ("payment_terms", "interim_schedule"),
        ("payment_terms", "interim_terms_text"),
        ("complex", "contract_dates"),
    }
)


def field_group(entity: str, field: str) -> FieldGroup:
    if entity == "payment_terms" or (entity, field) in _PRICE_FIELDS:
        return "price"
    if entity == "competition" or (entity, field) in _SCHEDULE_FIELDS:
        return "schedule"
    return "other"


FIELD_GROUP = field_group


def source_rank(entity: str, field: str, source_kind: str) -> int:
    """RA §3 출처 우선순위(1이 가장 높음). 표에 없는 출처는 3(언론급)으로 둔다."""
    return _RANKS[field_group(entity, field)].get(source_kind, 3)


def rule_text(entity: str, field: str) -> str:
    return RULE_TEXT[field_group(entity, field)]


# ---------------------------------------------------------------- 공고별 타입 가격 (계약 2026-10-09.2)

# payment_terms.price_by_type 의 항목. 출처 행 field = 'price_by_type.<type_code>.<항목>'
PRICE_BY_TYPE_ITEMS: Final = (
    "max_price_won",
    "floor_sample_price_won",
    "floor_sample_text",
    "units",
    "notice_type_code",
)
_PRICE_BY_TYPE = "price_by_type."


def price_by_type_field(type_code: str, item: str) -> str:
    return f"{_PRICE_BY_TYPE}{type_code}.{item}"


def split_price_by_type(field: str) -> tuple[str, str] | None:
    """'price_by_type.84A.max_price_won' → ('84A', 'max_price_won'). 아니면 None."""
    if not field.startswith(_PRICE_BY_TYPE):
        return None
    type_code, _, item = field[len(_PRICE_BY_TYPE) :].rpartition(".")
    if not type_code or item not in PRICE_BY_TYPE_ITEMS:
        return None
    return type_code, item


_DISCOUNT = "discount_by_type."


def discount_field(type_code: str) -> str:
    """공고에 명시된 할인(타입별, 계약 2026-10-09.8 — D11-6) 출처 필드: 'discount_by_type.<type_code>'."""
    return f"{_DISCOUNT}{type_code}"


def split_discount(field: str) -> str | None:
    """'discount_by_type.84A' → '84A'. 아니면 None."""
    if not field.startswith(_DISCOUNT):
        return None
    code = field[len(_DISCOUNT) :]
    return code or None


# ---------------------------------------------------------------- value_norm (계약 2026-10-09.2)

# 값이 불리언인 필드(파서가 bool 로 낸다)
BOOL_FIELDS: Final = frozenset({"resale_release_on_registration", "cancelled", "is_presale"})
# INT_FIELDS 밖의 정수 필드(실거래·미분양)
_EXTRA_INT_FIELDS: Final = frozenset({"floor", "completed_year", "total", "post_completion", "price_won"})
# 소수 필드(㎡·%·확률)
DECIMAL_FIELDS: Final = frozenset(
    {
        "area_m2",
        "down_payment_pct",
        "interim_pct",
        "balance_pct",
        "inclusion_prob",
        "winning_score_min",
        "winning_score_max",
        "winning_score_avg",
    }
)


def norm_value(value: float | int | str | bool | None) -> str | None:
    """정규화 값 → value_norm 정준 문자열(field_provenance.value_norm).

    정수·소수는 10진 표기('1573', '84.98', 10.0 → '10'), 불리언 'true'/'false',
    문자열(ISO 날짜·정규 JSON 등)은
    그대로, 없으면 None.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        try:
            d = Decimal(str(value)).normalize()
        except InvalidOperation:  # pragma: no cover - nan/inf
            return str(value)
        return format(d, "f")
    return value


def _int_field(field: str) -> bool:
    if split_discount(field) is not None:
        return True
    pbt = split_price_by_type(field)
    if pbt is not None:
        return pbt[1] in ("max_price_won", "floor_sample_price_won", "units")
    return field in INT_FIELDS or field in _EXTRA_INT_FIELDS


def value_from_norm(field: str, norm: str | None) -> float | int | str | bool | None:
    """value_norm → FieldCandidate.value (필드 종류로 형을 되돌린다). ``norm_value`` 의 역."""
    if norm is None:
        return None
    if field in BOOL_FIELDS and norm in ("true", "false"):
        return norm == "true"
    if _int_field(field):
        try:
            return int(norm)
        except ValueError:
            return norm
    if field in DECIMAL_FIELDS:
        try:
            return float(norm)
        except ValueError:
            return norm
    return norm


# ---------------------------------------------------------------- 출처 행 reason 표식 (R3 C3·M1)
#
# 라벨은 계약 5종(label.json) 그대로다. OCR·판정기 결과·상충 보류는 reason(라벨 한정어)으로 표시한다
# — 화면 표시 문자열은 '<label>(<reason>)'(fact.json 규칙): OCR 판독값 = '추정(OCR)'.

OCR_LABEL: Final = "추정"
OCR_REASON: Final = "OCR"
"""OCR 로 읽은 공고문(raw.error_text 'ocr'·'ocr_partial:<p>') 값: label '추정', reason 'OCR'
= 표시 '추정(OCR)'
(DECISIONS D5-4). 수치 필드는 needs_extract=True — 판정기 extract/audit 를 반드시 거친다."""
EXTRACT_REASON: Final = "판정기 추출"
AUDIT_FLAG_REASON: Final = "판정기 감사 flagged"
COMPARE_ADOPTED: Final = "판정기 compare 채택"
"""P5 compare 결과로 채택된 출처 행의 reason 머리(같은 rank 1차·1차 상충은 이 표식이 있어야 채택된다)."""
COMPARE_SIDE: Final = "판정기 compare 병기"
"""P5 compare 결과 병기(채택 안 됨) 출처 행의 reason 머리."""
CONFLICT_HOLD: Final = "출처 상충 — compare 대기"
"""같은 rank 1차·1차 상충이 compare 로 풀리기 전: 채택 보류(사실 테이블 값 없음 = 점수 미사용).
표시 '확인 불가(출처 상충 — compare 대기)'."""
_TAGS: Final = (COMPARE_ADOPTED, COMPARE_SIDE, CONFLICT_HOLD)
_TAG_SEP: Final = "; "
_REASON_MAX: Final = 120


def has_tag(reason: str | None, tag: str) -> bool:
    return (reason or "").startswith(tag)


def strip_tags(reason: str | None) -> str | None:
    """reason 앞의 compare·상충 보류 표식을 뗀다(원래 reason 만 남김)."""
    text = reason or ""
    changed = True
    while changed:
        changed = False
        for tag in _TAGS:
            if text.startswith(tag):
                _, sep, rest = text.partition(_TAG_SEP)
                text = rest if sep else ""
                changed = True
    return text or None


def with_tag(reason: str | None, tag: str, detail: str = "") -> str:
    """'<tag>[ <detail>]; <원래 reason>' (120자). 이미 붙은 compare·보류 표식은 바꾼다."""
    head = f"{tag} {detail}".strip()
    rest = strip_tags(reason)
    return (f"{head}{_TAG_SEP}{rest}" if rest else head)[:_REASON_MAX]


def compare_mark(reason: str | None) -> str | None:
    """reason 앞의 판정기 compare 표식 머리(채택·병기 — '<표식> jl_… — …'). 없으면 None.

    D23-3(R4 4차 N14): 같은 원문을 다시 정규화하면 그 원문의 출처 행 reason 이 파서 값으로
    다시 쓰인다 — 저장 단계가 이 머리를 이번 후보에 다시 붙여(``with_mark``) compare 결과를
    보존한다(같은 자리·같은 값만)."""
    text = reason or ""
    if not text.startswith((COMPARE_ADOPTED, COMPARE_SIDE)):
        return None
    head, _, _ = text.partition(_TAG_SEP)
    return head


def with_mark(reason: str | None, head: str) -> str:
    """``compare_mark`` 머리를 reason 앞에 다시 붙인다(``with_tag`` 와 같은 모양 — 같은 입력이면 같은 값)."""
    rest = strip_tags(reason)
    return (f"{head}{_TAG_SEP}{rest}" if rest else head)[:_REASON_MAX]


BALANCE_DERIVED_REASON: Final = "산술(100-계약금-중도금)"
"""잔금 비율을 표 머리에서 바로 읽지 못해 계약금·중도금 비율로 계산한 값의 '추정' 사유(R9-PARSE Q2)."""


def is_provisional(label: str | None, reason: str | None) -> bool:
    """판정기 추출이 나오면 물러나는 파서 값 후보: OCR 판독(R3 C3) 또는 잔금 산술(R9-PARSE Q2).

    둘 다 label '추정'이고 같은 원문의 판정기 extract 요청을 그대로 남긴다 — 판정기가 값을 확정하면
    그 추출 행이 채택된다."""
    return is_ocr(label, reason) or (label == "추정" and strip_tags(reason) == BALANCE_DERIVED_REASON)


def is_ocr(label: str | None, reason: str | None) -> bool:
    """OCR 판독 후보(판정기 추출 전): label '추정' + reason 'OCR'(앞 표식 제외)."""
    return label == OCR_LABEL and strip_tags(reason) == OCR_REASON


def is_numeric_field(entity: str, field: str, value: object = None) -> bool:
    """수치·날짜 필드인가(OCR 값의 needs_extract 대상, provenance 전수 검사와 같은 기준).

    NUMERIC_FIELDS·INT_FIELDS·DECIMAL_FIELDS·JSON 일정 필드·price_by_type 숫자 항목, 또는 값이 숫자.
    """
    if split_discount(field) is not None:
        return True
    pbt = split_price_by_type(field)
    if pbt is not None:
        return pbt[1] in ("max_price_won", "floor_sample_price_won", "units")
    if field in NUMERIC_FIELDS.get(entity, ()) or field in JSON_FIELDS:
        return True
    if field in INT_FIELDS or field in DECIMAL_FIELDS or field in _EXTRA_INT_FIELDS:
        return True
    return isinstance(value, int | float) and not isinstance(value, bool)


# ---------------------------------------------------------------- 금액 단위 (R4 재시험 N1, DECISIONS D21-1)

UNIT_ASSUMED: Final = "단위 표기 없음 — 원으로 봄"
"""공고문 공급금액 표 머리·근처에 금액 단위('(단위: 천원)'·'만원'·'원')가 없어 원으로 읽은 가격 후보의
reason(D21-1). 같은 단지·타입의 다른 1차 출처와 ``MAGNITUDE_RATIO`` 배 이상 다르면 순위로 채택하지 않고
compare(판정기)로 보낸다."""
MAGNITUDE_RATIO: Final = 10
"""D21-1: 같은 단지·타입 가격의 1차 출처끼리 이 배수 이상 다르면 단위 상충으로 본다(산술 — 판단이 아니다)."""
_PRICE_AMOUNTS: Final = frozenset({"max_price_won", "floor_sample_price_won"})


def is_price_amount(entity: str, field: str) -> bool:
    """단위 상충 검사 대상 가격 필드: 타입 행 최고가·대표층가(``complex_type``)와 공고별 타입 가격 항목
    (``price_by_type``)."""
    if entity == "complex_type":
        return field in _PRICE_AMOUNTS
    if entity == "payment_terms":
        pbt = split_price_by_type(field)
        return pbt is not None and pbt[1] in _PRICE_AMOUNTS
    return False


def _positive(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        d = Decimal(str(value).replace(",", "").strip())
    except InvalidOperation:
        return None
    return d if d > 0 else None


def magnitude_apart(a: object, b: object) -> bool:
    """두 금액(원)이 ``MAGNITUDE_RATIO`` 배 이상 다른가(둘 다 양수일 때만 — 값 없음·0 은 상충이 아니다)."""
    x, y = _positive(a), _positive(b)
    if x is None or y is None:
        return False
    big, small = (x, y) if x >= y else (y, x)
    return big >= small * MAGNITUDE_RATIO

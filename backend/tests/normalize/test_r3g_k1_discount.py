"""R3g CORE5 — 7차 리뷰 K1 / D15-1: 할인 '확인됨'은 **허용 목록**만(D14-2 대체).

허용 꼴: 한 줄 전체가 ``{타입} {분양가|공급금액} 할인 {금액}원`` (꼬리글·괄호·범위·'예정' 없음)이고, 다음 줄이
괄호·※·*·'단'·조건 낱말로 시작하지 않을 때만 '확인됨'. 금액 0원·할인 아닌 금액(경품·지원 등)은 할인 사실이 아니다.
그 밖은 전부 '추정'(표시만) 또는 사실 없음.

| 리뷰 | 테스트 |
| --- | --- |
| K1 리뷰 재현 문구(다음 줄 조건·예정·범위·0원+경품 등) | ``test_k1_review_phrases_not_confirmed`` |
| 리뷰어 퍼징 목록 전부(허용 꼴만 확인됨) | ``test_k1_reviewer_fuzz_cases`` |
| 0원·할인 아닌 금액은 사실 없음 | ``test_k1_zero_or_non_discount_amount_makes_no_fact`` |
| 문법 기반 퍼징: 허용 꼴이 아니면 '확인됨' 0건 | ``test_k1_property_confirmed_only_if_canonical`` |
| 허용 꼴 + 무해한 다음 줄은 확인됨(금액·위치) | ``test_k1_property_canonical_is_confirmed`` |
| 공고문 파서 경로(후보 라벨) | ``test_k1_parse_notice_text_labels`` |
"""

# ruff: noqa: E501

from __future__ import annotations

import re
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

SHORT, LONG = "84A", "084.9582A"


def _spec() -> object:
    from app.normalize.notice_parser import TypeSpec

    return TypeSpec(short=SHORT, long=LONG, area_text="84.9582", units=10, span=(0, 1))


def _call(text: str) -> object:
    from app.normalize.notice_parser import _discount_line

    return _discount_line(text, _spec())  # type: ignore[arg-type]


def _confirmed(text: str) -> bool:
    got = _call(text)
    return got is not None and bool(got.confirmed)  # type: ignore[attr-defined]


# ---------------------------------------------------------------- 독립 오라클(테스트 쪽 정의)

_ORACLE_CANON = re.compile(
    r"(?:84A|084\.9582A)[ \t]+(?:분양가|공급금액)[ \t]*할인[ \t]+([1-9][0-9]{0,2}(?:,[0-9]{3})+)[ \t]*원"
)
_ORACLE_NEXT_BAD = re.compile(
    r"[(（\[［※*＊]|단|주\)"
    r"|[0-9０-９]+[ \t]*(?:층|동|호|F|f|~|～|라인|세대)"
    r"|(?:층|동|호|라인|저층|고층|한정|한함|한하여|조건|선착순|특별공급|특공|일반공급|신혼|대상|해당|계약|기간|까지|일부|제외|이상|이하|최대|최소|잔금|완납|예정|변경|별도)"
)


def _oracle_ok(text: str, span: tuple[int, int]) -> bool:
    """span 을 담은 줄이 허용 꼴 전체 일치이고, 금액 위치가 같고, 다음 비어 있지 않은 줄이 조건 표지로 시작하지 않는다."""
    ls = text.rfind("\n", 0, span[0]) + 1
    le = text.find("\n", span[0])
    le = len(text) if le < 0 else le
    raw = text[ls:le]
    line = raw.strip(" \t\r")
    lead = len(raw) - len(raw.lstrip(" \t\r"))
    m = _ORACLE_CANON.fullmatch(line)
    if m is None or (ls + lead + m.start(1), ls + lead + m.end(1)) != span:
        return False
    for nxt in text[le + 1 :].split("\n"):
        n = nxt.strip(" \t\r")
        if n:
            return _ORACLE_NEXT_BAD.match(n) is None
    return True


# ---------------------------------------------------------------- 리뷰 재현


@pytest.mark.parametrize(
    "text",
    [
        "84A 분양가 할인 10,000,000원\n(1~3층에 한함)",
        "84A 분양가 할인 10,000,000원\n(일부 세대)",
        "84A 분양가 할인 10,000,000원\n(계약자에 한하여)",
        "84A 분양가 할인 10,000,000원\n(신혼부부)",
        "84A 분양가 할인 10,000,000원\n(1F~3F)",
        "84A 분양가 할인 10,000,000원\n(2026.10.31.)",
        "84A 분양가 할인 10,000,000원 예정",
        "84A 분양가 할인 10,000,000원 ~ 30,000,000원",
        "84A 분양가 할인 0원, 경품 10,000,000원",
        "84A 분양가 할인 10,000,000원\n※ 1~3층 세대에 한함",
        "84A 분양가 할인 10,000,000원\n단, 계약 순서에 따라 조기 종료",
        "84A 분양가 할인 10,000,000원\n\n  (1~3층에 한함)",  # 빈 줄 건너 다음 줄
        "84A 분양가 할인 10,000,000원\n* 저층 세대 한정",
        "84A 분양가 할인 10,000,000원\n（신혼부부）",
        "84A 분양가 할인 10,000,000원\n［1~3층］",
        "84A 분양가 할인 10,000,000원\n1~3층 세대에 한함",
        "84A 분양가 할인 10,000,000원\n계약자에 한함",
        "84A 분양가 할인 10,000,000원\n주) 조건 별도",
        "84A 분양가 할인 10,000,000원\n- 저층 한정",
        "84A 분양가 할인 10,000,000원\n선착순 30세대",
    ],
)
def test_k1_review_phrases_not_confirmed(text: str) -> None:
    """리뷰 재현: 예전엔 '확인됨'(구매가에서 차감) — 이제 None 또는 '추정'."""
    got = _call(text + "\n")
    assert got is None or got.confirmed is False, (text, got)  # type: ignore[attr-defined]
    if text.startswith("84A 분양가 할인 0원"):
        assert got is None, got  # 0원 → 사실 없음, 경품 금액은 할인이 아니다


# ---------------------------------------------------------------- 리뷰어 퍼징 목록(r7/b/fuzz_disc.py)

_CANONICAL = {
    "84A 분양가 할인 10,000,000원",
    "084.9582A 분양가 할인 10,000,000원",
    "84A 공급금액 할인 10,000,000원",
}

_FUZZ_CASES = [
    "84A 분양가 할인 10,000,000원(1~3층)",
    "84A 잔금 완납 시 분양가 할인 5,000,000원",
    "84A 분양가 할인 10,000,000원(특별공급 당첨자 한정)",
    "84A 분양가 할인 최대 10,000,000원",
    "84A 분양가 할인 없음, 취득세 지원 3,000,000원",
    "84A 분양가 할인 10,000,000원",
    "84A 분양가 할인 10,000,000원（１～３층）",
    "84A 분양가 할인 10,000,000원（저층부）",
    "84A 분양가 할인 １０,０００,０００원",
    "84A 분양가 할인 10,000,000원\n(1~3층에 한함)",
    "84A 분양가 할인 10,000,000원\n※ 1~3층 세대에 한함",
    "84A 분양가 할인 10,000,000원\n단, 계약 순서에 따라 조기 종료",
    "84A 분양가 할인 10,000,000원(일부 세대)",
    "84A 분양가 할인 10,000,000원(일부 타입)",
    "84A 분양가 할인 10,000,000원(세대 한정)",
    "84A 분양가 할인 10,000,000원(로열층 제외)",
    "84A 분양가 할인 10,000,000원(84A 타입에 한함)",
    "84A 분양가 할인 10,000,000원(계약자에 한하여)",
    "84A 분양가 할인 10,000,000원(조기 계약자)",
    "84A 분양가 할인 10,000,000원(조기계약)",
    "84A 분양가 할인 10,000,000원(당첨자에 한함)",
    "84A 분양가 할인 10,000,000원(정당계약 기간 내)",
    "84A 분양가 할인 10,000,000원(정당계약 체결 세대)",
    "84A 분양가 할인 10,000,000원(계약 순)",
    "84A 분양가 할인 10,000,000원(일부)",
    "84A 분양가 할인 10,000,000원(1층)",
    "84A 분양가 할인 10,000,000원(1·2층)",
    "84A 분양가 할인 10,000,000원(필로티 세대)",
    "84A 분양가 할인 10,000,000원(탑층 제외)",
    "84A 분양가 할인 10,000,000원(1차 계약분)",
    "84A 분양가 할인 1,000만원",
    "84A 분양가 할인 1천만원",
    "84A 분양가 할인 10M원",
    "84A 분양가 할인 10%",
    "84A 분양가 할인 10% (10,000,000원)",
    "84A 분양가 10% 할인 50,000,000원",
    "84A 분양가 할인 10,000,000원 ~ 30,000,000원",
    "84A 분양가 할인 10,000,000원~30,000,000원",
    "84A 분양가 할인 최소 10,000,000원",
    "84A 분양가 할인 최고 10,000,000원",
    "84A 분양가 할인 최대치 10,000,000원",
    "84A 분양가 할인 up to 10,000,000원",
    "84A 분양가 할인 이벤트 10,000,000원",
    "84A 분양가 할인 프로모션 10,000,000원",
    "84A 분양가 할인 예정 10,000,000원",
    "84A 분양가 할인 10,000,000원 예정",
    "84A 분양가 할인 10,000,000원 검토 중",
    "84A 분양가 할인 10,000,000원 가능",
    "84A 분양가 할인 계획 10,000,000원",
    "84A 분양가 할인 10,000,000원(협의)",
    "84A 분양가 할인 10,000,000원(변동 가능)",
    "84A 분양가 할인 10,000,000원(변경될 수 있음)",
    "84A 분양가 할인 10,000,000원(추후 확정)",
    "84A 분양가 할인 10,000,000원(미정)",
    "84A 분양가 할인 10,000,000원 내외",
    "84A 분양가 할인 약 10,000,000원",
    "84A 분양가 할인 10,000,000원 상당",
    "84A 분양가 할인 10,000,000원",
    "84A 분양가​할인 10,000,000원",
    "84A 분양가 할​인 10,000,000원",
    "84​A 분양가 할인 10,000,000원",
    "1~3층 84A 분양가 할인 10,000,000원",
    "저층 84A 분양가 할인 10,000,000원",
    "(특별공급) 84A 분양가 할인 10,000,000원",
    "84A 취득세 지원 3,000,000원, 분양가 할인 10,000,000원",
    "84A 분양가 할인 10,000,000원, 취득세 지원 3,000,000원",
    "84A 분양가 할인 10,000,000원 / 추가 할인 5,000,000원",
    "84A 분양가 할인 5,000,000원 + 10,000,000원",
    "84A 분양가 할인 10,000,000원(1차), 20,000,000원(2차)",
    "84A 분양가 할인 미적용 / 59A 분양가 할인 10,000,000원",
    "84A 분양가 할인 해당 없음 10,000,000원",
    "84A 분양가 할인 無",
    "84A 분양가 할인 - , 계약축하금 10,000,000원",
    "84A 분양가 할인 -  관리비 지원 3,000,000원",
    "84A 분양가 할인 0원, 경품 10,000,000원",
    "84A 분양가 할인 혜택 없이 사은품 10,000,000원",
    "| 84A | 분양가 할인 | 10,000,000원 |",
    "84A\t분양가 할인\t10,000,000원\t1~3층",
    "84A\t분양가 할인\t10,000,000원\t전세대",
    "| 84A | 10,000,000원 | 분양가 할인 |",
    "| 주택형 | 분양가 할인 |\n| 84A | 10,000,000원 |",
    "분양가 할인 84A 10,000,000원 (계약 시)",
    "분양가 할인 84A 10,000,000원 (계약시점 기준)",
    "84A 분양가 할인 10,000,000원 (부가세 별도)",
    "84A 분양가 할인 10,000,000원 (VAT 포함)",
    "84A 분양가 할인 10,000,000원 (발코니 미포함)",
    "84A 분양가할인 10,000,000원(한시적)",
    "84A 분양가할인 10,000,000원(한시)",
    "84A 분양가할인 10,000,000원(당월 계약분)",
    "84A 분양가할인 10,000,000원(10월 계약분)",
    "84A 분양가할인 10,000,000원(2026.10.31.)",
    "84A 분양가할인 10,000,000원(～2026.10.31)",
    "84A 분양가할인 10,000,000원(2026.10.1~10.31)",
    "84A 공급금액 할인 10,000,000원(무순위 당첨자)",
    "84A 공급금액 할인 10,000,000원(예비입주자)",
    "84A 공급금액 할인 10,000,000원(일반공급)",
    "84A 공급금액 할인 10,000,000원(신혼부부)",
    "84A 공급금액 할인 10,000,000원 (현금 납부)",
    "84A 공급금액 할인 10,000,000원 (대출 미이용)",
    "84A 분양가 할인 10,000,000원 (1개층)",
    "84A 분양가 할인 10,000,000원 (2F 이하)",
    "84A 분양가 할인 10,000,000원 (B1 제외)",
    "84A 분양가 할인 10,000,000원 (101~103동)",
    "84A 분양가 할인 10,000,000원 (101동~103동)",
    "84A 분양가 할인 10,000,000원 (1·2라인)",
    "84A 분양가 할인 10,000,000원 (1, 2호 라인)",
    "84A 분양가 할인 10,000,000원 (5호)",
    "84A 분양가 할인 10,000,000원 (조합원 제외)",
    "84A 분양가 할인 10,000,000원 (남향)",
    "84A 분양가 할인 10,000,000원 (판상형)",
    "84A 분양가 할인 10,000,000원 (선택 시)",
    "84A 분양가 할인 10,000,000원 (신청자)",
    "84A 분양가 할인 10,000,000원 (원하는 경우)",
    "84A 분양가 할인 10,000,000원 (대상: 1~3층)",
    "84A 분양가 할인 10,000,000원 (대상 세대 별도 안내)",
    "84A 분양가 할인 10,000,000원 (별도 안내)",
    "84A 분양가 할인 10,000,000원 (견본주택 문의)",
    "84A분양가할인10,000,000원1~3층",
    "84A 분양가 할인 10,000,000원 (1F~3F)",
    "84A 분양가 할인 10,000,000원 (3F)",
    "84A 분양가 할인 10,000,000원 (lower floors)",
    "84A 분양가 할인 10,000,000원 / 1~3F",
    "84A 분양가 할인 10,000,000원 (1~3)",
    "84A 분양가 할인 10,000,000원 [1~3층]",
    "84A 분양가 할인 10,000,000원 1~3層",
    "084.9582A 분양가 할인 10,000,000원",
    "84㎡ 분양가 할인 10,000,000원",
    "84B 분양가 할인 10,000,000원",
    "84a 분양가 할인 10,000,000원",
    "84Ａ 분양가 할인 10,000,000원",
    "84A형 분양가 할인 10,000,000원",
    "84 A 분양가 할인 10,000,000원",
    "84A·84B 분양가 할인 10,000,000원",
    "84A, 84B 분양가 할인 10,000,000원",
    "84A/84B 분양가 할인 10,000,000원",
    "84A~84C 분양가 할인 10,000,000원",
    "전 타입(84A 포함) 분양가 할인 10,000,000원",
    "84A 분양가 할인 10,000,000원 (84B 제외)",
    "84A 분양가 할인 10,000,000원 (84B는 5,000,000원)",
    "84A 분양가 할인 10,000,000원 / 84B 분양가 할인 5,000,000원",
    "84B 분양가 할인 5,000,000원 / 84A 분양가 할인 10,000,000원",
    "84A-1 분양가 할인 10,000,000원",
    "84A1 분양가 할인 10,000,000원",
    # 추가: 공급금액 허용 꼴·탭·앞뒤 공백
    "84A 공급금액 할인 10,000,000원",
    "84A 분양가 할인 10,000,000원 원",
    "84A 분양가 할인 10,000,000원.",
    "84A 분양가 할인 10,000,000원*",
    "84A 분양가 할인 10,000,000원 |",
    "84A 분양가 할인 010,000,000원",
    "84A 분양가 할인 0원",
    "84A 분양가 할인 0,000,000원",
]


@pytest.mark.parametrize("text", _FUZZ_CASES)
def test_k1_reviewer_fuzz_cases(text: str) -> None:
    """허용 꼴(정확히 그 줄)만 '확인됨'. 그 밖은 None 또는 '추정'."""
    got = _call(text + "\n")
    if text in _CANONICAL:
        assert got is not None and got.confirmed and got.won == 10_000_000, (text, got)  # type: ignore[attr-defined]
    else:
        assert got is None or got.confirmed is False, (text, got)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "text",
    [
        "84A 분양가 할인 0원, 경품 10,000,000원",
        "84A 분양가 할인 0원",
        "84A 분양가 할인 혜택 없이 사은품 10,000,000원",
        "84A 분양가 할인 - , 계약축하금 10,000,000원",
        "84A 분양가 할인 상품권 1,000,000원",
        "84A 분양가 할인 대신 캐시백 1,000,000원",
        "84A 분양가 할인 혜택: 선물 1,000,000원",
        "84A 분양가 할인 혜택 취득세 3,000,000원",
        "84A 분양가 할인 없음",
        "84A 분양가 할인 미적용 (참고 10,000,000원)",
    ],
)
def test_k1_zero_or_non_discount_amount_makes_no_fact(text: str) -> None:
    """D15-1: 금액 0원·할인 아닌 금액(경품·사은품·지원·축하금 등)·'할인 없음' 줄은 할인 사실이 아니다."""
    assert _call(text + "\n") is None, text


def test_k1_canonical_span_and_tabs() -> None:
    """허용 꼴: 앞뒤 ASCII 공백·탭은 허용, 금액 위치는 원문 오프셋."""
    text = "■ 공급금액\n\t84A\t분양가 할인  12,345,000 원  \n"
    got = _call(text)
    assert got is not None and got.confirmed and got.won == 12_345_000, got  # type: ignore[attr-defined]
    assert text[got.span[0] : got.span[1]] == "12,345,000"  # type: ignore[attr-defined]


# ---------------------------------------------------------------- 문법 기반 퍼징(hypothesis)

_TYPES = [
    SHORT,
    LONG,
    "84a",
    "84Ａ",
    "84A형",
    "84㎡",
    "84 A",
    "84B",
    "184A",
    "84A-1",
    "84​A",
    "84A·84B",
    "(84A)",
    "84A(30세대)",
]
_PREFIXES = ["", "", "", " ", "\t", "1~3층 ", "저층 ", "(특별공급) ", "| ", "주택형 ", "​", " ", "※ ", "* "]
_SEPS = [" ", " ", "\t", "  ", "", " ", "​", "　"]
_KINDS = [
    "분양가",
    "공급금액",
    "분양가",
    "공급금액",
    "분양 가격",
    "공급가",
    "계약금",
    "잔금 완납 시 분양가",
    "발코니",
    "분양가 최대",
]
_HALIN = ["할인", "할인", "할인", "할​인", "할인금액", "할인 :", "할인액", "할인(예정)"]
_MIDS = ["", "", "", "최대 ", "약 ", "예정 ", "최소 ", "1차 ", "~"]
_WONS = ["원", "원", " 원", "\t원", "원정", "만원", "원)", "원*"]
_TAILS = [
    "", "", "", "", " ", "\t", "(1~3층)", " 예정", " (일부 세대)", " |", ", 경품 10,000,000원", "*",
    "​", "（１～３층）", " 내외", " ~ 30,000,000원", "~30,000,000원", " 상당", "(2026.10.31.)",
    " (84B 제외)", ".", " 1~3층", " (단, 1층 제외)", "※",
]  # fmt: skip
_NEXTS = [
    None, None, "", "■ 납부 일정", "59B 분양가 할인 5,000,000원", "(1~3층에 한함)", "※ 1~3층",
    "단, 계약 순서에 따라 조기 종료", "* 조건 별도", "1~3층 한정", "  (일부 세대)", "\n\n(계약자에 한하여)",
    "계약자에 한함", "（신혼부부）", "［1F~3F］", "- 저층 한정", "주) 조건", "\t(2026.10.31.)",
    "선착순 30세대", "신혼부부", "일부 세대", "101동 한정", "1F~3F", "최대 금액 기준",
]  # fmt: skip


def _amount_text(draw: st.DrawFn) -> str:
    kind = draw(st.sampled_from(["comma", "comma", "comma", "plain", "zero", "full", "man", "lead0"]))
    n = draw(st.integers(min_value=1_000, max_value=999_999_999))
    if kind == "comma":
        return f"{n:,}"
    if kind == "plain":
        return str(n)
    if kind == "zero":
        return "0"
    if kind == "full":
        return f"{n:,}".translate(str.maketrans("0123456789", "０１２３４５６７８９"))
    if kind == "man":
        return f"{n // 10_000:,}만"
    return "0" + f"{n:,}"


@st.composite
def _discount_text(draw: st.DrawFn) -> str:
    line = (
        draw(st.sampled_from(_PREFIXES))
        + draw(st.sampled_from(_TYPES))
        + draw(st.sampled_from(_SEPS))
        + draw(st.sampled_from(_KINDS))
        + draw(st.sampled_from(["", " ", "​"]))
        + draw(st.sampled_from(_HALIN))
        + draw(st.sampled_from(_SEPS))
        + draw(st.sampled_from(_MIDS))
        + _amount_text(draw)
        + draw(st.sampled_from(_WONS))
        + draw(st.sampled_from(_TAILS))
        + draw(st.text(alphabet="  \t()~층동호예정단※*,.0123456789", max_size=3))
    )
    nxt = draw(st.sampled_from(_NEXTS))
    before = draw(st.sampled_from(["", "", "■ 할인 안내\n", "84B 분양가 할인 5,000,000원\n"]))
    return before + line + ("" if nxt is None else "\n" + nxt) + "\n"


@settings(max_examples=3000, deadline=None, derandomize=True)
@given(_discount_text())
def test_k1_property_confirmed_only_if_canonical(text: str) -> None:
    """허용 꼴이 아니면 '확인됨' 0건: 확인됨이면 독립 오라클(전체 일치 + 다음 줄 조건 없음)도 참이다."""
    got = _call(text)
    if got is not None and got.confirmed:  # type: ignore[attr-defined]
        assert _oracle_ok(text, got.span), (text, got)  # type: ignore[attr-defined]
        assert got.won > 0  # type: ignore[attr-defined]


@settings(max_examples=500, deadline=None, derandomize=True)
@given(
    st.sampled_from([SHORT, LONG]),
    st.sampled_from(["분양가", "공급금액"]),
    st.integers(min_value=1_000, max_value=999_999_999),
    st.sampled_from(["", " ", "\t"]),
    st.sampled_from(
        [None, "", "■ 납부 일정", "59B 분양가 할인 5,000,000원", "084.9100B 공급금액 할인 3,000,000원", "■"]
    ),
)
def test_k1_property_canonical_is_confirmed(typ: str, kind: str, won: int, pad: str, nxt: str | None) -> None:
    """허용 꼴 + 무해한 다음 줄(없음·빈 줄·다른 타입 허용 꼴·'■ 납부 일정') → 확인됨, 금액·위치 일치."""
    head = f"{pad}{typ} {kind} 할인 "
    amount = f"{won:,}"
    text = head + amount + "원" + pad + ("" if nxt is None else "\n" + nxt) + "\n"
    got = _call(text)
    assert got is not None and got.confirmed, (text, got)  # type: ignore[attr-defined]
    assert got.won == won and got.span == (len(head), len(head) + len(amount)), got  # type: ignore[attr-defined]


# ---------------------------------------------------------------- 공고문 파서 경로


def test_k1_parse_notice_text_labels() -> None:
    """parse_notice_text: 다음 줄 조건 → '추정'(차감 없음), 0원+경품 → 후보 없음, 허용 꼴 → '확인됨'."""
    from app.core.contracts_gen import RawDocument as RawDTO
    from app.normalize.notice_parser import parse_notice_text

    base = (Path(__file__).parent / "fixtures" / "notice" / "2025000222_switzen.txt").read_text(
        encoding="utf-8"
    )
    raw = RawDTO(id=1, source_kind="notice_pdf", url="https://static.applyhome.co.kr/x.pdf",
                 fetched_at="2026-10-09T00:00:00+09:00", http_status=200, sha256="0" * 64, region_id=1, path=None,
                 content_type=None, text_path=None, complex_id=None)  # fmt: skip

    def disc(tail: str) -> list[tuple[object, str, str | None]]:
        return [
            (c.value, c.label, c.reason)
            for c in parse_notice_text(base + "\n" + tail + "\n", raw)
            if c.field == "discount_by_type.84A"
        ]

    got = disc("84A 분양가 할인 1,200,000원\n(1~3층에 한함)")
    assert len(got) == 1 and got[0][:2] == (1_200_000, "추정") and "조건부 할인" in (got[0][2] or ""), got
    got = disc("84A 분양가 할인 1,200,000원 예정")
    assert len(got) == 1 and got[0][:2] == (1_200_000, "추정"), got
    assert disc("84A 분양가 할인 0원, 경품 1,200,000원") == []
    assert disc("84A 분양가 할인 1,200,000원") == [(1_200_000, "확인됨", None)]
    assert disc("84A 분양가 할인 1,200,000원\n■ 납부 일정") == [(1_200_000, "확인됨", None)]

"""R3h CORE6 — 8차 리뷰 N-C1 / **D16-1**: 자동 파싱으로 얻은 할인은 언제나 '추정'(D14-2·D15-1 대체).

공고문 파서는 할인 후보를 찾아 표시하지만 '확인됨'을 만들지 않는다 — 조건 문구는 앞뒤 줄·떨어진 각주·표 머리에 흩어져 있어
줄 단위 규칙으로 '조건 없음'을 증명할 수 없다(7·8차 누출). 구매가 차감은 사람 확인(``discount``)·공식 구조화 출처만
(``tests/api/test_r3h_discount_human.py``).

| 리뷰 | 테스트 |
| --- | --- |
| N-C1 (a)~(d) 재현 문구 + 7차 K1 문구 + 예전 허용 꼴 | ``test_nc1_parser_discount_is_never_confirmed`` |
| 속성: 파서 출력에 할인 '확인됨' 0건(문법 퍼징 — 앞 줄·머리줄·3줄 블록·떨어진 각주·목록 밖 조건 포함) | ``test_nc1_property_parser_never_confirms_discount`` |
| 금액 0원·할인 아닌 금액·'할인 없음' 줄 → 할인 후보 없음(표시도 안 함) | ``test_nc1_zero_or_non_discount_makes_no_candidate`` |
| '추정' 후보 사유 = 사람 확인 안내 | ``test_nc1_estimate_reason_points_to_human_check`` |
| 녹화 공고 전체: 할인 '확인됨' 0건 | ``test_nc1_recorded_notices_have_no_confirmed_discount`` |

m1(흔한 머리줄 다음 무조건 할인 과강등)·m2(오라클이 구현과 같은 금지어 방식)는 D16-1 로 흡수 — 과강등 개념이 없어졌고
오라클은 '확인됨 0건' 하나다.
"""

# ruff: noqa: E501

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

FIX = Path(__file__).parent / "fixtures" / "notice"
REPO = Path(__file__).resolve().parents[3]
TYPES = ("84A", "84B", "84C", "99A", "99B")  # 2025000222_switzen 공급 타입


@cache
def _base() -> str:
    return (FIX / "2025000222_switzen.txt").read_text(encoding="utf-8")


def _raw() -> Any:
    from app.core.contracts_gen import RawDocument as RawDTO

    return RawDTO(id=1, source_kind="notice_pdf", url="https://static.applyhome.co.kr/x.pdf",
                  fetched_at="2026-10-09T00:00:00+09:00", http_status=200, sha256="0" * 64, region_id=1, path=None,
                  content_type=None, text_path=None, complex_id=None)  # fmt: skip


def _disc(text: str) -> list[tuple[str, object, str | None, str | None]]:
    from app.normalize.notice_parser import parse_notice_text

    return [
        (c.field, c.value, c.label, c.reason)
        for c in parse_notice_text(text, _raw())
        if c.field.startswith("discount_by_type.")
    ]


C = "84A 분양가 할인 1,200,000원"

REVIEW_PHRASES = [
    # 예전 허용 꼴(D15-1 '확인됨') — 이제 '추정'
    C,
    "84A 공급금액 할인 1,200,000원",
    "84A\t분양가\t할인\t1,200,000\t원",
    "84A\t분양가 할인\t1,200,000원\t",
    C + "\n■ 납부 일정",
    # N-C1 (a) 타입 나열 뒤 공통 각주
    C + "\n84B 분양가 할인 1,100,000원\n(1~3층에 한함)",
    "84B 분양가 할인 1,100,000원\n" + C + "\n(1~3층에 한함)",
    # N-C1 (b) 목록 밖 조건
    C + "\n무주택자만 적용",
    C + "\n할부 시 미적용",
    C + "\n법인 불가",
    C + "\n타입별 상이",
    C + "\n현금 일시납 시",
    C + "\n견본주택 방문 고객 전용",
    C + "\n향후 사업 여건에 따라 축소될 수 있음",
    C + "\nApplied to 1-3F",
    # N-C1 (c) 앞 줄·머리줄 조건
    "[1~3층 한정]\n" + C,
    "■ 저층 세대(1~3층) 분양가 할인\n" + C,
    "※ 아래 할인은 1~3층 세대에 한함\n" + C,
    "(특별공급 당첨자 한정)\n" + C,
    "□ 계약 조건부 할인(선착순 30세대)\n" + C,
    # N-C1 (d) 떨어진 각주
    C + "\n■ 유의사항\n※ 상기 분양가 할인은 1~3층 세대에 한함",
    C + "\n\n■ 납부 일정\n계약금 10%\n※ 84A 할인은 1~3층 세대에 한함",
    # 7차 K1
    C + "\n(1~3층에 한함)",
    C + "\n(일부 세대)",
    C + " 예정",
    "84A 분양가 할인 1,200,000원 ~ 3,000,000원",
]


@pytest.mark.parametrize("tail", REVIEW_PHRASES)
@pytest.mark.parametrize("where", ["end", "start"])
def test_nc1_parser_discount_is_never_confirmed(tail: str, where: str) -> None:
    """리뷰 재현(8차 N-C1 a~d, 7차 K1, 예전 허용 꼴): 할인 후보는 있으면 '추정'뿐 — 500,000,000 → 490,000,000 차감 없음."""
    text = _base() + "\n" + tail + "\n" if where == "end" else tail + "\n" + _base()
    got = _disc(text)
    assert any(f == "discount_by_type.84A" for f, *_ in got), got  # 후보는 찾아 표시한다
    assert all(label == "추정" for _f, _v, label, _r in got), got


@pytest.mark.parametrize(
    "tail",
    [
        "84A 분양가 할인 0원, 경품 1,200,000원",
        "84A 분양가 할인 0원",
        "84A 취득세 지원 1,200,000원",
        "84A 분양가 할인 없음, 중도금 이자 지원 1,200,000원",
        "84A 경품 1,200,000원 할인",
        "84A 분양가 할인 미적용 (참고 1,200,000원)",
        "84A 분양가 할인 혜택 없이 사은품 1,200,000원",
    ],
)
def test_nc1_zero_or_non_discount_makes_no_candidate(tail: str) -> None:
    """0원·할인 아닌 금액(경품·지원 등)·'할인 없음' 줄은 할인 후보도 없다(표시할 할인이 아니다)."""
    assert _disc(_base() + "\n" + tail + "\n") == []


def test_nc1_estimate_reason_points_to_human_check() -> None:
    """'추정' 후보의 사유: 공고문 자동 추출 — 조건 확인 필요(사람 확인 시 구매가 반영, D16-1 화면 안내와 같은 뜻)."""
    got = _disc(_base() + "\n" + C + "\n")
    assert got and got[0][1] == 1_200_000 and got[0][2] == "추정", got
    assert "조건 확인 필요" in (got[0][3] or ""), got


# ---------------------------------------------------------------- 문법 퍼징(속성: '확인됨' 0건)

_PREV = [
    "",
    "",
    "",
    "[1~3층 한정]\n",
    "■ 저층 세대 할인\n",
    "※ 아래 할인은 1~3층\n",
    "(특별공급 한정)\n",
    "□ 할인 안내\n",
]
_SEPS = [" ", " ", "\t", "  ", "", " ", "​", "　"]
_KINDS = ["분양가", "공급금액", "분양가", "공급금액", "분양 가격", "공급가", "분양가 최대"]
_TAILS = ["", "", "", " ", "\t", "(1~3층)", " 예정", " (일부 세대)", " |", "*", "（１～３층）", " 내외", "."]
_NEXTS = [
    None, None, "", "■ 납부 일정", "84B 분양가 할인 5,000,000원", "(1~3층에 한함)", "무주택자만 적용", "할부 시 미적용",
    "법인 불가", "타입별 상이", "■ 유의사항\n※ 상기 할인은 1~3층", "84B 분양가 할인 5,000,000원\n(1~3층에 한함)",
    "\n\n■ 납부 일정\n계약금 10%\n※ 할인은 1~3층", "Applied to 1-3F", "신혼부부",
]  # fmt: skip


@st.composite
def _discount_block(draw: st.DrawFn) -> str:
    typ = draw(st.sampled_from(TYPES))
    won = draw(st.integers(min_value=1_000, max_value=99_999_999))
    amount = draw(st.sampled_from([f"{won:,}", f"{won:,}", str(won)]))
    line = (
        draw(st.sampled_from(["", "", " ", "\t"]))
        + typ
        + draw(st.sampled_from(_SEPS))
        + draw(st.sampled_from(_KINDS))
        + draw(st.sampled_from([" ", "", "\t"]))
        + "할인"
        + draw(st.sampled_from(_SEPS))
        + amount
        + draw(st.sampled_from(["원", " 원", "\t원"]))
        + draw(st.sampled_from(_TAILS))
    )
    nxt = draw(st.sampled_from(_NEXTS))
    return draw(st.sampled_from(_PREV)) + line + ("" if nxt is None else "\n" + nxt)


@settings(max_examples=600, deadline=None, derandomize=True)
@given(_discount_block(), st.sampled_from(["end", "start", "middle"]))
def test_nc1_property_parser_never_confirms_discount(block: str, where: str) -> None:
    """D16-1 속성: 공고문 파서 출력에 할인 '확인됨' 0건(어떤 꼴·위치·앞뒤 줄이든). 오라클 = '확인됨이 없다' 하나."""
    base = _base()
    if where == "end":
        text = base + "\n" + block + "\n"
    elif where == "start":
        text = block + "\n" + base
    else:
        cut = base.find("\n", len(base) // 2) + 1
        text = base[:cut] + block + "\n" + base[cut:]
    assert all(label != "확인됨" for _f, _v, label, _r in _disc(text)), (block, _disc(text))


def test_nc1_recorded_notices_have_no_confirmed_discount() -> None:
    """녹화 공고문 텍스트 전부(파서 픽스처·계약 픽스처): 할인 '확인됨' 0건(실데이터 영향 없음 — 할인 줄 0건 확인)."""
    texts = [p.read_text(encoding="utf-8") for p in sorted(FIX.glob("*.txt"))]
    texts += [
        p.read_text(encoding="utf-8")
        for p in sorted((REPO / "contracts" / "fixtures").rglob("raw/notice/*.txt"))
    ]
    assert len(texts) >= 16
    confirmed = [c for t in texts for c in _disc(t) if c[2] == "확인됨"]
    assert confirmed == []

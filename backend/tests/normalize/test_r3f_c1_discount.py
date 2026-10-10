"""R3f CORE4 — 6차 리뷰 C1 / D14-2: 할인 '확인됨'은 **줄 전체**(금액 앞뒤·괄호·각주)에 조건이 없을 때만.

| 리뷰 | 테스트 |
| --- | --- |
| C1 리뷰 재현 문구 5개(층 괄호·잔금 완납 시·특별공급 한정·최대·'할인 없음, 취득세 지원') | ``test_c1_review_phrases`` |
| D14-2 조건 토큰(줄 전체) | ``test_c1_condition_tokens_anywhere_on_line`` |
| D14-2 '할인 없음/미적용' 줄은 할인 사실 없음 | ``test_c1_no_discount_line_makes_no_fact`` |
| D14-2 취득세·중도금 이자·발코니·옵션 지원은 할인 아님 | ``test_c1_support_amount_is_not_discount`` |
| 조건 없는 줄은 그대로 '확인됨' | ``test_c1_plain_line_stays_confirmed`` |
| 공고문 파서 경로(후보 라벨) | ``test_c1_parse_notice_text_labels`` |
"""

# ruff: noqa: E501

from __future__ import annotations

from pathlib import Path

import pytest

T84 = ("84A", "084.9582A")


def _line(line: str, spec: tuple[str, str] = T84) -> tuple[int, bool] | None:
    from app.normalize.notice_parser import TypeSpec, _discount_line

    t = TypeSpec(short=spec[0], long=spec[1], area_text="84.9582", units=10, span=(0, 1))
    got = _discount_line(line + "\n", t)
    return None if got is None else (got.won, got.confirmed)


@pytest.mark.parametrize(
    ("line", "want"),
    [
        ("84A 분양가 할인 10,000,000원(1~3층)", (10_000_000, False)),
        ("84A 잔금 완납 시 분양가 할인 5,000,000원", (5_000_000, False)),
        ("84A 분양가 할인 10,000,000원(특별공급 당첨자 한정)", (10_000_000, False)),
        ("84A 분양가 할인 최대 10,000,000원", (10_000_000, False)),
        ("84A 분양가 할인 없음, 취득세 지원 3,000,000원", None),
    ],
)
def test_c1_review_phrases(line: str, want: tuple[int, bool] | None) -> None:
    """리뷰 재현: 예전엔 전부 '확인됨'((금액, True)) — 조건부는 '추정', '할인 없음' 줄은 할인 사실 없음."""
    assert _line(line) == want, line


@pytest.mark.parametrize(
    "line",
    [
        "84A 분양가 할인 10,000,000원 (잔금 완납 시)",
        "84A 분양가 할인 10,000,000원 (단, 1층 제외)",
        "84A 분양가 할인 10,000,000원 (101동 한정)",
        "84A 분양가 할인 10,000,000원 (3호 라인)",
        "84A 분양가 할인 10,000,000원 (선착순 30세대)",
        "84A 분양가 할인 10,000,000원 (계약 체결 시)",
        "84A 분양가 할인 10,000,000원 (2026.12.31까지)",
        "84A 분양가 할인 10,000,000원 (계약 기간 내)",
        "84A 분양가 할인 10,000,000원 ※ 조건 별도",
        "84A 분양가 할인 10,000,000원 (조건부)",
        "84A 분양가 할인 10,000,000원*",
        "84A 분양가 할인 10,000,000원(주1)",
        "84A 분양가 할인 10,000,000원 (84B 외)",
        "84A 분양가 할인 10,000,000원 (특공 제외)",
        "84A 현금완납 분양가 할인 10,000,000원",
        "84A 분양가 할인 10,000,000원 (10층 이상)",
        "84A 분양가 할인 10,000,000원 (저층)",
    ],
)
def test_c1_condition_tokens_anywhere_on_line(line: str) -> None:
    """D14-2: 조건이 금액 **뒤**·괄호·각주에 있어도 '추정'(구매가에서 빼지 않는다)."""
    got = _line(line)
    assert got is not None and got[1] is False, (line, got)


@pytest.mark.parametrize(
    "line",
    [
        "84A 분양가 할인 없음",
        "84A 분양가 할인 없음, 취득세 지원 3,000,000원",
        "84A 분양가 할인 미적용 (참고 10,000,000원)",
        "84A 분양가 할인 해당 없음 / 발코니 무상 3,000,000원",
        "84A 분양가 할인 10,000,000원 미적용",
    ],
)
def test_c1_no_discount_line_makes_no_fact(line: str) -> None:
    assert _line(line) is None, line


@pytest.mark.parametrize(
    "line",
    [
        "84A 분양가 할인 혜택: 취득세 지원 3,000,000원",
        "84A 분양가 할인 대신 중도금 이자 지원 3,000,000원",
        "84A 분양가 할인 상당 옵션 지원 3,000,000원",
        "84A 분양가 할인 상당 발코니 지원 3,000,000원",
    ],
)
def test_c1_support_amount_is_not_discount(line: str) -> None:
    """D14-2: 취득세·중도금 이자·발코니·옵션 **지원**은 할인이 아니다 — 그 금액으로 할인 사실을 만들지 않는다."""
    assert _line(line) is None, line


@pytest.mark.parametrize(
    "line",
    [
        "84A 분양가 할인 10,000,000원",
        "84A 공급금액 할인 10,000,000원",
        "84A(30세대) 분양가 할인 10,000,000원",
        "주택형 84A 분양가 할인금액 : 10,000,000원",
        "084.9582A 분양가 할인 10,000,000원",
    ],
)
def test_c1_plain_line_stays_confirmed(line: str) -> None:
    """조건 없는 분양가 할인 줄은 그대로 '확인됨'(회귀 방지)."""
    assert _line(line) == (10_000_000, True), line


def test_c1_parse_notice_text_labels() -> None:
    """공고문 파서 경로: 조건부 → 후보 라벨 '추정'(사유 '조건부 할인'), '할인 없음' 줄 → 할인 후보 없음."""
    from app.core.contracts_gen import RawDocument as RawDTO
    from app.normalize.notice_parser import parse_notice_text

    base = (Path(__file__).parent / "fixtures" / "notice" / "2025000222_switzen.txt").read_text(
        encoding="utf-8"
    )
    raw = RawDTO(id=1, source_kind="notice_pdf", url="https://static.applyhome.co.kr/x.pdf",
                 fetched_at="2026-10-09T00:00:00+09:00", http_status=200, sha256="0" * 64, region_id=1, path=None,
                 content_type=None, text_path=None, complex_id=None)  # fmt: skip

    def disc(line: str) -> list[tuple[object, str, str | None]]:
        return [
            (c.value, c.label, c.reason)
            for c in parse_notice_text(base + "\n" + line + "\n", raw)
            if c.field == "discount_by_type.84A"
        ]

    got = disc("84A 분양가 할인 1,200,000원(1~3층)")
    assert len(got) == 1 and got[0][:2] == (1_200_000, "추정") and "조건부 할인" in (got[0][2] or ""), got
    assert disc("84A 분양가 할인 없음, 취득세 지원 1,200,000원") == []
    assert disc("84A 분양가 할인 1,200,000원") == [(1_200_000, "확인됨", None)]

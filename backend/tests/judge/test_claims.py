"""claims.py — 원자 주장 분할(T6). 규칙 기반, 판정기 호출 없음."""

from __future__ import annotations

import pytest

from app.core.protocols import ClaimSplitter
from app.judge.claims import CompoundClaimError, RuleClaimSplitter, is_atomic
from app.judge.payloads import verify_payload

T6 = "3개는 unlikely이고 나머지는 uncertain"


@pytest.fixture
def splitter() -> RuleClaimSplitter:
    return RuleClaimSplitter()


def test_protocol(splitter: RuleClaimSplitter) -> None:
    assert isinstance(splitter, ClaimSplitter)


def test_t6_compound_sentence_splits(splitter: RuleClaimSplitter) -> None:
    claims = splitter.split(T6, section="12-4", snapshot_id=None, complex_id=None)
    assert len(claims) >= 2
    texts = [c.text for c in claims]
    assert texts[0] == "3개는 unlikely"
    assert texts[1] == "나머지는 uncertain"
    assert [c.ordinal for c in claims] == list(range(len(claims)))
    assert all(c.section == "12-4" for c in claims)
    assert all(c.verify_status is None and c.judgment_seq is None for c in claims)


def test_t6_compound_sentence_to_verify_fails() -> None:
    """복합 문장을 그대로 verify에 보내면 실패한다."""
    assert not is_atomic(T6)
    with pytest.raises(CompoundClaimError):
        verify_payload([T6], [("e1", "noul #120 결과: 3개 unlikely, 1개 uncertain")])


def test_atomic_claims_go_to_verify(splitter: RuleClaimSplitter) -> None:
    claims = [c.text for c in splitter.split(T6)]
    payload = verify_payload(claims, [("e1", "noul #120 결과")])
    assert payload["claims"] == claims
    assert payload["evidence"] == [{"id": "e1", "text": "noul #120 결과"}]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("엘리프의 +10% 명제는 0.45이며 +20% 명제는 0.36이다.", 2),
        ("그란테르 5.87, 엘리프 5.70, 한내들 5.33", 3),
        ("계약금은 10%이다. 중도금은 60%이다.", 2),
        ("전매 종료는 2028-09이고 거주의무는 없다", 2),
        ("센트레빌·더샵 AB23은 공동 5위다", 2),
        ("현재 구매가는 5.78~6.08억이다", 1),
        ("계약금 7,490만 ≤ 자기자본 1억", 1),
        ("입주는 2028-03이다", 1),
    ],
)
def test_split_counts(splitter: RuleClaimSplitter, text: str, expected: int) -> None:
    claims = splitter.split(text)
    assert len(claims) == expected, [c.text for c in claims]
    assert all(c.text.strip() for c in claims)


def test_subject_is_carried_to_later_clauses(splitter: RuleClaimSplitter) -> None:
    claims = splitter.split("엘리프의 +10% 명제는 0.45이며 +20% 명제는 0.36이다.")
    assert claims[1].text.startswith("엘리프의 ")


def test_enumerated_subject_is_distributed(splitter: RuleClaimSplitter) -> None:
    texts = [c.text for c in splitter.split("센트레빌·더샵 AB23은 공동 5위다")]
    assert texts == ["센트레빌은 공동 5위다", "더샵 AB23은 공동 5위다"]


def test_keywords_fill_claim(splitter: RuleClaimSplitter) -> None:
    (c,) = splitter.split("입주는 2028-03이다", section="6", snapshot_id=None, complex_id=None)
    assert c.section == "6"
    assert c.text == "입주는 2028-03이다"


def test_empty_text_gives_no_claims(splitter: RuleClaimSplitter) -> None:
    assert splitter.split("  ") == []

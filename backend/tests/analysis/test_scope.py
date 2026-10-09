"""R3 C2 / DECISIONS D9-1: 판정 범위 공용 함수(analysis/scope.py) — 미분류·manual_review·확인 불가·불가·보류 각각."""

# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass
import pytest

from app.analysis.scope import (
    JUDGE_SCOPES,
    SCOPE_TEXT,
    contract_scope,
    in_rerank,
    is_decide_candidate,
    is_scored,
    judge_scope,
    pick_intake,
    runs_ladder,
)

from ._support import EXPECTED, FIXTURE, load_json


def _scope(
    cls: str | None = "private_sale_apt",
    decision: str | None = "auto",
    price: bool = True,
    intake: str | None = "가능",
) -> str:
    return judge_scope(
        inclusion_class=cls, inclusion_decision=decision, has_price=price, intake_status=intake
    ).scope


@pytest.mark.parametrize(
    ("cls", "decision", "price", "intake", "want"),
    [
        # 미해결: classify 미분류·review·manual_review(결정·클래스 둘 다)
        ("미분류", None, True, "가능", "미해결"),
        (None, None, True, "가능", "미해결"),
        ("private_sale_apt", "review", True, "가능", "미해결"),
        ("private_sale_apt", "manual_review", True, "가능", "미해결"),
        ("manual_review", "auto", True, "가능", "미해결"),
        ("private_sale_apt", None, True, "가능", "미해결"),  # 판정기 결정 없음 = 확정 아님
        ("public_sale", "review", True, "가능", "미해결"),  # 제외 클래스도 auto 가 아니면 미해결
        # 제외: auto 제외 클래스, 범위 경계(결정 무관)
        ("public_sale", "auto", True, "가능", "제외"),
        ("public_rental", "auto", True, "가능", "제외"),
        ("private_rental", "auto", True, "가능", "제외"),
        ("non_apartment", "auto", True, "가능", "제외"),
        ("out_of_scope", "auto", True, "가능", "제외"),
        ("범위 경계", None, True, "가능", "제외"),
        # 보류: 포함 확정 + 분양가 미공개(접수 상태 무관)
        ("private_sale_apt", "auto", False, "가능", "보류"),
        ("private_sale_apt", "auto", False, "확인 불가", "보류"),
        # 참고: 포함 확정 + 가격 + 접수 확인 불가·불가·행 없음
        ("private_sale_apt", "auto", True, "확인 불가", "참고"),
        ("private_sale_apt", "auto", True, "불가", "참고"),
        ("private_sale_apt", "auto", True, None, "참고"),
        # 판정 대상: 포함 확정 + 가격 + 접수 가능·미정
        ("private_sale_apt", "auto", True, "가능", "판정 대상"),
        ("private_sale_apt", "auto", True, "미정", "판정 대상"),
    ],
)
def test_judge_scope_table(
    cls: str | None, decision: str | None, price: bool, intake: str | None, want: str
) -> None:
    assert _scope(cls, decision, price, intake) == want


def test_scope_text_and_reason_are_never_empty() -> None:
    assert SCOPE_TEXT["보류"] == "보류 — 공고 후 재판정"
    assert SCOPE_TEXT["참고"] == "참고 후보(순위만)"
    assert SCOPE_TEXT["미해결"] == "미해결(분류 판정 미해결)"
    r = judge_scope(
        inclusion_class="private_sale_apt", inclusion_decision="review", has_price=True, intake_status="가능"
    )
    assert r.text == "미해결(분류 판정 미해결)" and "review" in r.reason
    for s in JUDGE_SCOPES:
        assert SCOPE_TEXT[s].strip()


@pytest.mark.parametrize(
    ("scope", "ladder", "rerank", "scored", "decide"),
    [
        ("판정 대상", True, True, True, True),
        ("참고", False, True, True, False),  # 사다리 미실행, rerank 후보에는 포함(D9-1)
        ("보류", False, True, True, False),
        ("미해결", False, False, False, False),  # 판정 대상 아님 — 사다리·점수 없음
        ("제외", False, False, False, False),
    ],
)
def test_scope_participation_rules(
    scope: str, ladder: bool, rerank: bool, scored: bool, decide: bool
) -> None:
    assert (runs_ladder(scope), in_rerank(scope), is_scored(scope), is_decide_candidate(scope)) == (
        ladder, rerank, scored, decide,
    )  # fmt: skip


def test_contract_scope_carries_unresolved_as_unscored_until_contract_4() -> None:
    for s in ("판정 대상", "참고", "보류", "제외"):
        assert contract_scope(s) == s  # type: ignore[arg-type]
    assert contract_scope("미해결") in ("미해결", "제외")
    assert not is_scored(contract_scope("미해결"))


@dataclass
class _Row:
    id: int
    path: str
    checked_at: str | None
    status: str


def test_pick_intake_priority_then_day_then_id_minor21() -> None:
    rows = [
        _Row(1, "official_popup", "2026-10-08T09:00:00+09:00", "가능"),
        _Row(2, "unofficial_ref", "2026-10-09", "가능"),  # 비공식은 근거 아님
        _Row(3, "headless_shot", "2026-10-09T09:00:00+09:00", "불가"),
    ]
    assert pick_intake(rows) is rows[0]  # 경로 우선
    rows.append(_Row(4, "human_check", "2026-10-07", "미정"))
    assert pick_intake(rows) is rows[3]  # 사람 확인이 날짜가 이르더라도 우선
    # 같은 날 '날짜만' vs '시각 포함' — 시각 문자열 비교가 아니라 나중 기록(id)이 이긴다
    same_day = [
        _Row(10, "official_popup", "2026-10-08T23:00:00+09:00", "가능"),
        _Row(11, "official_popup", "2026-10-08", "불가"),
    ]
    assert pick_intake(same_day) is same_day[1]
    assert pick_intake(list(reversed(same_day))) is same_day[1]
    # 다른 날이면 최근 날짜
    days = [
        _Row(21, "official_popup", "2026-10-09", "미정"),
        _Row(20, "official_popup", "2026-10-08T10:00", "가능"),
    ]
    assert pick_intake(days) is days[0]
    assert pick_intake([_Row(5, "unofficial_ref", "2026-10-09", "가능")]) is None


def _fixture_scopes() -> dict[int, str]:
    out: dict[int, str] = {}
    for b in load_json(FIXTURE / "complexes.json"):
        c = b["complex"]
        intake = pick_intake(
            [_Row(i, r["path"], r.get("checked_at"), r["status"]) for i, r in enumerate(b["intake"], 1)]
        )
        has_price = any(
            (t["max_price_won"].get("v") if isinstance(t["max_price_won"], dict) else t["max_price_won"])
            is not None
            for t in b["types"]
        )
        out[c["id"]] = _scope(
            c["inclusion_class"], c["inclusion_decision"], has_price, intake.status if intake else None
        )
    return out


def test_d9_scope_on_fixture_facts_vs_golden_inputs_documented_diff() -> None:
    """골든 v2·T1 입력의 judge_scope(보고서 당시 규칙)와 D9-1을 픽스처 사실에 적용한 값의 차이 — 보고용 표.

    골든 파일은 입력에 judge_scope 를 내장하므로 회귀 재현(test_golden_v2·test_score_regression)은 그대로다.
    실데이터 파이프라인에서는 아래 단지가 다른 범위가 된다(사유: 픽스처 접수 '불가' / classify review).
    """
    d9 = _fixture_scopes()
    v2 = {
        c["complex_id"]: c["judge_scope"]
        for c in load_json(FIXTURE / "expected_scores_v2.json")["inputs"]["complexes"]
    }
    a = {c["complex_id"]: c["judge_scope"] for c in EXPECTED["complexes"]}
    assert v2 == a
    diff = {cid: (v2[cid], d9[cid]) for cid in sorted(d9) if d9[cid] != v2[cid]}
    assert diff == {
        1: ("판정 대상", "참고"),  # 더샵 송도그란테르: 픽스처 공식 팝업 '불가'
        4: ("판정 대상", "미해결"),  # 오퍼스 한강 스위첸: classify review
        12: ("판정 대상", "참고"),  # 더샵 송도마리나베이: 공식 팝업 '불가'
        14: ("참고", "미해결"),  # 사우역 지엔하임: classify review
        16: ("보류", "미해결"),  # 검단 센트레빌 그랑포레: classify review
    }

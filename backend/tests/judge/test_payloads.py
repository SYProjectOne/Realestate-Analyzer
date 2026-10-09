"""payloads.py — 증거 카드 ≤2,000자, 사다리 명제 3 horizon × 4(T10), rerank 전체 1회(T7), decide ≤6 + 요건 문자열.

payload 모양은 실제 JEV 0.14.1 입력 스키마(fixtures/jev_tools.json)로 검증한다.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import jsonschema
import pytest

from app.core.contracts_gen import RequirementPre, RequirementPreSet
from app.core.protocols import input_hash
from app.judge import payloads as P

from .conftest import FIXTURES, FakeTransport

ASOF = "2026-10-08"
TOOLS = {
    t["name"]: t["input_schema"]
    for t in json.loads((FIXTURES / "jev_tools.json").read_text("utf-8"))["tools"]
}


def assert_jev_valid(tool: str, payload: dict[str, Any]) -> None:
    jsonschema.validate(payload, TOOLS[f"jev_{tool}"])


def card(complex_id: int, name: str, move_in: str | None, **kw: Any) -> P.EvidenceCard:
    return P.EvidenceCard(
        complex_id=complex_id,
        name=name,
        basis_type="84A",
        price_range="5.78~6.08억",
        price_composition="공급가+발코니",
        move_in_ym=move_in,
        **kw,
    )


# ------------------------------------------------------------------ 증거 카드


def test_evidence_card_fixed_order_and_limit() -> None:
    c = card(
        2,
        "엘리프 검단 포레듀",
        "2028-03",
        living_area="서구(검단)",
        resale="전매 종료 2028-09",
        residency="거주의무 0개월",
        down_payment="계약금 10%",
        interim="중도금 이자후불제",
        intake="접수 가능(공식 팝업 2026-10-07)",
        comparables="생활권 신축 84㎡ 최근 6개월 실거래 5.4~6.1억",
        gap="가격 갭 중앙값 +2.1%",
        benchmark="벤치마크 3건: 분양가 대비 +18% 중앙",
        supply="입주 후 1년 ±12개월 동시 입주 3,200세대",
        catalysts=["인천 1호선 검단 연장(확정)", "x" * 3000],
    )
    text = P.evidence_card_text(c)
    assert len(text) <= P.EVIDENCE_CARD_MAX == 2000
    lines = text.splitlines()
    assert lines[0].startswith("단지: 엘리프 검단 포레듀")
    keys = [ln.split(":", 1)[0] for ln in lines]
    # 항목 순서 고정
    order = [k for k in P.EVIDENCE_CARD_ORDER if k in keys]
    assert keys[: len(order)] == order


def test_evidence_card_redacts_contact_info() -> None:
    c = card(1, "단지", "2028-03", intake="분양 문의 1588-1234 접수 가능")
    text = P.evidence_card_text(c)
    assert "1588-1234" not in text


# ------------------------------------------------------------------ 사다리 (T10)


def test_ladder_three_horizons_four_propositions_each() -> None:
    c = card(11, "고촌센트럴자이", "2027-06")
    specs = P.ladder_specs(c, asof_date=ASOF)
    assert [s.horizon for s in specs] == ["move_in_plus_1y", "asof_plus_3y", "asof_plus_5y"]
    for s in specs:
        assert len(s.propositions) == 4
        assert [k for k, _ in s.propositions] == ["p5", "p10", "p20", "p_flat"]
        payload = P.noul_payload(s, card_text=P.evidence_card_text(c))
        assert payload["propositions"] == [t for _, t in s.propositions]
        assert_jev_valid("noul", payload)
        assert s.purpose.startswith(f"noul:ladder:{s.horizon}:{s.target_ym}")


def test_t10_asof_plus_3y_target_is_same_for_all_complexes() -> None:
    """T10: 고촌(2027 입주) vs 리버프론트(2032 입주) — asof_plus_3y 목표 시점이 단지 무관 동일."""
    gochon = {s.horizon: s for s in P.ladder_specs(card(11, "고촌센트럴자이", "2027-06"), asof_date=ASOF)}
    river = {s.horizon: s for s in P.ladder_specs(card(9, "리버프론트", "2032-01"), asof_date=ASOF)}
    assert gochon["asof_plus_3y"].target_ym == river["asof_plus_3y"].target_ym == "2029-10"
    assert gochon["asof_plus_5y"].target_ym == river["asof_plus_5y"].target_ym == "2031-10"
    assert gochon["asof_plus_3y"].months_from_asof == river["asof_plus_3y"].months_from_asof == 36
    # 입주 기준 시점은 단지마다 다르다
    assert gochon["move_in_plus_1y"].target_ym == "2028-06"
    assert river["move_in_plus_1y"].target_ym == "2033-01"


def test_ladder_template_matches_meta_2_2() -> None:
    c = P.EvidenceCard(
        complex_id=2,
        name="엘리프 검단 포레듀",
        basis_type="84A",
        price_range="5.78~6.08억",
        price_composition="공급가+발코니",
        move_in_ym="2028-03",
    )
    spec = next(s for s in P.ladder_specs(c, asof_date=ASOF) if s.horizon == "move_in_plus_1y")
    assert spec.target_ym == "2029-03"
    assert spec.target_label == "2029 상반기"
    assert spec.months_from_asof == 29
    assert dict(spec.propositions)["p10"] == (
        "엘리프 검단 포레듀 전용 84A를 2026-10-08 현재 구매가(5.78~6.08억, 공급가+발코니)로 매수할 경우, "
        "입주(2028-03) 후 1년 시점인 2029 상반기 실거래가가 현재 구매가 대비 +10% 이상이다"
    )
    assert dict(spec.propositions)["p_flat"].endswith("현재 구매가 대비 이하(보합·하락)이다")


def test_immediate_move_in_uses_asof_plus_1y() -> None:
    c = card(5, "즉시입주단지", "2025-12", immediate_move_in=True)
    spec = next(s for s in P.ladder_specs(c, asof_date=ASOF) if s.horizon == "move_in_plus_1y")
    assert spec.target_ym == "2027-10"
    assert "기준일+1년 시점" in dict(spec.propositions)["p10"]


def test_annualized() -> None:
    assert P.annualized(29) == {"p5": 0.0204, "p10": 0.0402, "p20": 0.0784}


# ------------------------------------------------------------------ rerank (T7)


def _cards(n: int) -> list[P.EvidenceCard]:
    return [card(i, f"단지{i}", "2028-03") for i in range(1, n + 1)]


def test_rerank_payload_contains_every_candidate_once_in_stable_order() -> None:
    cards = _cards(8)
    p1 = P.rerank_payload(cards)
    p2 = P.rerank_payload(list(reversed(cards)))
    assert p1 == p2  # 순서 무관 같은 집합 = 같은 payload = 캐시
    assert [c["id"] for c in p1["candidates"]] == [f"complex:{i}" for i in range(1, 9)]
    assert p1["query"] == P.RERANK_QUERY
    assert_jev_valid("rerank", p1)


def test_t7_candidate_change_reruns_all_once(make_adapter: Callable[..., Any]) -> None:
    """T7: 후보 8 → 16이면 16개 전부를 담은 payload로 1회 재호출. 같은 집합은 캐시."""
    transport = FakeTransport()
    adapter = make_adapter(transport)
    purpose = P.rerank_purpose(region_id=1)
    eight, sixteen = P.rerank_payload(_cards(8)), P.rerank_payload(_cards(16))

    adapter.rerank(eight, purpose)
    adapter.rerank(eight, purpose)
    assert len(transport.calls) == 1
    adapter.rerank(sixteen, purpose)
    assert len(transport.calls) == 2
    sent = transport.calls[-1][1]
    assert len(sent["candidates"]) == 16
    assert {c["id"] for c in sent["candidates"]} == {f"complex:{i}" for i in range(1, 17)}
    assert P.rerank_needs_rerun({1, 2, 3}, {1, 2, 3}) is False
    assert P.rerank_needs_rerun({1, 2, 3}, {1, 2, 3, 4}) is True
    assert input_hash("rerank", purpose, eight, "v") != input_hash("rerank", purpose, sixteen, "v")


# ------------------------------------------------------------------ decide


def _pre(status: str = "충족") -> RequirementPreSet:
    return RequirementPreSet(
        access=RequirementPre(status=status, evidence="접수 가능(공식 팝업 2026-10-07) → 충족"),  # type: ignore[arg-type]
        regulation=RequirementPre(
            status="충족", evidence="거주의무 0개월, 재당첨 제한 미적용(비규제) → 충족"
        ),
        funds=RequirementPre(status="미입력", evidence="자기자본·대출 한도 미입력"),
    )


def test_decide_payload_max_six_with_precalc_strings() -> None:
    cands = [P.DecideCandidate(card=c, pre=_pre()) for c in _cards(6)]
    payload = P.decide_payload(
        scenario_name="상황 B 가점 낮음·소액",
        requirements=(
            "접근 가능성: 공식 경로로 접수 가능",
            "규제 제약: 규제 충돌 없음",
            "자금: 계약금·잔금 충당",
        ),
        candidates=cands,
        priorities="상승 확률 0.30, 상대 순위 0.15, 가격 갭 0.20, 벤치마크 0.10, 공급 0.10, 유동성 0.15",
    )
    assert_jev_valid("decide", payload)
    assert [c["id"] for c in payload["candidates"]] == [f"complex_{i}" for i in range(1, 7)]
    assert len(payload["requirements"]) == 3
    assert "접수 가능(공식 팝업 2026-10-07) → 충족" in payload["evidence"]
    assert "자기자본·대출 한도 미입력" in payload["evidence"]
    assert "auto_accept" not in payload  # 임계값을 넘기지 않는다 (D6)
    with pytest.raises(ValueError):
        P.decide_payload(
            scenario_name="x",
            requirements=("a", "b", "c"),
            candidates=[P.DecideCandidate(card=c, pre=_pre()) for c in _cards(7)],
            priorities="p",
        )


# ------------------------------------------------------------------ 기타 도구 모양


def test_other_builders_match_jev_schema() -> None:
    assert_jev_valid("screen", P.screen_payload("공고 발췌", task="청약 공고에서 가격 읽기"))
    ext = P.extract_payload(
        "공급금액 최고가 608,000,000원",
        [P.ExtractField(id="max_price", pattern="[0-9,]+원", description="공급금액 최고가(원)")],
        purpose="공고 수치 추출",
    )
    assert_jev_valid("extract", ext)
    assert_jev_valid(
        "audit",
        P.audit_payload("원문", [P.AuditRecord(id="max_price", request="최고가(원)", value="608,000,000원")]),
    )
    assert_jev_valid(
        "classify", P.classify_inclusion_payload(item_id="complex:1", text="사업주체: 민간 시행사")
    )
    assert_jev_valid(
        "classify", P.classify_catalyst_payload(item_id="catalyst:1", text="지하철 연장 확정 고시")
    )
    assert_jev_valid("compare", P.compare_payload("총 1,573세대", "총 1,769세대", aspects=["세대수"]))
    assert_jev_valid("verify", P.verify_payload(["계약금은 10%이다"], [("notice", "계약금 10%")]))
    for p in (
        P.screen_payload("x", task="t"),
        P.classify_inclusion_payload(item_id="complex:1", text="t"),
        P.compare_payload("a", "b"),
    ):
        assert not {"auto_accept", "minimum_margin", "block_at", "review_at", "wrong_at"} & set(p)


def test_verify_payload_limit_16() -> None:
    with pytest.raises(ValueError):
        P.verify_payload([f"주장 {i}번" for i in range(17)], [("e", "근거")])

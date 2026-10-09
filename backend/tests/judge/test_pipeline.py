"""pipeline.py — P1~P9 단계별: 입력 생성 → 어댑터 호출 → ladder/decision/claim 행 데이터."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from app.core.contracts_gen import (
    Claim,
    DecisionSet,
    LadderRow,
    RequirementPre,
    RequirementPreSet,
)
from app.core.protocols import JudgeUnavailable
from app.judge import payloads as P
from app.judge import pipeline

from .conftest import FakeTransport

ASOF = "2026-10-08"


def card(cid: int, name: str, move_in: str = "2028-03") -> P.EvidenceCard:
    return P.EvidenceCard(
        complex_id=cid, name=name, basis_type="84A", price_range="5.78~6.08억",
        price_composition="공급가+발코니", move_in_ym=move_in,
    )  # fmt: skip


def noul_response(probs: list[float], labels: list[str]) -> dict[str, Any]:
    return {
        "tool": "jev_noul",
        "status": "ok",
        "results": [
            {
                "id": f"proposition{i}",
                "proposition": f"p{i}",
                "probability": p,
                "label": lab,
                "auto": lab != "uncertain",
            }
            for i, (p, lab) in enumerate(zip(probs, labels, strict=True))
        ],
        "thresholds": {"auto_accept": 0.85},
    }


def test_p6_ladder_rows_three_horizons(make_adapter: Callable[..., Any]) -> None:
    t = FakeTransport(responses={"jev_noul": noul_response([0.48, 0.45, 0.36, 0.48], ["uncertain"] * 4)})
    adapter = make_adapter(t)
    rows = pipeline.p6_ladder(adapter, card(2, "엘리프 검단 포레듀"), asof_date=ASOF, snapshot_id=None)
    assert [r.horizon for r in rows] == ["move_in_plus_1y", "asof_plus_3y", "asof_plus_5y"]
    assert len(t.calls) == 3  # horizon 1개당 noul 1회
    r = rows[0]
    assert isinstance(r, LadderRow)
    assert (r.target_ym, r.months_from_asof, r.target_label) == ("2029-03", 29, "2029 상반기")
    assert r.p10.v == 0.45 and r.p10.label == "추정" and r.p10.prov == f"jl_{r.judgment_seq}"
    assert r.p10.unit == "prob"
    assert r.verdicts.p10 == "uncertain"
    assert r.annualized.p10 == 0.0402
    assert r.status == "ok"
    assert r.proposition_text and "+10% 이상이다" in r.proposition_text
    # 같은 단지 다시 → 캐시, 실제 호출 없음
    pipeline.p6_ladder(adapter, card(2, "엘리프 검단 포레듀"), asof_date=ASOF, snapshot_id=None)
    assert len(t.calls) == 3


def test_p6_review_gives_unknown_facts(make_adapter: Callable[..., Any]) -> None:
    bad = noul_response([0.5] * 4, ["uncertain"] * 4) | {"status": "invalid_response"}
    rows = pipeline.p6_ladder(
        make_adapter(FakeTransport(responses={"jev_noul": bad})),
        card(3, "단지"),
        asof_date=ASOF,
        snapshot_id=None,
    )
    assert all(r.status == "review" for r in rows)
    assert rows[0].p10.label == "확인 불가" and rows[0].p10.reason == "미판정" and rows[0].p10.v is None


def test_p7_rerank_anchor_with_prev(make_adapter: Callable[..., Any]) -> None:
    resp = {
        "tool": "jev_rerank",
        "query": P.RERANK_QUERY,
        "ranked": [
            {"rank": 1, "id": "complex:2", "relevance": 0.71, "text": "."},
            {"rank": 2, "id": "complex:1", "relevance": 0.5, "text": "."},
        ],
    }
    adapter = make_adapter(FakeTransport(responses={"jev_rerank": resp}))
    anchor = pipeline.p7_rerank(adapter, [card(1, "a"), card(2, "b")], region_id=1, snapshot_id=None)
    assert anchor.status == "ok"
    assert anchor.judgment_seq is not None
    assert [(i.complex_id, i.rank) for i in anchor.items] == [(2, 1), (1, 2)]
    assert anchor.prev is None


def decide_response(conf: float) -> dict[str, Any]:
    return {
        "tool": "jev_decide",
        "recommendation": {
            "selected": "complex_7",
            "escaped": False,
            "confidence": conf,
            "probabilities": {"complex_7": 0.54, "complex_2": 0.42, "complex_3": 0.02, "ask_user": 0.01,
                              "investigate": 0.01, "none": 0.0},
            "contradicted_requirements": [],
        },
        "requirements_checked": 3,
        "checks": [
            {"candidate": f"complex_{c}", "requirement": j, "answer": a}
            for c in (7, 2, 3)
            for j, a in enumerate(["supported", "supported", "contradicted" if c == 3 else "supported"])
        ],
        "warnings": [],
    }  # fmt: skip


def pre(funds: str = "충족") -> RequirementPreSet:
    return RequirementPreSet(
        access=RequirementPre(status="충족", evidence="접수 가능(공식 팝업 2026-10-07) → 충족"),
        regulation=RequirementPre(status="충족", evidence="거주의무 0개월 → 충족"),
        funds=RequirementPre(status=funds, evidence="계약금 3,403만(5%) ≤ 자기자본 2억 → 충족"),  # type: ignore[arg-type]
    )


def test_p8_decide_tie_when_confidence_below_0_6(make_adapter: Callable[..., Any]) -> None:
    """T2 모양: 칸타빌 0.54, 엘리프 0.42, confidence 0.48 → 두 후보 tie=true·chosen=true."""
    adapter = make_adapter(FakeTransport(responses={"jev_decide": decide_response(0.48)}))
    cands = [P.DecideCandidate(card=card(c, f"단지{c}"), pre=pre()) for c in (7, 2, 3)]
    ds = pipeline.p8_decide(
        adapter,
        scenario_id=3,
        scenario_code="B",
        scenario_name="상황 B",
        requirements=("접근", "규제", "자금"),
        priorities="상승 확률 0.30",
        candidates=cands,
        snapshot_id=None,
    )
    assert isinstance(ds, DecisionSet)
    assert ds.status == "ok" and ds.tie is True and ds.escaped is False
    assert ds.confidence is not None and ds.confidence.v == 0.48
    by = {(d.option_key, d.complex_id): d for d in ds.items}
    assert by[("complex", 7)].chosen and by[("complex", 7)].tie
    assert by[("complex", 2)].chosen and by[("complex", 2)].tie
    assert not by[("complex", 3)].chosen and not by[("complex", 3)].tie
    assert by[("complex", 7)].prob.v == 0.54
    assert ("ask_user", None) in by and ("investigate", None) in by
    # 사전 계산 충족 vs 판정기 contradicted → mismatch
    d3 = by[("complex", 3)]
    assert d3.requirements is not None
    assert d3.requirements.funds.judge == "contradicted" and d3.requirements.funds.mismatch is True
    assert d3.mismatch is True
    assert by[("complex", 7)].mismatch is False


def test_p8_no_tie_when_confident(make_adapter: Callable[..., Any]) -> None:
    adapter = make_adapter(FakeTransport(responses={"jev_decide": decide_response(0.9)}))
    cands = [P.DecideCandidate(card=card(c, f"단지{c}"), pre=pre()) for c in (7, 2, 3)]
    ds = pipeline.p8_decide(
        adapter, scenario_id=1, scenario_code="base", scenario_name="기본", requirements=("a", "b", "c"),
        priorities="p", candidates=cands, snapshot_id=None,
    )  # fmt: skip
    chosen = [d.complex_id for d in ds.items if d.chosen]
    assert chosen == [7]
    assert ds.tie is False


def test_p9_verify_splits_then_verifies(make_adapter: Callable[..., Any]) -> None:
    resp = {
        "tool": "jev_verify",
        "auto_accept": 0.8,
        "results": [
            {"id": "claim0", "claim": "3개는 unlikely", "verdict": "verified", "confidence": 0.95, "action": "auto"},
            {"id": "claim1", "claim": "나머지는 uncertain", "verdict": "contradicted", "confidence": 0.9,
             "action": "auto"},
        ],
    }  # fmt: skip
    t = FakeTransport(responses={"jev_verify": resp})
    claims = pipeline.p9_verify(
        make_adapter(t),
        section="12-4",
        text="3개는 unlikely이고 나머지는 uncertain",
        evidence=[("noul_120", "noul #120 결과")],
        snapshot_id=None,
    )
    sent = t.calls[0][1]["claims"]
    assert sent == ["3개는 unlikely", "나머지는 uncertain"]  # 원자 주장만 verify로
    assert all(isinstance(c, Claim) for c in claims)
    assert [c.verify_status for c in claims] == ["verified", "contradicted"]
    assert claims[0].judgment_seq is not None
    assert pipeline.has_contradiction(claims) is True


def test_p1_screen_and_p4_p5(make_adapter: Callable[..., Any], samples: dict[str, Any]) -> None:
    adapter = make_adapter(FakeTransport())
    s = pipeline.p1_screen(adapter, "공고 발췌 텍스트", task="공고 가격 읽기", purpose="screen:notice:1")
    assert s.usable is True and s.verdict == "pass"
    c = pipeline.p4_classify_inclusion(adapter, complex_id=1, text="사업주체: 민간", snapshot_id=None)
    assert c.label == "private_sale_apt" and c.resolved is True
    cmp_ = pipeline.p5_compare(
        adapter, "총 1,573세대", "총 1,769세대", aspects=["세대수"], purpose="compare:units:1"
    )
    assert cmp_.relation == "contradicts" and cmp_.resolved is True


def test_unavailable_propagates(make_adapter: Callable[..., Any]) -> None:
    with pytest.raises(JudgeUnavailable):
        pipeline.p6_ladder(
            make_adapter(FakeTransport(fail="unavailable")), card(1, "a"), asof_date=ASOF, snapshot_id=None
        )

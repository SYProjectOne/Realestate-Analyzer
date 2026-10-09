"""T2 decide 동률 · 요건 사전 계산(RA §6-7) · 내장 시나리오 시드 일치."""

from __future__ import annotations

import importlib.util
from typing import Any

import pytest

from app.analysis.scenarios import (
    BUILTIN_SCENARIOS,
    RequirementPrecalculator,
    builtin,
    precalc_rows,
    requirement_mismatch,
)
from app.analysis.score import decide_outcome
from app.core.protocols import RequirementPrecalc

from ._support import ASOF, EXPECTED, MIGRATION_0001, make_complex

# ---------------------------------------------------------------- T2


def test_t2_low_confidence_ties_top_two() -> None:
    t2 = EXPECTED["t2"]
    probs = {**t2["probs"], "hannaedeul": 0.01, "switzen": 0.01, "granter": 0.0, "wait_new": 0.0}
    out = decide_outcome(status="ok", confidence=t2["confidence"], probs=probs, selected="cantavil")
    by_key = {o.key: o for o in out}
    assert by_key["cantavil"].tie and by_key["cantavil"].chosen
    assert by_key["elif"].tie and by_key["elif"].chosen
    assert sorted(o.key for o in out if o.chosen) == sorted(t2["expected"]["chosen"])
    assert not any(o.tie for o in out if o.key not in ("cantavil", "elif"))


@pytest.mark.parametrize("code", ["base", "A", "C", "D"])
def test_confident_decide_chooses_selected_only(code: str) -> None:
    d = EXPECTED["decide_integrated"][code]
    out = decide_outcome(status="ok", confidence=d["confidence"], probs=d["probs"], selected=d["selected"])
    assert [o.key for o in out if o.chosen] == [d["selected"]]
    assert not any(o.tie for o in out)


def test_decide_boundary_and_non_ok_status() -> None:
    probs = {"a": 0.6, "b": 0.3}
    assert not any(o.tie for o in decide_outcome(status="ok", confidence=0.6, probs=probs, selected="a"))
    assert all(o.tie for o in decide_outcome(status="ok", confidence=0.5999, probs=probs, selected="a"))
    for status in ("review", "escaped", "blocked", "error"):
        out = decide_outcome(status=status, confidence=0.9, probs=probs, selected="a")
        assert not any(o.chosen or o.tie for o in out), status


# ---------------------------------------------------------------- 요건 사전 계산


def test_precalc_implements_protocol() -> None:
    assert isinstance(RequirementPrecalculator(), RequirementPrecalc)


def _elif(**over: Any):  # type: ignore[no-untyped-def]
    return make_complex(2, name="엘리프 검단 포레듀", **over)


def test_elif_resale_requirement_is_met_with_evidence() -> None:
    """엘리프 전매 3년(당첨 2025-09-10 → 2028-09) ≤ 매도 시작(기준일 + 5년 = 2031-10) → 충족."""
    res = RequirementPrecalculator().evaluate(_elif(), builtin("C"), asof_date=ASOF)
    assert res.access.status == "충족"
    ev = res.access.evidence
    assert "전매 종료 2028-09" in ev and "2031-10" in ev and ev.endswith("충족"), ev


def test_resale_requirement_not_met_when_holding_short() -> None:
    sc = builtin("C")
    rules = sc.requirements.model_copy(
        update={"access": sc.requirements.access.model_copy(update={"params": {"holding_years": 1}})}
    )
    res = RequirementPrecalculator().evaluate(
        _elif(), sc.model_copy(update={"requirements": rules}), asof_date=ASOF
    )
    assert res.access.status == "미충족"
    assert "2027-10" in res.access.evidence and res.access.evidence.endswith("미충족")


def test_funds_requirement_numbers_and_interim_note() -> None:
    # 엘리프 P_mid 5.93억, 계약금 5% = 2,965만 ≤ 자기자본 2억; 5.93 − 6 − 2 < 0 → 충족
    res = RequirementPrecalculator().evaluate(_elif(), builtin("B"), asof_date=ASOF)
    assert res.funds.status == "충족"
    assert res.funds.evidence == "계약금 2,965만(5%) ≤ 자기자본 2억; 잔금 부족 0 → 충족 (중도금 이자후불제)"


def test_funds_not_met_and_not_entered() -> None:
    # 그란테르 12.45~13.18억, 자기자본 2억, 한도 6억 → 잔금 부족 4.815억
    granter = make_complex(
        1, price_low_won=1_245_000_000, price_high_won=1_318_000_000, interim_terms_text=None
    )
    res = RequirementPrecalculator().evaluate(granter, builtin("B"), asof_date=ASOF)
    assert res.funds.status == "미충족"
    assert "잔금 부족 4.815억" in res.funds.evidence and res.funds.evidence.endswith("미충족")
    base = RequirementPrecalculator().evaluate(granter, builtin("base"), asof_date=ASOF)
    assert base.funds.status == "미입력" and base.funds.evidence


def test_access_intake_rules() -> None:
    calc = RequirementPrecalculator()
    ok = calc.evaluate(_elif(), builtin("base"), asof_date=ASOF).access
    assert ok.status == "충족" and "접수 가능" in ok.evidence and "공식 팝업" in ok.evidence
    unk = calc.evaluate(
        _elif(intake_status="확인 불가", intake_path=None), builtin("base"), asof_date=ASOF
    ).access
    assert unk.status == "확인 불가"
    unofficial = calc.evaluate(_elif(intake_path="unofficial_ref"), builtin("D"), asof_date=ASOF).access
    assert unofficial.status == "미충족" and "비공식" in unofficial.evidence
    a = calc.evaluate(_elif(has_priority_supply=False), builtin("A"), asof_date=ASOF).access
    assert a.status == "미충족"
    # R3 3차 RA 부분(§6-7): 공통 조건 path≠unofficial_ref 를 A·C 에도 AND
    for code in ("A", "C"):
        un = calc.evaluate(_elif(intake_path="unofficial_ref", has_priority_supply=True), builtin(code), asof_date=ASOF)
        assert un.access.status == "미충족" and "비공식" in un.access.evidence, code
    # B·D: 공급 경로(현재 공고)가 무순위·임의·선착순이어야 — 본청약 접수는 통장·가점 경로
    for code in ("B", "D"):
        main = calc.evaluate(_elif(current_supply_kind="본청약"), builtin(code), asof_date=ASOF).access
        assert main.status == "미충족" and "본청약" in main.evidence, code
        rem = calc.evaluate(_elif(current_supply_kind="선착순"), builtin(code), asof_date=ASOF).access
        assert rem.status == "충족" and "선착순" in rem.evidence, code
        unk = calc.evaluate(_elif(current_supply_kind=None), builtin(code), asof_date=ASOF).access
        assert unk.status == "확인 불가", code


def test_regulation_rules() -> None:
    calc = RequirementPrecalculator()
    ok = calc.evaluate(_elif(), builtin("B"), asof_date=ASOF).regulation
    # R3 3차 RA 부분: B·C·D 규제 요건도 재당첨 제한·규제지역을 본다(기본 상황과 같은 규칙)
    assert ok.status == "충족" and ok.evidence == "거주의무 0개월, 재당첨 제한 10년(이력 미입력), 비규제 → 충족"
    rewin = calc.evaluate(_elif(), builtin("B").model_copy(
        update={"params": builtin("B").params.model_copy(update={"rewin_restricted": True})}
    ), asof_date=ASOF).regulation  # fmt: skip
    assert rewin.status == "미충족" and "재당첨 제한 10년(이력 있음)" in rewin.evidence
    thesharp = make_complex(6, residency_months=36)
    bad = calc.evaluate(thesharp, builtin("B"), asof_date=ASOF).regulation
    assert bad.status == "미충족" and "거주의무 36개월" in bad.evidence
    conflict = calc.evaluate(_elif(), builtin("base"), asof_date=ASOF).regulation
    assert (
        conflict.status == "충족"
        and "재당첨 제한 10년" in conflict.evidence
        and "비규제" in conflict.evidence
    )
    # A는 거주의무 수용 → 거주의무 있어도 충돌 없음
    assert calc.evaluate(thesharp, builtin("A"), asof_date=ASOF).regulation.status == "충족"


def test_notice_field_labels_and_intake_checked_at() -> None:
    """계약 2026-10-09.2: 공고 필드 라벨(확인 불가 → 값 미사용, 추정 → 근거에 표기)·접수 확인 시각."""
    calc = RequirementPrecalculator()
    checked = _elif(intake_checked_at="2026-10-07T09:20:00+09:00")
    acc = calc.evaluate(checked, builtin("base"), asof_date=ASOF).access
    assert acc.status == "충족" and "확인 2026-10-07(D+1)" in acc.evidence
    unknown_res = _elif(residency_label="확인 불가")
    assert calc.evaluate(unknown_res, builtin("B"), asof_date=ASOF).regulation.status == "확인 불가"
    est = calc.evaluate(_elif(residency_label="추정"), builtin("B"), asof_date=ASOF).regulation
    assert est.evidence == "거주의무 0개월(추정), 재당첨 제한 10년(이력 미입력), 비규제 → 충족"
    resale = calc.evaluate(_elif(resale_label="확인 불가"), builtin("C"), asof_date=ASOF).access
    assert resale.status == "확인 불가"
    funds = calc.evaluate(_elif(down_payment_label="확인 불가"), builtin("A"), asof_date=ASOF).funds
    assert funds.status == "확인 불가" and "계약금 비율" in funds.evidence


def test_every_evidence_non_empty_for_all_scenarios() -> None:
    calc = RequirementPrecalculator()
    for sc in BUILTIN_SCENARIOS:
        for cx in (
            _elif(),
            make_complex(
                9,
                price_low_won=None,
                price_high_won=None,
                intake_status=None,
                intake_path=None,
                residency_months=None,
                resale_months=None,
                winner_date=None,
                down_payment_pct=None,
            ),
        ):
            res = calc.evaluate(cx, sc, asof_date=ASOF)
            for req in (res.access, res.regulation, res.funds):
                assert req.evidence.strip(), (sc.code, cx.complex_id)


def test_precalc_rows_mark_excluded_for_d() -> None:
    rows = precalc_rows([_elif(), make_complex(9, intake_status="불가")], builtin("D"), asof_date=ASOF)
    assert [(r.complex_id, r.excluded) for r in rows] == [(2, False), (9, True)]


@pytest.mark.parametrize(
    ("pre", "judge", "mismatch"),
    [
        ("충족", "contradicted", True),
        ("미충족", "supported", True),
        ("충족", "supported", False),
        ("미입력", "contradicted", False),
        ("확인 불가", "supported", False),
        ("충족", "unknown", False),
        ("충족", None, False),
    ],
)
def test_requirement_mismatch(pre: str, judge: str | None, mismatch: bool) -> None:
    assert requirement_mismatch(pre, judge) is mismatch  # type: ignore[arg-type]


# ---------------------------------------------------------------- 내장 시나리오


def test_builtin_scenarios_equal_migration_seed() -> None:
    spec = importlib.util.spec_from_file_location("mig0001", MIGRATION_0001)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    seed: list[dict[str, Any]] = mod.BUILTIN_SCENARIOS
    spec5 = importlib.util.spec_from_file_location("mig0005", MIGRATION_0001.with_name("0005_wait_new.py"))
    assert spec5 and spec5.loader
    mod5 = importlib.util.module_from_spec(spec5)
    spec5.loader.exec_module(mod5)
    wait_new: dict[str, bool] = mod5.BUILTIN_WAIT_NEW
    assert len(BUILTIN_SCENARIOS) == 5
    for idx, (sc, row) in enumerate(zip(BUILTIN_SCENARIOS, seed, strict=True), start=1):
        assert sc.id == idx
        assert sc.code == row["code"] and sc.name == row["name"] and sc.is_builtin
        assert sc.weights.model_dump(exclude_none=True) == row["weights"]
        assert sc.requirements.model_dump(exclude_none=True) == row["requirements"]
        # 0005(계약 2026-10-09.5): 내장 시나리오 policy.include_wait_new(A 만 true) — 0001 시드 + 0005 = 현재
        assert sc.policy.model_dump() == {**row["policy"], "include_wait_new": wait_new[row["code"]]}
        assert sc.params.model_dump() == row["params"]
        assert abs(sum(sc.weights.model_dump(exclude_none=True).values()) - 1) < 1e-9

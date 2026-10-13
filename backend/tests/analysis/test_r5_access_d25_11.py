"""R5-ACCESS 1 (D25-11): RA §6-7 접근 가능성의 ``intake_status ∈ {가능}`` and path ≠ unofficial_ref 는 A·B·C·D 공통 조건이다.

R3C 의 좁은 해석(A ``priority_supply``·C ``resale_before_exit`` 는 path 조건만)을 바로잡는다. A·C 접근 요건 = 상황 조건 AND 접수 상태.
상태는 둘 중 약한 쪽(미충족 > 확인 불가 > 미입력 > 충족), 근거는 RA 예시처럼 접수 부분 먼저 ·
상황 조건 뒤에 화살표 하나: "접수 가능(공식 팝업 …); 전매 종료 … ≤ 매도 시작 … → 충족".

| 테스트 | 확인 |
| --- | --- |
| ``test_c_resale_met_but_intake_not_open_is_not_met`` | C: 전매 조건 충족이어도 접수 미정·불가 → 미충족, 근거에 '접수 미정(…)' |
| ``test_a_priority_supply_met_but_intake_not_open_is_not_met`` | A: 1순위 공급 있어도 접수 미정·불가 → 미충족 |
| ``test_intake_unknown_makes_a_c_unknown`` | 접수 상태 확인 불가·없음 → 확인 불가(상황 조건 충족일 때) |
| ``test_ra_example_evidence_shape`` | 접수 가능 + 전매 충족 → 충족, 근거 = 접수 부분; 전매 부분 → 충족 (화살표 1개) |
| ``test_weaker_status_wins`` | 상태 순서 표(미충족 > 확인 불가 > 미입력 > 충족) — A 상황 조건 3 × 접수 3 조합 |
| ``test_weaker_status_with_not_entered`` | C 보유기간 미입력(미입력) × 접수 가능·확인 불가·미정 |
| ``test_own_condition_not_met_keeps_both_parts`` | 상황 조건 미충족 → 미충족, 근거에 접수 부분도 남는다 |
| ``test_b_d_and_base_unchanged`` | B·D·기본 근거 문자열은 바뀌지 않는다(가드) |
| ``test_unofficial_only_still_short_circuits`` | 비공식 경로만 → 어떤 상황이든 미충족(기존 공통 조건 그대로) |
"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

import pytest

from app.analysis.scenarios import RequirementPrecalculator, builtin
from app.core.contracts_gen import RequirementPre

from ._support import ASOF, make_complex

CALC = RequirementPrecalculator()


def _elif(**over: Any):  # type: ignore[no-untyped-def]
    return make_complex(2, name="엘리프 검단 포레듀", **over)


def _access(code: str, **over: Any) -> RequirementPre:
    return CALC.evaluate(_elif(**over), builtin(code), asof_date=ASOF).access


def _one_arrow(pre: RequirementPre) -> None:
    assert pre.evidence.count("→") == 1 and pre.evidence.endswith(f"→ {pre.status}"), pre.evidence


@pytest.mark.parametrize(
    ("status", "path"), [("미정", "official_popup"), ("불가", "official_popup"), ("미정", None)]
)
def test_c_resale_met_but_intake_not_open_is_not_met(status: str, path: str | None) -> None:
    pre = _access("C", intake_status=status, intake_path=path)
    assert pre.status == "미충족", pre.evidence
    where = "공식 팝업" if path else "경로 미상"
    assert pre.evidence.startswith(f"접수 {status}({where})"), pre.evidence
    assert "전매 종료 2028-09" in pre.evidence and "매도 시작 2031-10" in pre.evidence
    _one_arrow(pre)


@pytest.mark.parametrize("status", ["미정", "불가"])
def test_a_priority_supply_met_but_intake_not_open_is_not_met(status: str) -> None:
    pre = _access("A", intake_status=status, has_priority_supply=True)
    assert pre.status == "미충족", pre.evidence
    assert pre.evidence == f"접수 {status}(공식 팝업); 가점제 1순위 공급(본청약·예정 공고) 있음 → 미충족"


@pytest.mark.parametrize("code", ["A", "C"])
@pytest.mark.parametrize("status", ["확인 불가", None])
def test_intake_unknown_makes_a_c_unknown(code: str, status: str | None) -> None:
    pre = _access(code, intake_status=status, intake_path=None, has_priority_supply=True)
    assert pre.status == "확인 불가", pre.evidence
    assert pre.evidence.startswith("접수 상태 확인 불가(경로 미상)"), pre.evidence
    _one_arrow(pre)


def test_ra_example_evidence_shape() -> None:
    """RA §6-7 예: "접수 가능(공식 팝업 2026-10-07); 전매 종료 2028-09 < 매도 시작 2030-03 → 충족"."""
    pre = _access("C", intake_checked_at="2026-10-07T09:20:00+09:00")
    assert pre.status == "충족"
    assert pre.evidence == (
        "접수 가능(공식 팝업, 확인 2026-10-07(D+1), 기준일 2026-10-08); "
        "전매 종료 2028-09 (등기 시 해제) ≤ 매도 시작 2031-10(기준일 + 보유 5년) → 충족"
    )
    a = _access("A", has_priority_supply=True)
    assert a.status == "충족"
    assert (
        a.evidence
        == "접수 가능(공식 팝업, 기준일 2026-10-08); 가점제 1순위 공급(본청약·예정 공고) 있음 → 충족"
    )


# (상황 조건 입력, 접수 입력) → 기대 상태. 상황 조건: A has_priority_supply(True 충족·None 확인 불가·False 미충족)
_A_OWN = {"충족": True, "확인 불가": None, "미충족": False}
_INTAKE = {
    "충족": ("가능", "official_popup"),
    "확인 불가": ("확인 불가", None),
    "미충족": ("미정", "official_popup"),
}
_ORDER = ["미충족", "확인 불가", "미입력", "충족"]


@pytest.mark.parametrize("own", list(_A_OWN))
@pytest.mark.parametrize("intake", list(_INTAKE))
def test_weaker_status_wins(own: str, intake: str) -> None:
    status, path = _INTAKE[intake]
    pre = _access("A", has_priority_supply=_A_OWN[own], intake_status=status, intake_path=path)
    want = min(own, intake, key=_ORDER.index)
    assert pre.status == want, (own, intake, pre.evidence)
    _one_arrow(pre)


def test_weaker_status_with_not_entered() -> None:
    """C 보유기간 미입력(미입력) × 접수 가능 → 미입력, × 접수 확인 불가 → 확인 불가, × 미정 → 미충족."""
    sc = builtin("C")
    rules = sc.requirements.model_copy(
        update={"access": sc.requirements.access.model_copy(update={"params": None})}
    )
    no_holding = sc.model_copy(
        update={"requirements": rules, "params": sc.params.model_copy(update={"holding_years": None})}
    )
    for (status, path), want in (
        (("가능", "official_popup"), "미입력"),
        (("확인 불가", None), "확인 불가"),
        (("미정", "official_popup"), "미충족"),
    ):
        pre = CALC.evaluate(_elif(intake_status=status, intake_path=path), no_holding, asof_date=ASOF).access
        assert pre.status == want and "보유기간 미입력" in pre.evidence, pre.evidence
        _one_arrow(pre)


def test_own_condition_not_met_keeps_both_parts() -> None:
    sc = builtin("C")
    rules = sc.requirements.model_copy(
        update={"access": sc.requirements.access.model_copy(update={"params": {"holding_years": 1}})}
    )
    pre = CALC.evaluate(_elif(), sc.model_copy(update={"requirements": rules}), asof_date=ASOF).access
    assert pre.status == "미충족"
    assert pre.evidence == (
        "접수 가능(공식 팝업, 기준일 2026-10-08); "
        "전매 종료 2028-09 (등기 시 해제) > 매도 시작 2027-10(기준일 + 보유 1년) → 미충족"
    )
    a = _access("A", has_priority_supply=False)
    assert (
        a.evidence
        == "접수 가능(공식 팝업, 기준일 2026-10-08); 가점제 1순위 공급 없음(무순위·임의·선착순 경로만) → 미충족"
    )


def test_b_d_and_base_unchanged() -> None:
    assert _access("base").evidence == "접수 가능(공식 팝업, 기준일 2026-10-08) → 충족"
    assert _access("base", intake_status="미정").evidence == "접수 미정(공식 팝업) → 미충족"
    assert (
        _access("B", current_supply_kind="선착순").evidence
        == "통장·가점 없이 공식 경로(선착순): 접수 가능(공식 팝업, 기준일 2026-10-08) → 충족"
    )
    assert (
        _access("D", current_supply_kind="무순위", intake_status="불가").evidence
        == "무순위 공고: 접수 불가(공식 팝업) → 미충족"
    )
    assert (
        _access("B", current_supply_kind="본청약").evidence
        == "현재 공고 본청약(통장·가점 경로) — 무순위·임의·선착순 공고 아님 → 미충족"
    )


@pytest.mark.parametrize("code", ["base", "A", "B", "C", "D"])
def test_unofficial_only_still_short_circuits(code: str) -> None:
    pre = _access(code, intake_path="unofficial_ref", has_priority_supply=True, current_supply_kind="선착순")
    assert pre.status == "미충족"
    assert pre.evidence == "접수 가능(비공식 경로만, 판정 미사용) → 미충족"

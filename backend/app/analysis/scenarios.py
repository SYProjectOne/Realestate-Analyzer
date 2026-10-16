"""내장 시나리오 5개 + 요건 사전 계산 (RA §6-4 상황 표, §6-7, contracts/schemas/scenario.json RequirementRule).

``BUILTIN_SCENARIOS``는 마이그레이션 0001 시드(id 1~5) + 0005(policy.include_wait_new, A만 true)와 같다(테스트가 비교한다). 사전 계산은 판정기 호출 없는
산술 규칙이고, 결과 문자열(evidence)은 decide payload 증거에 그대로 들어가며 decision.req_*_pre에 저장된다.
판정기 판정(supported/contradicted)과 다르면 ``requirement_mismatch`` → '증거와 상이' 배지.
"""

# ruff: noqa: E501  (한국어 docstring·식 문자열은 화면 폭 기준으로 길다)

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Final, Literal

from app.analysis._common import add_months_date, dec, fmt_won, num, parse_date, ym_of
from app.analysis.complex_input import resale_input_label
from app.analysis.price import MID_PRICE_TEXT, price_of
from app.core.contracts_gen import (
    ComplexScoreInput,
    RequirementPre,
    RequirementPreRow,
    RequirementPreSet,
    RequirementRule,
    Scenario,
)
from app.core.time import format_d_day, kst_day

PreStatus = Literal["충족", "미충족", "미입력", "확인 불가"]
JudgeCheck = Literal["supported", "contradicted", "unknown"]

_CREATED_AT: Final = "2026-10-09T00:00:00+09:00"
_BASE_PARAMS: Final[dict[str, Any]] = {
    "residence": None,
    "homeless": True,
    "household_size": None,
    "subscription": None,
    "equity_won": None,
    "loan_limit_won": None,
    "purpose": "병행",
    "holding_years": None,
    "preferred_area_m2": 84,
    "move_in_by": None,
    "rewin_restricted": None,
    "accepts_residency_obligation": None,
}


def _funds(text: str, equity: int, loan: int) -> dict[str, Any]:
    return {
        "code": "equity_and_loan",
        "text": text,
        "params": {"equity_won": equity, "loan_limit_won": loan},
    }


_SEED: Final[list[dict[str, Any]]] = [
    {
        "code": "base",
        "name": "기본",
        "params": dict(_BASE_PARAMS),
        "weights": {
            "p10": 0.35,
            "rerank": 0.2,
            "gap": 0.15,
            "benchmark": 0.1,
            "supply": 0.1,
            "liquidity": 0.1,
        },
        "requirements": {
            "access": {"code": "intake_open", "text": "공식 경로로 지금 접수 가능"},
            "regulation": {
                "code": "no_conflict",
                "text": "거주의무·재당첨 제한·규제지역 요건과 충돌 없음(입주 후 2년 내 매도 가능)",
            },
            "funds": {
                "code": "equity_and_loan",
                "text": "자기자본·대출한도로 계약금·잔금 충당(미입력이면 '미입력')",
            },
        },
        "policy": {
            "p10_horizon": "move_in_plus_1y",
            "exclude_intake_not_open": False,
            "include_wait_new": False,
        },
    },
    {
        "code": "A",
        "name": "A 가점 높음(실거주)",
        "params": _BASE_PARAMS
        | {
            "subscription": {"has_account": True, "score": 60},
            "equity_won": 300_000_000,
            "loan_limit_won": 600_000_000,
            "purpose": "실거주",
            "rewin_restricted": False,
            "accepts_residency_obligation": True,
        },
        "weights": {"p10": 0.35, "rerank": 0.2, "gap": 0.15, "benchmark": 0.1, "supply": 0.1, "move_in": 0.1},
        "requirements": {
            "access": {
                "code": "priority_supply",
                "text": "가점제 1순위 공급(본청약·예정 공고)으로 접근 가능",
            },
            "regulation": {"code": "no_conflict", "text": "거주의무·전매제한이 실거주 계획과 충돌 없음"},
            "funds": _funds("자기자본 3억 이하로 계약금·잔금 충당", 300_000_000, 600_000_000),
        },
        "policy": {
            "p10_horizon": "move_in_plus_1y",
            "exclude_intake_not_open": False,
            "include_wait_new": True,
        },
    },
    {
        "code": "B",
        "name": "B 가점 낮음·소액 자기자본",
        "params": _BASE_PARAMS
        | {
            "subscription": {"has_account": None, "score": 20},
            "equity_won": 200_000_000,
            "loan_limit_won": 600_000_000,
            "holding_years": 2,
            "accepts_residency_obligation": False,
        },
        "weights": {
            "p10": 0.3,
            "rerank": 0.15,
            "gap": 0.2,
            "benchmark": 0.1,
            "supply": 0.1,
            "liquidity": 0.15,
        },
        "requirements": {
            "access": {
                "code": "official_path_no_account",
                "text": "통장 없이 공식 접수 경로(무순위·임의·선착순)로 접근 가능",
            },
            "regulation": {"code": "no_residency_obligation", "text": "거주의무 없음"},
            "funds": _funds("자기자본 2억 이하로 계약금·잔금 충당", 200_000_000, 600_000_000),
        },
        "policy": {
            "p10_horizon": "move_in_plus_1y",
            "exclude_intake_not_open": False,
            "include_wait_new": False,
        },
    },
    {
        "code": "C",
        "name": "C 시세차익 우선",
        "params": _BASE_PARAMS
        | {
            "equity_won": 400_000_000,
            "loan_limit_won": 600_000_000,
            "purpose": "시세차익",
            "holding_years": 5,
            "accepts_residency_obligation": False,
        },
        "weights": {
            "p10": 0.45,
            "rerank": 0.15,
            "gap": 0.15,
            "benchmark": 0.05,
            "supply": 0.05,
            "liquidity": 0.15,
        },
        "requirements": {
            "access": {
                "code": "resale_before_exit",
                "text": "전매 종료 ≤ 목표 매도 시점(기준일 + 보유 5년)",
                "params": {"holding_years": 5},
            },
            "regulation": {"code": "no_residency_obligation", "text": "거주의무 없음"},
            "funds": _funds("자기자본 4억 이하로 계약금·잔금 충당", 400_000_000, 600_000_000),
        },
        "policy": {
            "p10_horizon": "asof_plus_5y",
            "exclude_intake_not_open": False,
            "include_wait_new": False,
        },
    },
    {
        "code": "D",
        "name": "D 즉시 구매",
        "params": _BASE_PARAMS
        | {"equity_won": 300_000_000, "loan_limit_won": 600_000_000, "accepts_residency_obligation": False},
        "weights": {"p10": 0.35, "rerank": 0.2, "gap": 0.15, "benchmark": 0.1, "supply": 0.1, "move_in": 0.1},
        "requirements": {
            "access": {"code": "official_path", "text": "공식 접수 경로로 지금 계약 가능"},
            "regulation": {"code": "no_residency_obligation", "text": "거주의무 없음"},
            "funds": _funds("자기자본 3억 이하로 계약금·잔금 충당", 300_000_000, 600_000_000),
        },
        "policy": {
            "p10_horizon": "move_in_plus_1y",
            "exclude_intake_not_open": True,
            "include_wait_new": False,
        },
    },
]

BUILTIN_SCENARIOS: Final[tuple[Scenario, ...]] = tuple(
    Scenario.model_validate({"id": i, "is_builtin": True, "created_at": _CREATED_AT, **row})
    for i, row in enumerate(_SEED, start=1)
)


def builtin(code: str) -> Scenario:
    for sc in BUILTIN_SCENARIOS:
        if sc.code == code:
            return sc
    raise KeyError(f"내장 시나리오 없음: {code}")


def is_excluded(complex_: ComplexScoreInput, scenario: Scenario) -> bool:
    """policy.exclude_intake_not_open(D)이면 접수 '가능'이 아닌 단지는 후보·순위에서 뺀다."""
    return scenario.policy.exclude_intake_not_open and complex_.intake_status != "가능"


def requirement_mismatch(pre: PreStatus | None, judge: JudgeCheck | None) -> bool:
    """사전 계산과 판정기가 반대면 True(충족↔contradicted, 미충족↔supported). 미입력·확인 불가·unknown은 불일치 아님."""
    return (pre == "충족" and judge == "contradicted") or (pre == "미충족" and judge == "supported")


# ------------------------------------------------------------------ 사전 계산

_PATH_LABEL: Final[dict[str, str]] = {
    "official_popup": "공식 팝업",
    "headless_shot": "공식 홈페이지 렌더",
    "human_check": "사람 확인",
    "unofficial_ref": "비공식",
}


def _known[T](value: T | None, label: str | None) -> T | None:
    """공고 필드 라벨이 '확인 불가'면 값이 있어도 쓰지 않는다(계약 2026-10-09.2 *_label)."""
    return None if label == "확인 불가" else value


def _label_note(label: str | None) -> str:
    """확인됨이 아닌 라벨(추정·비공식·재가공)은 근거 문구에 붙인다."""
    return f"({label})" if label not in (None, "확인됨", "확인 불가") else ""


def _checked_note(c: ComplexScoreInput, asof_date: str) -> str:
    """접수 상태 확인 시각(intake_checked_at) → ', 확인 YYYY-MM-DD(D±n)'. 없으면 ''."""
    if not c.intake_checked_at:
        return ""
    checked = parse_date(kst_day(c.intake_checked_at))  # KST 날짜(D14-6 공용 함수 — '…Z' 저녁은 다음 날)
    return f", 확인 {checked.isoformat()}({format_d_day(checked, parse_date(asof_date))})"


def _pre(status: PreStatus, evidence: str) -> RequirementPre:
    return RequirementPre(status=status, evidence=f"{evidence} → {status}")


def _param(rule: RequirementRule, scenario: Scenario, key: str) -> Any:
    if rule.params and rule.params.get(key) is not None:
        return rule.params[key]
    return getattr(scenario.params, key, None)


def _intake_part(c: ComplexScoreInput, asof_date: str, prefix: str) -> tuple[PreStatus, str]:
    """접수 상태 부분(상태, 화살표 없는 근거). path ≠ unofficial_ref 는 ``_access`` 가 먼저 본다."""
    status, path = c.intake_status, c.intake_path
    where = _PATH_LABEL.get(path or "", "경로 미상") + _checked_note(c, asof_date)
    if status is None or status == "확인 불가":
        return "확인 불가", f"{prefix}접수 상태 확인 불가({where})"
    if path == "unofficial_ref":
        return "미충족", f"{prefix}접수 {status}(비공식 경로만, 판정 미사용)"
    if status == "가능":
        return "충족", f"{prefix}접수 가능({where}, 기준일 {asof_date})"
    return "미충족", f"{prefix}접수 {status}({where})"


def _access_intake(c: ComplexScoreInput, asof_date: str, prefix: str) -> RequirementPre:
    return _pre(*_intake_part(c, asof_date, prefix))


_REMAINDER_KINDS: Final = frozenset({"무순위", "임의", "선착순"})


def _priority_supply(c: ComplexScoreInput) -> tuple[PreStatus, str]:
    """A: 가점제 1순위 공급 존재."""
    if c.has_priority_supply is None:
        return "확인 불가", "가점제 1순위 공급 여부 확인 불가"
    if c.has_priority_supply:
        return "충족", "가점제 1순위 공급(본청약·예정 공고) 있음"
    return "미충족", "가점제 1순위 공급 없음(무순위·임의·선착순 경로만)"


def _resale_before_exit(
    c: ComplexScoreInput, sc: Scenario, rule: RequirementRule, asof_date: str
) -> tuple[PreStatus, str]:
    """C: 전매 종료 ≤ 목표 매도 시점(기준일 + 보유기간)."""
    holding = _param(rule, sc, "holding_years")
    if holding is None:
        return "미입력", "보유기간 미입력"
    resale_months = _known(c.resale_months, c.resale_label)
    if c.winner_date is None or resale_months is None:
        return "확인 불가", "전매제한 기간 확인 불가"
    end = add_months_date(parse_date(c.winner_date), resale_months)
    months = int((dec(holding) * 12).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    exit_ = add_months_date(parse_date(asof_date), months)
    reg = " (등기 시 해제)" if c.resale_release_on_registration else ""
    # 전매 종료 = 당첨일 + 기간 → 라벨은 두 입력 중 약한 것(R3 M2; winner_label 은 계약 .7)
    end_label = resale_input_label(c.resale_label, c.winner_label)
    head = f"전매 종료 {ym_of(end)}{reg}{_label_note(end_label)}"
    tail = f"매도 시작 {ym_of(exit_)}(기준일 + 보유 {num(dec(holding), 1)}년)"
    if end <= exit_:
        return "충족", f"{head} ≤ {tail}"
    return "미충족", f"{head} > {tail}"


_PRE_ORDER: Final[dict[PreStatus, int]] = {"미충족": 0, "확인 불가": 1, "미입력": 2, "충족": 3}


def _and_intake(c: ComplexScoreInput, asof_date: str, own: tuple[PreStatus, str]) -> RequirementPre:
    """D25-11(RA §6-7): A·C 접근 조건 = ``intake_status ∈ {가능}`` AND 상황 조건. 상태는 둘 중 약한 쪽(미충족 > 확인 불가 >
    미입력 > 충족), 근거는 RA 예시처럼 접수 부분; 상황 조건 → 상태 ("접수 가능(공식 팝업 …); 전매 종료 … ≤ 매도 시작 … → 충족")."""
    intake_status, intake_text = _intake_part(c, asof_date, "")
    own_status, own_text = own
    status = min(intake_status, own_status, key=_PRE_ORDER.__getitem__)
    return _pre(status, f"{intake_text}; {own_text}")


def _access(c: ComplexScoreInput, sc: Scenario, asof_date: str) -> RequirementPre:
    """§6-7 접근성. 공통 조건(RA §6-7, D25-11): 접수 경로가 비공식(unofficial_ref)뿐이면 어떤 상황이든 미충족, 그 밖에는
    ``intake_status ∈ {가능}`` 이 A·B·C·D 모두의 조건이다 — A(가점제 1순위 공급)·C(전매 종료 ≤ 매도 시점)는 상황 조건과 AND.
    B·D(통장 없이·지금 계약)는 공급 경로도 본다 — 현재 공고가 무순위·임의·선착순이어야 한다(본청약 접수는 통장·가점 경로)."""
    rule = sc.requirements.access
    if c.intake_path == "unofficial_ref":
        return _pre("미충족", f"접수 {c.intake_status or '상태 미상'}(비공식 경로만, 판정 미사용)")
    if rule.code in ("official_path_no_account", "official_path"):
        kind = c.current_supply_kind
        if kind is None:
            return _pre("확인 불가", "공급 경로(현재 공고 종류) 확인 불가")
        if kind not in _REMAINDER_KINDS:
            return _pre("미충족", f"현재 공고 {kind}(통장·가점 경로) — 무순위·임의·선착순 공고 아님")
    if rule.code == "priority_supply":
        return _and_intake(c, asof_date, _priority_supply(c))
    if rule.code == "resale_before_exit":
        return _and_intake(c, asof_date, _resale_before_exit(c, sc, rule, asof_date))
    prefix = (
        f"통장·가점 없이 공식 경로({c.current_supply_kind}): "
        if rule.code == "official_path_no_account"
        else (f"{c.current_supply_kind} 공고: " if rule.code == "official_path" else "")
    )
    return _access_intake(c, asof_date, prefix)


def _regulation(c: ComplexScoreInput, sc: Scenario) -> RequirementPre:
    rule = sc.requirements.regulation
    res = _known(c.residency_months, c.residency_label)
    res_note = _label_note(c.residency_label)
    if rule.code == "no_residency_obligation":
        # B·C·D(R3 3차 RA 부분): 거주의무에 더해 재당첨 제한·규제지역도 본다(기본 상황과 같은 규칙)
        head = "거주의무 확인 불가" if res is None else f"거주의무 {res}개월{res_note}"
        tail, conflict = _rewin_regulated(c, sc)
        text = ", ".join([head, *tail])
        if (res is not None and res > 0) or conflict:
            return _pre("미충족", text)
        if res is None:
            return _pre("확인 불가", text)
        return _pre("충족", text)
    params = sc.params
    parts: list[str] = []
    conflict = False
    if res is None:
        parts.append("거주의무 확인 불가")
    elif res > 0:
        accepted = params.accepts_residency_obligation is True
        parts.append(f"거주의무 {res}개월{res_note}({'수용' if accepted else '실거주 계획과 충돌'})")
        conflict = conflict or not accepted
    else:
        parts.append("거주의무 0개월")
    tail, rr_conflict = _rewin_regulated(c, sc)
    parts.extend(tail)
    conflict = conflict or rr_conflict
    text = ", ".join(parts)
    if conflict:
        return _pre("미충족", text)
    if res is None:
        return _pre("확인 불가", text)
    return _pre("충족", text)


def _rewin_regulated(c: ComplexScoreInput, sc: Scenario) -> tuple[list[str], bool]:
    """재당첨 제한·규제지역 문구와 충돌 여부(상황 params: rewin_restricted·homeless)."""
    params = sc.params
    parts: list[str] = []
    conflict = False
    years = c.rewin_restriction_years
    if years is None:
        parts.append("재당첨 제한 확인 불가")
    elif years > 0:
        hist = {True: "이력 있음", False: "이력 없음", None: "이력 미입력"}[params.rewin_restricted]
        parts.append(f"재당첨 제한 {years}년({hist})")
        conflict = conflict or params.rewin_restricted is True
    else:
        parts.append("재당첨 제한 없음")
    if c.regulated is None:
        parts.append("규제지역 확인 불가")
    elif c.regulated:
        parts.append("규제지역")
        conflict = conflict or params.homeless is False
    else:
        parts.append("비규제")
    return parts, conflict


def _interim_note(text: str | None) -> str:
    if not text:
        return ""
    if "무이자" in text:
        return " (중도금 무이자)"
    if "이자후불" in text:
        return " (중도금 이자후불제)"
    if "대납" in text:
        return " (중도금 이자 대납)"
    return ""


def _funds_pre(c: ComplexScoreInput, sc: Scenario) -> RequirementPre:
    rule = sc.requirements.funds
    equity = _param(rule, sc, "equity_won")
    loan = _param(rule, sc, "loan_limit_won")
    missing = [n for n, v in (("자기자본", equity), ("대출한도", loan)) if v is None]
    if missing:
        return _pre("미입력", f"{'·'.join(missing)} 미입력")
    price = price_of(c)
    if price is None:
        return _pre("확인 불가", "현재 구매가 확인 불가(분양가 미공개)")
    down_pct = _known(c.down_payment_pct, c.down_payment_label)
    if down_pct is None:
        return _pre("확인 불가", f"계약금 비율 확인 불가({MID_PRICE_TEXT} {fmt_won(price.mid_won)})")
    d = dec(down_pct)
    down = (price.mid_won * d / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    shortfall = price.mid_won - Decimal(loan) - Decimal(equity)
    ok = down <= equity and shortfall <= 0
    status: PreStatus = "충족" if ok else "미충족"
    lack = "0" if shortfall <= 0 else fmt_won(shortfall)
    evidence = (
        f"계약금 {fmt_won(down)}({num(d)}%{_label_note(c.down_payment_label)}) "
        f"{'≤' if down <= equity else '>'} 자기자본 {fmt_won(equity)}; "
        f"잔금 부족 {lack} → {status}{_interim_note(c.interim_terms_text)}"
    )
    return RequirementPre(status=status, evidence=evidence)


class RequirementPrecalculator:
    """``app.core.protocols.RequirementPrecalc`` 구현 (RA §6-7). 순수 함수, 판정기 호출 없음."""

    def evaluate(
        self, complex: ComplexScoreInput, scenario: Scenario, *, asof_date: str
    ) -> RequirementPreSet:
        return RequirementPreSet(
            access=_access(complex, scenario, asof_date),
            regulation=_regulation(complex, scenario),
            funds=_funds_pre(complex, scenario),
        )


def precalc_rows(
    complexes: Iterable[ComplexScoreInput], scenario: Scenario, *, asof_date: str
) -> list[RequirementPreRow]:
    """ScenarioPreview.requirements_pre 행(complex_id 순). excluded = D의 접수 '가능' 아님."""
    calc = RequirementPrecalculator()
    rows: list[RequirementPreRow] = []
    for c in sorted(complexes, key=lambda x: x.complex_id):
        res = calc.evaluate(c, scenario, asof_date=asof_date)
        rows.append(
            RequirementPreRow(
                complex_id=c.complex_id,
                name=c.name,
                excluded=is_excluded(c, scenario),
                access=res.access,
                regulation=res.regulation,
                funds=res.funds,
            )
        )
    return rows


def requirement_checks_mismatch(
    pre: RequirementPreSet, judge: Mapping[str, JudgeCheck | None]
) -> dict[str, bool]:
    """요건별 mismatch(access·regulation·funds)."""
    return {
        key: requirement_mismatch(getattr(pre, key).status, judge.get(key))
        for key in ("access", "regulation", "funds")
    }

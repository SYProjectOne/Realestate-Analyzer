"""사실 행 → ``ComplexScoreInput`` (점수·요건 사전 계산 입력) — 파이프라인과 G5 미리보기가 같은 함수를 쓴다(R3 minor 20).

파이프라인(``scheduler.inputs.complex_input``)과 API 미리보기(``api.views.score_input``)가 입력을 서로 다르게
만들던 것(has_priority_supply False→None, regulated 매핑, immediate_move_in 누락, 접수 행 선택)을 여기 하나로 모은다.
DB 접근 없음 — 호출자가 읽은 행(ORM·DTO)을 넘긴다. 판정 범위·현재 구매가·표시 접수 행은 ``scope``·``price_view``.
"""

# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any, Final, Protocol

from app.analysis.price_view import PriceView
from app.analysis.scope import JudgeScope, contract_scope, runs_ladder
from app.analysis.types import Label
from app.core.contracts_gen import ComplexScoreInput, LadderInput

__all__ = [
    "ComplexLike",
    "LadderRowLike",
    "build_complex_input",
    "immediate_move_in",
    "ladder_inputs",
    "priority_supply",
    "regulated_flag",
]

_REGULATED: Final = {"규제": True, "비규제": False}
_NON_PRIORITY_KINDS: Final = frozenset({"무순위", "임의", "선착순"})


class ComplexLike(Protocol):
    @property
    def id(self) -> int: ...
    @property
    def name(self) -> str: ...
    @property
    def living_area(self) -> str | None: ...
    @property
    def move_in_ym(self) -> str | None: ...
    @property
    def winner_date(self) -> str | None: ...
    @property
    def resale_months(self) -> int | None: ...
    @property
    def resale_release_on_registration(self) -> bool | None: ...
    @property
    def residency_months(self) -> int | None: ...
    @property
    def rewin_restriction_years(self) -> int | None: ...
    @property
    def regulated(self) -> str | None: ...


class TermsLike(Protocol):
    @property
    def down_payment_pct(self) -> Decimal | None: ...
    @property
    def interim_terms_text(self) -> str | None: ...


class NoticeKindLike(Protocol):
    @property
    def notice_kind(self) -> str | None: ...


class IntakeLike(Protocol):
    @property
    def status(self) -> str: ...
    @property
    def path(self) -> str: ...
    @property
    def checked_at(self) -> str | None: ...


class LadderRowLike(Protocol):
    @property
    def horizon(self) -> str: ...
    @property
    def target_ym(self) -> str: ...
    @property
    def months_from_asof(self) -> int | None: ...
    @property
    def p5(self) -> Any: ...
    @property
    def p10(self) -> Any: ...
    @property
    def p20(self) -> Any: ...
    @property
    def p_flat(self) -> Any: ...
    @property
    def status(self) -> str: ...
    @property
    def judgment_seq(self) -> int | None: ...


def _num(v: Any) -> float | None:
    return float(v) if v is not None else None


def ladder_inputs(rows: Iterable[LadderRowLike]) -> list[LadderInput]:
    """ladder 행 → LadderInput(시점 순). 판정 값·봉투 status 그대로."""
    return [
        LadderInput.model_validate(
            {
                "horizon": r.horizon,
                "target_ym": r.target_ym,
                "months_from_asof": r.months_from_asof or 0,
                "p5": _num(r.p5),
                "p10": _num(r.p10),
                "p20": _num(r.p20),
                "p_flat": _num(r.p_flat),
                "status": r.status,
                "judgment_seq": r.judgment_seq,
            }
        )
        for r in sorted(rows, key=lambda x: x.horizon)
    ]


def priority_supply(payments: Iterable[NoticeKindLike]) -> bool | None:
    """가점제 1순위 공급 경로: 본청약 공고가 있으면 True, 공고가 모두 무순위·임의·선착순이면 False, 공고 없음·미상이면 None."""
    kinds = [p.notice_kind for p in payments]
    if "본청약" in kinds:
        return True
    if kinds and all(k in _NON_PRIORITY_KINDS for k in kinds):
        return False
    return None


def regulated_flag(text: str | None) -> bool | None:
    """complex.regulated('규제'/'비규제') → bool, 그 밖(미상)은 None."""
    return _REGULATED.get(text or "")


def immediate_move_in(move_in_ym: str | None, asof_date: str) -> bool:
    """입주월 ≤ 기준일 월이면 즉시 입주(§6-3 '기준일+1년')."""
    return bool(move_in_ym) and str(move_in_ym)[:7] <= asof_date[:7]


def build_complex_input(
    cx: ComplexLike,
    *,
    scope: JudgeScope,
    price: PriceView,
    asof_date: str,
    terms: TermsLike | None = None,
    payments: Iterable[NoticeKindLike] = (),
    intake: IntakeLike | None = None,
    labels: Mapping[str, Label | None] | None = None,
    ladders: Iterable[LadderRowLike] = (),
) -> ComplexScoreInput:
    """``labels`` 키: price·resale·residency·down_payment·move_in(없으면 null = 계약 설명대로 값이 있으면 확인됨).

    ``ladders`` 는 사다리를 돌리는 범위(``analysis.scope.runs_ladder`` = 판정 대상)일 때만 싣는다 — '참고'·'보류'·'미해결'·
    '제외' 단지는 같은 스냅샷에 남은 사다리 행(이전 범위의 판정·이월·devseed)이 있어도 p10 에 쓰지 않는다(D9-1: 사다리 미실행
    → p10 null → 종합 '미판정'). 파이프라인·G5 미리보기가 이 함수 하나를 쓴다.
    """
    lab = labels or {}
    ladders = ladders if runs_ladder(scope) else ()
    return ComplexScoreInput(
        complex_id=cx.id,
        name=cx.name,
        living_area=cx.living_area,
        judge_scope=contract_scope(scope),
        price_low_won=price.low_won,
        price_high_won=price.high_won,
        price_label=lab.get("price"),
        move_in_ym=cx.move_in_ym,
        move_in_label=lab.get("move_in"),  # 계약 2026-10-09.4 (F2 요청, M2)
        immediate_move_in=immediate_move_in(cx.move_in_ym, asof_date),
        completed_year=None,
        ladders=ladder_inputs(ladders),
        winner_date=cx.winner_date,
        resale_months=cx.resale_months,
        resale_label=lab.get("resale"),
        resale_release_on_registration=cx.resale_release_on_registration,
        residency_months=cx.residency_months,
        residency_label=lab.get("residency"),
        down_payment_pct=float(terms.down_payment_pct)
        if terms and terms.down_payment_pct is not None
        else None,
        down_payment_label=lab.get("down_payment"),
        interim_terms_text=terms.interim_terms_text if terms else None,
        intake_status=intake.status if intake else None,
        intake_path=intake.path if intake else None,
        intake_checked_at=intake.checked_at if intake else None,
        regulated=regulated_flag(cx.regulated),
        rewin_restriction_years=cx.rewin_restriction_years,
        has_priority_supply=priority_supply(payments),
        fixed_components=None,
    )

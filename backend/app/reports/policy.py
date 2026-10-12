"""보고서의 판정 범위·현재 구매가 계산 지점 — 공용 함수(``app.analysis``) 호출만 둔다(D9-1·§6-1, R3 M3).

규칙은 ``app.analysis.scope``·``app.analysis.price_view`` 한 곳에 있다(파이프라인·API·보고서 공용).
여기는 보고서가 그 함수를 부르는 이름과 참여 규칙(API ``views.load_bundles`` 와 같음)만 둔다
— 규칙을 다시 쓰지 않는다.

- ``judge_scope(...)`` → ``ScopeResult``(범위 5종 + 사유)
- ``complex_scope(cx, types, payments, intakes)`` → 단지 사실·표시 접수 행으로 계산한 ``ScopeResult``
- ``current_price(types, payments)`` → ``PriceView``(최신 공고 ``payment_terms.price_by_type`` 우선)
- ``current_terms(payments)`` → 현재 공고 조건(effective_from → notice_no → id)
- ``pick_intake(rows)`` → 표시 접수 행
- ``shows_ladder(scope)`` → 사다리 행·p10 을 표시·집계에 쓰는가('판정 대상'만)
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Final

from app.analysis import price_view, scope
from app.analysis.price_view import PaymentTermsLike, PriceView, TypeRowLike
from app.analysis.scope import IntakeRowLike, JudgeScope, ScopeResult, original_missing
from app.models import Complex

__all__ = [
    "JUDGE_SCOPE_TEXT",
    "JudgeScope",
    "PriceView",
    "ScopeResult",
    "complex_scope",
    "current_price",
    "current_terms",
    "judge_scope",
    "original_missing",
    "pick_intake",
    "scope_note",
    "shows_ladder",
]

JUDGE_SCOPE_TEXT: Final = scope.SCOPE_TEXT
"""meta §1-3-4 표시 문구(공용 ``analysis.scope.SCOPE_TEXT``)."""


def judge_scope(
    *,
    inclusion_class: str | None,
    inclusion_decision: str | None,
    has_price: bool,
    intake_status: str | None,
    original_notice_missing: bool = False,
) -> ScopeResult:
    """판정 범위(D9-1) = ``analysis.scope.judge_scope``."""
    return scope.judge_scope(
        inclusion_class=inclusion_class,
        inclusion_decision=inclusion_decision,
        has_price=has_price,
        intake_status=intake_status,
        original_notice_missing=original_notice_missing,
    )


def current_price(
    types: Sequence[TypeRowLike],
    payments: Sequence[PaymentTermsLike],
    *,
    discount_label: price_view.DiscountLabel | None,
) -> PriceView:
    """현재 구매가(§6-1) = ``analysis.price_view.current_price``(할인은 출처 라벨 확인됨만, D12-3)."""
    return price_view.current_price(types, payments, discount_label=discount_label)


def current_terms[P: PaymentTermsLike](payments: Iterable[P]) -> P | None:
    """현재 공고 조건 = ``analysis.price_view.current_terms``(effective_from → notice_no → id)."""
    return price_view.current_terms(payments)


def pick_intake[R: IntakeRowLike](rows: Iterable[R]) -> R | None:
    """표시 접수 행 = ``analysis.scope.pick_intake``."""
    return scope.pick_intake(rows)


def complex_scope(
    cx: Complex,
    types: Sequence[TypeRowLike],
    payments: Sequence[PaymentTermsLike],
    intakes: Iterable[IntakeRowLike],
) -> ScopeResult:
    """단지 하나의 판정 범위 — README 사용 예 그대로(현재 사실 + 그 스냅샷의 표시 접수 행)."""
    shown = pick_intake(intakes)
    return judge_scope(
        inclusion_class=cx.inclusion_class,
        inclusion_decision=cx.inclusion_decision,
        has_price=current_price(types, payments, discount_label=None).known,  # 할인은 known 과 무관
        intake_status=shown.status if shown is not None else None,
        original_notice_missing=scope.original_missing(cx.applyhome_id, cx.notice_date),
    )


def shows_ladder(value: str) -> bool:
    """사다리 행·p10 을 보고서 표시·집계에 쓰는가 — '판정 대상'만(D9-1, API ``load_bundles`` 참여 규칙).

    '참고'·'보류'·'미해결'·'제외' 단지는 같은 스냅샷에 남은 사다리 행(이전 범위의 판정·이월)이 있어도
    쓰지 않는다.
    """
    return scope.runs_ladder(value)


def scope_note(text: str, reason: str) -> str:
    """사다리·확률 자리에 쓰는 문구: '판정 범위: <표시 문구> — <사유>'."""
    return f"판정 범위: {text} — {reason}"

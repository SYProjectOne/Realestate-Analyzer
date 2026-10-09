"""판정 범위 (meta §1-3-4, DECISIONS D9-1) — 파이프라인·API·보고서가 모두 이 모듈 하나로 계산한다.

판단하지 않는다: 포함/제외는 판정기 classify 결과(``complex.inclusion_class``·``inclusion_decision``), 접수 상태는
표시 접수 행(``pick_intake``)의 status 다. 여기서는 그 결과를 범위 5종으로 옮기는 표(규칙)만 둔다.

| 순서 | 조건 | 범위 | 사다리 | rerank | 점수 | decide |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | inclusion_class = '범위 경계'(D2-6) | 제외 | × | × | × | × |
| 2 | classify auto + 제외 클래스(공공분양·공공/민간임대·비아파트·범위 밖) | 제외 | × | × | × | × |
| 3 | classify 미해결(decision ≠ auto: review·manual_review·escaped·없음) 또는 클래스 미분류·manual_review | 미해결 | × | × | × | × |
| 4 | 포함 확정 + 분양가 미공개(현재 구매가 없음) | 보류 | × | ○ | ○ | × |
| 5 | 포함 확정 + 가격 있음 + 접수 '확인 불가'·'불가'·접수 행 없음 | 참고 | × | ○ | ○ | × |
| 6 | 포함 확정 + 가격 있음 + 접수 '가능'·'미정' | 판정 대상 | ○ | ○ | ○ | ○ |

'점수 ○'는 성분 행을 만든다는 뜻이다(사다리가 없으면 p10 null → 종합 '미판정', RA §6-4).
'미해결'은 계약 2026-10-09.4(F3)에서 score_total.judge_scope 값으로 추가된다. 그 전까지 ``ComplexScoreInput``
(계약 Literal 4종)에는 ``contract_scope`` 가 같은 효과(점수·사다리 없음)의 '제외'로 싣는다.
"""

# ruff: noqa: E501  (한국어 docstring·표)

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final, Literal, Protocol, cast, get_args

from app.core.contracts_gen import ComplexScoreInput

__all__ = [
    "BOUNDARY_CLASS",
    "EXCLUDED_CLASSES",
    "INCLUDED_CLASS",
    "INTAKE_PRIORITY",
    "JUDGE_SCOPES",
    "SCOPE_TEXT",
    "UNRESOLVED",
    "ContractScope",
    "IntakeRowLike",
    "JudgeScope",
    "ScopeResult",
    "contract_scope",
    "in_rerank",
    "is_decide_candidate",
    "is_scored",
    "judge_scope",
    "pick_intake",
    "runs_ladder",
]

JudgeScope = Literal["판정 대상", "참고", "보류", "미해결", "제외"]
ContractScope = Literal["판정 대상", "보류", "참고", "제외"]
"""계약 2026-10-09.3 의 ComplexScoreInput.judge_scope(‘미해결’ 없음)."""

JUDGE_SCOPES: Final[tuple[JudgeScope, ...]] = ("판정 대상", "참고", "보류", "미해결", "제외")
UNRESOLVED: Final[JudgeScope] = "미해결"
SCOPE_TEXT: Final[dict[JudgeScope, str]] = {
    "판정 대상": "판정 대상",
    "참고": "참고 후보(순위만)",
    "보류": "보류 — 공고 후 재판정",
    "미해결": "미해결(분류 판정 미해결)",
    "제외": "제외",
}
"""화면·보고서 표시 문구(meta §1-3-4 원문)."""

BOUNDARY_CLASS: Final = "범위 경계"
INCLUDED_CLASS: Final = "private_sale_apt"
EXCLUDED_CLASSES: Final = frozenset(
    {"public_sale", "public_rental", "private_rental", "non_apartment", "out_of_scope"}
)
"""판정기 classify 의 제외 클래스(사업주체 명의 기준). '범위 경계'는 판정기가 아니라 주소 매칭(D2-6)."""
INTAKE_JUDGED: Final = frozenset({"가능", "미정"})
INTAKE_PRIORITY: Final[dict[str, int]] = {"human_check": 0, "official_popup": 1, "headless_shot": 2}
"""표시 접수 행 우선순위. unofficial_ref(보도자료·블로그)는 '비공식'이라 접수 근거가 아니다(meta §1-3-5)."""

_LADDER: Final = frozenset({"판정 대상"})
_RERANK: Final = frozenset({"판정 대상", "참고", "보류"})
_SCORED: Final = _RERANK


@dataclass(frozen=True, slots=True)
class ScopeResult:
    """범위 + 표시 문구 + 근거(왜 그 범위인지, 사람이 읽는 한 줄)."""

    scope: JudgeScope
    reason: str

    @property
    def text(self) -> str:
        return SCOPE_TEXT[self.scope]

    @property
    def ladder(self) -> bool:
        return runs_ladder(self.scope)

    @property
    def rerank(self) -> bool:
        return in_rerank(self.scope)

    @property
    def scored(self) -> bool:
        return is_scored(self.scope)

    @property
    def decide(self) -> bool:
        return is_decide_candidate(self.scope)


def judge_scope(
    *,
    inclusion_class: str | None,
    inclusion_decision: str | None,
    has_price: bool,
    intake_status: str | None,
) -> ScopeResult:
    """D9-1 판정 범위(모듈 docstring 표 순서대로 첫 번째로 맞는 행).

    - ``inclusion_class``·``inclusion_decision``: complex 행 그대로(판정기 classify P4 결과).
    - ``has_price``: 현재 구매가(``analysis.price_view.current_price``)가 있는가.
    - ``intake_status``: 표시 접수 행(``pick_intake``)의 status. 행이 없으면 None(= 접수 확인 불가).
    """
    cls = inclusion_class or "미분류"
    if cls == BOUNDARY_CLASS:
        return ScopeResult("제외", "범위 경계(주소가 지역 법정동에 매칭 안 됨)")
    if inclusion_decision != "auto" or cls in ("미분류", "manual_review"):
        why = inclusion_decision or "분류 전"
        return ScopeResult("미해결", f"포함/제외 classify 미해결({why}, {cls})")
    if cls in EXCLUDED_CLASSES:
        return ScopeResult("제외", f"포함/제외 classify 제외 클래스({cls})")
    if cls != INCLUDED_CLASS:  # 계약 밖 값 — 판정 대상으로 넘기지 않는다
        return ScopeResult("미해결", f"알 수 없는 분류({cls})")
    if not has_price:
        return ScopeResult("보류", "분양가 미공개(공고 전)")
    if intake_status in INTAKE_JUDGED:
        return ScopeResult("판정 대상", f"포함 확정 · 접수 {intake_status}")
    return ScopeResult("참고", f"접수 {intake_status or '확인 불가(접수 행 없음)'}")


def runs_ladder(scope: str) -> bool:
    """P6 noul 사다리를 돌리는 범위(판정 대상만)."""
    return scope in _LADDER


def in_rerank(scope: str) -> bool:
    """P7 rerank 후보(판정 대상·참고·보류). 제외·미해결은 후보가 아니다."""
    return scope in _RERANK


def is_scored(scope: str) -> bool:
    """점수 엔진이 성분 행을 만드는 범위(제외·미해결 빼고)."""
    return scope in _SCORED


def is_decide_candidate(scope: str) -> bool:
    """P8 decide 후보(판정 대상만)."""
    return scope in _LADDER


_CONTRACT_VALUES: Final = frozenset(get_args(ComplexScoreInput.model_fields["judge_scope"].annotation))


def contract_scope(scope: JudgeScope) -> ContractScope:
    """``ComplexScoreInput.judge_scope`` 에 넣을 값. 계약에 '미해결'이 없으면(2026-10-09.3) '제외'(점수·사다리 없음)로.

    계약 .4 가 '미해결'을 추가하면 그대로 넘긴다(분석 엔진은 ``is_scored`` 로 둘 다 뺀다).
    """
    if scope in _CONTRACT_VALUES:
        return cast(ContractScope, scope)
    return "제외"


class IntakeRowLike(Protocol):
    """intake_status 행(ORM·DTO 모두)에서 표시 행 선택에 쓰는 속성."""

    @property
    def id(self) -> int: ...
    @property
    def path(self) -> str: ...
    @property
    def checked_at(self) -> str | None: ...
    @property
    def status(self) -> str: ...


def pick_intake[R: IntakeRowLike](rows: Iterable[R]) -> R | None:
    """표시 접수 행: 경로 human_check > official_popup > headless_shot, 같은 경로면 확인 **날짜**가 최근, 같은 날이면 id 가 큰 것.

    같은 날 '날짜만'(사람 입력)과 '시각 포함'(수집) 값은 문자열로 비교할 수 없으므로 날짜(앞 10자)만 비교하고
    나중에 기록된 행(id)이 이긴다 — 파이프라인·API·보고서가 같은 행을 고른다(R3 minor 21).
    """
    usable = [r for r in rows if r.path in INTAKE_PRIORITY]
    if not usable:
        return None
    return min(usable, key=lambda r: (INTAKE_PRIORITY[r.path], _neg_day(r.checked_at), -r.id))


def _neg_day(checked_at: str | None) -> tuple[int, ...]:
    day = (checked_at or "")[:10]
    return (*tuple(-ord(ch) for ch in day), 1)  # 빈 값('')은 가장 오래된 것으로

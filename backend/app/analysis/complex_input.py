"""사실 행 → ``ComplexScoreInput`` (점수·요건 사전 계산 입력) — 파이프라인과 G5 미리보기가 같은 함수를 쓴다(R3 minor 20).

파이프라인(``scheduler.inputs.complex_input``)과 API 미리보기(``api.views.score_input``)가 입력을 서로 다르게
만들던 것(has_priority_supply False→None, regulated 매핑, immediate_move_in 누락, 접수 행 선택)을 여기 하나로 모은다.
DB 접근 없음 — 호출자가 읽은 행(ORM·DTO)을 넘긴다. 판정 범위·현재 구매가·표시 접수 행은 ``scope``·``price_view``.
"""

# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any, Final, Protocol, cast

from app.analysis.price_view import PriceView
from app.analysis.scope import JudgeScope, contract_scope, runs_ladder
from app.analysis.types import Label, weakest_label
from app.core.contracts_gen import ComplexScoreInput, LadderInput

__all__ = [
    "ComplexLike",
    "LadderRowLike",
    "build_complex_input",
    "immediate_move_in",
    "ladder_inputs",
    "masked",
    "priority_supply",
    "regulated_flag",
    "resale_input_label",
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


class _Masked:
    """행(ORM·DTO)의 일부 속성만 None 으로 보이게 하는 읽기 전용 감싸개(DB 쓰기 없음).

    판정기 추출 전 OCR 값(label '추정' + reason 'OCR', D5-4)은 screen 거부·extract 실패면 점수 입력에서 null 이어야 한다
    (R3 C3). 사실 행은 그대로 두고(화면은 '추정(OCR)'으로 보인다) 점수 입력 빌더에만 이 감싸개를 넘긴다.
    ``price_by_type.<타입>.<필드>`` 처럼 점으로 이은 이름은 JSON 항목 하나만 지운다."""

    __slots__ = ("_fields", "_row")

    def __init__(self, row: Any, fields: frozenset[str]) -> None:
        self._row = row
        self._fields = fields

    def __getattr__(self, name: str) -> Any:
        if name in self._fields:
            return None
        value = getattr(self._row, name)
        # '<속성>.<키>.<필드>' — 키(주택형 코드)에 점이 있을 수 있어 마지막 점에서 나눈다
        nested = [f[len(name) + 1 :].rsplit(".", 1) for f in self._fields if f.startswith(name + ".")]
        if nested and isinstance(value, Mapping):
            out = {k: dict(v) if isinstance(v, Mapping) else v for k, v in value.items()}
            for parts in nested:
                if len(parts) == 2 and isinstance(out.get(parts[0]), dict):
                    out[parts[0]][parts[1]] = None
                elif len(parts) == 1:  # '<속성>.<키>' — 키 하나(할인 discount_by_type.<타입>, 계약 .8)
                    whole = f"{name}.{parts[0]}"
                    key = next((k for k in out if f"{name}.{k}" == whole), None)
                    if key is not None:
                        out.pop(key)
            return out
        return value


def masked[T](row: T, fields: Iterable[str]) -> T:
    """``fields`` 가 비면 행 그대로, 아니면 그 속성만 None 인 감싸개(같은 Protocol 로 쓴다)."""
    names = frozenset(fields)
    if not names:
        return row
    return cast(T, _Masked(row, names))


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


def resale_input_label(resale: Label | None, winner: Label | None) -> Label | None:
    """전매 종료(= 당첨일 + 전매 기간 — 유동성 성분·요건 사전 계산 입력)의 라벨 = 두 입력 중 약한 것(R3 M2).

    둘 다 null(미상)이면 null(= 값이 있으면 확인됨). 점수 엔진(``score.liquidity_component``)·요건 사전 계산이 쓴다 —
    당첨일 라벨은 계약 ``ComplexScoreInput.winner_label``(계약 2026-10-09.7)."""
    if resale is None and winner is None:
        return None
    return weakest_label(resale or "확인됨", winner or "확인됨")


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
    """``labels`` 키: price·resale·winner·residency·down_payment·move_in(없으면 null = 계약 설명대로 값이 있으면 확인됨).
    winner(당첨일 라벨)는 ``winner_label``(계약 2026-10-09.7, R3 M2 — 유동성 성분·전매 종료 라벨 합성).

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
        winner_label=lab.get("winner"),  # 계약 2026-10-09.7 (R3 M2)
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
        current_supply_kind=_supply_kind(terms),
        fixed_components=None,
    )


_SUPPLY_KINDS: Final = frozenset({"본청약", "무순위", "임의", "선착순"})


def _supply_kind(terms: Any) -> Any:
    """현재 조건(최신 공고)의 공급 경로(계약 .8 ``current_supply_kind`` — §6-7 B·D 접근성). 모르면 None."""
    kind = getattr(terms, "notice_kind", None) if terms is not None else None
    return kind if kind in _SUPPLY_KINDS else None

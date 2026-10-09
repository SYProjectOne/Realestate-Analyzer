"""§6-3 사다리 명제 3개 시점 · 연율 환산 (RA §6-3, §9 T10).

| horizon | 목표 시점 |
| --- | --- |
| move_in_plus_1y | 입주월 + 12개월 (즉시 입주거나 입주월이 기준일 이전이면 기준일 + 12개월) |
| asof_plus_3y | 기준일 + 36개월 — 입주 시기가 다른 단지도 목표 시점이 같다 |
| asof_plus_5y | 기준일 + 60개월 (상황 C) |

개월 수 m = 목표 연월 − 기준일 연월(일은 무시). 연율 r = (1 + g)^(12/m) − 1, 소수 4자리.
명제 템플릿은 meta §2-2 / contracts/schemas/ladder.json 설명 그대로. 확률은 판정기(noul)만 낸다 — 여기서는 목표·문장·연율만.
"""

# ruff: noqa: E501  (한국어 docstring·식 문자열은 화면 폭 기준으로 길다)

from __future__ import annotations

import math
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from app.analysis._common import Q4, add_months_ym, parse_date, ym_index, ym_of
from app.analysis.types import Horizon, LadderTarget
from app.core.contracts_gen import LadderAnnualized, LadderInput

THRESHOLDS: Final[dict[str, Decimal]] = {
    "p5": Decimal("0.05"),
    "p10": Decimal("0.10"),
    "p20": Decimal("0.20"),
}
_OFFSETS: Final[dict[Horizon, int]] = {"asof_plus_3y": 36, "asof_plus_5y": 60}


def target_label(ym: str) -> str:
    """'2029-03' → '2029 상반기', '2029-10' → '2029 하반기'."""
    month = int(ym[5:7])
    return f"{ym[:4]} {'상반기' if month <= 6 else '하반기'}"


def ladder_target(
    horizon: Horizon, asof_date: str, *, move_in_ym: str | None, immediate: bool
) -> LadderTarget | None:
    """horizon 1개의 목표(사다리 명제·판정기 payload 용 — ``judge.payloads.ladder_specs`` 가 이 함수를 쓴다, 한 구현).

    입주월을 모르고 즉시 입주도 아니면 move_in_plus_1y 목표는 없다(None — 명제를 만들지 않는다; 추측해 기준일 + 1년으로
    두지 않는다). 점수의 공급 창(``ladder_targets``)은 같은 경우 기준일을 쓴다(성분 계산 기준선 — 판정이 아니다)."""
    if horizon == "move_in_plus_1y" and not move_in_ym and not immediate:
        return None
    return ladder_targets(asof_date, move_in_ym=move_in_ym, immediate=immediate)[horizon]


def ladder_targets(asof_date: str, *, move_in_ym: str | None, immediate: bool) -> dict[Horizon, LadderTarget]:
    asof_ym = ym_of(parse_date(asof_date))
    base = (
        asof_ym if (immediate or not move_in_ym or ym_index(move_in_ym) <= ym_index(asof_ym)) else move_in_ym
    )
    out: dict[Horizon, LadderTarget] = {}
    targets: list[tuple[Horizon, str]] = [("move_in_plus_1y", add_months_ym(base, 12))]
    targets += [(h, add_months_ym(asof_ym, n)) for h, n in _OFFSETS.items()]
    for horizon, ym in targets:
        out[horizon] = LadderTarget(
            horizon=horizon,
            target_ym=ym,
            months_from_asof=ym_index(ym) - ym_index(asof_ym),
            target_label=target_label(ym),
        )
    return out


def annualize(g: Decimal, months: int) -> Decimal:
    """r = (1+g)^(12/m) − 1, 소수 4자리(반올림)."""
    if months <= 0:
        raise ValueError("개월 수는 1 이상")
    r = math.pow(1 + float(g), 12 / months) - 1
    return Decimal(repr(r)).quantize(Q4, rounding=ROUND_HALF_UP)


def annualized(months: int) -> LadderAnnualized:
    return LadderAnnualized(**{k: float(annualize(g, months)) for k, g in THRESHOLDS.items()})


def pick_ladder(ladders: Iterable[LadderInput], horizon: Horizon) -> LadderInput | None:
    """해당 horizon의 사다리(여럿이면 judgment_seq가 큰 것). status는 호출자가 본다."""
    found = [lad for lad in ladders if lad.horizon == horizon]
    if not found:
        return None
    return max(found, key=lambda lad: lad.judgment_seq if lad.judgment_seq is not None else -1)


def _horizon_text(horizon: Horizon, move_in_ym: str | None, asof_date: str) -> str:
    if horizon == "move_in_plus_1y":
        return f"입주({move_in_ym}) 후 1년 시점" if move_in_ym else "즉시 입주 후 1년 시점"
    years = _OFFSETS[horizon] // 12
    return f"기준일({asof_date}) 후 {years}년 시점"


def proposition_texts(
    *,
    name: str,
    type_code: str,
    asof_date: str,
    price_text: str,
    horizon: Horizon,
    move_in_ym: str | None,
    target_ym: str,
) -> dict[str, str]:
    """meta §2-2 명제 4개(p5·p10·p20·p_flat). 판정기 noul payload용 문장."""
    head = (
        f"{name} 전용 {type_code}을 {asof_date} 현재 구매가({price_text})로 매수할 경우, "
        f"{_horizon_text(horizon, move_in_ym, asof_date)}인 {target_label(target_ym)} 실거래가가 현재 구매가 대비 "
    )
    return {
        "p5": head + "+5% 이상이다",
        "p10": head + "+10% 이상이다",
        "p20": head + "+20% 이상이다",
        "p_flat": head + "이하(보합·하락)이다",
    }

"""analysis 입력·중간 결과 dataclass (RA §6).

계약 DTO(``app.core.contracts_gen``의 ScoreInputs·ComplexScoreInput 등)는 그대로 받고, 식 계산에 필요한
정규화 입력(``Trade``)과 식의 중간 결과(성분·가격·비교군·사다리 시점)를 불변 dataclass로 둔다.
금액은 원 단위 정수, 비율·점수는 ``Decimal``이다(부동소수 합 금지 — score_run.json).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Final, Literal

from app.analysis._common import parse_date, to_float
from app.core.contracts_gen import ScoreComponent, TradeInput

ComponentKey = Literal["p10", "rerank", "gap", "benchmark", "supply", "liquidity", "move_in"]
Label = Literal["확인됨", "추정", "비공식", "재가공", "확인 불가"]
Horizon = Literal["move_in_plus_1y", "asof_plus_3y", "asof_plus_5y"]
EnvelopeStatus = Literal["ok", "review", "escaped", "blocked", "error"]

COMPONENT_ORDER: Final[tuple[ComponentKey, ...]] = (
    "p10",
    "rerank",
    "gap",
    "benchmark",
    "supply",
    "liquidity",
    "move_in",
)
HORIZONS: Final[tuple[Horizon, ...]] = ("move_in_plus_1y", "asof_plus_3y", "asof_plus_5y")

# 라벨 약함 순서: 여러 입력을 섞은 값의 라벨은 가장 약한 입력의 라벨이다.
_LABEL_RANK: Final[dict[Label, int]] = {"확인됨": 0, "재가공": 1, "비공식": 2, "추정": 3, "확인 불가": 4}


def weakest_label(*labels: Label | None) -> Label:
    present = [lab for lab in labels if lab is not None]
    if not present:
        return "확인 불가"
    return max(present, key=lambda lab: _LABEL_RANK[lab])


@dataclass(frozen=True)
class Trade:
    """rtms_trade 1행(정규화). TradeInput에서 만든다."""

    trade_id: int | None
    living_area: str | None
    apt_name: str
    completed_year: int | None
    area_m2: Decimal
    price_won: int
    deal_date: date
    cancelled: bool
    source: Literal["openapi", "reprocessed"]
    is_presale: bool

    @classmethod
    def of(cls, t: TradeInput) -> Trade:
        return cls(
            trade_id=t.id,
            living_area=t.living_area,
            apt_name=t.apt_name,
            completed_year=t.completed_year,
            area_m2=Decimal(repr(t.area_m2)),
            price_won=t.price_won,
            deal_date=parse_date(t.deal_date),
            cancelled=t.cancelled,
            source=t.source,
            is_presale=bool(t.is_presale),
        )

    @property
    def label(self) -> Label:
        return "확인됨" if self.source == "openapi" else "재가공"


@dataclass(frozen=True)
class PurchasePrice:
    """§6-1 현재 구매가: P_low = 대표층 + 발코니 + 옵션, P_high = 최고가 + 발코니 + 옵션, P_mid = 평균."""

    low_won: int
    high_won: int
    mid_won: Decimal


@dataclass(frozen=True)
class ComparableMember:
    """비교군 단지 1개 = comparable_set 1행(+ C2 위스커 1열). 원본 거래는 바꾸지 않는다."""

    member_apt_name: str
    completed_year: int | None
    substitute: bool
    adjusted: bool
    coef_used: Decimal | None
    n_trades: int
    low_won: int | None
    median_won: int | None
    adjusted_median_won: int | None
    high_won: int | None
    outliers_excluded: int
    excluded_reason: str | None
    note: str | None
    prices_won: tuple[int, ...] = ()
    adjusted_prices_won: tuple[Decimal, ...] = ()


@dataclass(frozen=True)
class GapResult:
    """§6-2 가격 갭 결과. gap_pct는 보정 중앙값 기준, gap_pct_unadjusted는 미보정 기준(둘 다 표시)."""

    price: PurchasePrice | None
    members: tuple[ComparableMember, ...]
    n_trades: int
    median_adjusted: Decimal | None
    median_unadjusted: Decimal | None
    gap_pct: Decimal | None
    gap_pct_unadjusted: Decimal | None
    score: Decimal | None
    substitute: bool
    label: Label
    reason: str | None
    flags: tuple[str, ...]
    formula_text: str
    empty_reason: str | None


@dataclass(frozen=True)
class LadderTarget:
    """§6-3 사다리 1개 시점의 목표."""

    horizon: Horizon
    target_ym: str
    months_from_asof: int
    target_label: str


@dataclass(frozen=True)
class ComponentResult:
    """성분 1개 = score_component 1행. score=None이면 종합 미계산('미판정')."""

    complex_id: int
    component: ComponentKey
    raw_value: Decimal | None
    score: Decimal | None
    formula_text: str
    label: Label
    reason: str | None = None
    delta: Decimal | None = None
    flags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.formula_text.strip():
            raise ValueError(f"formula_text 비어 있음: {self.complex_id}/{self.component}")

    def to_contract(self) -> ScoreComponent:
        return ScoreComponent(
            complex_id=self.complex_id,
            component=self.component,
            raw_value=to_float(self.raw_value),
            score_0_10=to_float(self.score),
            formula_text=self.formula_text,
            label=self.label,
            reason=self.reason,
            delta=to_float(self.delta),
            flags=list(self.flags),
        )


@dataclass(frozen=True)
class RankedEntry:
    complex_id: int
    total: Decimal
    rank: int
    tie_group: int | None


@dataclass(frozen=True)
class DecideOption:
    """decide 후보 1개의 표시 결과(§6-4 동률 규칙)."""

    key: str
    prob: float
    chosen: bool
    tie: bool

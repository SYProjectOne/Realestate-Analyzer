"""DB → 판정·점수 입력 조립 (RA §6, contracts/schemas/score_inputs.json, 계약 2026-10-09.2 필드).

- ``load_facts``: 단지마다 현재 구매가(``analysis.price_view.current_price`` — §6-1 최신 공고 price_by_type 우선,
  API·보고서와 같은 함수)·현재 납부 조건·표시 접수 행(``analysis.scope.pick_intake``)·공고 필드 라벨
  (field_provenance chosen 행; 가격 출처 행이 없으면 null = '확인 불가(출처 누락)')·판정 범위
  (``analysis.scope.judge_scope`` — DECISIONS D9-1, 파이프라인·API·보고서 공용).
- ``build_score_inputs``: ScoreInputs(생활권 세대수·unsold_scope_codes, 거래·벤치마크·공급·미분양 원자료,
  단지별 사다리). 비교군 선택·필터는 WP4 규칙이라 거래는 거르지 않고 넣는다(기준일 전 24개월만).
- ``evidence_card``: 판정기 증거 카드(표시 문자열). 수치는 출처 라벨과 함께 문자열로만 넣는다.

여기서는 판단하지 않는다: 포함 여부는 complex.inclusion_class(판정기 classify 결과), 접수 상태는 intake_status 행.
"""

# ruff: noqa: E501

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Final, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.complex_input import build_complex_input
from app.analysis.gap import compute_gap
from app.analysis.price_view import FieldRef, PriceView, current_price, current_terms
from app.analysis.scope import EXCLUDED_CLASSES, INTAKE_PRIORITY, JudgeScope, judge_scope, pick_intake
from app.analysis.types import GapResult, Label
from app.core.contracts_gen import (
    AgePremiumCoef,
    BenchmarkInput,
    ComplexScoreInput,
    LivingAreaScoreInput,
    RegionScoreParams,
    RerankAnchor,
    ScoreInputs,
    SupplyInput,
    TradeInput,
    UnsoldInput,
)
from app.judge.payloads import EvidenceCard
from app.models import (
    Benchmark,
    Complex,
    ComplexType,
    FieldProvenance,
    IntakeStatus,
    Ladder,
    LegalDong,
    PaymentTerms,
    Region,
    RtmsTrade,
    Snapshot,
    Supply,
    Unsold,
)
from app.normalize.living_area import living_area_of, region_household_facts

__all__ = [
    "EXCLUDED_CLASSES",
    "INTAKE_PRIORITY",
    "ComplexFacts",
    "JudgeScope",
    "age_coef",
    "build_score_inputs",
    "complex_input",
    "display_intake",
    "evidence_card",
    "fmt_eok",
    "gap_of",
    "load_facts",
]

LABELS: Final = ("확인됨", "추정", "비공식", "재가공", "확인 불가")
_PATH_TEXT: Final = {
    "human_check": "사람 확인",
    "official_popup": "공식 팝업",
    "headless_shot": "공식 홈페이지 렌더",
}
TRADE_WINDOW_DAYS: Final = 730
DEFAULT_COEF: Final = {"c_per_year": 0.015, "cap_years": 8, "label": "추정"}


def _label(value: str | None) -> Label | None:
    return cast(Label, value) if value in LABELS else None


def fmt_eok(won: int | Decimal) -> str:
    """원 → '6.26억' (소수 2자리, 끝 0 제거)."""
    v = (Decimal(won) / Decimal(100_000_000)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    text = format(v.normalize(), "f")
    return f"{text}억"


def age_coef(region: Region) -> AgePremiumCoef:
    return AgePremiumCoef.model_validate(region.age_premium_coef or DEFAULT_COEF)


@dataclass
class ComplexFacts:
    """단지 1개의 현재 사실(점수·카드 입력의 원천)."""

    row: Complex
    basis: ComplexType | None = None
    price_low: int | None = None
    price_high: int | None = None
    price_label: Label | None = None
    price_composition: str | None = None
    price: PriceView | None = None
    terms: PaymentTerms | None = None
    payments: list[PaymentTerms] = field(default_factory=list)
    intake: IntakeStatus | None = None
    labels: dict[str, Label | None] = field(default_factory=dict)
    living_area_name: str | None = None
    scope: JudgeScope = "판정 대상"
    scope_reason: str = ""
    evidence: list[tuple[str, str]] = field(default_factory=list)  # (fp_<id>, 발췌) — verify 근거

    @property
    def complex_id(self) -> int:
        return self.row.id


def display_intake(rows: Iterable[IntakeStatus]) -> IntakeStatus | None:
    """표시 접수 행 = ``analysis.scope.pick_intake``(API·보고서와 같은 규칙, R3 minor 21)."""
    return pick_intake(rows)


def _chosen_provenance(
    session: Session, entity: str, ids: Sequence[int]
) -> dict[tuple[int, str], FieldProvenance]:
    if not ids:
        return {}
    out: dict[tuple[int, str], FieldProvenance] = {}
    stmt = select(FieldProvenance).where(
        FieldProvenance.entity == entity,
        FieldProvenance.entity_id.in_(list(ids)),
        FieldProvenance.chosen.is_(True),
    )
    for fp in session.scalars(stmt.order_by(FieldProvenance.id)):
        if fp.entity_id is not None:
            out[(fp.entity_id, fp.field)] = fp
    return out


def load_facts(session: Session, snapshot: Snapshot, region: Region) -> list[ComplexFacts]:
    """지역 단지 전부의 현재 사실(complex_id 순)."""
    complexes = list(
        session.scalars(select(Complex).where(Complex.region_id == region.id).order_by(Complex.id))
    )
    if not complexes:
        return []
    ids = [c.id for c in complexes]
    types: dict[int, list[ComplexType]] = defaultdict(list)
    for t in session.scalars(
        select(ComplexType).where(ComplexType.complex_id.in_(ids)).order_by(ComplexType.id)
    ):
        types[t.complex_id].append(t)
    terms: dict[int, list[PaymentTerms]] = defaultdict(list)
    for p in session.scalars(select(PaymentTerms).where(PaymentTerms.complex_id.in_(ids))):
        terms[p.complex_id].append(p)
    intakes: dict[int, list[IntakeStatus]] = defaultdict(list)
    for i in session.scalars(
        select(IntakeStatus).where(IntakeStatus.snapshot_id == snapshot.id, IntakeStatus.complex_id.in_(ids))
    ):
        intakes[i.complex_id].append(i)
    cx_prov = _chosen_provenance(session, "complex", ids)
    type_prov = _chosen_provenance(session, "complex_type", [t.id for ts in types.values() for t in ts])
    terms_prov = _chosen_provenance(session, "payment_terms", [p.id for ps in terms.values() for p in ps])
    area_names = {str(a.get("id")): str(a.get("name") or "") for a in region.living_areas or []}

    out: list[ComplexFacts] = []
    for cx in complexes:
        f = ComplexFacts(row=cx, living_area_name=area_names.get(cx.living_area or "") or None)
        cx_types = types.get(cx.id, [])
        f.payments = terms.get(cx.id, [])
        cur = current_terms(f.payments)
        f.terms = cur
        _price(f, cx_types, type_prov, terms_prov)
        f.intake = pick_intake(intakes.get(cx.id, []))
        resale = cx_prov.get((cx.id, "resale_months"))
        residency = cx_prov.get((cx.id, "residency_months"))
        down = terms_prov.get((cur.id, "down_payment_pct")) if cur is not None else None
        f.labels = {
            "resale": _label(resale.label) if resale else None,
            "residency": _label(residency.label) if residency else None,
            "down_payment": _label(down.label) if down else None,
        }
        for fp in (
            resale,
            residency,
            down,
            cx_prov.get((cx.id, "move_in_ym")),
            type_prov.get((f.basis.id, "max_price_won")) if f.basis is not None else None,
        ):
            if fp is not None and fp.excerpt and fp.label != "확인 불가":
                f.evidence.append((f"fp_{fp.id}", fp.excerpt))
        sr = judge_scope(
            inclusion_class=cx.inclusion_class,
            inclusion_decision=cx.inclusion_decision,
            has_price=f.price_high is not None,
            intake_status=f.intake.status if f.intake is not None else None,
        )
        f.scope, f.scope_reason = sr.scope, sr.reason
        out.append(f)
    return out


def _prov_of(
    ref: FieldRef | None,
    type_prov: Mapping[tuple[int, str], FieldProvenance],
    terms_prov: Mapping[tuple[int, str], FieldProvenance],
) -> FieldProvenance | None:
    if ref is None:
        return None
    src = type_prov if ref.entity == "complex_type" else terms_prov
    return src.get((ref.entity_id, ref.field))


def _price(
    f: ComplexFacts,
    cx_types: Sequence[ComplexType],
    type_prov: Mapping[tuple[int, str], FieldProvenance],
    terms_prov: Mapping[tuple[int, str], FieldProvenance],
) -> None:
    """§6-1 현재 구매가 = ``analysis.price_view.current_price``(API·보고서와 같은 값, R3 M3)."""
    view = current_price(cx_types, f.payments)
    f.price = view
    f.basis = next((t for t in cx_types if t.type_code == view.basis_type_code), None)
    if not view.known:
        return
    f.price_low, f.price_high = view.low_won, view.high_won
    fp = _prov_of(view.max_ref, type_prov, terms_prov)
    if fp is None and view.from_terms and f.basis is not None:  # 공고별 가격 출처 행이 없으면 타입 행 출처
        fp = type_prov.get((f.basis.id, "max_price_won"))
    f.price_label = _label(fp.label) if fp is not None else None  # null → gap '확인 불가(가격 출처 누락)'
    f.price_composition = "+".join(view.composition)


def complex_input(f: ComplexFacts, asof_date: str, ladders: Iterable[Ladder] = ()) -> ComplexScoreInput:
    """``analysis.complex_input.build_complex_input`` (G5 미리보기와 같은 함수, R3 minor 20)."""
    return build_complex_input(
        f.row,
        scope=f.scope,
        price=f.price if f.price is not None else current_price([], []),
        asof_date=asof_date,
        terms=f.terms,
        payments=f.payments,
        intake=f.intake,
        labels={"price": f.price_label, **f.labels},
        ladders=ladders,
    )


def _living_areas(session: Session, region: Region) -> list[LivingAreaScoreInput]:
    areas = list(region.living_areas or [])
    try:
        facts = region_household_facts(session, region)
    except Exception:  # 참조 표가 없으면 세대수 미상(확인 불가)
        facts = {}
    codes = sorted({c for a in areas for c in (a.get("legal_dong_codes") or [])})
    sigungu = (
        {r.code: r.sigungu_code for r in session.scalars(select(LegalDong).where(LegalDong.code.in_(codes)))}
        if codes
        else {}
    )
    out: list[LivingAreaScoreInput] = []
    for a in areas:
        aid = str(a.get("id"))
        # 세대 현황 집계(참조 표)가 값이 있으면 그것, 없으면 region.living_areas 에 저장된 Fact
        v = None
        for hh in ((facts.get(aid) or {}).get("households"), a.get("households")):
            if isinstance(hh, dict) and isinstance(hh.get("v"), int | float):
                v = hh["v"]
                break
        scopes = sorted({sigungu.get(c) or c[:5] for c in (a.get("legal_dong_codes") or [])})
        out.append(
            LivingAreaScoreInput(
                id=aid,
                name=a.get("name"),
                households=int(v) if isinstance(v, int | float) else None,
                unsold_scope_codes=scopes,
            )
        )
    return out


def _trades(session: Session, region: Region, asof_date: str) -> list[TradeInput]:
    start = (date.fromisoformat(asof_date) - timedelta(days=TRADE_WINDOW_DAYS)).isoformat()
    areas = list(region.living_areas or [])
    rows = session.scalars(
        select(RtmsTrade)
        .where(
            RtmsTrade.region_id == region.id, RtmsTrade.deal_date >= start, RtmsTrade.deal_date <= asof_date
        )
        .order_by(RtmsTrade.id)
    )
    return [
        TradeInput(
            id=t.id,
            living_area=living_area_of(t.legal_dong_code, areas),
            apt_name=t.apt_name,
            completed_year=t.completed_year,
            area_m2=float(t.area_m2),
            floor=t.floor,
            price_won=int(t.price_won),
            deal_date=t.deal_date,
            cancelled=bool(t.cancelled),
            source=t.source,
            is_presale=bool(t.is_presale),
        )
        for t in rows
    ]


def build_score_inputs(
    session: Session,
    snapshot: Snapshot,
    region: Region,
    facts: Sequence[ComplexFacts],
    anchor: RerankAnchor,
) -> ScoreInputs:
    """ScoreInputs(계약 2026-10-09.2): 사다리는 이 스냅샷의 ladder 행에서."""
    ids = [f.complex_id for f in facts]
    ladders: dict[int, list[Ladder]] = defaultdict(list)
    if ids:
        for row in session.scalars(
            select(Ladder).where(Ladder.snapshot_id == snapshot.id, Ladder.complex_id.in_(ids))
        ):
            ladders[row.complex_id].append(row)
    benchmarks = [
        BenchmarkInput(
            id=b.id,
            living_area=b.living_area,
            name=b.name,
            completed_year=b.completed_year,
            sale_year=b.sale_year,
            sale_price_84_won=b.sale_price_84_won,
            trade_median_won=b.trade_median_won,
            is_presale=bool(b.is_presale),
            label=_label(b.sale_price_label) or "추정",
        )
        for b in session.scalars(
            select(Benchmark).where(Benchmark.region_id == region.id).order_by(Benchmark.id)
        )
    ]
    supply = [
        SupplyInput(
            living_area=s.living_area,
            year=s.year,
            ym=s.ym,
            units=s.units,
            label=_label(s.label) or "추정",
            complex_id=s.complex_id,
        )
        for s in session.scalars(select(Supply).where(Supply.region_id == region.id).order_by(Supply.id))
    ]
    unsold = [
        UnsoldInput(
            ym=u.ym,
            scope_code=u.scope_code,
            total=u.total,
            post_completion=u.post_completion,
            label=_label(u.source_label),
        )
        for u in session.scalars(select(Unsold).where(Unsold.region_id == region.id).order_by(Unsold.id))
    ]
    return ScoreInputs(
        snapshot_id=snapshot.id,
        asof_date=snapshot.asof_date,
        region=RegionScoreParams(
            age_premium_coef=age_coef(region),
            supply_ref_pct=float(region.supply_ref_pct) if region.supply_ref_pct is not None else 0.08,
        ),
        rerank=anchor,
        living_areas=_living_areas(session, region),
        trades=_trades(session, region, snapshot.asof_date),
        benchmarks=benchmarks,
        supply=supply,
        unsold=unsold,
        complexes=[complex_input(f, snapshot.asof_date, ladders.get(f.complex_id, [])) for f in facts],
    )


def gap_of(
    f: ComplexFacts, trades: Sequence[TradeInput], *, asof_date: str, coef: AgePremiumCoef
) -> GapResult:
    return compute_gap(complex_input(f, asof_date), trades, asof_date=asof_date, coef=coef)


def _gap_text(g: GapResult | None) -> tuple[str | None, str | None]:
    if g is None:
        return None, None
    if g.gap_pct is None:
        return None, g.empty_reason
    comps = f"비교군 {len(g.members)}단지 {g.n_trades}건"
    if g.median_adjusted is not None:
        comps += f", 중앙 {fmt_eok(g.median_adjusted)}"
    label = g.label + (f"({g.reason})" if g.reason else "")
    return comps, f"{g.gap_pct:+.1f}% ({label})"


def _with_label(text: str, label: Label | None) -> str:
    return text if label in (None, "확인됨") else f"{text} ({label})"


def evidence_card(f: ComplexFacts, *, gap: GapResult | None = None) -> EvidenceCard:
    """판정기 증거 카드(문자열). 날짜에 따라 바뀌는 문구(D±)는 넣지 않는다 — 같은 사실이면 같은 카드."""
    cx = f.row
    price = None
    if f.price_low is not None and f.price_high is not None:
        lo, hi = fmt_eok(f.price_low), fmt_eok(f.price_high)
        price = _with_label(lo if lo == hi else f"{lo.removesuffix('억')}~{hi}", f.price_label)
    basis = None
    if f.basis is not None:
        area = (
            f"({format(Decimal(f.basis.area_m2).normalize(), 'f')}㎡)" if f.basis.area_m2 is not None else ""
        )
        basis = f"{f.basis.type_code}{area}"
    resale = None
    if cx.resale_months is not None:
        resale = f"당첨 후 {cx.resale_months}개월" + (
            " (등기 시 해제)" if cx.resale_release_on_registration else ""
        )
        resale = _with_label(resale, f.labels.get("resale"))
    residency = (
        _with_label(f"{cx.residency_months}개월", f.labels.get("residency"))
        if cx.residency_months is not None
        else None
    )
    down = None
    if f.terms is not None and f.terms.down_payment_pct is not None:
        down = _with_label(
            f"{format(Decimal(f.terms.down_payment_pct).normalize(), 'f')}%", f.labels.get("down_payment")
        )
    intake = None
    if f.intake is not None:
        intake = f"{f.intake.status}({_PATH_TEXT.get(f.intake.path, f.intake.path)}"
        intake += f", {f.intake.reason})" if f.intake.reason else ")"
    comparables, gap_text = _gap_text(gap)
    return EvidenceCard(
        complex_id=cx.id,
        name=cx.name,
        basis_type=basis,
        price_range=price,
        price_composition=f.price_composition if price else None,
        move_in_ym=cx.move_in_ym,
        immediate_move_in=False,
        living_area=f.living_area_name,
        resale=resale,
        residency=residency,
        down_payment=down,
        interim=f.terms.interim_terms_text if f.terms is not None else None,
        intake=intake,
        comparables=comparables,
        gap=gap_text,
        notes=None,
    )


def facts_by_id(facts: Iterable[ComplexFacts]) -> dict[int, ComplexFacts]:
    return {f.complex_id: f for f in facts}


def payload_names(facts: Iterable[ComplexFacts]) -> dict[int, str]:
    return {f.complex_id: f.row.name for f in facts}

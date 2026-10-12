"""DB → 판정·점수 입력 조립 (RA §6, contracts/schemas/score_inputs.json, 계약 2026-10-09.2 필드).

- ``load_facts``: 단지마다 현재 구매가(``analysis.price_view.current_price`` — §6-1 최신 공고 price_by_type 우선,
  API·보고서와 같은 함수)·현재 납부 조건·표시 접수 행(``analysis.scope.pick_intake``)·공고 필드 라벨
  (field_provenance chosen 행; 가격 출처 행이 없으면 null = '확인 불가(출처 누락)')·판정 범위
  (``analysis.scope.judge_scope`` — DECISIONS D9-1, 파이프라인·API·보고서 공용).
- ``build_score_inputs``: ScoreInputs(생활권 세대수·unsold_scope_codes, 거래·벤치마크·공급·미분양 원자료,
  단지별 사다리). 비교군 선택·필터는 WP4 규칙이라 거래는 거르지 않고 넣는다(기준일 전 24개월만).
- ``evidence_card``: 판정기 증거 카드(표시 문자열). 수치는 출처 라벨과 함께 문자열로만 넣는다.
- OCR 값(R3 C3, D5-4): chosen 출처 행이 아직 OCR 판독(label '추정' + reason 'OCR' — 판정기 extract 전·screen 거부·extract
  실패)인 필드는 점수·범위 입력에서 null 이다(``ocr_pending_fields`` → ``analysis.complex_input.masked``). 사실 행은
  그대로라 화면에는 '추정(OCR)'으로 보인다. API 미리보기(``api.views.score_input``)도 같은 함수를 쓴다.

여기서는 판단하지 않는다: 포함 여부는 complex.inclusion_class(판정기 classify 결과), 접수 상태는 intake_status 행.
"""

# ruff: noqa: E501

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Final, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.complex_input import build_complex_input, masked
from app.analysis.gap import compute_gap
from app.analysis.price_view import FieldRef, PriceView, current_price, current_terms, labels_from
from app.analysis.scope import (
    EXCLUDED_CLASSES,
    INTAKE_PRIORITY,
    JudgeScope,
    judge_scope,
    original_missing,
    pick_intake,
)
from app.analysis.types import GapResult, Label, weakest_label
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
from app.facts_view import chosen_from_rows, load_overlay
from app.judge.payloads import EvidenceCard
from app.models import (
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
from app.normalize.fields import OCR_LABEL, OCR_REASON, is_ocr
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
    "ocr_pending_fields",
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
    ocr_fields: frozenset[str] = (
        frozenset()
    )  # complex 행에서 판정기 추출 전 OCR 값 필드(점수 입력 null, R3 C3)
    demoted: frozenset[str] = frozenset()
    """complex 행에서 강등(검증 모순) 중인 필드 — ``app.facts_view`` 오버레이(D11-3). 읽기는 ``fact_row``·``score_row``."""

    @property
    def complex_id(self) -> int:
        return self.row.id

    @property
    def fact_row(self) -> Complex:
        """읽기용 complex 행(강등 필드 = None, D11-3). 판정 카드·사실 문장·체크리스트가 쓴다. 쓰기는 ``row`` 에."""
        return masked(self.row, self.demoted)

    @property
    def score_row(self) -> Complex:
        """점수 입력용 complex 행(OCR 값·강등 필드 = None). 쓰기는 ``row`` 에."""
        return masked(self.row, self.ocr_fields | self.demoted)


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


def ocr_pending_fields(
    session: Session, entity: str, ids: Sequence[int], *, id_query: Any | None = None
) -> dict[int, frozenset[str]]:
    """entity_id → 판정기 추출 전 OCR 값 필드들(chosen 출처 행이 OCR 판독, ``normalize.fields.is_ocr``).

    extract 가 반영되면 chosen 이 추출 행으로 바뀌므로 여기서 빠진다. screen 거부·extract 실패·review 면 남는다.
    ``id_query``: ids 대신 쓸 id 하위 질의(지역 단지 전부 — IN 목록 펼침 없음)."""
    want = sorted(set(ids))
    out: dict[int, set[str]] = defaultdict(set)
    conds = (
        [FieldProvenance.entity_id.in_(id_query)]
        if id_query is not None
        else [FieldProvenance.entity_id.in_(want[i : i + 500]) for i in range(0, len(want), 500)]
    )
    for cond in conds:
        stmt = select(
            FieldProvenance.entity_id, FieldProvenance.field, FieldProvenance.label, FieldProvenance.reason
        ).where(
            FieldProvenance.entity == entity,
            cond,
            FieldProvenance.chosen.is_(True),
            FieldProvenance.label == OCR_LABEL,
            # reason 이 'OCR'(앞 표식 뒤)로 끝나는 행만 — 아래 is_ocr 가 정확히 가린다(SQL 은 줄이기만, 목록 성능)
            FieldProvenance.reason.like(f"%{OCR_REASON}"),
        )
        for eid, name, label, reason in session.execute(stmt):
            if eid is not None and is_ocr(label, reason):
                out[eid].add(name)
    return {k: frozenset(v) for k, v in out.items()}


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
    ocr_cx = _ocr_of(cx_prov)
    ocr_type = _ocr_of(type_prov)
    ocr_terms = _ocr_of(terms_prov)
    # D11-3 강등 오버레이: 사실 테이블 값은 그대로, 읽기에서 모순 값을 뺀다(점수·범위·카드·사실 문장 공통)
    overlay = load_overlay(
        session,
        complex_ids=ids,
        chosen=chosen_from_rows([*cx_prov.values(), *type_prov.values(), *terms_prov.values()]),
    )
    area_names = {str(a.get("id")): str(a.get("name") or "") for a in region.living_areas or []}

    out: list[ComplexFacts] = []
    for cx in complexes:
        f = ComplexFacts(row=cx, living_area_name=area_names.get(cx.living_area or "") or None)
        f.ocr_fields = ocr_cx.get(cx.id, frozenset())
        f.demoted = overlay.fields("complex", cx.id)
        cx_types = [
            masked(t, ocr_type.get(t.id, frozenset()) | overlay.fields("complex_type", t.id))
            for t in types.get(cx.id, [])
        ]
        f.payments = [
            masked(p, ocr_terms.get(p.id, frozenset()) | overlay.fields("payment_terms", p.id))
            for p in terms.get(cx.id, [])
        ]
        cur = current_terms(f.payments)
        f.terms = cur
        _price(f, cx_types, type_prov, terms_prov)
        f.intake = pick_intake(intakes.get(cx.id, []))
        resale = cx_prov.get((cx.id, "resale_months"))
        residency = cx_prov.get((cx.id, "residency_months"))
        down = terms_prov.get((cur.id, "down_payment_pct")) if cur is not None else None
        move_in = cx_prov.get((cx.id, "move_in_ym"))
        winner = cx_prov.get((cx.id, "winner_date"))

        def lab(fp: FieldProvenance | None, value: object) -> Label | None:
            if fp is not None and overlay.is_demoted(fp.entity, fp.entity_id, fp.field):
                return None  # 강등(검증 모순) = 값 없음
            if fp is None:
                # 값은 있는데 출처 행이 없으면 '확인 불가'(API 의 '확인 불가(출처 누락)'과 같다) — null 로 두면 점수
                # 라벨 합성이 '확인됨'으로 본다(R3 3차 minor 6, AGENTS 규칙 5)
                return "확인 불가" if value is not None else None
            return _label(fp.label)

        f.labels = {
            "resale": lab(resale, cx.resale_months),
            "residency": lab(residency, cx.residency_months),
            "down_payment": lab(down, cur.down_payment_pct if cur is not None else None),
            "move_in": lab(move_in, cx.move_in_ym),  # 계약 .4 move_in_label(M2)
            # 당첨일 라벨(R3 M2) → ComplexScoreInput.winner_label(계약 .7) — 유동성·전매 종료 라벨 합성
            "winner": lab(winner, cx.winner_date),
        }
        price_fp = _prov_of(f.price.max_ref, type_prov, terms_prov) if f.price is not None else None
        for fp in (resale, residency, down, move_in, price_fp):
            if fp is None or not fp.excerpt or fp.label == "확인 불가":
                continue
            if overlay.is_demoted(fp.entity, fp.entity_id, fp.field):
                continue  # 강등된 사실은 verify 근거·사실 문장에 쓰지 않는다
            f.evidence.append((f"fp_{fp.id}", fp.excerpt))
        sr = judge_scope(
            inclusion_class=cx.inclusion_class,
            inclusion_decision=cx.inclusion_decision,
            has_price=f.price_high is not None,
            intake_status=f.intake.status if f.intake is not None else None,
            original_notice_missing=original_missing(cx.applyhome_id, cx.notice_date),
            address=cx.address,
            legal_dong_code=cx.legal_dong_code,
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
    """§6-1 현재 구매가 = ``analysis.price_view.current_price``(API·보고서와 같은 값, R3 M3). 할인은 그 출처 라벨이
    확인됨일 때만(D12-3)."""

    def label(entity: str, entity_id: int, name: str) -> str | None:
        fp = (type_prov if entity == "complex_type" else terms_prov).get((entity_id, name))
        return fp.label if fp is not None else None

    view = current_price(cx_types, f.payments, discount_label=labels_from(label))
    f.price = view
    f.basis = next((t for t in cx_types if t.type_code == view.basis_type_code), None)
    if not view.known:
        return
    f.price_low, f.price_high = view.low_won, view.high_won
    # 라벨 = 구매가에 쓴 모든 필드(low·high 구성: 공급가·발코니·옵션·할인) 출처 라벨 중 가장 약한 것 — API
    # ``FactMaker.combine`` 과 같다(R3 3차 minor 6: 이전에는 최고가 출처만). 출처 행이 하나라도 없으면 타입 행
    # 라벨로 대신하지 않는다(R3 재리뷰 F2) — null → gap 성분 '확인 불가(가격 출처 누락)'
    refs = [*view.low_refs, *view.high_refs]
    fps = [_prov_of(r, type_prov, terms_prov) for r in refs] or [
        _prov_of(view.max_ref, type_prov, terms_prov)
    ]
    labs = [_label(fp.label) if fp is not None else None for fp in fps]
    f.price_label = weakest_label(*[x for x in labs if x is not None]) if labs and None not in labs else None
    f.price_composition = "+".join(view.composition)


def _ocr_of(prov: Mapping[tuple[int, str], FieldProvenance]) -> dict[int, frozenset[str]]:
    """chosen 출처 행 → entity_id 별 OCR 판독(추출 전) 필드."""
    out: dict[int, set[str]] = defaultdict(set)
    for (eid, name), fp in prov.items():
        if is_ocr(fp.label, fp.reason):
            out[eid].add(name)
    return {k: frozenset(v) for k, v in out.items()}


def complex_input(f: ComplexFacts, asof_date: str, ladders: Iterable[Ladder] = ()) -> ComplexScoreInput:
    """``analysis.complex_input.build_complex_input`` (G5 미리보기와 같은 함수, R3 minor 20). OCR 값 필드는 null."""
    return build_complex_input(
        f.score_row,
        scope=f.scope,
        price=f.price if f.price is not None else current_price([], [], discount_label=None),
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
    """ScoreInputs(계약 2026-10-09.2): 사다리는 이 스냅샷의 ladder 행에서, 벤치마크는 이 스냅샷이 인용하는 행만(C-1)."""
    from app.api.benchmarks import benchmarks_for

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
            substitute=bool(b.substitute),  # 계약 2026-10-09.7: 지역 전체 대체 행(N-M4 식·라벨 '대체')
            label=_label(b.sale_price_label) or "추정",
        )
        # C-1: 그 스냅샷(리비전)이 인용하는 벤치마크 행만(``api.benchmarks.benchmarks_for`` — API·보고서와
        # 같은 함수). 지역 전체 행을 읽으면 주간 수집마다 새로 조립된 행이 이전 행과 겹쳐 사례가 이중
        # 집계되고, 과거 스냅샷 재채점에 미래 행이 섞인다
        for b in benchmarks_for(session, snapshot)
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
    """판정기 증거 카드(문자열). 날짜에 따라 바뀌는 문구(D±)는 넣지 않는다 — 같은 사실이면 같은 카드.
    강등 중인 사실(D11-3)은 카드에 없다(``fact_row``)."""
    cx = f.fact_row
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

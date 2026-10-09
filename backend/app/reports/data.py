"""DB → 보고서 데이터 모델 (DECISIONS D4).

모든 수치는 ``Fact``(라벨·출처) — 출처 없는 수치는 '확인 불가(출처 누락)'.

읽기만 한다(판정기·점수 계산 없음, ADR-11). 사실 테이블(complex 등)은 현재값, 파생 테이블(intake_status,
judgment_log, claim, score_*, ladder, decision)은 스냅샷별이다(RA §3). Fact.prov 접두어:
fp_=field_provenance, sc_=score_component, st_=score_total, jl_=judgment_log seq, rd_=raw_document.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Final
from urllib.parse import urlparse

from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.price import judge_type, purchase_price
from app.core.contracts_gen import Fact
from app.core.protocols import CONTRACT_VERSION
from app.core.time import now_kst
from app.models import (
    Benchmark,
    Catalyst,
    CatalystLink,
    ChangeEvent,
    ChecklistItem,
    Claim,
    Competition,
    Complex,
    ComplexType,
    Decision,
    FieldProvenance,
    IntakeStatus,
    JudgmentLog,
    Ladder,
    PaymentTerms,
    RawDocument,
    Region,
    RemainingEvent,
    Scenario,
    ScoreComponent,
    ScoreRun,
    ScoreTotal,
    Snapshot,
    Supply,
    Unsold,
)
from app.reports.errors import ReportBlocked, ReportNotFound
from app.reports.fmt import make_fact, round_half_up, unknown_fact

__all__ = [
    "COMPONENT_LABELS",
    "ReportData",
    "count_remaining_contradicted",
    "is_valid_url",
    "load_report",
]

COMPONENT_LABELS: Final[dict[str, str]] = {
    "p10": "+10% 확률",
    "rerank": "판정기 순위",
    "gap": "가격 갭",
    "benchmark": "벤치마크",
    "supply": "공급",
    "liquidity": "유동성",
    "move_in": "입주 시기",
}
COMPONENT_ORDER: Final = ("p10", "rerank", "gap", "benchmark", "supply", "liquidity", "move_in")
HORIZON_LABELS: Final[dict[str, str]] = {
    "move_in_plus_1y": "입주 후 1년",
    "asof_plus_3y": "기준일 + 3년",
    "asof_plus_5y": "기준일 + 5년",
}
INTAKE_PRIORITY: Final = ("human_check", "official_popup", "headless_shot")
PATH_LABELS: Final[dict[str, str]] = {
    "human_check": "사람 확인",
    "official_popup": "공식 팝업",
    "headless_shot": "렌더 캡처",
    "unofficial_ref": "비공식 참고",
}
OPTION_LABELS: Final[dict[str, str]] = {
    "wait_new": "모집공고 대기",
    "ask_user": "사용자에게 질문",
    "investigate": "추가 조사",
    "none": "선택 없음",
}
COMPLEX_UNITS: Final[dict[str, str]] = {
    "housing_type": "text",
    "land_type": "text",
    "price_cap": "text",
    "regulated": "text",
    "units_total": "units",
    "units_general": "units",
    "units_special": "units",
    "officetel_units": "units",
    "notice_date": "date",
    "winner_date": "date",
    "move_in_ym": "ym",
    "resale_months": "months",
    "resale_release_on_registration": "text",
    "residency_months": "months",
    "rewin_restriction_years": "years",
}
JUDGMENT_SECTIONS: Final[dict[str, str]] = {
    "screen": "§4 입력 검사",
    "extract": "§4 수치 추출",
    "audit": "§4 감사",
    "classify": "§3·§5 분류",
    "compare": "§5 출처 충돌",
    "noul": "§6 사다리",
    "rerank": "§6 rerank",
    "decide": "§8 상황별 결정",
    "verify": "§7·§8 검증",
}
URL_RE: Final = re.compile(r"^https?://[^\s<>\"']+$")


def is_valid_url(url: str | None) -> bool:
    if not url or not URL_RE.match(url):
        return False
    u = urlparse(url)
    return u.scheme in ("http", "https") and bool(u.netloc) and "." in (u.hostname or "")


# ------------------------------------------------------------------ 뷰 모델


@dataclass(slots=True)
class IntakeView:
    status: str
    path: str
    path_label: str
    checked_at: str
    http_status: int | None
    reason: str | None
    evidence_url: str | None
    note: str | None
    used: bool  # 표시값(우선순위로 채택)

    @property
    def text(self) -> str:
        why = self.reason or (str(self.http_status) if self.http_status else None)
        if self.status == "확인 불가":
            return f"확인 불가({why or '사유 미기재'}, {self.checked_at[:10]})"
        return self.status


@dataclass(slots=True)
class TypeView:
    type_code: str
    area: Fact
    units: Fact
    floor_price: Fact
    max_price: Fact
    balcony: Fact
    options: Fact
    options_text: str | None
    floor_text: str | None
    is_basis: bool


@dataclass(slots=True)
class PaymentView:
    notice_no: str
    notice_kind: str | None
    effective_from: Fact
    down_payment_pct: Fact
    down_payment_first: Fact
    interim_pct: Fact
    balance_pct: Fact
    interim_terms_text: str | None
    is_current: bool


@dataclass(slots=True)
class CompetitionView:
    round: str
    kind: str
    type_code: str
    supply: Fact
    applied: Fact
    ratio_text: str | None


@dataclass(slots=True)
class EventView:
    kind: str
    notice_no: str | None
    notice_date: Fact
    units_text: str
    ratio_text: str | None
    result_text: str | None


@dataclass(slots=True)
class LadderView:
    complex_id: int
    name: str
    horizon: str
    horizon_label: str
    target_ym: str
    status: str
    p5: Fact
    p10: Fact
    p20: Fact
    p_flat: Fact
    verdict_p10: str | None
    proposition: str | None
    judgment_seq: int | None


@dataclass(slots=True)
class ComponentView:
    key: str
    label: str
    score: Fact
    raw: Fact
    weight: float
    contribution: float | None
    formula_text: str
    reason: str | None


@dataclass(slots=True)
class ScoreView:
    complex_id: int
    name: str
    living_area_name: str
    total: Fact
    total_raw: Decimal | None
    rank: int | None
    tie_group: int | None
    unstable: bool
    components: dict[str, ComponentView]
    note: str  # TOP 5 탈락·미판정 사유


@dataclass(slots=True)
class ComplexView:
    id: int
    name: str
    former_names: list[str]
    address: str | None
    living_area: str | None
    living_area_name: str
    track: str | None
    developer: str | None
    builder: str | None
    official_site_url: str | None
    inclusion_class: str
    inclusion_decision: str | None
    inclusion_prob: Fact
    facts: dict[str, Fact]
    types: list[TypeView]
    basis: TypeView | None
    price_low: Fact
    price_high: Fact
    payments: list[PaymentView]
    competition: list[CompetitionView]
    events: list[EventView]
    intake: list[IntakeView]
    intake_shown: IntakeView | None
    date_facts: list[tuple[str, Fact]]  # 접수·계약·중도금 일정(캘린더)

    @property
    def current_payment(self) -> PaymentView | None:
        cur = [p for p in self.payments if p.is_current]
        return cur[0] if cur else None


@dataclass(slots=True)
class JudgeToolRow:
    tool: str
    calls: int
    by_status: dict[str, int]
    thresholds: str
    section: str


@dataclass(slots=True)
class CallRow:
    seq: int
    snapshot_id: int | None
    tool: str
    purpose: str
    complex_name: str
    status: str
    confidence: Fact
    input_summary: str
    result_summary: str
    used_in: str
    created_at: str


@dataclass(slots=True)
class ClassifyRow:
    complex_id: int
    name: str
    inclusion_class: str
    decision: str | None
    prob: Fact
    unresolved: bool


@dataclass(slots=True)
class BenchmarkView:
    living_area_name: str
    name: str
    completed_year: Fact
    sale_year: Fact
    sale_price: Fact
    trade_median: Fact
    change_pct: Fact
    is_presale: bool


@dataclass(slots=True)
class CatalystView:
    name: str
    kind: str
    stage: str
    prob: Fact
    decision: str | None
    unresolved: bool
    note: str | None


@dataclass(slots=True)
class ConflictView:
    complex_name: str
    group: str
    chosen_text: str
    chosen_label: str
    others: list[str]
    compare_seq: int | None
    compare_status: str | None


@dataclass(slots=True)
class SupplyView:
    living_area_name: str
    year: int
    units: Fact


@dataclass(slots=True)
class UnsoldView:
    scope: str
    ym: str
    total: Fact
    post_completion: Fact


@dataclass(slots=True)
class DecisionView:
    option: str
    complex_id: int | None
    prob: Fact
    chosen: bool
    tie: bool
    mismatch: bool
    pre: dict[str, dict[str, str] | None]
    judge: dict[str, str | None]


@dataclass(slots=True)
class ScenarioBlock:
    code: str
    name: str
    weights: dict[str, float]
    top: list[ScoreView]
    decisions: list[DecisionView]
    confidence: Fact
    status: str | None
    warnings: list[str]
    judgment_seq: int | None
    tie: bool


@dataclass(slots=True)
class ClaimRow:
    section: str
    text: str
    status: str | None
    judgment_seq: int | None
    split: bool


@dataclass(slots=True)
class VerifySummary:
    section: str
    counts: dict[str, int]
    judgment_seqs: list[int]


@dataclass(slots=True)
class CalendarRow:
    day: str
    what: str
    complex_name: str
    fact: Fact | None


@dataclass(slots=True)
class ChecklistRow:
    kind: str
    title: str
    complex_name: str
    due: str | None
    status: str
    note: str | None


@dataclass(slots=True)
class FailedSource:
    url: str
    source_kind: str
    status: str
    complex_name: str
    fetched_at: str


@dataclass(slots=True)
class RefRow:
    url: str
    kind: str
    complex_name: str
    checked_at: str
    result: str


@dataclass(slots=True)
class ChartSpec:
    id: str
    title: str
    subtitle: str
    option: dict[str, Any]
    columns: list[str]
    rows: list[list[Any]]  # 셀 = Fact 또는 문자열
    height: int = 360


@dataclass(slots=True)
class ExtraView:
    base_snapshot_id: int
    base_asof: str
    added: list[str]
    removed: list[str]
    rank_rows: list[
        tuple[str, str, str, Fact | None, Fact | None]
    ]  # 이름, 이전 순위, 현재 순위, 이전·현재 점수
    rerank_prev_seq: int | None
    rerank_seq: int | None
    summary: str


@dataclass(slots=True)
class ReportData:
    snapshot_id: int
    asof_date: str
    snapshot_status: str
    degraded: bool
    published_at: str | None
    region_name: str
    region_query: str
    living_areas: list[dict[str, Any]]
    contract_version: str
    generated_at: str
    scenario_code: str
    scenario_name: str
    weights: dict[str, float]
    complexes: list[ComplexView]
    regulation_rows: list[dict[str, Any]]
    adapter_versions: list[str]
    judge_tools: list[JudgeToolRow]
    total_calls: int
    classify_rows: list[ClassifyRow]
    excluded: list[ComplexView]
    stage_counts: list[dict[str, Any]]
    benchmarks: list[BenchmarkView]
    recent_sale_cases: dict[str, bool]
    catalysts: list[CatalystView]
    conflicts: list[ConflictView]
    supply: list[SupplyView]
    unsold: list[UnsoldView]
    ladders: list[LadderView]
    ladder_other: dict[int, list[LadderView]]
    rerank_seq: int | None
    rerank_rows: list[tuple[str, Fact, Fact]]
    scores: list[ScoreView]
    top5: list[ScoreView]
    scenarios: list[ScenarioBlock]
    checklist: list[ChecklistRow]
    calendar: list[CalendarRow]
    claims: list[ClaimRow]
    verify: list[VerifySummary]
    failed_sources: list[FailedSource]
    label_counts: dict[str, int]
    unresolved_calls: list[CallRow]
    calls: list[CallRow]
    references: list[RefRow]
    invalid_urls: list[RefRow]
    changes: list[dict[str, str]]
    charts: list[ChartSpec] = field(default_factory=list)
    extra: ExtraView | None = None
    complex_by_id: dict[int, ComplexView] = field(default_factory=dict)
    catalyst_links: dict[int, list[CatalystView]] = field(default_factory=dict)


# ------------------------------------------------------------------ 공통


def count_remaining_contradicted(session: Session, snapshot_id: int) -> list[Claim]:
    """남은 contradicted 주장 = 분할 재검증(자식 주장)이 없는 contradicted 행.

    T6: 복합 주장은 원자 주장으로 나눠 다시 검증한다 — 자식이 있으면 그 결과를 쓴다.
    """
    rows = list(session.scalars(select(Claim).where(Claim.snapshot_id == snapshot_id)))
    parents = {r.parent_claim_id for r in rows if r.parent_claim_id is not None}
    return [r for r in rows if r.verify_status == "contradicted" and r.id not in parents]


class _ProvIndex:
    """(entity, entity_id, field) → 채택(chosen) 출처 행."""

    def __init__(self, session: Session, keys: Mapping[str, Iterable[int]]) -> None:
        self._rows: dict[tuple[str, int, str], FieldProvenance] = {}
        self.all_rows: list[FieldProvenance] = []
        for entity, ids in keys.items():
            id_list = sorted(set(ids))
            for i in range(0, len(id_list), 500):
                chunk = id_list[i : i + 500]
                stmt = select(FieldProvenance).where(
                    FieldProvenance.entity == entity, FieldProvenance.entity_id.in_(chunk)
                )
                for row in session.scalars(stmt):
                    self.all_rows.append(row)
                    if row.entity_id is None or not row.chosen:
                        continue
                    key = (row.entity, row.entity_id, row.field)
                    if key not in self._rows or row.id < self._rows[key].id:
                        self._rows[key] = row

    def fact(self, entity: str, entity_id: int, fld: str, value: Any, unit: str | None = None) -> Fact:
        row = self._rows.get((entity, entity_id, fld))
        if row is None:
            if value is None:
                return unknown_fact("출처 누락", unit=unit)
            return unknown_fact("출처 누락", unit=unit)
        return make_fact(value, row.label, f"fp_{row.id}", row.checked_at, unit=unit, reason=row.reason)

    def row(self, entity: str, entity_id: int, fld: str) -> FieldProvenance | None:
        return self._rows.get((entity, entity_id, fld))


def _num(v: Decimal | int | None) -> float | int | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    return v


def _embedded_fact(obj: Any, unit: str) -> Fact | None:
    """json 컬럼 안의 Fact 모양 값(apply_dates 등). 모양이 아니면 None."""
    if isinstance(obj, dict) and "label" in obj and "v" in obj:
        try:
            f = Fact.model_validate(
                {k: obj.get(k) for k in ("v", "label", "reason", "prov", "checked_at", "unit")}
            )
        except ValueError:
            return None
        if f.unit is None:
            f = f.model_copy(update={"unit": unit})
        return f
    return None


def _ymd(s: str | None) -> date | None:
    if not s:
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    return date(int(m[1]), int(m[2]), int(m[3])) if m else None


def _short(text: str, n: int = 60) -> str:
    t = " ".join(text.split())
    return t if len(t) <= n else t[: n - 1] + "…"


def _thresholds(obj: Any) -> dict[str, Any]:
    """output_json 어디에 있든 'thresholds' 사전을 찾는다(JEV 응답 모양 차이 흡수)."""
    if isinstance(obj, dict):
        th = obj.get("thresholds")
        if isinstance(th, dict):
            return th
        for v in obj.values():
            found = _thresholds(v)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _thresholds(v)
            if found:
                return found
    return {}


# ------------------------------------------------------------------ 로더


class _Loader:
    def __init__(
        self,
        session: Session,
        snapshot: Snapshot,
        region: Region,
        scenario: Scenario,
        compare: Snapshot | None,
    ) -> None:
        self.s = session
        self.snap = snapshot
        self.region = region
        self.scenario = scenario
        self.compare = compare
        self.asof = snapshot.asof_date
        self.la_names = {str(la.get("id")): str(la.get("name")) for la in region.living_areas or []}
        self.prov = _ProvIndex(session, {})

    # -- 범위
    def scope_ids(self) -> list[int]:
        s, sid = self.s, self.snap.id
        ids: set[int] = set()
        runs = select(ScoreRun.id).where(ScoreRun.snapshot_id == sid)
        ids |= set(self.s.scalars(select(ScoreTotal.complex_id).where(ScoreTotal.score_run_id.in_(runs))))
        ids |= set(s.scalars(select(IntakeStatus.complex_id).where(IntakeStatus.snapshot_id == sid)))
        ids |= set(s.scalars(select(Ladder.complex_id).where(Ladder.snapshot_id == sid)))
        ids |= {
            c
            for c in s.scalars(select(JudgmentLog.complex_id).where(JudgmentLog.snapshot_id == sid))
            if c is not None
        }
        region_ids = set(s.scalars(select(Complex.id).where(Complex.region_id == self.region.id)))
        return sorted(ids & region_ids) if ids else sorted(region_ids)

    def la_name(self, la: str | None) -> str:
        return self.la_names.get(la or "", la or "생활권 미배정")

    # -- 단지
    def complexes(self, ids: list[int]) -> list[ComplexView]:
        s = self.s
        cxs = list(s.scalars(select(Complex).where(Complex.id.in_(ids)).order_by(Complex.id)))
        types = list(
            s.scalars(select(ComplexType).where(ComplexType.complex_id.in_(ids)).order_by(ComplexType.id))
        )
        pays = list(
            s.scalars(select(PaymentTerms).where(PaymentTerms.complex_id.in_(ids)).order_by(PaymentTerms.id))
        )
        comps = list(
            s.scalars(select(Competition).where(Competition.complex_id.in_(ids)).order_by(Competition.id))
        )
        events = list(
            s.scalars(
                select(RemainingEvent).where(RemainingEvent.complex_id.in_(ids)).order_by(RemainingEvent.id)
            )
        )
        intakes = list(
            s.scalars(
                select(IntakeStatus)
                .where(IntakeStatus.snapshot_id == self.snap.id, IntakeStatus.complex_id.in_(ids))
                .order_by(IntakeStatus.id)
            )
        )
        self.prov = _ProvIndex(
            s,
            {
                "complex": ids,
                "complex_type": [t.id for t in types],
                "payment_terms": [p.id for p in pays],
                "competition": [c.id for c in comps],
                "remaining_event": [e.id for e in events],
            },
        )
        P = self.prov
        out: list[ComplexView] = []
        for c in cxs:
            facts: dict[str, Fact] = {}
            for fld, unit in COMPLEX_UNITS.items():
                val: Any = getattr(c, fld)
                if fld == "resale_release_on_registration":
                    val = None if val is None else ("등기 시 해제" if val else "해제 조건 없음")
                facts[fld] = P.fact("complex", c.id, fld, val, unit)
            tviews = [
                TypeView(
                    type_code=t.type_code,
                    area=P.fact("complex_type", t.id, "area_m2", _num(t.area_m2), "m2"),
                    units=P.fact("complex_type", t.id, "units", t.units, "units"),
                    floor_price=P.fact(
                        "complex_type", t.id, "floor_sample_price_won", t.floor_sample_price_won, "won"
                    ),
                    max_price=P.fact("complex_type", t.id, "max_price_won", t.max_price_won, "won"),
                    balcony=P.fact("complex_type", t.id, "balcony_won", t.balcony_won, "won"),
                    options=P.fact(
                        "complex_type", t.id, "options_required_won", t.options_required_won, "won"
                    ),
                    options_text=t.options_text,
                    floor_text=t.floor_sample_text,
                    is_basis=False,
                )
                for t in types
                if t.complex_id == c.id
            ]
            my_types = [t for t in types if t.complex_id == c.id]
            basis_code = judge_type((t.type_code, t.area_m2) for t in my_types)
            basis = next((tv for tv in tviews if tv.type_code == basis_code), None)
            if basis is not None:
                basis.is_basis = True
            low, high = self._price(basis)
            my_pays = [p for p in pays if p.complex_id == c.id]
            latest = max((p.effective_from or "" for p in my_pays), default="")
            pviews = [
                PaymentView(
                    notice_no=p.notice_no,
                    notice_kind=p.notice_kind,
                    effective_from=P.fact("payment_terms", p.id, "effective_from", p.effective_from, "date"),
                    down_payment_pct=P.fact(
                        "payment_terms", p.id, "down_payment_pct", _num(p.down_payment_pct), "pct"
                    ),
                    down_payment_first=P.fact(
                        "payment_terms", p.id, "down_payment_first_won", p.down_payment_first_won, "won"
                    ),
                    interim_pct=P.fact("payment_terms", p.id, "interim_pct", _num(p.interim_pct), "pct"),
                    balance_pct=P.fact("payment_terms", p.id, "balance_pct", _num(p.balance_pct), "pct"),
                    interim_terms_text=p.interim_terms_text,
                    is_current=(p.effective_from or "") == latest,
                )
                for p in my_pays
            ]
            cviews = [
                CompetitionView(
                    round=k.round,
                    kind=k.kind,
                    type_code=k.type_code,
                    supply=P.fact("competition", k.id, "supply", k.supply, "units"),
                    applied=P.fact("competition", k.id, "applied", k.applied, "count"),
                    ratio_text=k.ratio_or_shortfall_text,
                )
                for k in comps
                if k.complex_id == c.id
            ]
            eviews = [
                EventView(
                    kind=e.kind,
                    notice_no=e.notice_no,
                    notice_date=P.fact("remaining_event", e.id, "notice_date", e.notice_date, "date"),
                    units_text=", ".join(f"{k} {v}" for k, v in (e.units_by_type or {}).items()),
                    ratio_text=e.ratio_text,
                    result_text=e.result_text,
                )
                for e in events
                if e.complex_id == c.id
            ]
            iviews = [
                IntakeView(
                    status=i.status,
                    path=i.path,
                    path_label=PATH_LABELS.get(i.path, i.path),
                    checked_at=i.checked_at,
                    http_status=i.http_status,
                    reason=i.reason,
                    evidence_url=i.evidence_url,
                    note=i.note,
                    used=False,
                )
                for i in intakes
                if i.complex_id == c.id
            ]
            shown = None
            for path in INTAKE_PRIORITY:
                cand = [i for i in iviews if i.path == path]
                if cand:
                    shown = max(cand, key=lambda i: i.checked_at)
                    shown.used = True
                    break
            incl_prob = (
                make_fact(
                    _num(c.inclusion_prob),
                    "추정",
                    f"jl_{c.inclusion_judgment_seq}",
                    self.asof,
                    unit="prob",
                    reason="판정기 classify",
                )
                if c.inclusion_judgment_seq is not None
                else unknown_fact("미판정", unit="prob")
            )
            out.append(
                ComplexView(
                    id=c.id,
                    name=c.name,
                    former_names=list(c.former_names or []),
                    address=c.address,
                    living_area=c.living_area,
                    living_area_name=self.la_name(c.living_area),
                    track=c.track,
                    developer=c.developer,
                    builder=c.builder,
                    official_site_url=c.official_site_url,
                    inclusion_class=c.inclusion_class,
                    inclusion_decision=c.inclusion_decision,
                    inclusion_prob=incl_prob,
                    facts=facts,
                    types=tviews,
                    basis=basis,
                    price_low=low,
                    price_high=high,
                    payments=pviews,
                    competition=cviews,
                    events=eviews,
                    intake=iviews,
                    intake_shown=shown,
                    date_facts=self._dates(c, my_pays),
                )
            )
        return out

    def _price(self, basis: TypeView | None) -> tuple[Fact, Fact]:
        """§6-1 현재 구매가(84㎡ 판정 타입): (대표층 ~ 최고가) + 발코니 + 필수 옵션. 더하면 '추정(산술)'."""
        if basis is None or basis.max_price.v is None:
            why = "판정 타입 없음" if basis is None else "최고가 확인 불가"
            return unknown_fact(why, unit="won"), unknown_fact(why, unit="won")
        b = int(basis.balcony.v or 0) if isinstance(basis.balcony.v, (int, float)) else 0
        o = int(basis.options.v or 0) if isinstance(basis.options.v, (int, float)) else 0
        floor = int(basis.floor_price.v) if isinstance(basis.floor_price.v, (int, float)) else None
        top = int(basis.max_price.v) if isinstance(basis.max_price.v, (int, float)) else 0
        pp = purchase_price(floor_won=floor, max_won=top, balcony_won=b, options_won=o)
        if b == 0 and o == 0:
            low_src = basis.floor_price if floor is not None else basis.max_price
            return low_src, basis.max_price
        reason = "산술: 공급금액 + 발코니 + 필수 옵션"
        lo_prov = (basis.floor_price if floor is not None else basis.max_price).prov
        return (
            make_fact(pp.low_won, "추정", lo_prov, basis.max_price.checked_at, unit="won", reason=reason),
            make_fact(
                pp.high_won,
                "추정",
                basis.max_price.prov,
                basis.max_price.checked_at,
                unit="won",
                reason=reason,
            ),
        )

    def _dates(self, c: Complex, pays: Sequence[PaymentTerms]) -> list[tuple[str, Fact]]:
        out: list[tuple[str, Fact]] = []
        for item in c.apply_dates or []:
            if isinstance(item, dict):
                kind = str(item.get("kind") or "접수")
                for k in ("start", "end"):
                    f = _embedded_fact(item.get(k), "date")
                    if f is not None and f.v is not None:
                        out.append((f"{kind} {'시작' if k == 'start' else '종료'}", f))
        for item in c.contract_dates or []:
            if isinstance(item, dict):
                for k in ("start", "end"):
                    f = _embedded_fact(item.get(k), "date")
                    if f is not None and f.v is not None:
                        out.append((f"계약 {'시작' if k == 'start' else '종료'}", f))
        for p in pays:
            for item in p.interim_schedule or []:
                if isinstance(item, dict):
                    f = _embedded_fact(item.get("due_date"), "date")
                    if f is not None and f.v is not None:
                        out.append((f"중도금 {item.get('seq', '')}회차".replace("  ", " "), f))
        return out

    # -- 판정 로그
    def calls(self) -> list[JudgmentLog]:
        snaps = select(Snapshot.id).where(
            Snapshot.region_id == self.region.id, Snapshot.asof_date <= self.asof
        )
        stmt = select(JudgmentLog).where(JudgmentLog.snapshot_id.in_(snaps)).order_by(JudgmentLog.seq)
        return list(self.s.scalars(stmt))


def _score_views(
    session: Session, run: ScoreRun | None, names: Mapping[int, str], la_names: Mapping[int, str]
) -> list[ScoreView]:
    if run is None:
        return []
    totals = list(session.scalars(select(ScoreTotal).where(ScoreTotal.score_run_id == run.id)))
    comps = list(session.scalars(select(ScoreComponent).where(ScoreComponent.score_run_id == run.id)))
    weights = {k: float(v) for k, v in (run.weights or {}).items() if v is not None}
    asof = run.created_at
    by_cx: dict[int, dict[str, ComponentView]] = defaultdict(dict)
    for c in comps:
        sc = c.score_0_10
        score = (
            make_fact(
                float(round_half_up(sc, 2)),
                c.label if c.label != "확인 불가" else "추정",
                f"sc_{c.id}",
                asof,
                unit="score",
                reason=c.reason,
            )
            if sc is not None
            else unknown_fact(c.reason or "미판정", unit="score")
        )
        raw = (
            make_fact(
                _num(c.raw_value),
                c.label if c.label != "확인 불가" else "추정",
                f"sc_{c.id}",
                asof,
                reason=c.reason,
            )
            if c.raw_value is not None
            else unknown_fact(c.reason or "원값 없음")
        )
        w = weights.get(c.component, 0.0)
        by_cx[c.complex_id][c.component] = ComponentView(
            key=c.component,
            label=COMPONENT_LABELS.get(c.component, c.component),
            score=score,
            raw=raw,
            weight=w,
            contribution=None if sc is None else float(Decimal(str(w)) * sc),
            formula_text=c.formula_text,
            reason=c.reason,
        )
    views: list[ScoreView] = []
    for t in totals:
        comps_cx = by_cx.get(t.complex_id, {})
        if t.total is None:
            total = unknown_fact("미판정", unit="score")
            missing = [v for v in comps_cx.values() if v.score.v is None]
            note = "미판정 — " + (missing[0].reason or missing[0].formula_text if missing else "성분 없음")
        else:
            total = make_fact(
                float(round_half_up(t.total, 2)), "추정", f"st_{t.id}", asof, unit="score", reason="가중 합"
            )
            note = "" if (t.rank or 99) <= 5 else f"{t.rank}위 — TOP 5 밖(상위 5위 경계 점수 미달)"
        views.append(
            ScoreView(
                complex_id=t.complex_id,
                name=names.get(t.complex_id, f"단지 {t.complex_id}"),
                living_area_name=la_names.get(t.complex_id, ""),
                total=total,
                total_raw=t.total,
                rank=t.rank,
                tie_group=t.tie_group,
                unstable=t.unstable,
                components={k: comps_cx[k] for k in COMPONENT_ORDER if k in comps_cx},
                note=_short(note, 90),
            )
        )
    views.sort(key=lambda v: (v.rank is None, v.rank or 0, -(v.total_raw or 0), v.complex_id))
    return views


def _latest_run(session: Session, snapshot_id: int, scenario_id: int) -> ScoreRun | None:
    stmt = (
        select(ScoreRun)
        .where(ScoreRun.snapshot_id == snapshot_id, ScoreRun.scenario_id == scenario_id)
        .order_by(ScoreRun.id.desc())
        .limit(1)
    )
    return session.scalars(stmt).first()


def _prob(
    v: Decimal | None, seq: int | None, asof: str, reason: str | None = None, *, missing: str | None = None
) -> Fact:
    """판정기 확률 → Fact(추정, jl_<seq>). 값이 없으면 '확인 불가(missing 또는 reason)'."""
    if v is None:
        return unknown_fact(missing or reason or "미판정", unit="prob")
    if seq is None:
        return unknown_fact("출처 누락", unit="prob")
    return make_fact(float(v), "추정", f"jl_{seq}", asof, unit="prob", reason=reason)


@dataclass(slots=True)
class _Ctx:
    session: Session
    snap: Snapshot
    region: Region
    loader: _Loader
    ids: list[int]
    complexes: list[ComplexView]
    by_id: dict[int, ComplexView]
    names: dict[int, str]
    asof: str


def _add_once(used: dict[int, list[str]], seq: int | None, where: str) -> None:
    if seq is not None and where not in used[seq]:
        used[seq].append(where)


def _used_in(
    ctx: _Ctx,
    ladders: Sequence[Ladder],
    decisions: Sequence[Decision],
    runs: Iterable[ScoreRun],
    claims: Sequence[Claim],
    catalysts: Sequence[Catalyst],
) -> dict[int, list[str]]:
    """judgment_seq → 반영 위치(부록 A '반영 위치' 열)."""
    used: dict[int, list[str]] = defaultdict(list)
    for lad in ladders:
        _add_once(used, lad.judgment_seq, f"§6 사다리({ctx.names.get(lad.complex_id, lad.complex_id)})")
    for dec in decisions:
        _add_once(used, dec.judgment_seq, "§8 상황별 결정")
    for run in runs:
        _add_once(used, run.rerank_judgment_seq, "§6 종합 점수(rerank)")
    for cl in claims:
        _add_once(used, cl.judgment_seq, f"검증 {cl.section}")
    for cat in catalysts:
        _add_once(used, cat.judgment_seq, "§5 호재 단계")
    for cx in ctx.session.scalars(select(Complex).where(Complex.region_id == ctx.region.id)):
        _add_once(used, cx.inclusion_judgment_seq, "§3 포함 분류")
    for prov in ctx.loader.prov.all_rows:
        _add_once(used, prov.compare_judgment_seq, "§5 출처 충돌")
    return used


def _summaries(j: JudgmentLog) -> tuple[str, str]:
    """입력 요약(길이 + 짧은 문구)·결과 요약. payload 원문 전체는 싣지 않는다."""
    payload = j.input_json or {}
    summary = ""
    for key in ("input_summary", "situation", "query", "text"):
        if isinstance(payload.get(key), str):
            summary = payload[key]
            break
    if not summary and isinstance(payload.get("candidates"), list):
        summary = f"후보 {len(payload['candidates'])}개"
    out = j.output_json or {}
    rsum = j.status
    for key in ("verdict", "overall", "decision", "selected", "reason"):
        if isinstance(out.get(key), str):
            rsum = f"{j.status} · {key}={out[key]}"
            break
    return _short(f"[{j.input_len or 0}자] {summary}", 70), _short(rsum, 50)


def _calls(
    ctx: _Ctx, logs: Sequence[JudgmentLog], used: Mapping[int, list[str]]
) -> tuple[list[CallRow], list[JudgeToolRow], list[str]]:
    calls: list[CallRow] = []
    tool_counts: dict[str, Counter[str]] = defaultdict(Counter)
    tool_th: dict[str, dict[str, Any]] = {}
    versions: list[str] = []
    for j in logs:
        tool_counts[j.tool][j.status] += 1
        th = _thresholds(j.output_json)
        if th:
            tool_th.setdefault(j.tool, {}).update(th)
        if j.adapter_version not in versions:
            versions.append(j.adapter_version)
        inp, res = _summaries(j)
        calls.append(
            CallRow(
                seq=j.seq,
                snapshot_id=j.snapshot_id,
                tool=j.tool,
                purpose=j.purpose,
                complex_name=ctx.names.get(j.complex_id, "—") if j.complex_id else "—",
                status=j.status,
                confidence=_prob(j.confidence, j.seq, j.created_at, missing="판정기 미제공"),
                input_summary=inp,
                result_summary=res,
                used_in=", ".join(used.get(j.seq, [])) or "기록만(직접 반영 없음)",
                created_at=j.created_at[:10],
            )
        )
    tools = [
        JudgeToolRow(
            tool=t,
            calls=sum(tool_counts[t].values()),
            by_status=dict(tool_counts[t]),
            thresholds=", ".join(f"{k} {v}" for k, v in sorted(tool_th.get(t, {}).items()))
            or "응답에 임계값 없음",
            section=JUDGMENT_SECTIONS.get(t, ""),
        )
        for t in ("screen", "extract", "audit", "classify", "compare", "noul", "rerank", "decide", "verify")
        if t in tool_counts
    ]
    return calls, tools, versions


def _market(ctx: _Ctx) -> tuple[list[BenchmarkView], dict[str, bool], list[SupplyView], list[UnsoldView]]:
    s, rid = ctx.session, ctx.region.id
    benches = list(s.scalars(select(Benchmark).where(Benchmark.region_id == rid).order_by(Benchmark.id)))
    supplies = list(
        s.scalars(select(Supply).where(Supply.region_id == rid).order_by(Supply.living_area, Supply.year))
    )
    unsolds = list(
        s.scalars(select(Unsold).where(Unsold.region_id == rid).order_by(Unsold.scope_code, Unsold.ym))
    )
    mp = _ProvIndex(
        s,
        {
            "benchmark": [b.id for b in benches],
            "supply": [x.id for x in supplies],
            "unsold": [u.id for u in unsolds],
        },
    )
    asof_year = int(ctx.asof[:4])
    views: list[BenchmarkView] = []
    recent: dict[str, bool] = {}
    for b in benches:
        sale = mp.fact("benchmark", b.id, "sale_price_84_won", b.sale_price_84_won, "won")
        med = mp.fact("benchmark", b.id, "trade_median_won", b.trade_median_won, "won")
        if b.sale_price_84_won and b.trade_median_won and med.prov:
            pct = (Decimal(b.trade_median_won) / Decimal(b.sale_price_84_won) - 1) * 100
            change = make_fact(
                float(round_half_up(pct, 1)),
                "추정",
                med.prov,
                med.checked_at,
                unit="pct",
                reason="산술: 실거래 중앙값 ÷ 분양가 − 1",
            )
        else:
            change = unknown_fact("분양가 또는 실거래 없음", unit="pct")
        la = ctx.loader.la_name(b.living_area)
        views.append(
            BenchmarkView(
                living_area_name=la,
                name=b.name,
                completed_year=mp.fact("benchmark", b.id, "completed_year", b.completed_year, "year"),
                sale_year=mp.fact("benchmark", b.id, "sale_year", b.sale_year, "year"),
                sale_price=sale,
                trade_median=med,
                change_pct=change,
                is_presale=b.is_presale,
            )
        )
        has_case = not b.is_presale and b.sale_year is not None and bool(b.trade_median_won)
        recent[la] = recent.get(la, False) or (has_case and (b.sale_year or 0) >= asof_year - 3)
    sviews = [
        SupplyView(
            living_area_name=ctx.loader.la_name(x.living_area),
            year=x.year,
            units=mp.fact("supply", x.id, "units", x.units, "units"),
        )
        for x in supplies
    ]
    uviews = [
        UnsoldView(
            scope=u.scope_name or u.scope_code or "지역 합계",
            ym=u.ym,
            total=mp.fact("unsold", u.id, "total", u.total, "units"),
            post_completion=mp.fact("unsold", u.id, "post_completion", u.post_completion, "units"),
        )
        for u in unsolds
    ]
    return views, recent, sviews, uviews


def _catalysts(
    ctx: _Ctx, catalysts: Sequence[Catalyst]
) -> tuple[list[CatalystView], list[dict[str, Any]], dict[int, list[CatalystView]]]:
    views = [
        CatalystView(
            name=cat.name,
            kind=cat.kind,
            stage=cat.stage,
            prob=_prob(cat.stage_prob, cat.judgment_seq, ctx.asof, "판정기 classify"),
            decision=cat.decision,
            unresolved=cat.decision not in (None, "auto") or cat.stage == "미확정",
            note=cat.note,
        )
        for cat in catalysts
    ]
    stages = [
        {"stage": st, "n": sum(1 for v in views if v.stage == st)}
        for st in ("확정", "계획", "추진", "언론", "미확정")
    ]
    by_id = {cat.id: v for cat, v in zip(catalysts, views, strict=True)}
    links: dict[int, list[CatalystView]] = defaultdict(list)
    for link in ctx.session.scalars(select(CatalystLink).where(CatalystLink.complex_id.in_(ctx.ids))):
        if link.catalyst_id in by_id:
            links[link.complex_id].append(by_id[link.catalyst_id])
    return views, stages, dict(links)


def _conflicts(ctx: _Ctx, seq_status: Mapping[int, str]) -> list[ConflictView]:
    owner: dict[tuple[str, int], int] = {("complex", cid): cid for cid in ctx.ids}
    for t in ctx.session.scalars(select(ComplexType).where(ComplexType.complex_id.in_(ctx.ids))):
        owner[("complex_type", t.id)] = t.complex_id
    for pt in ctx.session.scalars(select(PaymentTerms).where(PaymentTerms.complex_id.in_(ctx.ids))):
        owner[("payment_terms", pt.id)] = pt.complex_id
    groups: dict[str, list[FieldProvenance]] = defaultdict(list)
    for prov in ctx.loader.prov.all_rows:
        if prov.conflict_group:
            groups[prov.conflict_group].append(prov)
    out: list[ConflictView] = []
    for group, rows in sorted(groups.items()):
        chosen = next((r for r in rows if r.chosen), rows[0])
        cid = owner.get((chosen.entity, chosen.entity_id or 0))
        seq = next((r.compare_judgment_seq for r in rows if r.compare_judgment_seq is not None), None)
        out.append(
            ConflictView(
                complex_name=ctx.by_id[cid].name if cid in ctx.by_id else "—",
                group=group,
                chosen_text=chosen.value_text or "",
                chosen_label=chosen.label,
                others=[f"{r.value_text} [{r.label}]" for r in rows if r is not chosen],
                compare_seq=seq,
                compare_status=seq_status.get(seq) if seq is not None else None,
            )
        )
    return out


def _ladder_views(
    ctx: _Ctx, ladders: Sequence[Ladder]
) -> tuple[list[LadderView], dict[int, list[LadderView]]]:
    main: list[LadderView] = []
    other: dict[int, list[LadderView]] = defaultdict(list)
    for lad in sorted(ladders, key=lambda x: (x.complex_id, x.horizon)):
        why = None if lad.status == "ok" else f"판정 {lad.status}(미해결)"
        view = LadderView(
            complex_id=lad.complex_id,
            name=ctx.names.get(lad.complex_id, str(lad.complex_id)),
            horizon=lad.horizon,
            horizon_label=HORIZON_LABELS.get(lad.horizon, lad.horizon),
            target_ym=lad.target_ym,
            status=lad.status,
            p5=_prob(lad.p5, lad.judgment_seq, ctx.asof, why, missing=why),
            p10=_prob(lad.p10, lad.judgment_seq, ctx.asof, why, missing=why),
            p20=_prob(lad.p20, lad.judgment_seq, ctx.asof, why, missing=why),
            p_flat=_prob(lad.p_flat, lad.judgment_seq, ctx.asof, why, missing=why),
            verdict_p10=(lad.verdicts or {}).get("p10"),
            proposition=lad.proposition_text,
            judgment_seq=lad.judgment_seq,
        )
        if lad.horizon == "move_in_plus_1y":
            main.append(view)
        else:
            other[lad.complex_id].append(view)
    return main, dict(other)


def _decision_view(d: Decision, names: Mapping[int, str], asof: str) -> DecisionView:
    return DecisionView(
        option=names.get(d.complex_id, str(d.complex_id))
        if d.complex_id is not None
        else OPTION_LABELS.get(d.option_key, d.option_key),
        complex_id=d.complex_id,
        prob=_prob(d.prob, d.judgment_seq, asof, missing="판정기 확률 미기재"),
        chosen=d.chosen,
        tie=d.tie,
        mismatch=d.mismatch,
        pre={"access": d.req_access_pre, "regulation": d.req_regulation_pre, "funds": d.req_funds_pre},
        judge={
            "access": d.req_access_judge,
            "regulation": d.req_regulation_judge,
            "funds": d.req_funds_judge,
        },
    )


def _scenario_blocks(
    ctx: _Ctx,
    scenarios: Sequence[Scenario],
    runs: Mapping[int, ScoreRun],
    decisions: Sequence[Decision],
    seq_status: Mapping[int, str],
    la_of: Mapping[int, str],
) -> list[ScenarioBlock]:
    blocks: list[ScenarioBlock] = []
    for sc in scenarios:
        run = runs.get(sc.id)
        if run is None:
            continue
        views = _score_views(ctx.session, run, ctx.names, la_of)
        mine = [d for d in decisions if d.score_run_id == run.id]

        def order(v: DecisionView) -> tuple[bool, float]:
            return (not v.chosen, -(float(v.prob.v) if isinstance(v.prob.v, (int, float)) else -1.0))

        dviews = sorted((_decision_view(d, ctx.names, ctx.asof) for d in mine), key=order)
        seq = mine[0].judgment_seq if mine else None
        conf = mine[0].confidence if mine else None
        blocks.append(
            ScenarioBlock(
                code=sc.code or str(sc.id),
                name=sc.name,
                weights={k: float(v) for k, v in (run.weights or {}).items() if v is not None},
                top=[v for v in views if v.rank is not None and v.rank <= 5],
                decisions=dviews,
                confidence=_prob(conf, seq, ctx.asof, missing="decide 없음" if not mine else "판정기 미제공"),
                status=seq_status.get(seq) if seq is not None else None,
                warnings=list(mine[0].warnings or []) if mine else [],
                judgment_seq=seq,
                tie=any(d.tie for d in mine),
            )
        )
    return blocks


def _checklist_calendar(ctx: _Ctx) -> tuple[list[ChecklistRow], list[CalendarRow]]:
    items = ctx.session.scalars(
        select(ChecklistItem)
        .where(ChecklistItem.complex_id.in_(ctx.ids) | ChecklistItem.complex_id.is_(None))
        .order_by(ChecklistItem.due_date, ChecklistItem.id)
    )
    checklist = [
        ChecklistRow(
            kind=i.kind,
            title=i.title,
            complex_name=ctx.names.get(i.complex_id, "지역 공통") if i.complex_id else "지역 공통",
            due=i.due_date,
            status=i.status,
            note=i.note,
        )
        for i in items
    ]
    start = _ymd(ctx.asof) or date.today()
    end = start + relativedelta(months=3)
    calendar: list[CalendarRow] = []
    for cx in ctx.complexes:
        for what, f in cx.date_facts:
            day = _ymd(str(f.v))
            if day is not None and start <= day <= end:
                calendar.append(CalendarRow(day=str(f.v), what=what, complex_name=cx.name, fact=f))
    for row in checklist:
        due = _ymd(row.due)
        if due is not None and start <= due <= end:
            calendar.append(
                CalendarRow(
                    day=row.due or "",
                    what=f"[{row.kind}] {row.title}",
                    complex_name=row.complex_name,
                    fact=None,
                )
            )
    calendar.sort(key=lambda r: r.day)
    return checklist, calendar


def _claims(claims: Sequence[Claim]) -> tuple[list[ClaimRow], list[VerifySummary]]:
    parents = {c.parent_claim_id for c in claims if c.parent_claim_id is not None}
    rows = [
        ClaimRow(
            section=c.section,
            text=c.text,
            status=c.verify_status,
            judgment_seq=c.judgment_seq,
            split=c.id in parents,
        )
        for c in claims
    ]
    summary: dict[str, VerifySummary] = {}
    for c in claims:
        v = summary.setdefault(c.section, VerifySummary(section=c.section, counts={}, judgment_seqs=[]))
        st = "contradicted→분할 재검증" if c.id in parents else (c.verify_status or "미검증")
        v.counts[st] = v.counts.get(st, 0) + 1
        if c.judgment_seq is not None and c.judgment_seq not in v.judgment_seqs:
            v.judgment_seqs.append(c.judgment_seq)
    return rows, sorted(summary.values(), key=lambda v: v.section)


def _failed_sources(ctx: _Ctx, docs: Sequence[RawDocument]) -> list[FailedSource]:
    failed = [
        FailedSource(
            url=d.url,
            source_kind=d.source_kind,
            status=f"HTTP {d.http_status}" if d.http_status else (d.error_text or "실패"),
            complex_name=ctx.names.get(d.complex_id, "—") if d.complex_id else "—",
            fetched_at=d.fetched_at[:10],
        )
        for d in docs
        if (d.http_status is not None and d.http_status >= 400) or (d.http_status is None and d.error_text)
    ]
    for cx in ctx.complexes:
        for i in cx.intake:
            if i.status == "확인 불가" and i.evidence_url and all(f.url != i.evidence_url for f in failed):
                failed.append(
                    FailedSource(
                        url=i.evidence_url,
                        source_kind="official_site",
                        status=i.text,
                        complex_name=cx.name,
                        fetched_at=i.checked_at[:10],
                    )
                )
    return failed


def _references(
    ctx: _Ctx, docs: Sequence[RawDocument], catalysts: Sequence[Catalyst]
) -> tuple[list[RefRow], list[RefRow]]:
    """부록 B: 원문·출처·공식 홈페이지·접수 근거·호재 URL 전수(중복 제거). 형식 오류는 따로(§9)."""
    refs: dict[str, RefRow] = {}

    def add(url: str | None, kind: str, cname: str, checked: str, result: str) -> None:
        if url and url not in refs:
            refs[url] = RefRow(url=url, kind=kind, complex_name=cname, checked_at=checked[:10], result=result)

    for d in docs:
        res = f"HTTP {d.http_status}" if d.http_status else (d.error_text or "응답 없음")
        add(
            d.url, d.source_kind, ctx.names.get(d.complex_id, "—") if d.complex_id else "—", d.fetched_at, res
        )
    for prov in ctx.loader.prov.all_rows:
        add(prov.url, f"출처({prov.entity}.{prov.field})", "—", prov.checked_at or "", prov.label)
    for cx in ctx.complexes:
        add(
            cx.official_site_url,
            "공식 홈페이지",
            cx.name,
            ctx.asof,
            cx.intake_shown.text if cx.intake_shown else "—",
        )
        for i in cx.intake:
            add(i.evidence_url, f"접수 상태({i.path_label})", cx.name, i.checked_at, i.text)
    for cat in catalysts:
        add(cat.source_url, "호재", "—", ctx.asof, cat.stage)
    valid = sorted((r for r in refs.values() if is_valid_url(r.url)), key=lambda r: (r.kind, r.url))
    return valid, [r for r in refs.values() if not is_valid_url(r.url)]


def _changes(ctx: _Ctx) -> list[dict[str, str]]:
    stmt = select(ChangeEvent).where(ChangeEvent.snapshot_id == ctx.snap.id).order_by(ChangeEvent.id)
    return [
        {
            "detected_at": e.detected_at[:10],
            "entity": e.entity,
            "field": e.field,
            "old": e.old_text or "",
            "new": e.new_text or "",
            "severity": e.severity,
            "complex": ctx.names.get(e.complex_id, "—") if e.complex_id else "—",
        }
        for e in ctx.session.scalars(stmt)
    ]


def _resolve(
    session: Session, snapshot_id: int, scenario_id: int | None, compare_snapshot_id: int | None
) -> tuple[Snapshot, Region, Scenario, Snapshot | None]:
    snap = session.get(Snapshot, snapshot_id)
    if snap is None:
        raise ReportNotFound(f"스냅샷 {snapshot_id} 없음")
    blocked = count_remaining_contradicted(session, snapshot_id)
    if blocked:
        ids = ", ".join(str(c.id) for c in blocked[:10])
        raise ReportBlocked(
            f"스냅샷 {snapshot_id}에 contradicted 주장 {len(blocked)}건이 남아 있음(claim id {ids})"
        )
    region = session.get(Region, snap.region_id)
    if region is None:  # pragma: no cover - FK
        raise ReportNotFound(f"지역 {snap.region_id} 없음")
    if scenario_id is not None:
        scenario = session.get(Scenario, scenario_id)
    else:
        scenario = session.scalars(select(Scenario).where(Scenario.code == "base")).first()
    if scenario is None:
        raise ReportNotFound(f"시나리오 {scenario_id or 'base'} 없음")
    compare = None
    if compare_snapshot_id is not None:
        compare = session.get(Snapshot, compare_snapshot_id)
        if compare is None:
            raise ReportNotFound(f"비교 스냅샷 {compare_snapshot_id} 없음")
    return snap, region, scenario, compare


def load_report(
    session: Session,
    snapshot_id: int,
    *,
    scenario_id: int | None = None,
    compare_snapshot_id: int | None = None,
) -> ReportData:
    """보고서 데이터 모델. contradicted 주장이 남아 있으면 ``ReportBlocked``(파일을 만들기 전)."""
    snap, region, scenario, compare = _resolve(session, snapshot_id, scenario_id, compare_snapshot_id)
    loader = _Loader(session, snap, region, scenario, compare)
    ids = loader.scope_ids()
    complexes = loader.complexes(ids)
    names = {c.id: c.name for c in session.scalars(select(Complex).where(Complex.region_id == region.id))}
    ctx = _Ctx(
        session, snap, region, loader, ids, complexes, {c.id: c for c in complexes}, names, snap.asof_date
    )
    la_of = {c.id: c.living_area_name for c in complexes}

    by_la: dict[str, list[ComplexView]] = defaultdict(list)
    for cx in complexes:
        by_la[cx.living_area_name].append(cx)

    logs = loader.calls()
    seq_status = {j.seq: j.status for j in logs}
    scenarios = list(session.scalars(select(Scenario).order_by(Scenario.id)))
    runs = {sc.id: r for sc in scenarios if (r := _latest_run(session, snap.id, sc.id)) is not None}
    run = runs.get(scenario.id)
    ladders = list(session.scalars(select(Ladder).where(Ladder.snapshot_id == snap.id)))
    decisions = [
        d
        for r in runs.values()
        for d in session.scalars(select(Decision).where(Decision.score_run_id == r.id))
    ]
    claims = list(session.scalars(select(Claim).where(Claim.snapshot_id == snap.id).order_by(Claim.id)))
    catalysts = list(session.scalars(select(Catalyst).where(Catalyst.region_id == region.id)))
    docs = list(
        session.scalars(
            select(RawDocument).where(RawDocument.region_id == region.id).order_by(RawDocument.id)
        )
    )

    used = _used_in(ctx, ladders, decisions, runs.values(), claims, catalysts)
    calls, judge_tools, versions = _calls(ctx, logs, used)
    benchmarks, recent, supply, unsold = _market(ctx)
    cat_views, stage_counts, links = _catalysts(ctx, catalysts)
    ladder_views, ladder_other = _ladder_views(ctx, ladders)
    scores = _score_views(session, run, names, la_of)
    rerank_rows = sorted(
        (
            (s.name, s.components["rerank"].raw, s.components["rerank"].score)
            for s in scores
            if "rerank" in s.components
        ),
        key=lambda r: -(float(r[1].v) if isinstance(r[1].v, (int, float)) else -1.0),
    )
    checklist, calendar = _checklist_calendar(ctx)
    claim_rows, verify = _claims(claims)
    references, invalid = _references(ctx, docs, catalysts)
    label_counts = Counter(p.label for p in loader.prov.all_rows if p.chosen)

    data = ReportData(
        snapshot_id=snap.id,
        asof_date=snap.asof_date,
        snapshot_status=snap.status,
        degraded=snap.degraded,
        published_at=snap.published_at,
        region_name=region.name,
        region_query=region.query_text,
        living_areas=list(region.living_areas or []),
        contract_version=CONTRACT_VERSION,
        generated_at=now_kst().isoformat(timespec="seconds"),
        scenario_code=scenario.code or str(scenario.id),
        scenario_name=scenario.name,
        weights={
            k: float(v)
            for k, v in ((run.weights if run else scenario.weights) or {}).items()
            if v is not None
        },
        complexes=complexes,
        regulation_rows=[{"living_area": la, "complexes": cs} for la, cs in by_la.items()],
        adapter_versions=versions,
        judge_tools=judge_tools,
        total_calls=len(calls),
        classify_rows=[
            ClassifyRow(
                complex_id=cx.id,
                name=cx.name,
                inclusion_class=cx.inclusion_class,
                decision=cx.inclusion_decision,
                prob=cx.inclusion_prob,
                unresolved=cx.inclusion_decision not in (None, "auto"),
            )
            for cx in complexes
        ],
        excluded=[cx for cx in complexes if cx.inclusion_class != "private_sale_apt"],
        stage_counts=stage_counts,
        benchmarks=benchmarks,
        recent_sale_cases=recent,
        catalysts=cat_views,
        conflicts=_conflicts(ctx, seq_status),
        supply=supply,
        unsold=unsold,
        ladders=ladder_views,
        ladder_other=ladder_other,
        rerank_seq=run.rerank_judgment_seq if run else None,
        rerank_rows=rerank_rows,
        scores=scores,
        top5=[s for s in scores if s.rank is not None and s.rank <= 5],
        scenarios=_scenario_blocks(ctx, scenarios, runs, decisions, seq_status, la_of),
        checklist=checklist,
        calendar=calendar,
        claims=claim_rows,
        verify=verify,
        failed_sources=_failed_sources(ctx, docs),
        label_counts=dict(label_counts),
        unresolved_calls=[c for c in calls if c.status != "ok"],
        calls=calls,
        references=references,
        invalid_urls=invalid,
        changes=_changes(ctx),
        complex_by_id=ctx.by_id,
        catalyst_links=links,
    )
    if compare is not None:
        data.extra = _extra(session, data, compare, scenario, names)
    return data


def _extra(
    session: Session, data: ReportData, base: Snapshot, scenario: Scenario, names: Mapping[int, str]
) -> ExtraView:
    """§12 지역 추가·변경 장: 후보군 변화, rerank 재실행, 순위 변화 한 문단(meta §2-3)."""
    prev_run = _latest_run(session, base.id, scenario.id)
    prev = {v.complex_id: v for v in _score_views(session, prev_run, names, {})}
    cur = {v.complex_id: v for v in data.scores}
    added = sorted(names.get(i, str(i)) for i in set(cur) - set(prev))
    removed = sorted(names.get(i, str(i)) for i in set(prev) - set(cur))
    rank_rows: list[tuple[str, str, str, Fact | None, Fact | None]] = []
    for cid in sorted(set(cur) | set(prev), key=lambda i: (cur[i].rank or 99) if i in cur else 99):
        a, b = prev.get(cid), cur.get(cid)
        rank_rows.append(
            (
                names.get(cid, str(cid)),
                f"{a.rank}위" if a and a.rank else ("—" if a is None else "미판정"),
                f"{b.rank}위" if b and b.rank else ("—" if b is None else "미판정"),
                a.total if a else None,
                b.total if b else None,
            )
        )
    prev_top = [v.name for v in prev.values() if v.rank is not None and v.rank <= 5]
    cur_top = [v.name for v in data.top5]
    entered = [n for n in cur_top if n not in prev_top]
    left = [n for n in prev_top if n not in cur_top]
    summary = (
        f"{base.asof_date} 스냅샷 대비 후보 {len(prev)}개 → {len(cur)}개"
        f"(추가 {len(added)}, 제외 {len(removed)}). "
        f"rerank는 후보군 전체로 다시 실행했다(#{prev_run.rerank_judgment_seq if prev_run else '—'} → "
        f"#{data.rerank_seq or '—'}). TOP 5 진입: {', '.join(entered) or '없음'}; "
        f"이탈: {', '.join(left) or '없음'}. "
        f"종합 점수는 새 rerank 호출 값만 쓴다(§6-5 고정 앵커)."
    )
    return ExtraView(
        base_snapshot_id=base.id,
        base_asof=base.asof_date,
        added=added,
        removed=removed,
        rank_rows=rank_rows,
        rerank_prev_seq=prev_run.rerank_judgment_seq if prev_run else None,
        rerank_seq=data.rerank_seq,
        summary=summary,
    )

"""DB → 보고서 데이터 모델 (DECISIONS D4).

모든 수치는 ``Fact``(라벨·출처). 값이 있는데 출처 행이 없으면(T13, API ``FactMaker.missing`` 과 같은 규칙):
ENV=dev → ``ReportProvenanceMissing``, ENV=prod → 경고 로그 + '확인 불가(출처 누락)'.
판정 범위·현재 구매가·표시 접수 행은 ``app.reports.policy``
(= 공용 ``app.analysis.scope``·``price_view``)로만 계산한다.
사다리 행·p10 은 '판정 대상' 단지만 표시·집계한다(D9-1 참여 규칙 — API ``load_bundles`` 와 같음).
판정 범위·순위·총점·성분은 그 스냅샷 score_run 의 **저장값**(D10-1, ADR-8). 현재 사실로 계산한 범위가 저장값과
다르면 '재판정 필요' 배지만 단다(한 행에 섞지 않는다). 저장값이 없는 단지(점수 행 없음)만
현재 사실로 계산한다.

읽기만 한다(판정기·점수 계산 없음, ADR-11). 사실 테이블(complex 등)은 현재값, 파생 테이블(intake_status,
judgment_log, claim, score_*, ladder, decision)은 스냅샷별이다(RA §3). Fact.prov 접두어:
fp_=field_provenance, sc_=score_component, st_=score_total, jl_=judgment_log seq, rd_=raw_document.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Final
from urllib.parse import urlparse

from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.complex_input import masked
from app.analysis.price_view import labels_from
from app.core.contracts_gen import Fact
from app.core.logging import get_logger
from app.core.protocols import CONTRACT_VERSION
from app.core.settings import get_settings
from app.core.time import kst_day, now_kst
from app.facts_view import DEMOTION_REASON, DemotionOverlay, load_overlay
from app.models import (
    Catalyst,
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
from app.normalize.competition import display_type_codes
from app.reports.errors import ReportBlocked, ReportNotFound, ReportProvenanceMissing
from app.reports.fmt import MISSING_REASON, count_missing, make_fact, round_half_up, unknown_fact
from app.reports.policy import (
    JUDGE_SCOPE_TEXT,
    PriceView,
    current_price,
    current_terms,
    judge_scope,
    original_missing,
    pick_intake,
    scope_note,
    shows_ladder,
)

__all__ = [
    "COMPONENT_LABELS",
    "ReportData",
    "compare_problem",
    "count_remaining_contradicted",
    "is_valid_url",
    "load_report",
    "load_report_live",
    "report_living_areas",
    "report_payload_live",
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

log = get_logger("app.reports.data")


def is_valid_url(url: str | None) -> bool:
    if not url or not URL_RE.match(url):
        return False
    u = urlparse(url)
    return u.scheme in ("http", "https") and bool(u.netloc) and "." in (u.hostname or "")


# ------------------------------------------------------------------ 뷰 모델


@dataclass(slots=True)
class IntakeView:
    id: int
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
    def checked_day(self) -> str:
        """확인 날짜(KST, D14-6 — 'Z'·다른 오프셋 시각도 서울 달력 날짜)."""
        return kst_day(self.checked_at)

    @property
    def text(self) -> str:
        why = self.reason or (str(self.http_status) if self.http_status else None)
        if self.status == "확인 불가":
            return f"확인 불가({why or '사유 미기재'}, {self.checked_day})"
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
    judge_scope: str  # 표시 범위 = 스냅샷 저장값(score_total.judge_scope), 없으면 현재 사실로 계산(D10-1)
    judge_scope_text: str
    scope_reason: str = ""  # 범위 사유
    scope_note: str = ""  # '판정 범위: <표시 문구> — <사유>'(사다리·확률 자리 표시)
    scope_source: str = "현재 사실"  # '스냅샷 저장값' | '현재 사실'(저장값 없음)
    current_scope: str = ""  # 현재 사실로 계산한 범위(policy.judge_scope, D9-1)
    current_scope_text: str = ""
    current_reason: str = ""
    changed_after_run: bool = False
    """점수 실행 뒤 재판정을 부르는 변경(change_event triggers_rejudge — 단지·지역 단위)이 있었다(API 와 같은 규칙,
    R3 5차 minor: 보고서 '재판정 필요'가 범위가 같으면 바뀐 사실을 반영하지 않았다)."""

    @property
    def rejudge_needed(self) -> bool:
        """저장값과 현재 사실의 범위가 다르거나 점수 실행 뒤 재판정을 부르는 변경이 있었다(D10-1 '재판정 필요' 배지)."""
        return self.scope_source == "스냅샷 저장값" and (
            self.current_scope != self.judge_scope or self.changed_after_run
        )

    @property
    def rejudge_text(self) -> str:
        if self.current_scope == self.judge_scope and self.changed_after_run:
            return "재판정 필요 — 점수 실행 뒤 사실이 바뀌었다(가격·입주월·사람 확인·강등·생활권 등)"
        return f"재판정 필요 — 현재 사실로는 {self.current_scope_text}({self.current_reason})"

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
    unresolved: bool  # 판정 범위 '미해결'(classify review·manual_review·미분류)
    scope_text: str


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
    substitute: bool = False  # 생활권 자체 표본 0 → 지역 전체 표본 복사 행(D9-2, 추정)


@dataclass(slots=True)
class BenchmarkArea:
    """생활권 하나의 벤치마크(N-M3·N-M4): 자체 행·대체 행을 나눠 세고, 행이 없으면 사유."""

    living_area_name: str
    rows: list[BenchmarkView]
    own_n: int  # 자체 표본 행(대체 아님)
    substitute_n: int  # 지역 전체 대체 행(다른 생활권 표본의 복사 — 지역 집계에 다시 세지 않는다)
    recent: bool  # 최근 3년 분양분 사례(자체 행 기준, 자체 0 이면 대체 행 기준)
    empty_reason: str | None  # 행이 하나도 없을 때 '벤치마크 없음(사유)'


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
    virtual: bool  # 가상 후보 '모집공고 대기'(wait_new, 계약 .5)
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
    wait_new_evidence: str | None = None  # decide 입력의 [wait_new] 근거 블록(공고 예정 목록 요약)

    @property
    def has_wait_new(self) -> bool:
        return any(d.virtual for d in self.decisions)

    @property
    def picked(self) -> list[str]:
        """판정기 선택(동률이면 여럿)."""
        return [d.option for d in self.decisions if d.chosen]

    @property
    def runner_up(self) -> list[DecisionView]:
        """차순위: 선택되지 않은 후보 중 확률이 있는 것(확률 순, 최대 3)."""
        return [d for d in self.decisions if not d.chosen and isinstance(d.prob.v, (int, float))][:3]


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
    # D15-5: 12-1 순위표·TOP 5 를 생략한 사유(비교 기준 리비전에 이 시나리오 없음). None = 같은 시나리오끼리 비교함
    rank_note: str | None = None


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
    benchmark_areas: list[BenchmarkArea]
    catalysts: list[CatalystView]
    conflicts: list[ConflictView]
    supply: list[SupplyView]
    unsold: list[UnsoldView]
    ladders: list[LadderView]
    ladder_other: dict[int, list[LadderView]]
    ladder_scoped_out: list[ComplexView]  # 사다리 자리에 '판정 범위: …'를 쓰는 단지(점수 행·남은 사다리 행)
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
    """남은 contradicted 주장 — 정의는 ``app.judge.claims.remaining_contradicted`` 하나(WP7 publish 와 공용).

    분할 재검증(자식 주장)이 없는 contradicted 행(T6).
    """
    from app.judge.claims import remaining_contradicted

    return remaining_contradicted(session, snapshot_id)


class _ProvIndex:
    """(entity, entity_id, field) → 채택(chosen) 출처 행. ``env`` = Settings.env(출처 누락 처리)."""

    def __init__(self, session: Session, keys: Mapping[str, Iterable[int]], env: str = "dev") -> None:
        self.env = env
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
        # D11-3 강등 오버레이(API·파이프라인과 같은 ``app.facts_view``): 강등 중인 사실은 '확인 불가(검증
        # 모순)'
        self.overlay = DemotionOverlay()
        cx_ids = set(keys.get("complex", ()))
        if cx_ids:  # 강등은 단지 사실에만(시장 표·벤치마크 색인은 오버레이 없음)
            from app.facts_view import chosen_from_rows

            self.overlay = load_overlay(
                session,
                complex_ids=cx_ids,
                chosen=chosen_from_rows(r for r in self.all_rows if r.chosen),
            )

    def label(self, entity: str, entity_id: int, fld: str) -> str | None:
        """채택 출처 행 라벨(강등 중이면 None) — 할인 차감 판정(``price_view.labels_from``, D12-3)."""
        row = self._rows.get((entity, entity_id, fld))
        if row is None or self.overlay.is_demoted(entity, entity_id, fld):
            return None
        return row.label

    def fact(
        self,
        entity: str,
        entity_id: int,
        fld: str,
        value: Any,
        unit: str | None = None,
        *,
        prov_field: str | None = None,
    ) -> Fact:
        """DB 값 + 채택 출처 행 → Fact. ``prov_field`` = 출처 행 이름이 컬럼과 다를 때. 강등 중이면 '확인 불가(검증 모순)'."""
        name = prov_field or fld
        row = self._rows.get((entity, entity_id, name))
        if self.overlay.is_demoted(entity, entity_id, name):
            return unknown_fact(DEMOTION_REASON, unit=unit)
        if row is None:
            if value is None:
                return unknown_fact("값 없음", unit=unit)
            return self.missing(entity, entity_id, name, unit)
        return make_fact(value, row.label, f"fp_{row.id}", row.checked_at, unit=unit, reason=row.reason)

    def missing(self, entity: str, entity_id: int, fld: str, unit: str | None = None) -> Fact:
        """값은 있는데 출처 행이 없음(T13): dev = 예외, prod = 경고 로그 + '확인 불가(출처 누락)'."""
        detail = f"{entity} {entity_id} field {fld} has no field_provenance row ({MISSING_REASON})"
        # 저장본 계산 중(D14-8)이면 ENV 와 무관하게 라벨 + 건수(API ``FactMaker.missing`` 과 같은 규칙, R3 7차 minor 12)
        if not count_missing() and self.env == "dev":
            raise ReportProvenanceMissing(detail)
        log.warning(
            "%s: %s", MISSING_REASON, detail, extra={"entity": entity, "entity_id": entity_id, "field": fld}
        )
        return unknown_fact(MISSING_REASON, unit=unit)

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


def _date_text(raw: Any) -> str | None:
    """날짜 값(문자열 또는 Fact 모양)의 'YYYY-MM-DD' 부분."""
    v = raw.get("v") if isinstance(raw, dict) else raw
    return str(v)[:10] if v else None


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
        env: str = "dev",
    ) -> None:
        self.s = session
        self.env = env
        self.snap = snapshot
        self.region = region
        self.scenario = scenario
        self.compare = compare
        self.asof = snapshot.asof_date
        self.la_names = {str(la.get("id")): str(la.get("name")) for la in region.living_areas or []}
        self.prov = _ProvIndex(session, {}, env)

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
            self.env,
        )
        P = self.prov
        types_by: dict[int, list[ComplexType]] = defaultdict(list)
        for t in types:
            types_by[t.complex_id].append(t)
        pays_by: dict[int, list[PaymentTerms]] = defaultdict(list)
        for p in pays:
            pays_by[p.complex_id].append(p)
        comps_by: dict[int, list[Competition]] = defaultdict(list)
        for k in comps:
            comps_by[k.complex_id].append(k)
        events_by: dict[int, list[RemainingEvent]] = defaultdict(list)
        for e in events:
            events_by[e.complex_id].append(e)
        intakes_by: dict[int, list[IntakeStatus]] = defaultdict(list)
        for i in intakes:
            intakes_by[i.complex_id].append(i)
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
                for t in types_by.get(c.id, [])
            ]
            # 강등 중인 사실(D11-3)은 현재 구매가·판정 범위 계산에서도 빠진다(API ``load_bundles`` 와 같은
            # 오버레이)
            my_types = [masked(t, P.overlay.fields("complex_type", t.id)) for t in types_by.get(c.id, [])]
            my_pays = [masked(p, P.overlay.fields("payment_terms", p.id)) for p in pays_by.get(c.id, [])]
            view = current_price(my_types, my_pays, discount_label=labels_from(P.label))
            basis = next((tv for tv in tviews if tv.type_code == view.basis_type_code), None)
            if basis is not None:
                basis.is_basis = True
            low, high = self._price(view, my_pays, my_types)
            cur_terms = current_terms(my_pays)
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
                    is_current=cur_terms is not None and p.id == cur_terms.id,
                )
                for p in my_pays
            ]
            comp_shown = display_type_codes(types_by.get(c.id, []), comps_by.get(c.id, []))  # D23-2 표시 주택형
            cviews = [
                CompetitionView(
                    round=k.round,
                    kind=k.kind,
                    type_code=comp_shown.get(k.id, k.type_code),
                    supply=P.fact("competition", k.id, "supply", k.supply, "units"),
                    applied=P.fact("competition", k.id, "applied", k.applied, "count"),
                    ratio_text=k.ratio_or_shortfall_text,
                )
                for k in comps_by.get(c.id, [])
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
                for e in events_by.get(c.id, [])
            ]
            my_intakes = intakes_by.get(c.id, [])
            shown_row = pick_intake(my_intakes)
            iviews = [
                IntakeView(
                    id=i.id,
                    status=i.status,
                    path=i.path,
                    path_label=PATH_LABELS.get(i.path, i.path),
                    checked_at=i.checked_at,
                    http_status=i.http_status,
                    reason=i.reason,
                    evidence_url=i.evidence_url,
                    note=i.note,
                    used=shown_row is not None and i.id == shown_row.id,
                )
                for i in my_intakes
            ]
            shown = next((i for i in iviews if i.used), None)
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
            scope = judge_scope(
                inclusion_class=c.inclusion_class,
                inclusion_decision=c.inclusion_decision,
                has_price=view.known,
                intake_status=shown_row.status if shown_row is not None else None,
                original_notice_missing=original_missing(c.applyhome_id, c.notice_date),
                address=c.address,
                legal_dong_code=c.legal_dong_code,
            )
            my_events = events_by.get(c.id, [])
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
                    date_facts=self._dates(c, my_pays, my_events),
                    judge_scope=scope.scope,
                    judge_scope_text=scope.text,
                    scope_reason=scope.reason,
                    scope_note=scope_note(scope.text, scope.reason),
                    current_scope=scope.scope,
                    current_scope_text=scope.text,
                    current_reason=scope.reason,
                )
            )
        return out

    def _price_demoted(self, view: PriceView, pays: Sequence[Any], types: Sequence[Any]) -> bool:
        """기준 타입 가격이 강등(검증 모순)으로 가려졌는가 — 공고문 타입 행 또는 현재 공고의 그 타입 가격(D11-3·D12-2)."""
        code = view.basis_type_code
        if code is None:
            return False
        ov = self.prov.overlay
        if any(ov.is_demoted("complex_type", t.id, "max_price_won") for t in types if t.type_code == code):
            return True
        cur = current_terms(pays)
        return cur is not None and ov.is_demoted(
            "payment_terms", cur.id, f"price_by_type.{code}.max_price_won"
        )

    def _price(
        self, view: PriceView, pays: Sequence[PaymentTerms], types: Sequence[Any] = ()
    ) -> tuple[Fact, Fact]:
        """§6-1 현재 구매가(84㎡ 판정 타입): (대표층 ~ 최고가) + 발코니 + 필수 옵션. 더하면 '추정(산술)'.

        값은 ``policy.current_price``(= ``analysis.price_view.current_price``) 하나 — 최신 공고
        price_by_type 우선, 없으면 complex_type. 라벨·출처는 그 값을 만든 필드(``FieldRef``)의 채택 출처 행.
        """
        if view.basis_type_code is None:
            why = "판정 타입 없음"
            return unknown_fact(why, unit="won"), unknown_fact(why, unit="won")
        if not view.known or view.max_ref is None:
            why = view.empty_reason or "최고가 확인 불가"
            if self._price_demoted(view, pays, types):
                why = DEMOTION_REASON  # R3 5차 minor: 강등된 가격은 API 와 같이 '검증 모순'(예전 '분양가 미공개')
            return unknown_fact(why, unit="won"), unknown_fact(why, unit="won")
        P = self.prov
        ref = view.max_ref
        max_f = P.fact(ref.entity, ref.entity_id, ref.field, ref.value, "won")
        if max_f.v is None:  # prod: 출처 누락 → '확인 불가(출처 누락)'
            return max_f, max_f
        floor_f = None
        if view.floor_ref is not None:
            fr = view.floor_ref
            floor_f = P.fact(fr.entity, fr.entity_id, fr.field, fr.value, "won")
            if floor_f.v is None:
                floor_f = None
        low_src = floor_f if floor_f is not None else max_f
        if len(view.composition) <= 1:  # 공급가만(발코니·옵션 없음)
            return low_src, max_f
        notice = next((p.notice_no for p in pays if p.id == view.terms_id), None) if view.from_terms else None
        supply = f"공급금액(공고 {notice})" if notice else "공급금액"
        parts = [supply]
        if "발코니" in view.composition:
            parts.append("발코니")
        if "옵션" in view.composition:
            parts.append("필수 옵션")
        reason = "산술: " + " + ".join(parts)
        if view.discount_applied and view.discount_ref is not None:  # 확인된 공고 할인만 뺐다(D11-6·D12-3)
            reason += f" − 할인 {int(view.discount_ref.value) // 10_000:,}만"
        low_won = view.low_won if floor_f is not None else view.high_won
        return (
            make_fact(low_won, "추정", low_src.prov, max_f.checked_at, unit="won", reason=reason),
            make_fact(view.high_won, "추정", max_f.prov, max_f.checked_at, unit="won", reason=reason),
        )

    def _dates(
        self, c: Complex, pays: Sequence[PaymentTerms], events: Sequence[RemainingEvent] = ()
    ) -> list[tuple[str, Fact]]:
        """캘린더 날짜. 저장 형태 전부를 읽는다(M14):

        - 정규화기: apply_dates ``[{kind, date}]``, contract_dates ``[{from, to}]``,
          interim_schedule ``[{seq, due_date: 'YYYY-MM-DD', pct}]`` — 값은 문자열, 출처는 필드 단위 행 하나
        - devseed: ``[{kind, start, end}]`` 문자열 / 녹화 픽스처: start·end·due_date 가 Fact 모양
        - remaining_event.apply_dates ``['YYYY-MM-DD', …]``
        """
        out: list[tuple[str, Fact]] = []

        def add(what: str, raw: Any, entity: str, eid: int, fld: str) -> None:
            f = _embedded_fact(raw, "date")
            if f is None:
                if not isinstance(raw, str) or _ymd(raw) is None:
                    return
                f = self.prov.fact(entity, eid, fld, raw[:10], "date")
            if f.v is not None:
                out.append((what, f))

        def span(item: Mapping[str, Any], name: str, entity: str, eid: int, fld: str) -> None:
            start = item.get("start") or item.get("date") or item.get("from")
            end = item.get("end") or item.get("to")
            if end is None or _date_text(end) == _date_text(start):
                add(name, start, entity, eid, fld)
            else:
                add(f"{name} 시작", start, entity, eid, fld)
                add(f"{name} 종료", end, entity, eid, fld)

        for item in c.apply_dates or []:
            if isinstance(item, dict):
                kind = str(item.get("kind") or "접수")
                span(item, kind if "청약" in kind else f"청약 {kind}", "complex", c.id, "apply_dates")
        for item in c.contract_dates or []:
            if isinstance(item, dict):
                span(item, str(item.get("kind") or "계약"), "complex", c.id, "contract_dates")
        for p in pays:
            for n, item in enumerate(p.interim_schedule or [], start=1):
                if isinstance(item, dict):
                    seq = item.get("seq") or n
                    add(f"중도금 {seq}회차", item.get("due_date"), "payment_terms", p.id, "interim_schedule")
        for e in events:
            for d in e.apply_dates or []:
                add(f"{e.kind} 접수", d, "remaining_event", e.id, "apply_dates")
        return out

    # -- 판정 로그
    def calls(self) -> list[JudgmentLog]:
        snaps = select(Snapshot.id).where(
            Snapshot.region_id == self.region.id, Snapshot.asof_date <= self.asof
        )
        stmt = select(JudgmentLog).where(JudgmentLog.snapshot_id.in_(snaps)).order_by(JudgmentLog.seq)
        return list(self.s.scalars(stmt))


def _score_views(
    session: Session,
    run: ScoreRun | None,
    names: Mapping[int, str],
    la_names: Mapping[int, str],
    *,
    copy: bool = True,
) -> list[ScoreView]:
    """점수 실행의 점수 행. 저장본 계산(``app.api.memo``) 안에서는 같은 실행·같은 이름이면 한 번만 만들고 얕은 사본을 돌려준다
    (시나리오 보고서마다 §8 상황별 블록이 실행 5개를 다시 만들었다 — D14-5 성능. 사본이라 ``_scope_notes`` 가 고쳐도 안전)."""
    if run is None:
        return []
    from app.api import memo

    if memo.store() is None:
        return _score_views_live(session, run, names, la_names)
    key = ("report_score_views", run.id, hash(frozenset(names.items())), hash(frozenset(la_names.items())))
    got = memo.cached(key, lambda: _score_views_live(session, run, names, la_names))
    if (
        not copy
    ):  # 읽기만 하는 곳(§8 상황별 TOP 5) — 같은 객체를 그대로(보고서 직렬화 메모도 같은 객체로 맞는다)
        return list(got)
    import dataclasses

    return [dataclasses.replace(v) for v in got]


def _score_views_live(
    session: Session, run: ScoreRun, names: Mapping[int, str], la_names: Mapping[int, str]
) -> list[ScoreView]:
    totals = list(session.scalars(select(ScoreTotal).where(ScoreTotal.score_run_id == run.id)))
    comps = list(session.scalars(select(ScoreComponent).where(ScoreComponent.score_run_id == run.id)))
    weights = {k: float(v) for k, v in (run.weights or {}).items() if v is not None}
    asof = run.created_at
    by_cx: dict[int, dict[str, ComponentView]] = defaultdict(dict)
    for c in comps:
        sc = c.score_0_10
        # R3 8차 minor 6: 점수 prov 는 API 출처 서랍 id 모양(sc_<실행>_<단지>_<성분>·st_<실행>_<단지>) — 행 id(sc_<성분 행>)는
        # 서랍이 없고 KPI st_<실행> 과 부딪혔다
        prov = f"sc_{run.id}_{c.complex_id}_{c.component}"
        score = (
            make_fact(
                float(round_half_up(sc, 2)),
                c.label if c.label != "확인 불가" else "추정",
                prov,
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
                prov,
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
                float(round_half_up(t.total, 2)),
                "추정",
                f"st_{run.id}_{t.complex_id}",
                asof,
                unit="score",
                reason="가중 합",
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


def _scope_notes(views: Sequence[ScoreView], by_id: Mapping[int, ComplexView]) -> None:
    """판정 대상이 아닌 단지의 점수 행에 판정 범위를 적는다(D9-1: 참고 = 순위만, 사다리 미실행)."""
    for v in views:
        cx = by_id.get(v.complex_id)
        if cx is None or cx.judge_scope == "판정 대상":
            continue
        v.note = _short(" · ".join(x for x in (cx.judge_scope_text, v.note) if x), 90)


def _stored_scopes(session: Session, run: ScoreRun | None) -> dict[int, str]:
    """그 스냅샷 점수 실행의 저장 범위(score_total.judge_scope, D10-1)."""
    if run is None:
        return {}
    stmt = select(ScoreTotal.complex_id, ScoreTotal.judge_scope).where(
        ScoreTotal.score_run_id == run.id, ScoreTotal.judge_scope.is_not(None)
    )
    return {cid: str(sc) for cid, sc in session.execute(stmt)}


def _apply_stored_scopes(
    complexes: Sequence[ComplexView], stored: Mapping[int, str], snapshot_id: int
) -> None:
    """표시 범위를 스냅샷 저장값으로(D10-1). 현재 사실 범위(current_*)는 '재판정 필요' 배지용으로만 남긴다."""
    for cx in complexes:
        value = stored.get(cx.id)
        if value is None:
            continue
        cx.judge_scope = value
        cx.judge_scope_text = next((t for k, t in JUDGE_SCOPE_TEXT.items() if k == value), value)
        cx.scope_source = "스냅샷 저장값"
        cx.scope_reason = (
            cx.current_reason if value == cx.current_scope else f"스냅샷 {snapshot_id} 점수 실행 저장값"
        )
        cx.scope_note = scope_note(cx.judge_scope_text, cx.scope_reason)


def _ladder_scoped_out(
    ctx: _Ctx, scores: Sequence[ScoreView], all_ladders: Sequence[Ladder]
) -> list[ComplexView]:
    """사다리 자리에 '판정 범위: <사유>'를 쓰는 단지.

    점수 행이 있거나 남은 사다리 행이 있는데 '판정 대상'이 아닌 것.

    순서 = 종합 점수 순, 그다음 단지 id."""
    order = [s.complex_id for s in scores] + sorted({lad.complex_id for lad in all_ladders})
    out: list[ComplexView] = []
    for cid in dict.fromkeys(order):
        cx = ctx.by_id.get(cid)
        if cx is not None and not shows_ladder(cx.judge_scope):
            out.append(cx)
    return out


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
        count_missing()
        return unknown_fact(MISSING_REASON, unit="prob")
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
    tool_th: dict[str, dict[str, list[Any]]] = {}
    versions: list[str] = []
    for j in logs:
        tool_counts[j.tool][j.status] += 1
        for k, v in _thresholds(j.output_json).items():
            seen = tool_th.setdefault(j.tool, {}).setdefault(str(k), [])
            if v not in seen:  # JEV 업데이트로 값이 바뀌면(D6) 누계 부록에 모두 적는다(호출 순)
                seen.append(v)
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
                created_at=kst_day(j.created_at),
            )
        )
    tools = [
        JudgeToolRow(
            tool=t,
            calls=sum(tool_counts[t].values()),
            by_status=dict(tool_counts[t]),
            thresholds=", ".join(
                f"{k} {' / '.join(str(v) for v in vals)}" for k, vals in sorted(tool_th.get(t, {}).items())
            )
            or "응답에 임계값 없음",
            section=JUDGMENT_SECTIONS.get(t, ""),
        )
        for t in ("screen", "extract", "audit", "classify", "compare", "noul", "rerank", "decide", "verify")
        if t in tool_counts
    ]
    return calls, tools, versions


def _year_fact(mp: _ProvIndex, bid: int, fld: str, value: int | None) -> Fact:
    """벤치마크 준공·분양 연도: 자기 출처 행, 없으면 같은 기록의 분양가 출처 행(한 출처의 한 단지 기록)."""
    own = mp.row("benchmark", bid, fld)
    return mp.fact("benchmark", bid, fld, value, "year", prov_field=None if own else "sale_price_84_won")


def _market(ctx: _Ctx) -> tuple[list[BenchmarkView], dict[str, bool], list[SupplyView], list[UnsoldView]]:
    s, rid = ctx.session, ctx.region.id
    # M-6: 그 스냅샷(리비전)이 인용하는 벤치마크만(``api.benchmarks.benchmarks_for`` — 파이프라인·API 와 같은
    # 함수). 지역 전체 행을 읽으면 다른 스냅샷·미래 조립분이 섞여 사례가 중복된다
    from app.api.benchmarks import benchmarks_for

    benches = benchmarks_for(s, ctx.snap)
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
        ctx.loader.env,
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
                completed_year=_year_fact(mp, b.id, "completed_year", b.completed_year),
                sale_year=_year_fact(mp, b.id, "sale_year", b.sale_year),
                sale_price=sale,
                trade_median=med,
                change_pct=change,
                is_presale=b.is_presale,
                substitute=bool(b.substitute),  # 계약 2026-10-09.7 benchmark.substitute(0007)
            )
        )
        has_case = not b.is_presale and b.sale_year is not None and bool(b.trade_median_won)
        if not views[-1].substitute:  # 대체 행은 원 생활권 사례 — 이 생활권 사례로 다시 세지 않는다(N-M4)
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


BENCHMARK_EMPTY_DEFAULT: Final = "생활권·지역 전체 분양 사례 0 — 벤치마크 성분 미계산(D9-2)"


def _benchmark_areas(
    ctx: _Ctx, views: Sequence[BenchmarkView], scores: Sequence[ScoreView], asof: str
) -> list[BenchmarkArea]:
    """생활권별 벤치마크 묶음 — 지역 생활권 전부(행 없는 생활권 포함, '벤치마크 없음(사유)' N-M3).

    사유 = 그 생활권 단지의 저장된 벤치마크 성분(score_component)이 미계산이면 그 산출식 문구,
    없으면 기본 문구.
    """
    names = [ctx.loader.la_name(str(la.get("id"))) for la in ctx.region.living_areas or []]
    names += [v.living_area_name for v in views if v.living_area_name not in names]
    asof_year = int(asof[:4])
    out: list[BenchmarkArea] = []
    for la in dict.fromkeys(names):
        rows = [v for v in views if v.living_area_name == la]
        own = [v for v in rows if not v.substitute]
        basis = own or rows
        recent = any(
            not v.is_presale
            and isinstance(v.sale_year.v, (int, float))
            and isinstance(v.trade_median.v, (int, float))
            and int(v.sale_year.v) >= asof_year - 3
            for v in basis
        )
        reason = None
        if not rows:
            comp = next(
                (
                    sv.components["benchmark"]
                    for sv in scores
                    if sv.living_area_name == la
                    and "benchmark" in sv.components
                    and sv.components["benchmark"].score.v is None
                ),
                None,
            )
            why = (comp.formula_text or comp.reason) if comp is not None else None
            reason = f"벤치마크 없음({why or BENCHMARK_EMPTY_DEFAULT})"
        out.append(
            BenchmarkArea(
                living_area_name=la,
                rows=rows,
                own_n=len(own),
                substitute_n=len(rows) - len(own),
                recent=recent,
                empty_reason=reason,
            )
        )
    return out


def _catalysts(
    ctx: _Ctx, pairs: Sequence[tuple[Any, Sequence[Any]]]
) -> tuple[list[CatalystView], list[dict[str, Any]], dict[int, list[CatalystView]]]:
    """§5 호재(``facts_view.region_catalysts`` — 지금 단계·연결, '호재 아님' 제외; 발행 리비전은 저장본, D13-1)."""
    catalysts = [c for c, _ in pairs]
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
    wanted = set(ctx.ids)
    for cat, cat_links in pairs:
        for link in cat_links:
            if link.complex_id in wanted and cat.id in by_id:
                links[link.complex_id].append(by_id[cat.id])
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
        virtual=d.option_key == "wait_new",
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


WAIT_NEW_BLOCK: Final = re.compile(r"\[wait_new\][^\n]*\n?(.*?)(?=\n\n\[|\Z)", re.S)


def wait_new_evidence(input_json: Mapping[str, Any] | None) -> str | None:
    """decide 입력 evidence 의 ``[wait_new]`` 블록 본문(지역 (A) 트랙 공고 예정 목록 요약, 계약 .5).

    없으면 None.

    판정기에 보낸 입력 그대로(공개 정보) — 보고서가 다시 계산하지 않는다(스냅샷 저장값, D10-1)."""
    ev = (input_json or {}).get("evidence")
    if not isinstance(ev, str):
        return None
    m = WAIT_NEW_BLOCK.search(ev)
    body = m.group(1).strip() if m else ""
    return body or None


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
        views = _score_views(ctx.session, run, ctx.names, la_of, copy=False)
        mine = [d for d in decisions if d.score_run_id == run.id]

        def order(v: DecisionView) -> tuple[bool, float]:
            return (not v.chosen, -(float(v.prob.v) if isinstance(v.prob.v, (int, float)) else -1.0))

        dviews = sorted((_decision_view(d, ctx.names, ctx.asof) for d in mine), key=order)
        seq = mine[0].judgment_seq if mine else None
        conf = mine[0].confidence if mine else None
        log = ctx.session.get(JudgmentLog, seq) if seq is not None else None
        evidence = (
            wait_new_evidence(log.input_json)
            if log is not None and any(d.option_key == "wait_new" for d in mine)
            else None
        )
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
                wait_new_evidence=evidence,
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
            fetched_at=kst_day(d.fetched_at),
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
                        fetched_at=i.checked_day,
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
            refs[url] = RefRow(
                url=url, kind=kind, complex_name=cname, checked_at=kst_day(checked), result=result
            )

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
            "detected_at": kst_day(e.detected_at),
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
    # T15 생성 거부는 발행 리비전에도 그대로 건다(발행 때 0 을 확인했지만 거부 규칙은 보고서 쪽에서도 지킨다 — 저장본을 렌더할
    # 때도 같은 검사, 결과 바이트에는 영향 없음)
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


def report_living_areas(session: Session, region: Region) -> list[dict[str, Any]]:
    """§1-1 생활권(이름·법정동·세대수 Fact) — D21-7(R4 재시험 m-d): 세대수는 저장 json(지역 생성 때 null 일 수 있다)이
    아니라 API(``views.region_view``)와 같은 세대 현황 집계(``living_area.region_household_facts`` — 출처 = 세대 현황 원문
    ``rd_``)를 쓴다. 집계가 없으면 저장된 Fact 그대로."""
    from app.normalize.living_area import region_household_facts

    try:
        computed = region_household_facts(session, region)
    except Exception:  # 참조 표 없음 등 — 저장 json 그대로(보고서 생성을 막지 않는다)
        computed = {}
    out: list[dict[str, Any]] = []
    for a in region.living_areas or []:
        item = dict(a)
        hit = computed.get(str(a.get("id")))
        house = (hit or {}).get("households")
        if isinstance(house, dict) and house.get("label") != "확인 불가":
            item["households"] = house
            item["supply_ref_units"] = (hit or {}).get("supply_ref_units")
        out.append(item)
    return out


def load_report_live(
    session: Session,
    snapshot_id: int,
    *,
    scenario_id: int | None = None,
    cache: dict[Any, Any] | None = None,
    env: str | None = None,
) -> ReportData:
    """보고서 데이터 모델을 지금 사실로 적재한다(발행 전 리비전·발행 때 저장본 만들기 — D13-1). §12(extra)는 없다.
    contradicted 주장이 남아 있으면 ``ReportBlocked``(파일을 만들기 전). ``cache``(materialize — 시나리오만 다른 적재
    여러 번)는 시나리오와 무관한 단지 뷰를 한 번만 만든다(범위 표시는 시나리오마다 얕은 복사에 적용)."""
    import dataclasses

    snap, region, scenario, _compare = _resolve(session, snapshot_id, scenario_id, None)
    loader = _Loader(session, snap, region, scenario, None, env or get_settings().env)
    ids = loader.scope_ids()
    key = ("complexes", snap.id, tuple(ids))
    scenarios = list(session.scalars(select(Scenario).order_by(Scenario.id)))
    runs = {sc.id: r for sc in scenarios if (r := _latest_run(session, snap.id, sc.id)) is not None}
    run = runs.get(scenario.id)
    stored_scopes = _stored_scopes(session, run)
    changed = _changed_after_run(session, snap, run, ids)
    # 같은 계산(cache) 안에서 저장 범위·'재판정 필요'가 앞 시나리오와 같으면 그 시나리오의 단지 뷰를 그대로 쓴다(사본·범위
    # 적용·직렬화를 다시 하지 않는다 — D14-5 성능). 다르면 얕은 사본에 이 시나리오 범위를 적용한다
    view_key = (key, tuple(sorted(stored_scopes.items())), tuple(sorted(changed)))
    if cache is not None and ("cx_views", view_key) in cache:
        loader.prov = cache[("prov", snap.id)]
        complexes = cache[("cx_views", view_key)]
    else:
        if cache is not None and key in cache:
            loader.prov = cache[("prov", snap.id)]
            complexes = [dataclasses.replace(cv) for cv in cache[key]]
        else:
            complexes = loader.complexes(ids)
            if cache is not None:
                cache[key] = [dataclasses.replace(cv) for cv in complexes]
                cache[("prov", snap.id)] = loader.prov
        _apply_stored_scopes(complexes, stored_scopes, snap.id)
        for cv in complexes:
            cv.changed_after_run = cv.id in changed
        if cache is not None:
            cache[("cx_views", view_key)] = complexes
    names = {c.id: c.name for c in session.scalars(select(Complex).where(Complex.region_id == region.id))}
    ctx = _Ctx(
        session, snap, region, loader, ids, complexes, {c.id: c for c in complexes}, names, snap.asof_date
    )
    la_of = {c.id: c.living_area_name for c in complexes}

    by_la: dict[str, list[ComplexView]] = defaultdict(list)
    for cx in complexes:
        by_la[cx.living_area_name].append(cx)

    # 저장본 계산(cache — 시나리오만 다른 적재 여러 번): 시나리오와 무관한 부분은 한 번만 만든다(D14-5 성능). 범위에 따라
    # 달라질 수 있는 부분은 단지 범위 지문(sfp)이 같을 때만 다시 쓴다(시나리오 실행끼리 범위가 다르면 다시 계산)
    sfp = (tuple(ids), tuple((cv.id, cv.judge_scope) for cv in complexes))

    def part(name: str, scoped: bool, make: Callable[[], Any]) -> Any:
        if cache is None:
            return make()
        k = ("report_part", snap.id, name, sfp if scoped else None)
        if k not in cache:
            cache[k] = make()
        return cache[k]

    logs = part("logs", False, loader.calls)
    seq_status = {j.seq: j.status for j in logs}
    # D9-1 참여 규칙: 사다리는 '판정 대상'만. 다른 범위 단지의 남은 사다리 행(이전 범위의 판정·이월)은
    # 표(§6·§7·§8)·C1·부록 A 반영 위치 어디에도 쓰지 않는다(API ``views.load_bundles`` 와 같은 규칙).
    all_ladders = part(
        "ladders", False, lambda: list(session.scalars(select(Ladder).where(Ladder.snapshot_id == snap.id)))
    )
    ladders = [
        lad
        for lad in all_ladders
        if lad.complex_id in ctx.by_id and shows_ladder(ctx.by_id[lad.complex_id].judge_scope)
    ]
    decisions = [
        d
        for r in runs.values()
        for d in session.scalars(select(Decision).where(Decision.score_run_id == r.id))
    ]
    claims = part(
        "claims",
        False,
        lambda: list(session.scalars(select(Claim).where(Claim.snapshot_id == snap.id).order_by(Claim.id))),
    )
    from app.facts_view import region_catalysts

    # '호재 아님'은 §5 에 넣지 않는다(D11-2). 발행 리비전은 이 데이터가 저장된다(D13-1)
    cat_pairs = part("cat_pairs", False, lambda: region_catalysts(session, region.id))
    catalysts = [c for c, _ in cat_pairs]
    docs = part(
        "docs",
        False,
        lambda: list(
            session.scalars(
                select(RawDocument).where(RawDocument.region_id == region.id).order_by(RawDocument.id)
            )
        ),
    )

    used = part("used", True, lambda: _used_in(ctx, ladders, decisions, runs.values(), claims, catalysts))
    calls, judge_tools, versions = part("calls", True, lambda: _calls(ctx, logs, used))
    benchmarks, recent, supply, unsold = part("market", True, lambda: _market(ctx))
    cat_views, stage_counts, links = part("catalysts", True, lambda: _catalysts(ctx, cat_pairs))
    ladder_views, ladder_other = part("ladder_views", True, lambda: _ladder_views(ctx, ladders))
    scores = _score_views(session, run, names, la_of)
    _scope_notes(scores, ctx.by_id)
    scoped_out = _ladder_scoped_out(ctx, scores, all_ladders)
    rerank_rows = sorted(
        (
            (s.name, s.components["rerank"].raw, s.components["rerank"].score)
            for s in scores
            if "rerank" in s.components
        ),
        key=lambda r: -(float(r[1].v) if isinstance(r[1].v, (int, float)) else -1.0),
    )
    checklist, calendar = part("checklist", True, lambda: _checklist_calendar(ctx))
    claim_rows, verify = part("claim_rows", False, lambda: _claims(claims))
    references, invalid = part("references", True, lambda: _references(ctx, docs, catalysts))
    label_counts = part("labels", False, lambda: Counter(p.label for p in loader.prov.all_rows if p.chosen))
    conflicts = part("conflicts", True, lambda: _conflicts(ctx, seq_status))
    failed_sources = part("failed_sources", True, lambda: _failed_sources(ctx, docs))
    changes = part("changes", True, lambda: _changes(ctx))

    data = ReportData(
        snapshot_id=snap.id,
        asof_date=snap.asof_date,
        snapshot_status=snap.status,
        degraded=snap.degraded,
        published_at=snap.published_at,
        region_name=region.name,
        region_query=region.query_text,
        living_areas=part("living_areas", False, lambda: report_living_areas(session, region)),
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
                unresolved=cx.current_scope == "미해결",
                scope_text=cx.judge_scope_text,
            )
            for cx in complexes
        ],
        excluded=[cx for cx in complexes if cx.judge_scope == "제외"],
        stage_counts=stage_counts,
        benchmarks=benchmarks,
        recent_sale_cases=recent,
        benchmark_areas=_benchmark_areas(ctx, benchmarks, scores, snap.asof_date),
        catalysts=cat_views,
        conflicts=conflicts,
        supply=supply,
        unsold=unsold,
        ladders=ladder_views,
        ladder_other=ladder_other,
        ladder_scoped_out=scoped_out,
        rerank_seq=run.rerank_judgment_seq if run else None,
        rerank_rows=rerank_rows,
        scores=scores,
        top5=[s for s in scores if s.rank is not None and s.rank <= 5],
        scenarios=_scenario_blocks(ctx, scenarios, runs, decisions, seq_status, la_of),
        checklist=checklist,
        calendar=calendar,
        claims=claim_rows,
        verify=verify,
        failed_sources=failed_sources,
        label_counts=dict(label_counts),
        unresolved_calls=[c for c in calls if c.status != "ok"],
        calls=calls,
        references=references,
        invalid_urls=invalid,
        changes=changes,
        complex_by_id=ctx.by_id,
        catalyst_links=links,
    )
    return data


def report_payload_live(
    session: Session,
    snapshot_id: int,
    scenario_id: int,
    *,
    cache: dict[Any, Any] | None = None,
    env: str | None = None,
) -> dict[str, Any]:
    """저장본(D13-1 kind=report): 보고서 입력 데이터(태그 JSON) + §12 비교에 쓰는 후보군·rerank·단지 이름."""
    from app.reports.codec import encode_data

    data = load_report_live(session, snapshot_id, scenario_id=scenario_id, cache=cache, env=env)
    # 저장본의 생성 시각 = 발행 시각(같은 리비전을 다시 계산해도 같은 바이트). 보고서를 만들 때는 그때 시각으로 바꾼다(m4)
    data.generated_at = str(data.published_at or "")
    run = _latest_run(session, snapshot_id, scenario_id)
    memo = cache.setdefault("codec", {}) if cache is not None else None
    return {
        "data": encode_data(data, memo),
        "candidates": sorted(_candidates(session, run, {s.complex_id for s in data.scores})),
        "rerank_seq": run.rerank_judgment_seq if run is not None else None,
        "names": {
            str(c.id): c.name
            for c in session.scalars(
                select(Complex).where(
                    Complex.region_id
                    == select(Snapshot.region_id).where(Snapshot.id == snapshot_id).scalar_subquery()
                )
            )
        },
    }


def _payload(session: Session, snap: Snapshot, scenario: Scenario) -> dict[str, Any]:
    """발행 리비전 = 저장본, 그 밖 = 지금 적재(``snapshot_view.read``)."""
    from app import snapshot_view as sv

    got: dict[str, Any] = sv.read(session, snap, "report", scenario=scenario)
    return got


def load_report(
    session: Session,
    snapshot_id: int,
    *,
    scenario_id: int | None = None,
    compare_snapshot_id: int | None = None,
) -> ReportData:
    """보고서 데이터 모델. 발행 리비전은 발행 때 저장한 입력 데이터(D13-1 — 이후 사실·강등·사람 확인·생활권·호재·
    지역 이름 변경이 옛 보고서를 바꾸지 않는다), 발행 전이면 지금 적재. §12(``compare_snapshot_id``)는 두 리비전의
    입력 데이터(저장본)로 계산한다. 발행 전 리비전에 contradicted 주장이 남아 있으면 ``ReportBlocked``."""
    from app.reports.codec import decode_data

    snap, _region, scenario, compare = _resolve(session, snapshot_id, scenario_id, compare_snapshot_id)
    payload = _payload(session, snap, scenario)
    data: ReportData = decode_data(payload["data"])
    # R3 6차 m4: '생성 시각'은 보고서를 만드는 지금이다(저장본의 계산 시각을 그대로 쓰지 않는다)
    data.generated_at = now_kst().isoformat(timespec="seconds")
    if compare is not None:
        base_payload, same_scenario = compare_payload(session, compare, scenario)
        data.extra = _extra(data, payload, base_payload, compare, same_scenario=same_scenario)
    return data


def compare_payload(session: Session, compare: Snapshot, scenario: Scenario) -> tuple[dict[str, Any], bool]:
    """§12 비교 기준 입력과 '같은 시나리오인가'(D14-3·D15-5): 같은 시나리오 저장본(True), 그 리비전에 그 시나리오가
    없으면(발행 뒤 만든 사용자 시나리오) 기본 시나리오(False) — §12 후보 건수 비교는 시나리오와 무관하게 내지만 12-1
    순위표·TOP 5 진입·이탈은 같은 시나리오끼리만(False 면 ``_extra`` 가 사유와 함께 생략, delta 표는
    ``export.generate`` 가 생략)."""
    from app import snapshot_view as sv

    try:
        return _payload(session, compare, scenario), True
    except sv.NotInRevision:
        base = session.scalars(select(Scenario).where(Scenario.code == "base")).first()
        if base is None or base.id == scenario.id:
            raise
        return _payload(session, compare, base), False


def compare_problem(snap: Snapshot, compare: Snapshot) -> str | None:
    """비교 기준 리비전 규칙(API ``POST /reports`` 와 같음 — R3 5차 M5·6차 m5): 같은 지역, 발행 리비전(저장본, D13-1),
    대상보다 **앞선** 리비전(같거나 더 새 리비전은 '이전 → 현재' 표가 뒤집힌다). 어긋나면 사유, 맞으면 None."""
    if compare.region_id != snap.region_id:
        return f"비교 스냅샷 {compare.id} 은 다른 지역({compare.region_id})이다"
    if compare.status != "published":
        return f"비교 스냅샷 {compare.id} 는 발행 전({compare.status})이라 비교할 수 없다"
    if (compare.asof_date, int(compare.revision or 1), compare.id) >= (
        snap.asof_date,
        int(snap.revision or 1),
        snap.id,
    ):
        return f"비교 스냅샷 {compare.id} 은 대상 {snap.id} 와 같거나 더 새 리비전이다 — 앞선 리비전을 고른다"
    return None


def scenario_in_revision(session: Session, snap: Snapshot, scenario_id: int) -> bool:
    """그 리비전에 그 시나리오 보고서 입력이 있는가(D14-3 — 발행 리비전은 저장본, 발행 전은 늘 True)."""
    from app import snapshot_view as sv

    if not sv.is_published(snap):
        return True
    if not sv.kind_ready(session, snap.id, "report"):
        raise sv.MaterializePending(f"발행 리비전 {snap.id} 의 report 저장본을 아직 만들지 않았다")
    return sv.stored(session, snap.id, "report", scenario=str(scenario_id)) is not None


def _changed_after_run(session: Session, snap: Snapshot, run: ScoreRun | None, ids: list[int]) -> set[int]:
    """점수 실행 뒤 재판정을 부르는 변경이 있었던 단지(API ``views.load_bundles`` 와 같은 규칙 — 단지 단위 + 지역 단위
    이벤트). 발행 리비전은 지역의 가장 새 발행 리비전일 때만 비교한다(과거 리비전은 그때의 기록, D13-1 저장 시점)."""
    if run is None or not run.created_at or not ids:
        return set()
    if snap.status == "published":
        from app.api.views import latest_snapshot_id

        if latest_snapshot_id(session, snap.region_id) != snap.id:
            return set()
    region_level = session.scalars(
        select(ChangeEvent.id)
        .where(
            ChangeEvent.complex_id.is_(None),
            ChangeEvent.entity == "region",
            ChangeEvent.entity_id == snap.region_id,
            ChangeEvent.triggers_rejudge.is_(True),
            ChangeEvent.detected_at > run.created_at,
        )
        .limit(1)
    ).first()
    if region_level is not None:
        return set(ids)
    out: set[int] = set()
    for i in range(0, len(ids), 500):
        out |= {
            int(c)
            for c in session.scalars(
                select(ChangeEvent.complex_id).where(
                    ChangeEvent.complex_id.in_(ids[i : i + 500]),
                    ChangeEvent.triggers_rejudge.is_(True),
                    ChangeEvent.detected_at > run.created_at,
                )
            )
            if c is not None
        }
    return out


def _candidates(session: Session, run: ScoreRun | None, ids: set[int]) -> set[int]:
    """점수 실행의 rerank 후보(저장 judge_scope 가 판정 대상·참고·보류). 저장값이 없는 옛 행은 후보로 본다."""
    from app.analysis.scope import in_rerank

    if run is None:
        return set()
    out: set[int] = set()
    for cid, scope in session.execute(
        select(ScoreTotal.complex_id, ScoreTotal.judge_scope).where(ScoreTotal.score_run_id == run.id)
    ):
        if cid in ids and (scope is None or in_rerank(str(scope))):
            out.add(int(cid))
    return out


def _extra(
    data: ReportData,
    cur: Mapping[str, Any],
    base_payload: Mapping[str, Any],
    base: Snapshot,
    *,
    same_scenario: bool = True,
) -> ExtraView:
    """§12 지역 추가·변경 장: 후보군 변화, rerank 재실행, 순위 변화 한 문단(meta §2-3).

    후보군 = 그 점수 실행에서 rerank 후보 범위(판정 대상·참고·보류 — ``analysis.scope.in_rerank``)인 단지(R3 4차 M-4:
    지역 선택에서 빠져 '제외'(범위 경계)가 된 단지도 점수 행은 남아 '제외 0'으로 보였다). 두 리비전 모두 보고서 입력
    데이터(발행 리비전 = 저장본, D13-1)로 계산한다 — 지금 사실·이름을 다시 읽지 않는다.

    ``same_scenario=False``(비교 기준 리비전에 이 시나리오가 없어 기본 시나리오 입력을 받음, D15-5): 후보 건수·추가·제외·
    rerank 문장만 내고 12-1 순위표·TOP 5 진입·이탈은 사유(``rank_note``)와 함께 생략한다(시나리오가 다른 순위를 섞지 않는다)."""
    from app.reports.codec import decode_data

    base_data: ReportData = decode_data(base_payload["data"])
    names: dict[int, str] = {int(k): v for k, v in (base_payload.get("names") or {}).items()}
    names.update({int(k): v for k, v in (cur.get("names") or {}).items()})
    prev = {v.complex_id: v for v in base_data.scores}
    cur_scores = {v.complex_id: v for v in data.scores}
    prev_c, cur_c = set(base_payload.get("candidates") or []), set(cur.get("candidates") or [])
    added = sorted(names.get(i, str(i)) for i in cur_c - prev_c)
    removed = sorted(names.get(i, str(i)) for i in prev_c - cur_c)
    prev = {k: v for k, v in prev.items() if k in prev_c}
    cur_scores = {k: v for k, v in cur_scores.items() if k in cur_c}
    rank_rows: list[tuple[str, str, str, Fact | None, Fact | None]] = []
    rank_note = (
        None
        if same_scenario
        else "비교 기준 리비전에 이 시나리오가 없어 12-1 순위 비교와 TOP 5 진입·이탈은 생략했다"
        "(같은 시나리오끼리만 비교, D15-5)."
    )
    for cid in sorted(
        set(cur_scores) | set(prev) if same_scenario else (),
        key=lambda i: (cur_scores[i].rank or 99) if i in cur_scores else 99,
    ):
        a, b = prev.get(cid), cur_scores.get(cid)
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
    prev_seq = base_payload.get("rerank_seq")
    if data.rerank_seq is not None and data.rerank_seq != prev_seq:
        rerank_text = (
            f"rerank는 후보군 전체로 다시 실행했다(#{prev_seq or '—'} → #{data.rerank_seq}). "
            "종합 점수는 새 rerank 호출 값만 쓴다(§6-5 고정 앵커)."
        )
    else:
        # R3 4차 minor: 사람 확인·단지 재판정 리비전은 rerank 를 다시 부르지 않았다 — '다시 실행' 이라고 쓰지 않는다
        rerank_text = f"rerank는 다시 실행하지 않았다(같은 호출 #{data.rerank_seq or prev_seq or '—'} 유지)."
    top_text = rank_note or f"TOP 5 진입: {', '.join(entered) or '없음'}; 이탈: {', '.join(left) or '없음'}."
    summary = (
        f"{base.asof_date} 스냅샷(리비전 {int(base.revision or 1)}) 대비 후보 {len(prev)}개 → {len(cur_scores)}개"
        f"(추가 {len(added)}, 제외 {len(removed)}). {rerank_text} {top_text}"
    )
    return ExtraView(
        base_snapshot_id=base.id,
        base_asof=base.asof_date,
        added=added,
        removed=removed,
        rank_rows=rank_rows,
        rerank_prev_seq=prev_seq,
        rerank_seq=data.rerank_seq,
        summary=summary,
        rank_note=rank_note,
    )

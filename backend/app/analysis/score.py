"""§6-4 구성 점수 6개 + move_in, 가중 합, 동점·동률, §6-5 rerank 고정 앵커 (RA §6-4·§6-5, §4-3 ScoreEngine).

순수 함수: DB·네트워크·시계 접근 없음, 같은 inputs = 같은 결과(입력 순서와 무관 — complex_id 순으로 처리).
판정 값은 봉투 status='ok'인 것만 쓴다(review·escaped·blocked·error → 그 성분 null → 종합 '미판정').

| 성분 | 식 | raw_value |
| --- | --- | --- |
| p10 | 10 × P(+10%, policy.p10_horizon) | 확률 |
| rerank | 10 × (N − rank)/(N − 1), 한 judgment_seq 호출의 items만 | relevance |
| gap | §6-2 (gap.py) | gap% |
| benchmark | clamp(10 × median(gain)/0.5, 0, 10), is_presale=false | median gain |
| supply | clamp(10 − 10 × U_window/U_ref, 0, 10) − pen (0 미만은 0) | U_window |
| liquidity | clamp(10 − 2×Y_resale − 3×[거주의무>0] − D/5, 0, 10) | Y_resale |
| move_in | clamp(10 − 2×입주까지 연수, 0, 10) (A·D) | 입주까지 연수 |

라벨: liquidity·move_in 은 입력 라벨(resale·residency·down_payment[·move_in]_label) 중 가장 약한 것(R3 M2).
라벨 null 은 계약 설명대로 '값이 있으면 확인됨'. rerank delta = 이전 run 대비 rerank 점수 차(§6-5, R3 minor 25).
점수 대상 = ``analysis.scope.is_scored``(제외·미해결 빼고, DECISIONS D9-1).

연수 = 일수/365(4자리). 성분 점수는 4자리 반올림 후 가중 합(10진, 반올림 없음 = ScoreTotal.total 원값).
"""

# ruff: noqa: E501  (한국어 docstring·식 문자열은 화면 폭 기준으로 길다)

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Final, cast, get_args

from app.analysis._common import (
    TEN,
    ZERO,
    add_months_date,
    add_months_ym,
    clamp,
    dec,
    median,
    num,
    paren,
    parse_date,
    q4,
    slope,
    years_until,
    ym_first_day,
    ym_index,
    ym_of,
)
from app.analysis._ranking import rank_totals, weighted_total
from app.analysis.gap import compute_gap
from app.analysis.ladder import ladder_targets, pick_ladder
from app.analysis.scenarios import is_excluded
from app.analysis.scope import is_scored
from app.analysis.sensitivity import compute_sensitivity, weights_map
from app.analysis.types import (
    ComponentKey,
    ComponentResult,
    DecideOption,
    GapResult,
    Horizon,
    Label,
    LadderTarget,
    weakest_label,
)
from app.core.contracts_gen import (
    BenchmarkInput,
    ComplexScoreInput,
    RerankAnchor,
    RerankItem,
    Scenario,
    ScoreInputs,
    ScoreRunResult,
    ScoreTotal,
    Sensitivity,
    Snapshot,
    SupplyInput,
    UnsoldInput,
)

__all__ = [
    "AnalysisScoreEngine",
    "ScoreRunDetail",
    "benchmark_component",
    "decide_outcome",
    "liquidity_component",
    "move_in_component",
    "p10_component",
    "rank_totals",
    "rerank_component",
    "run_detailed",
    "supply_component",
    "weighted_total",
]

DECIDE_TIE_CONFIDENCE: Final = 0.6
_LABELS: Final = frozenset(get_args(Label))
BENCHMARK_SCALE: Final = Decimal("0.5")
RECENT_SALE_YEARS: Final = 3
SUPPLY_WINDOW_MONTHS: Final = 12
UNSOLD_WINDOW_MONTHS: Final = 12


def _unscored(cid: int, comp: ComponentKey, why: str, *, reason: str | None = None) -> ComponentResult:
    return ComponentResult(
        complex_id=cid,
        component=comp,
        raw_value=None,
        score=None,
        formula_text=why,
        label="확인 불가",
        reason=reason,
    )


def _seq(seq: int | None) -> str:
    return f"jl_{seq}" if seq is not None else "jl_?"


# ------------------------------------------------------------------ p10


def p10_component(complex_: ComplexScoreInput, *, horizon: Horizon) -> ComponentResult:
    cid = complex_.complex_id
    lad = pick_ladder(complex_.ladders, horizon)
    if lad is None:
        return _unscored(cid, "p10", f"미판정: {horizon} 사다리 없음", reason="사다리 없음")
    if lad.status != "ok" or lad.p10 is None:
        return _unscored(
            cid,
            "p10",
            f"미판정: noul status={lad.status} ({horizon}, {_seq(lad.judgment_seq)}) — 점수에 쓰지 않음",
            reason=f"판정기 {lad.status}",
        )
    p = dec(lad.p10)
    s = q4(clamp(TEN * p))
    return ComponentResult(
        complex_id=cid,
        component="p10",
        raw_value=p,
        score=s,
        formula_text=f"10 × {num(p, 4)} = {num(s)} ({_seq(lad.judgment_seq)}, {horizon})",
        label="추정",
        reason="판정기 noul",
    )


# ------------------------------------------------------------------ rerank


def _find_item(items: Iterable[RerankItem], cid: int) -> RerankItem | None:
    for it in items:
        if it.complex_id == cid or it.candidate_id == f"complex:{cid}":
            return it
    return None


def _rank_score(rank: int, n: int) -> Decimal:
    """s_rerank = 10 × (N − rank)/(N − 1) (N ≤ 1 이면 10)."""
    return TEN if n <= 1 else q4(clamp(TEN * (n - rank) / (n - 1)))


def _rerank_delta(anchor: RerankAnchor, item: RerankItem | None, cid: int) -> Decimal | None:
    """§6-5 '이전 run 과의 점수 차이' = s_rerank(이번 호출) − s_rerank(이전 호출). 이전 후보가 아니면 None."""
    if item is None or anchor.prev is None:
        return None
    prev = _find_item(anchor.prev.items, cid)
    if prev is None:
        return None
    now = _rank_score(item.rank, len(anchor.items))
    before = _rank_score(prev.rank, len(anchor.prev.items))
    return q4(now - before)


def rerank_component(complex_: ComplexScoreInput, anchor: RerankAnchor) -> ComponentResult:
    """§6-5 고정 앵커: anchor(judgment_seq 한 호출)의 items만 쓴다. delta = rerank 점수 − 이전 호출 rerank 점수."""
    cid = complex_.complex_id
    if anchor.status != "ok":
        return _unscored(
            cid,
            "rerank",
            f"미판정: rerank status={anchor.status} ({_seq(anchor.judgment_seq)}) — 점수에 쓰지 않음",
            reason=f"판정기 {anchor.status}",
        )
    item = _find_item(anchor.items, cid)
    if item is None:
        return _unscored(
            cid, "rerank", f"미판정: rerank 후보 아님 ({_seq(anchor.judgment_seq)})", reason="후보 아님"
        )
    n = len(anchor.items)
    s = _rank_score(item.rank, n)
    rel = dec(item.relevance)
    return ComponentResult(
        complex_id=cid,
        component="rerank",
        raw_value=rel,
        score=s,
        formula_text=(
            f"10 × ({n} − {item.rank})/({n} − 1) = {num(s)} "
            f"(rank {item.rank}/{n}, relevance {num(rel, 4)}, {_seq(anchor.judgment_seq)})"
        ),
        label="추정",
        reason="판정기 rerank",
        delta=_rerank_delta(anchor, item, cid),
    )


# ------------------------------------------------------------------ benchmark


def benchmark_component(
    complex_: ComplexScoreInput, benchmarks: Iterable[BenchmarkInput], *, asof_date: str
) -> ComponentResult:
    cid = complex_.complex_id
    la = complex_.living_area
    rows = sorted(
        (
            b
            for b in benchmarks
            if la is not None
            and b.living_area == la
            and not b.is_presale
            and b.sale_price_84_won
            and b.sale_price_84_won > 0
            and b.trade_median_won is not None
        ),
        key=lambda b: (b.name, b.sale_year or 0),
    )
    if not rows:
        return _unscored(
            cid, "benchmark", "벤치마크 미계산: 생활권 분양 사례(분양권 제외) 없음", reason="표본 0"
        )
    gains = [
        (
            b,
            (Decimal(b.trade_median_won or 0) - Decimal(b.sale_price_84_won or 0))
            / Decimal(b.sale_price_84_won or 1),
        )
        for b in rows
    ]
    g = median([x for _, x in gains])
    s = q4(clamp(TEN * g / BENCHMARK_SCALE))
    n = len(rows)
    asof_year = parse_date(asof_date).year
    flags: tuple[str, ...] = ()
    if not any(b.sale_year is not None and b.sale_year >= asof_year - RECENT_SALE_YEARS for b in rows):
        flags = ("no_recent_sale_case",)
    if n < 3:
        label: Label = "추정"
        reason: str | None = f"표본 {n}"
    else:
        label = weakest_label(*(b.label for b in rows))
        reason = None
    cases = ", ".join(f"{b.name} {'+' if x >= 0 else ''}{num(x * 100, 1)}%" for b, x in gains)
    text = f"clamp(10 × {paren(g, 4)}/0.5, 0, 10) = {num(s)} (분양가 대비 입주 후 실거래 중앙 gain, {n}건: {cases}"
    text += "; 최근 3년 분양 사례 0건)" if flags else ")"
    return ComponentResult(
        complex_id=cid,
        component="benchmark",
        raw_value=q4(g),
        score=s,
        formula_text=text,
        label=label,
        reason=reason,
        flags=flags,
    )


# ------------------------------------------------------------------ supply


def _units(u: Decimal) -> str:
    """세대수 표기: 정수면 '12,857', 아니면 소수 1자리 '7,023.7'."""
    if u == u.to_integral_value():
        return f"{int(u):,}"
    return f"{u.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP):,}"


def _unsold_points(
    unsold: Sequence[UnsoldInput],
    living_area: str,
    asof_idx: int,
    scope_codes: Sequence[str] = (),
) -> tuple[list[tuple[int, Decimal]], list[tuple[int, Decimal]], str]:
    # 생활권 ↔ 미분양 scope_code(시군구) 매핑: LivingAreaScoreInput.unsold_scope_codes(계약 2026-10-09.2).
    # 매핑이 없으면 scope_code 가 생활권 id 와 같은 행(이전 입력 호환), 그것도 없으면 지역 합계.
    codes = set(scope_codes)
    scoped = [u for u in unsold if (u.scope_code in codes if codes else u.scope_code == living_area)]
    scope = "생활권"
    if not scoped:
        scoped = list(unsold)
        scope = "지역 합계"
    lo = asof_idx - UNSOLD_WINDOW_MONTHS
    totals: dict[int, Decimal] = {}
    post: dict[int, Decimal] = {}
    for u in scoped:
        idx = ym_index(u.ym)
        if not (lo < idx <= asof_idx):
            continue
        if u.total is not None:
            totals[idx] = totals.get(idx, ZERO) + u.total
        if u.post_completion is not None:
            post[idx] = post.get(idx, ZERO) + u.post_completion
    return sorted(totals.items()), sorted(post.items()), scope


def supply_component(
    complex_: ComplexScoreInput,
    supply: Iterable[SupplyInput],
    unsold: Sequence[UnsoldInput],
    *,
    households: Mapping[str, int | None],
    ref_pct: float,
    asof_date: str,
    unsold_scopes: Mapping[str, Sequence[str]] | None = None,
) -> ComponentResult:
    cid = complex_.complex_id
    la = complex_.living_area
    if la is None:
        return _unscored(cid, "supply", "공급 미계산: 생활권 미배정", reason="생활권 없음")
    target = ladder_targets(
        asof_date, move_in_ym=complex_.move_in_ym, immediate=bool(complex_.immediate_move_in)
    )["move_in_plus_1y"].target_ym
    start, end = add_months_ym(target, -SUPPLY_WINDOW_MONTHS), add_months_ym(target, SUPPLY_WINDOW_MONTHS)
    lo, hi = ym_index(start), ym_index(end)
    units = ZERO
    year_only = False
    labels: list[Label] = []
    for row in supply:
        if row.living_area != la:
            continue
        if row.ym:
            share = Decimal(1) if lo <= ym_index(row.ym) <= hi else ZERO
        else:  # 연 단위 물량은 12개월에 균등 분배해 창에 걸친 개월 비율만 센다
            months = sum(1 for m in range(12) if lo <= row.year * 12 + m <= hi)
            share = Decimal(months) / 12
            year_only = year_only or months > 0
        if share > 0:
            units += Decimal(row.units) * share
            labels.append(row.label)
    units = q4(units)
    hh = households.get(la)
    if hh is None or hh <= 0:
        return _unscored(
            cid,
            "supply",
            f"공급 미계산: 생활권 세대수 없음(U_ref = 세대수 × {num(dec(ref_pct), 4)}), U_window {_units(units)}세대({start}~{end})",
            reason="세대수 없음",
        )
    u_ref = Decimal(hh) * dec(ref_pct)
    base = clamp(TEN - TEN * units / u_ref)
    asof_idx = ym_index(ym_of(parse_date(asof_date)))
    totals, post, scope = _unsold_points(unsold, la, asof_idx, (unsold_scopes or {}).get(la, ()))
    pen = 0
    notes: list[str] = []
    k = slope(totals)
    if k is None:
        notes.append(f"미분양 12개월 기울기 산출 불가({scope} {len(totals)}개월)")
    else:
        notes.append(f"미분양 12개월 기울기 {paren(k, 1)}/월({scope})")
        if k > 0:
            pen += 2
    if len(post) >= 2:
        first, last = post[0][1], post[-1][1]
        notes.append(f"준공 후 미분양 {num(first, 0)}→{num(last, 0)}")
        if last > first:
            pen += 1
    s = q4(max(ZERO, base - pen))
    text = (
        f"clamp(10 − 10 × {_units(units)}/{num(u_ref, 0)}, 0, 10) − pen={pen} = {num(s)} "
        f"(U_window {start}~{end} 입주 {_units(units)}세대, U_ref = 세대수 {hh:,} × {num(dec(ref_pct), 4)}; {'; '.join(notes)})"
    )
    reason = "U_ref 추정(세대수 × 기준치)" + (
        ", 연 단위 입주 물량은 12개월 균등 분배로 가정" if year_only else ""
    )
    return ComponentResult(
        complex_id=cid,
        component="supply",
        raw_value=units,
        score=s,
        formula_text=text,
        label=weakest_label("추정", *labels),
        reason=reason,
    )


# ------------------------------------------------------------------ liquidity · move_in


def _move_in_date(complex_: ComplexScoreInput, asof_date: str) -> tuple[str, date] | None:
    if complex_.immediate_move_in:
        return ("즉시", parse_date(asof_date))
    if complex_.move_in_ym:
        return (complex_.move_in_ym, ym_first_day(complex_.move_in_ym))
    return None


def liquidity_component(complex_: ComplexScoreInput, *, asof_date: str) -> ComponentResult:
    cid = complex_.complex_id
    missing = [
        name
        for name, v in (
            ("계약금%", complex_.down_payment_pct),
            ("거주의무", complex_.residency_months),
            ("전매기간", complex_.resale_months),
            ("당첨일", complex_.winner_date),
        )
        if v is None
    ]
    if missing:
        return _unscored(
            cid, "liquidity", f"유동성 미계산: 입력 없음({', '.join(missing)})", reason="공고문 값 없음"
        )
    asof = parse_date(asof_date)
    assert complex_.winner_date is not None and complex_.resale_months is not None
    assert complex_.down_payment_pct is not None and complex_.residency_months is not None
    end = add_months_date(parse_date(complex_.winner_date), complex_.resale_months)
    end_note = f"전매 종료 {ym_of(end)}"
    mv = _move_in_date(complex_, asof_date)
    used_move_in = False
    if complex_.resale_release_on_registration and mv is not None:
        mv_label, mv_day = mv
        if mv_day < end:
            end = mv_day
            end_note += f"(등기 시 해제 → 입주 {mv_label} 기준)"
            used_move_in = not complex_.immediate_move_in
    y = years_until(end, asof)
    d = dec(complex_.down_payment_pct)
    res_term = 3 if complex_.residency_months > 0 else 0
    s = q4(clamp(TEN - 2 * y - res_term - d / 5))
    text = (
        f"clamp(10 − 2×{num(y, 4)} − 3×[거주의무>0]={res_term} − D/5({num(d)}/5={num(d / 5)}), 0, 10) = {num(s)} "
        f"({end_note}, Y_resale {num(y, 4)}년, 거주의무 {complex_.residency_months}개월, 계약금 {num(d)}%)"
    )
    inputs: list[tuple[str, Label | None]] = [
        ("전매", complex_.resale_label),
        ("거주의무", complex_.residency_label),
        ("계약금", complex_.down_payment_label),
    ]
    if used_move_in:
        inputs.append(("입주월", _move_in_label(complex_)))
    label, reason = _input_label(inputs)
    return ComponentResult(
        complex_id=cid, component="liquidity", raw_value=y, score=s, formula_text=text, label=label, reason=reason
    )


def _move_in_label(complex_: ComplexScoreInput) -> Label | None:
    """입주월 라벨 — 계약(2026-10-09.3)에 필드가 없어 None(=확인됨). 계약 .4 에 move_in_label 이 생기면 그 값."""
    value = getattr(complex_, "move_in_label", None)
    return cast(Label, value) if value in _LABELS else None


def _input_label(inputs: Sequence[tuple[str, Label | None]]) -> tuple[Label, str | None]:
    """입력 라벨 중 가장 약한 것(R3 M2). null 은 '값이 있으면 확인됨'(계약 설명). reason = 약한 입력 이름."""
    resolved = [(name, lab or "확인됨") for name, lab in inputs]
    label = weakest_label(*(lab for _, lab in resolved))
    if label == "확인됨":
        return label, None
    weak = ", ".join(f"{name} {lab}" for name, lab in resolved if lab == label)
    return label, f"라벨: 가장 약한 입력({weak})"


def move_in_component(complex_: ComplexScoreInput, *, asof_date: str) -> ComponentResult:
    cid = complex_.complex_id
    mv = _move_in_date(complex_, asof_date)
    if mv is None:
        return _unscored(cid, "move_in", "입주 점수 미계산: 입주월 없음", reason="입주월 없음")
    mv_label, mv_day = mv
    y = years_until(mv_day, parse_date(asof_date))
    s = q4(clamp(TEN - 2 * y))
    label, reason = _input_label(
        [] if complex_.immediate_move_in else [("입주월", _move_in_label(complex_))]
    )
    return ComponentResult(
        complex_id=cid,
        component="move_in",
        raw_value=y,
        score=s,
        formula_text=f"clamp(10 − 2×{num(y, 4)}, 0, 10) = {num(s)} (입주 {mv_label}, 입주까지 {num(y, 4)}년)",
        label=label,
        reason=reason,
    )


# ------------------------------------------------------------------ 고정 입력 (회귀 (a)단계)


def _fixed(complex_: ComplexScoreInput, key: ComponentKey, anchor: RerankAnchor) -> ComponentResult | None:
    fc = complex_.fixed_components
    if fc is None:
        return None
    value = getattr(fc, key, None)
    if value is None:
        return None
    s = q4(clamp(dec(value)))
    raw: Decimal | None = None
    delta: Decimal | None = None
    if key == "rerank":
        item = _find_item(anchor.items, complex_.complex_id)
        raw = None if item is None else dec(item.relevance)
        delta = _rerank_delta(anchor, item, complex_.complex_id)
    return ComponentResult(
        complex_id=complex_.complex_id,
        component=key,
        raw_value=raw,
        score=s,
        formula_text=f"고정 입력: {fc.source} → {num(s)}",
        label="추정",
        reason="회귀 (a)단계 고정 입력",
        delta=delta,
    )


# ------------------------------------------------------------------ 엔진


@dataclass(frozen=True)
class ScoreRunDetail:
    """ScoreRunResult + 저장·화면에 필요한 중간 결과(비교군 comparable_set, 사다리 목표, 민감도)."""

    result: ScoreRunResult
    components: dict[int, dict[ComponentKey, ComponentResult]]
    gaps: dict[int, GapResult]
    ladder_targets: dict[int, dict[Horizon, LadderTarget]]
    sensitivity: Sensitivity | None
    excluded: frozenset[int]


def _component(
    key: ComponentKey,
    cx: ComplexScoreInput,
    *,
    scenario: Scenario,
    inputs: ScoreInputs,
    households: Mapping[str, int | None],
    gaps: dict[int, GapResult],
) -> ComponentResult:
    fixed = _fixed(cx, key, inputs.rerank)
    if key == "gap":
        gaps[cx.complex_id] = compute_gap(
            cx, inputs.trades, asof_date=inputs.asof_date, coef=inputs.region.age_premium_coef
        )
    if fixed is not None:
        return fixed
    if key == "p10":
        return p10_component(cx, horizon=scenario.policy.p10_horizon)
    if key == "rerank":
        return rerank_component(cx, inputs.rerank)
    if key == "gap":
        g = gaps[cx.complex_id]
        return ComponentResult(
            complex_id=cx.complex_id,
            component="gap",
            raw_value=g.gap_pct,
            score=g.score,
            formula_text=g.formula_text,
            label=g.label,
            reason=g.reason,
            flags=g.flags,
        )
    if key == "benchmark":
        return benchmark_component(cx, inputs.benchmarks, asof_date=inputs.asof_date)
    if key == "supply":
        return supply_component(
            cx,
            inputs.supply,
            inputs.unsold,
            households=households,
            ref_pct=inputs.region.supply_ref_pct,
            asof_date=inputs.asof_date,
            unsold_scopes={la.id: la.unsold_scope_codes or [] for la in inputs.living_areas},
        )
    if key == "liquidity":
        return liquidity_component(cx, asof_date=inputs.asof_date)
    return move_in_component(cx, asof_date=inputs.asof_date)


def run_detailed(
    snapshot: Snapshot, scenario: Scenario, inputs: ScoreInputs, *, with_sensitivity: bool = True
) -> ScoreRunDetail:
    if snapshot.id != inputs.snapshot_id:
        raise ValueError(f"snapshot 불일치: {snapshot.id} != inputs.snapshot_id {inputs.snapshot_id}")
    weights = weights_map(scenario.weights)
    households = {la.id: la.households for la in inputs.living_areas}
    complexes = sorted((c for c in inputs.complexes if is_scored(c.judge_scope)), key=lambda c: c.complex_id)

    comps: dict[int, dict[ComponentKey, ComponentResult]] = {}
    gaps: dict[int, GapResult] = {}
    targets: dict[int, dict[Horizon, LadderTarget]] = {}
    totals: dict[int, Decimal | None] = {}
    excluded: set[int] = set()
    for cx in complexes:
        row = {
            key: _component(key, cx, scenario=scenario, inputs=inputs, households=households, gaps=gaps)
            for key in weights
        }
        comps[cx.complex_id] = row
        targets[cx.complex_id] = ladder_targets(
            inputs.asof_date, move_in_ym=cx.move_in_ym, immediate=bool(cx.immediate_move_in)
        )
        totals[cx.complex_id] = weighted_total({k: r.score for k, r in row.items()}, weights)
        if is_excluded(cx, scenario):
            excluded.add(cx.complex_id)

    rankable = {cid: t for cid, t in totals.items() if cid not in excluded}
    ranked = rank_totals(rankable)
    sens: Sensitivity | None = None
    unstable: frozenset[int] = frozenset()
    if with_sensitivity:
        sens = compute_sensitivity(
            {cid: {k: r.score for k, r in comps[cid].items()} for cid in rankable},
            scenario.weights,
            snapshot_id=snapshot.id,
            scenario_id=scenario.id,
        )
        unstable = frozenset(sens.unstable_complex_ids)

    result = ScoreRunResult(
        snapshot_id=snapshot.id,
        scenario_id=scenario.id,
        weights=scenario.weights,
        rerank_judgment_seq=inputs.rerank.judgment_seq,
        components=[r.to_contract() for cid in sorted(comps) for r in comps[cid].values()],
        totals=[
            ScoreTotal(
                complex_id=cid,
                total=None if totals[cid] is None else float(totals[cid] or ZERO),
                rank=ranked[cid].rank if cid in ranked else None,
                tie_group=ranked[cid].tie_group if cid in ranked else None,
                unstable=cid in unstable,
            )
            for cid in sorted(totals)
        ],
    )
    return ScoreRunDetail(
        result=result,
        components=comps,
        gaps=gaps,
        ladder_targets=targets,
        sensitivity=sens,
        excluded=frozenset(excluded),
    )


class AnalysisScoreEngine:
    """``app.core.protocols.ScoreEngine`` 구현. 상태 없음."""

    def run(self, snapshot: Snapshot, scenario: Scenario, inputs: ScoreInputs) -> ScoreRunResult:
        return run_detailed(snapshot, scenario, inputs).result


# ------------------------------------------------------------------ decide 동률 (§6-4)


def decide_outcome(
    *, status: str, confidence: float | None, probs: Mapping[str, float], selected: str | None
) -> list[DecideOption]:
    """decide 결과 표시 규칙: status≠ok면 아무것도 고르지 않는다. confidence < 0.6이면 확률 상위 2개를 tie·chosen
    (1순위를 하나로 말하지 않음, T2). 아니면 selected(없으면 최고 확률) 하나만 chosen."""
    order = sorted(probs.items(), key=lambda kv: (-kv[1], kv[0]))
    if status != "ok" or not order:
        return [DecideOption(key=k, prob=p, chosen=False, tie=False) for k, p in order]
    if confidence is not None and confidence < DECIDE_TIE_CONFIDENCE and len(order) >= 2:
        top2 = {order[0][0], order[1][0]}
        return [DecideOption(key=k, prob=p, chosen=k in top2, tie=k in top2) for k, p in order]
    pick = selected if selected in probs else order[0][0]
    return [DecideOption(key=k, prob=p, chosen=k == pick, tie=False) for k, p in order]

"""시나리오 → 판정 payload 목록 (계약 2026-10-09.3, WP5-5) + 파이프라인과 공용인 입력 조립 단계.

``scenario_payloads(session, snapshot_id, scenario_id)`` 는 그 스냅샷에서 시나리오 1개를 재판정할 때
``pipeline.run_pipeline`` 이 판정기에 보낼 호출(P6 noul · P7 rerank · P8 decide)을 판정기를 부르지 않고 만든다.
``cache_status`` 는 각 호출의 input_hash(``core.protocols.input_hash``)로 judgment_log 최종 행이 있는지 본다 —
미리보기(WP5 ``/scenarios/{id}/preview``)의 cache_hits·cache_misses 가 이것이다.

정확성: payload 는 파이프라인과 **같은 함수**(``score_base``·``rerank_pool``·``decide_plan`` +
``judge.payloads``)로 만든다. decide 입력은 rerank 결과·사다리(앞 단계 판정)에 달려 있으므로, 앞 단계 호출이 하나라도
캐시에 없으면 decide payload 는 정할 수 없다(``payload=None`` = 미스로 센다 — 새 판정 결과가 들어가면 decide 입력도
바뀐다). 앞 단계가 전부 캐시면 decide payload 는 실행 때와 같다.

판정 범위(JudgeScope): ``analysis.scope.judge_scope``(DECISIONS D9-1, API·보고서와 같은 함수) 하나로 정한다 —
사다리(noul) = 판정 대상만(``runs_ladder``), rerank 후보 = 판정 대상·참고·보류(``in_rerank``; 미해결·제외 빼고),
decide 후보 = 판정 대상만(+ 시나리오 policy.include_wait_new 면 가상 후보 '모집공고 대기', 계약 .5). 저장 범위(score_total.judge_scope)도 같은 값(``stored_scope``) — 사다리 결과로 범위를
바꾸지 않는다(사다리가 review 면 p10 null → 종합 '미판정', RA §6-4).
"""

# ruff: noqa: E501

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.scenarios import RequirementPrecalculator
from app.analysis.scope import SCOPE_TEXT, UNRESOLVED, in_rerank, is_decide_candidate, is_scored, runs_ladder
from app.analysis.score import ScoreRunDetail, run_detailed
from app.core.contracts_gen import RerankAnchor, RerankItem, ScoreInputs
from app.core.contracts_gen import Scenario as ScenarioDTO
from app.core.contracts_gen import Snapshot as SnapshotDTO
from app.core.protocols import JudgePayload, JudgeTool, input_hash
from app.judge import payloads as P
from app.models import JudgmentLog, Region, Snapshot
from app.scheduler.inputs import (
    ComplexFacts,
    JudgeScope,
    RegionContext,
    age_coef,
    build_score_inputs,
    evidence_card,
    gap_of,
    load_facts,
    region_context,
)
from app.scheduler.snapshots import snapshot_dto

__all__ = [
    "JudgeInputs",
    "PlannedCall",
    "ScenarioPlan",
    "cache_status",
    "decide_plan",
    "judge_inputs",
    "rerank_pool",
    "scenario_payloads",
    "score_base",
    "stored_scope",
    "wait_new_evidence",
    "wants_wait_new",
]

EMPTY_ANCHOR = RerankAnchor(judgment_seq=None, status="review", items=[])


# ---------------------------------------------------------------- 파이프라인과 공용 단계


def stored_scope(session: Session, snapshot_id: int, facts: Sequence[ComplexFacts]) -> dict[int, JudgeScope]:
    """저장 판정 범위(score_total.judge_scope) = ``analysis.scope.judge_scope`` 결과 그대로(D9-1).

    (이전 규칙 '사다리 ok 없는 판정 대상 → 참고'는 D9-1 에 없는 두 번째 규칙이라 없앴다 — R3 C2.)
    """
    del session, snapshot_id
    return {f.complex_id: f.scope for f in facts}


@dataclass(frozen=True)
class JudgeInputs:
    """P6 noul·P7 rerank·P8 decide 공용 입력(R5-PIPE): 앵커 없는 ScoreInputs + 단지별 증거 카드(가격 갭·벤치마크·공급·호재·
    제도 비고) + 지역 맥락(noul 컨텍스트 ``benchmark``·``policy``). 파이프라인과 미리보기가 같은 함수로 만든다(같은 input_hash)."""

    base: ScoreInputs
    cards: dict[int, P.EvidenceCard]
    ctx: RegionContext

    def benchmark_text(self) -> str | None:
        return self.ctx.benchmark_text()

    def policy_text(self, f: ComplexFacts) -> str:
        return self.ctx.policy_text(f)


def judge_inputs(
    session: Session, snap: Snapshot, region: Region, facts: Sequence[ComplexFacts]
) -> JudgeInputs:
    """``score_base`` 의 본체. 카드는 사다리와 무관하다(P6 앞뒤 같은 카드) — 사다리를 반영한 ScoreInputs 는 ``inputs.with_ladders``."""
    base = build_score_inputs(session, snap, region, facts, EMPTY_ANCHOR)
    coef = age_coef(region)
    gaps = {
        f.complex_id: gap_of(f, base.trades, asof_date=snap.asof_date, coef=coef)
        for f in facts
        if is_scored(f.scope)
    }
    ctx = region_context(session, region, base)
    cards = {f.complex_id: evidence_card(f, gap=gaps.get(f.complex_id), ctx=ctx) for f in facts}
    return JudgeInputs(base, cards, ctx)


def score_base(
    session: Session, snap: Snapshot, region: Region, facts: Sequence[ComplexFacts]
) -> tuple[ScoreInputs, dict[int, P.EvidenceCard]]:
    """앵커 없는 ScoreInputs + 단지별 증거 카드(가격 갭·지역 맥락 포함) — rerank·decide 입력."""
    ji = judge_inputs(session, snap, region, facts)
    return ji.base, ji.cards


def rerank_pool(
    facts: Sequence[ComplexFacts], cards: Mapping[int, P.EvidenceCard], scope: Mapping[int, str]
) -> list[P.EvidenceCard]:
    """P7 후보군 = 판정 대상·참고·보류(``analysis.scope.in_rerank``; 미해결·제외 빼고), complex_id 순."""
    return [cards[f.complex_id] for f in facts if in_rerank(scope.get(f.complex_id, "제외"))]


def decide_candidates(
    ranked: Mapping[int, int | None],
    excluded: frozenset[int],
    scope: Mapping[int, str],
    *,
    limit: int = P.DECIDE_MAX,
) -> list[int]:
    """판정 대상 중 시나리오 제외(D: 접수 가능 아님)를 뺀 상위 ≤limit(기본 6, 가상 후보가 있으면 5) — 순위(점수 없으면
    complex_id) 순."""
    ids = [cid for cid, s in scope.items() if is_decide_candidate(s) and cid not in excluded]
    ids.sort(key=lambda cid: (ranked.get(cid) is None, ranked.get(cid) or 0, cid))
    return ids[:limit]


def wants_wait_new(sc: ScenarioDTO) -> bool:
    """시나리오 policy.include_wait_new(계약 2026-10-09.5) — 내장 A 만 true(보고서 §8-2·§12-5-2 #126)."""
    return bool(sc.policy.include_wait_new)


WAIT_NEW_MONTHS: Final = 12
"""'모집공고 대기' 근거의 공고 예정 창(meta §1-3: 조사 기간 = 기준일~+12개월)."""


def _plus_months(day: str, months: int) -> str:
    y, m = int(day[:4]), int(day[5:7])
    t = y * 12 + (m - 1) + months
    return f"{t // 12:04d}-{t % 12 + 1:02d}{day[7:10]}"


def wait_new_evidence(facts: Sequence[ComplexFacts], asof_date: str) -> str:
    """가상 후보 '모집공고 대기'의 근거 = 지역 (A) 트랙(청약 진행·예정) 중 **12개월 내 공고 예정**(공고일 없음 = 공고 전,
    또는 기준일 뒤 ~ 기준일+12개월) 단지 목록 요약(R3 재리뷰 F2).

    판단 없음 — complex.track·notice_date·판정 범위(``analysis.scope``) 그대로 옮긴다. 넣지 않는 것: 제외·미해결(포함
    분류가 확정되지 않음), 이미 공고된 단지, 공고일이 12개월 창 밖인 단지. '보류'(포함 확정 + 분양가 미공개)는 공고 전
    단지 그 자체라 넣는다(보고서 §1·§8-2 상황 A 근거 = 공고 전 보류 단지).
    """
    until = _plus_months(asof_date[:10], WAIT_NEW_MONTHS)
    rows: list[str] = []
    for f in facts:
        cx = f.row
        if cx.track != "A" or f.scope in ("제외", UNRESOLVED):
            continue
        nd = (cx.notice_date or "")[:10]
        if nd and nd <= asof_date:
            continue  # 이미 공고된 단지는 '공고 예정'이 아니다
        if nd and nd > until:
            continue  # 12개월 창 밖
        when = f"모집공고 {nd} 예정" if nd else "모집공고일 미정(공고 전)"
        area = f", {f.living_area_name}" if f.living_area_name else ""
        price = "분양가 미공개" if f.price_high is None else "분양가 공개"
        rows.append(f"- {cx.name}({when}{area}; {price}; 판정 범위 {SCOPE_TEXT[f.scope]})")
    head = f"지역 (A) 트랙 공고 예정 {len(rows)}곳(기준일 {asof_date}, 12개월 내 공고 예정 단지)"
    return "\n".join([head + (":" if rows else " — 기다릴 공고 예정 단지가 확인되지 않음"), *rows])


def priorities_text(sc: ScenarioDTO) -> str:
    w = {k: v for k, v in sc.weights.model_dump().items() if v is not None}
    parts = [f"상황 '{sc.name}' 가중치: " + ", ".join(f"{k} {v:.2f}" for k, v in w.items())]
    p = sc.params
    if p.purpose:
        parts.append(f"목적 {p.purpose}")
    if p.holding_years is not None:
        parts.append(f"보유 {p.holding_years:g}년")
    if p.move_in_by:
        parts.append(f"입주 희망 {p.move_in_by}")
    parts.append("요건 사전 계산(충족/미충족) 근거를 우선한다")
    return "; ".join(parts)


@dataclass
class DecidePlan:
    detail: ScoreRunDetail
    candidate_ids: list[int]
    candidates: list[P.DecideCandidate]
    requirements: tuple[str, str, str]
    priorities: str
    include_wait_new: bool = False
    wait_new_evidence: str | None = None

    @property
    def n_options(self) -> int:
        """판정기 후보 수 = 단지 + 가상 후보(모집공고 대기)."""
        return len(self.candidate_ids) + (1 if self.include_wait_new else 0)

    @property
    def runnable(self) -> bool:
        return self.n_options >= 2


def decide_plan(
    snap_dto: SnapshotDTO,
    sc: ScenarioDTO,
    inputs: ScoreInputs,
    cards: Mapping[int, P.EvidenceCard],
    scope: Mapping[int, str],
    *,
    precalc: RequirementPrecalculator | None = None,
    wait_new_text: str | None = None,
) -> DecidePlan:
    """점수(시나리오 1개) → P8 decide 후보 ≤6 + 요건 사전 계산.

    시나리오 policy.include_wait_new(계약 .5)면 가상 후보 '모집공고 대기'를 넣고 단지 후보는 상위 ≤5(합 ≤6, 보고서
    §8-2 'TOP 5 + 모집공고 대기'). ``wait_new_text`` = 그 근거(``wait_new_evidence``)."""
    detail = run_detailed(snap_dto, sc, inputs)
    ranked = {t.complex_id: t.rank for t in detail.result.totals}
    wait = wants_wait_new(sc)
    ids = decide_candidates(ranked, detail.excluded, scope, limit=P.DECIDE_MAX - (1 if wait else 0))
    by_input = {c.complex_id: c for c in inputs.complexes}
    pre = precalc or RequirementPrecalculator()
    cands = (
        [
            P.DecideCandidate(
                card=cards[cid], pre=pre.evaluate(by_input[cid], sc, asof_date=snap_dto.asof_date)
            )
            for cid in ids
        ]
        if len(ids) + (1 if wait else 0) >= 2
        else []
    )
    req = sc.requirements
    return DecidePlan(
        detail=detail,
        candidate_ids=ids,
        candidates=cands,
        requirements=(req.access.text, req.regulation.text, req.funds.text),
        priorities=priorities_text(sc),
        include_wait_new=wait,
        wait_new_evidence=wait_new_text if wait else None,
    )


# ---------------------------------------------------------------- 빌더


@dataclass(frozen=True, slots=True)
class PlannedCall:
    """판정기 호출 1건의 입력. payload=None 이면 앞 단계 판정이 캐시에 없어 아직 정할 수 없다(미스)."""

    tool: JudgeTool
    purpose: str
    payload: JudgePayload | None
    complex_id: int | None = None
    note: str | None = None

    def input_hash(self, adapter_version: str) -> str | None:
        if self.payload is None:
            return None
        return input_hash(self.tool, self.purpose, self.payload, adapter_version)


@dataclass
class ScenarioPlan:
    snapshot_id: int
    scenario_id: int
    adapter_version: str | None
    calls: list[PlannedCall] = field(default_factory=list)


def latest_adapter_version(session: Session) -> str | None:
    """마지막 judgment_log 행의 adapter_version(모델 접미 포함). 파이프라인이 다음에 쓸 버전의 최선 추정."""
    return session.scalars(
        select(JudgmentLog.adapter_version).order_by(JudgmentLog.seq.desc()).limit(1)
    ).first()


def _final_row(session: Session, key: str | None) -> JudgmentLog | None:
    if key is None:
        return None
    row = session.scalars(select(JudgmentLog).where(JudgmentLog.input_hash == key)).one_or_none()
    return row if row is not None and row.status != "error" else None


def _anchor_from(row: JudgmentLog) -> RerankAnchor:
    """캐시된 rerank 행 → 앵커(파이프라인 p7_rerank 와 같은 변환). 정규화 결과는 result_json(옛 행은 재정규화)."""
    result = row.result_json if isinstance(row.result_json, dict) and row.result_json else None
    if result is None:
        from app.judge.jev_mcp import normalize

        result = normalize("rerank", row.output_json or {}, row.input_json or {}, row.purpose).result
    items = [RerankItem.model_validate(i) for i in result.get("items", [])] if row.status == "ok" else []
    return RerankAnchor(judgment_seq=row.seq, status=row.status, items=items)


@dataclass(frozen=True, slots=True)
class _Unknown:
    """앞 단계(벤치마크 screen) 판정이 캐시에 없어 noul 입력을 정할 수 없다."""

    why: str


def _screen_verdict(row: JudgmentLog | None) -> str | None:
    if row is None:
        return None
    result = row.result_json if isinstance(row.result_json, dict) else {}
    v = result.get("verdict")
    return str(v) if isinstance(v, str) else None


def _planned_benchmark(
    session: Session, version: str | None, text: str | None, region_id: int
) -> tuple[list[PlannedCall], str | _Unknown | None]:
    """파이프라인 ``jp.p1_screen_benchmark`` 와 같은 호출(screen → skip 이면 다른 목적·입력 재screen)을 계획하고, 캐시 행의
    판정으로 noul 컨텍스트 ``benchmark`` 를 정한다(pass·ok = 텍스트, 그 밖 = 없음, 캐시 없음 = 모름)."""
    from app.judge.pipeline import benchmark_screen_purpose

    if not text:
        return [], None
    purpose = benchmark_screen_purpose(region_id)
    first = PlannedCall("screen", purpose, P.screen_payload(text, task=P.BENCHMARK_SCREEN_TASK))
    row = _final_row(session, first.input_hash(version)) if version else None
    if row is None:
        return [first], _Unknown("벤치마크 P1 screen 판정이 캐시에 없음")
    verdict = _screen_verdict(row)
    if verdict == "skip":
        retry = PlannedCall(
            "screen", f"{purpose}:retry"[:128],
            P.screen_payload(P.benchmark_rescreen_text(text), task=P.BENCHMARK_RESCREEN_TASK),
        )  # fmt: skip
        rrow = _final_row(session, retry.input_hash(version)) if version else None
        if rrow is None:
            return [first, retry], _Unknown("벤치마크 P1 재screen 판정이 캐시에 없음")
        return [first, retry], text if rrow.status == "ok" and _screen_verdict(rrow) == "pass" else None
    return [first], text if row.status == "ok" and verdict == "pass" else None


def scenario_payloads(
    session: Session,
    snapshot_id: int,
    scenario: ScenarioDTO,
    *,
    adapter_version: str | None = None,
) -> ScenarioPlan:
    """시나리오 1개 재판정의 판정 호출 목록(noul·rerank·decide). DB 를 읽기만 하고 판정기를 부르지 않는다."""
    snap = session.get(Snapshot, snapshot_id)
    if snap is None:
        raise LookupError(f"snapshot {snapshot_id} 없음")
    region = session.get(Region, snap.region_id)
    if region is None:
        raise LookupError(f"region {snap.region_id} 없음")
    version = adapter_version or latest_adapter_version(session)
    plan = ScenarioPlan(snapshot_id, scenario.id, version)
    facts = load_facts(session, snap, region)
    ji = judge_inputs(session, snap, region, facts)
    base, cards = ji.base, ji.cards
    # P6 noul — 판정 대상만(analysis.scope.runs_ladder, 파이프라인과 같은 규칙). 컨텍스트 = 카드 + 지역 벤치마크(P1 screen
    # 통과분 — 그 screen 판정이 캐시에 없으면 noul 입력을 정할 수 없다) + 제도
    ladder_facts = [f for f in facts if runs_ladder(f.scope)]
    bench: str | _Unknown | None = None
    if ladder_facts:
        screens, bench = _planned_benchmark(session, version, ji.benchmark_text(), region.id)
        plan.calls.extend(screens)
    for f in ladder_facts:
        card = cards[f.complex_id]
        text = P.evidence_card_text(card)
        for spec in P.ladder_specs(card, asof_date=snap.asof_date):
            if isinstance(bench, _Unknown):
                plan.calls.append(PlannedCall("noul", spec.purpose, None, f.complex_id, note=bench.why))
                continue
            payload = P.noul_payload(
                spec, card_text=text, benchmark_text=bench, policy_text=ji.policy_text(f)
            )
            plan.calls.append(PlannedCall("noul", spec.purpose, payload, f.complex_id))
    noul_all_hit = version is not None and all(_final_row(session, c.input_hash(version)) for c in plan.calls)
    scope = {f.complex_id: f.scope for f in facts}
    pool = rerank_pool(facts, cards, scope)
    anchor: RerankAnchor | None = EMPTY_ANCHOR
    if pool:
        rerank = PlannedCall("rerank", P.rerank_purpose(region_id=region.id), P.rerank_payload(pool))
        plan.calls.append(rerank)
        row = _final_row(session, rerank.input_hash(version)) if version else None
        anchor = _anchor_from(row) if row is not None else None
    purpose = P.decide_purpose(scenario.code or scenario.id)
    if anchor is None or not noul_all_hit:
        plan.calls.append(
            PlannedCall("decide", purpose, None, note="앞 단계(rerank·noul) 판정이 캐시에 없음")
        )
        return plan
    inputs = base.model_copy(update={"rerank": anchor})
    dp = decide_plan(
        snapshot_dto(snap),
        scenario,
        inputs,
        cards,
        scope,
        wait_new_text=wait_new_evidence(facts, snap.asof_date),
    )  # fmt: skip
    if dp.runnable:
        payload = P.decide_payload(
            scenario_name=scenario.name,
            requirements=dp.requirements,
            candidates=dp.candidates,
            priorities=dp.priorities,
            include_wait_new=dp.include_wait_new,
            wait_new_evidence=dp.wait_new_evidence,
        )
        plan.calls.append(PlannedCall("decide", purpose, payload))
    return plan


@dataclass(frozen=True, slots=True)
class CacheStatus:
    hits: int
    misses: int
    calls_by_tool: dict[str, int]  # 미스(판정기로 갈 호출) 도구별


def cache_status(
    session: Session, plan: ScenarioPlan, tools: Iterable[str] = ("decide", "noul", "rerank")
) -> CacheStatus:
    """계획의 각 호출: 같은 input_hash 의 최종(error 아님) judgment_log 행이 있으면 히트."""
    hits = 0
    misses: Counter[str] = Counter({t: 0 for t in tools})
    for c in plan.calls:
        key = c.input_hash(plan.adapter_version) if plan.adapter_version else None
        if _final_row(session, key) is not None:
            hits += 1
        else:
            misses[c.tool] += 1
    return CacheStatus(hits, sum(misses.values()), dict(misses))

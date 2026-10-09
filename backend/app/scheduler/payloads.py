"""시나리오 → 판정 payload 목록 (계약 2026-10-09.3, WP5-5) + 파이프라인과 공용인 입력 조립 단계.

``scenario_payloads(session, snapshot_id, scenario_id)`` 는 그 스냅샷에서 시나리오 1개를 재판정할 때
``pipeline.run_pipeline`` 이 판정기에 보낼 호출(P6 noul · P7 rerank · P8 decide)을 판정기를 부르지 않고 만든다.
``cache_status`` 는 각 호출의 input_hash(``core.protocols.input_hash``)로 judgment_log 최종 행이 있는지 본다 —
미리보기(WP5 ``/scenarios/{id}/preview``)의 cache_hits·cache_misses 가 이것이다.

정확성: payload 는 파이프라인과 **같은 함수**(``score_base``·``rerank_pool``·``decide_plan`` +
``judge.payloads``)로 만든다. decide 입력은 rerank 결과·사다리(앞 단계 판정)에 달려 있으므로, 앞 단계 호출이 하나라도
캐시에 없으면 decide payload 는 정할 수 없다(``payload=None`` = 미스로 센다 — 새 판정 결과가 들어가면 decide 입력도
바뀐다). 앞 단계가 전부 캐시면 decide payload 는 실행 때와 같다.

판정 범위(JudgeScope): 호출 대상은 ``inputs._scope``(제외/보류/판정 대상) — 판정 대상만 noul, 제외 아닌 단지 전부
rerank, 판정 대상만 decide 후보. 저장·표시 범위(score_total.judge_scope)는 ``stored_scope`` = 여기에 사다리 ok 행이
없는 판정 대상을 '참고'(순위만, meta §1-3-4)로 바꾼 것.
"""

# ruff: noqa: E501

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.scenarios import RequirementPrecalculator
from app.analysis.score import ScoreRunDetail, run_detailed
from app.core.contracts_gen import RerankAnchor, RerankItem, ScoreInputs
from app.core.contracts_gen import Scenario as ScenarioDTO
from app.core.contracts_gen import Snapshot as SnapshotDTO
from app.core.protocols import JudgePayload, JudgeTool, input_hash
from app.judge import payloads as P
from app.models import JudgmentLog, Ladder, Region, Snapshot
from app.scheduler.inputs import (
    ComplexFacts,
    JudgeScope,
    age_coef,
    build_score_inputs,
    evidence_card,
    gap_of,
    load_facts,
)

__all__ = [
    "PlannedCall",
    "ScenarioPlan",
    "cache_status",
    "decide_plan",
    "rerank_pool",
    "scenario_payloads",
    "score_base",
    "stored_scope",
]

EMPTY_ANCHOR = RerankAnchor(judgment_seq=None, status="review", items=[])


# ---------------------------------------------------------------- 파이프라인과 공용 단계


def stored_scope(session: Session, snapshot_id: int, facts: Sequence[ComplexFacts]) -> dict[int, JudgeScope]:
    """저장·표시 판정 범위: 사다리 ok 행이 없는 '판정 대상' → '참고'(순위만, meta §1-3-4). facts 는 그대로."""
    ok = set(
        session.scalars(
            select(Ladder.complex_id).where(Ladder.snapshot_id == snapshot_id, Ladder.status == "ok")
        )
    )
    return {
        f.complex_id: ("참고" if f.scope == "판정 대상" and f.complex_id not in ok else f.scope)
        for f in facts
    }


def score_base(
    session: Session, snap: Snapshot, region: Region, facts: Sequence[ComplexFacts]
) -> tuple[ScoreInputs, dict[int, P.EvidenceCard]]:
    """앵커 없는 ScoreInputs + 단지별 증거 카드(가격 갭 포함) — rerank·decide 입력."""
    base = build_score_inputs(session, snap, region, facts, EMPTY_ANCHOR)
    coef = age_coef(region)
    gaps = {
        f.complex_id: gap_of(f, base.trades, asof_date=snap.asof_date, coef=coef)
        for f in facts
        if f.scope != "제외"
    }
    cards = {f.complex_id: evidence_card(f, gap=gaps.get(f.complex_id)) for f in facts}
    return base, cards


def rerank_pool(
    facts: Sequence[ComplexFacts], cards: Mapping[int, P.EvidenceCard], scope: Mapping[int, str]
) -> list[P.EvidenceCard]:
    """P7 후보군 = 제외가 아닌 단지 전부(complex_id 순)."""
    return [cards[f.complex_id] for f in facts if scope.get(f.complex_id) != "제외"]


def decide_candidates(
    ranked: Mapping[int, int | None], excluded: frozenset[int], scope: Mapping[int, str]
) -> list[int]:
    """판정 대상 중 시나리오 제외(D: 접수 가능 아님)를 뺀 상위 ≤6 — 순위(점수 없으면 complex_id) 순."""
    ids = [cid for cid, s in scope.items() if s == "판정 대상" and cid not in excluded]
    ids.sort(key=lambda cid: (ranked.get(cid) is None, ranked.get(cid) or 0, cid))
    return ids[: P.DECIDE_MAX]


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

    @property
    def runnable(self) -> bool:
        return len(self.candidates) >= 2


def decide_plan(
    snap_dto: SnapshotDTO,
    sc: ScenarioDTO,
    inputs: ScoreInputs,
    cards: Mapping[int, P.EvidenceCard],
    scope: Mapping[int, str],
    *,
    precalc: RequirementPrecalculator | None = None,
) -> DecidePlan:
    """점수(시나리오 1개) → P8 decide 후보 ≤6 + 요건 사전 계산."""
    detail = run_detailed(snap_dto, sc, inputs)
    ranked = {t.complex_id: t.rank for t in detail.result.totals}
    ids = decide_candidates(ranked, detail.excluded, scope)
    by_input = {c.complex_id: c for c in inputs.complexes}
    pre = precalc or RequirementPrecalculator()
    cands = (
        [
            P.DecideCandidate(
                card=cards[cid], pre=pre.evaluate(by_input[cid], sc, asof_date=snap_dto.asof_date)
            )
            for cid in ids
        ]
        if len(ids) >= 2
        else []
    )
    req = sc.requirements
    return DecidePlan(
        detail=detail,
        candidate_ids=ids,
        candidates=cands,
        requirements=(req.access.text, req.regulation.text, req.funds.text),
        priorities=priorities_text(sc),
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
    # P6 noul — 판정 대상(정제 전 범위: 파이프라인도 사다리를 만든 뒤 참고를 가린다)
    for f in facts:
        if f.scope != "판정 대상":
            continue
        card = evidence_card(f)
        text = P.evidence_card_text(card)
        for spec in P.ladder_specs(card, asof_date=snap.asof_date):
            plan.calls.append(
                PlannedCall("noul", spec.purpose, P.noul_payload(spec, card_text=text), f.complex_id)
            )
    noul_all_hit = version is not None and all(_final_row(session, c.input_hash(version)) for c in plan.calls)
    scope = {f.complex_id: f.scope for f in facts}
    base, cards = score_base(session, snap, region, facts)
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
        SnapshotDTO(
            id=snap.id, region_id=snap.region_id, asof_date=snap.asof_date, status=snap.status,
            degraded=bool(snap.degraded), created_at=snap.created_at, published_at=snap.published_at,
        ),
        scenario,
        inputs,
        cards,
        scope,
    )  # fmt: skip
    if dp.runnable:
        payload = P.decide_payload(
            scenario_name=scenario.name,
            requirements=dp.requirements,
            candidates=dp.candidates,
            priorities=dp.priorities,
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

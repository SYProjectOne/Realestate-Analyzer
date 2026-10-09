"""파생 테이블 쓰기 (RA §3 스냅샷 규칙: snapshot_id 별로 쌓고 지우지 않는다).

- ladder: (snapshot, complex, horizon) 유일 → 같은 스냅샷 재판정이면 갱신.
- score_run / score_component / score_total / decision: 실행마다 새 run(prev_score_run_id 로 이전 run 연결).
- claim: 같은 (snapshot, section, complex, text)면 새 행 없이 verify_status·judgment_seq 갱신.
- comparable_set: (snapshot, complex)에 행이 없을 때만(비교군 기록).
- 판정 seq FK(judgment_log.seq): 행이 없으면(MockAdapter 녹화 재생 — DB에 쓰지 않음) None 으로 둔다.
- ``carry_forward``: 변경 없는 날(T8) — 이전 스냅샷의 파생 행을 그대로 복사(판정기 호출 0).
"""

# ruff: noqa: E501  (한국어 docstring·로그 필드)

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.scenarios import requirement_mismatch
from app.analysis.score import ScoreRunDetail, decide_outcome, weighted_total
from app.analysis.sensitivity import weights_map
from app.analysis.types import GapResult
from app.core.contracts_gen import Claim as ClaimDTO
from app.core.contracts_gen import DecisionSet, Fact, LadderRow, RequirementPre
from app.models import (
    Claim,
    ComparableSet,
    Decision,
    IntakeStatus,
    JudgmentLog,
    Ladder,
    ScoreComponent,
    ScoreRun,
    ScoreTotal,
)

__all__ = [
    "SeqResolver",
    "carry_forward",
    "copy_claims",
    "copy_intake",
    "copy_ladders",
    "save_claims",
    "save_comparables",
    "save_decisions",
    "save_ladders",
    "save_score_run",
    "to_dec",
]

_Q4 = Decimal("0.0001")


def to_dec(v: float | Decimal | None, q: Decimal = _Q4) -> Decimal | None:
    if v is None:
        return None
    return Decimal(str(v)).quantize(q, rounding=ROUND_HALF_UP)


def _fact_v(f: Fact | None) -> Decimal | None:
    if f is None or f.v is None or isinstance(f.v, str):
        return None
    return to_dec(f.v)


class SeqResolver:
    """judgment_seq → DB 에 있는 seq 만(FK). 한 세션 안에서 결과를 기억한다."""

    def __init__(self, session: Session) -> None:
        self._s = session
        self._known: dict[int, bool] = {}

    def __call__(self, seq: int | None) -> int | None:
        if seq is None:
            return None
        if seq not in self._known:
            self._known[seq] = self._s.get(JudgmentLog, seq) is not None
        return seq if self._known[seq] else None


# ---------------------------------------------------------------- ladder


def save_ladders(session: Session, snapshot_id: int, rows: Iterable[LadderRow], seq: SeqResolver) -> int:
    n = 0
    for r in rows:
        existing = session.scalars(
            select(Ladder).where(
                Ladder.snapshot_id == snapshot_id,
                Ladder.complex_id == r.complex_id,
                Ladder.horizon == r.horizon,
            )
        ).first()
        row = existing or Ladder(snapshot_id=snapshot_id, complex_id=r.complex_id, horizon=r.horizon)
        row.target_ym = r.target_ym
        row.months_from_asof = r.months_from_asof
        row.p5, row.p10, row.p20, row.p_flat = (
            _fact_v(r.p5),
            _fact_v(r.p10),
            _fact_v(r.p20),
            _fact_v(r.p_flat),
        )
        row.verdicts = r.verdicts.model_dump()
        row.annualized = r.annualized.model_dump()
        row.status = r.status
        row.judgment_seq = seq(r.judgment_seq)
        row.proposition_text = r.proposition_text
        if existing is None:
            session.add(row)
        n += 1
    session.flush()
    return n


def copy_ladders(
    session: Session, src_snapshot_id: int, dst_snapshot_id: int, complex_ids: Iterable[int]
) -> int:
    """dst 에 사다리가 없는 단지만 src 에서 복사(재판정 대상이 아닌 단지 — 이전 판정 그대로)."""
    ids = list(complex_ids)
    if not ids:
        return 0
    have = {
        (c, h)
        for c, h in session.execute(
            select(Ladder.complex_id, Ladder.horizon).where(
                Ladder.snapshot_id == dst_snapshot_id, Ladder.complex_id.in_(ids)
            )
        )
    }
    n = 0
    for src in session.scalars(
        select(Ladder).where(Ladder.snapshot_id == src_snapshot_id, Ladder.complex_id.in_(ids))
    ):
        if (src.complex_id, src.horizon) in have:
            continue
        session.add(
            Ladder(
                snapshot_id=dst_snapshot_id,
                complex_id=src.complex_id,
                horizon=src.horizon,
                target_ym=src.target_ym,
                months_from_asof=src.months_from_asof,
                p5=src.p5,
                p10=src.p10,
                p20=src.p20,
                p_flat=src.p_flat,
                verdicts=dict(src.verdicts or {}),
                annualized=dict(src.annualized or {}),
                status=src.status,
                judgment_seq=src.judgment_seq,
                proposition_text=src.proposition_text,
            )
        )
        n += 1
    session.flush()
    return n


# ---------------------------------------------------------------- score


def _prev_run(
    session: Session, snapshot_id: int, scenario_id: int, before_asof_ids: Sequence[int]
) -> int | None:
    stmt = select(ScoreRun.id).where(ScoreRun.scenario_id == scenario_id)
    same = session.scalars(
        stmt.where(ScoreRun.snapshot_id == snapshot_id).order_by(ScoreRun.id.desc())
    ).first()
    if same is not None:
        return same
    for sid in before_asof_ids:  # 이전 스냅샷(최근 것부터)
        run = session.scalars(stmt.where(ScoreRun.snapshot_id == sid).order_by(ScoreRun.id.desc())).first()
        if run is not None:
            return run
    return None


def save_score_run(
    session: Session,
    detail: ScoreRunDetail,
    *,
    created_at: str,
    seq: SeqResolver,
    previous_snapshot_ids: Sequence[int] = (),
    scopes: Mapping[int, str] | None = None,
) -> ScoreRun:
    """score_run + component + total. ``scopes`` = 이 실행의 판정 범위 → score_total.judge_scope(계약 2026-10-09.3)."""
    res = detail.result
    run = ScoreRun(
        snapshot_id=res.snapshot_id,
        scenario_id=res.scenario_id,
        weights={k: v for k, v in res.weights.model_dump().items() if v is not None},
        rerank_judgment_seq=seq(res.rerank_judgment_seq),
        prev_score_run_id=_prev_run(session, res.snapshot_id, res.scenario_id, previous_snapshot_ids),
        created_at=created_at,
    )
    session.add(run)
    session.flush()
    for c in res.components:
        session.add(
            ScoreComponent(
                score_run_id=run.id,
                complex_id=c.complex_id,
                component=c.component,
                raw_value=to_dec(c.raw_value, Decimal("0.000001")),
                score_0_10=to_dec(c.score_0_10, Decimal("0.001")),
                formula_text=c.formula_text,
                label=c.label,
                reason=(c.reason or None) and str(c.reason)[:120],
                delta=to_dec(c.delta),
                flags=list(c.flags or []),
            )
        )
    weights = weights_map(res.weights)
    for t in res.totals:
        comps = detail.components.get(t.complex_id, {})
        exact = weighted_total({k: r.score for k, r in comps.items()}, weights) if comps else None
        session.add(
            ScoreTotal(
                score_run_id=run.id,
                complex_id=t.complex_id,
                total=to_dec(exact if exact is not None else t.total),
                rank=t.rank,
                tie_group=t.tie_group,
                unstable=bool(t.unstable),
                judge_scope=(scopes or {}).get(t.complex_id),
            )
        )
    session.flush()
    return run


def save_comparables(session: Session, snapshot_id: int, gaps: dict[int, GapResult]) -> int:
    n = 0
    for cid, g in sorted(gaps.items()):
        exists = session.scalars(
            select(ComparableSet.id).where(
                ComparableSet.snapshot_id == snapshot_id, ComparableSet.complex_id == cid
            )
        ).first()
        if exists is not None:
            continue
        for m in g.members:
            session.add(
                ComparableSet(
                    complex_id=cid,
                    snapshot_id=snapshot_id,
                    member_apt_name=m.member_apt_name,
                    completed_year=m.completed_year,
                    substitute=m.substitute,
                    adjusted=m.adjusted,
                    coef_used=m.coef_used,
                    n_trades=m.n_trades,
                    low_won=m.low_won,
                    median_won=m.median_won,
                    adjusted_median_won=m.adjusted_median_won,
                    high_won=m.high_won,
                    outliers_excluded=m.outliers_excluded,
                    excluded_reason=(m.excluded_reason or None) and m.excluded_reason[:64],
                    note=m.note,
                )
            )
            n += 1
    session.flush()
    return n


# ---------------------------------------------------------------- decision


def _pre_json(pre: RequirementPre | None) -> dict[str, Any] | None:
    return pre.model_dump() if pre is not None else None


def save_decisions(session: Session, run: ScoreRun, dset: DecisionSet, seq: SeqResolver) -> list[Decision]:
    """DecisionSet → decision 행. chosen·tie 는 ``analysis.score.decide_outcome`` 이 원본(판정기 쪽 표시 규칙과
    중복 계산하지 않는다). mismatch 는 ``analysis.scenarios.requirement_mismatch``."""

    def key(d: Any) -> str:
        return f"complex:{d.complex_id}" if d.option_key == "complex" else str(d.option_key)

    probs = {key(d): float(d.prob.v) for d in dset.items if isinstance(d.prob.v, int | float)}
    selected = next((key(d) for d in dset.items if d.chosen), None)
    conf = (
        float(dset.confidence.v)
        if dset.confidence is not None and isinstance(dset.confidence.v, int | float)
        else None
    )
    outcome = {
        o.key: o for o in decide_outcome(status=dset.status, confidence=conf, probs=probs, selected=selected)
    }
    out: list[Decision] = []
    for d in dset.items:
        k = key(d)
        o = outcome.get(k)
        req = d.requirements
        pre = {name: getattr(req, name).pre if req else None for name in ("access", "regulation", "funds")}
        judge = {
            name: getattr(req, name).judge if req else None for name in ("access", "regulation", "funds")
        }
        mismatch = any(requirement_mismatch(p.status if p else None, judge[name]) for name, p in pre.items())
        row = Decision(
            score_run_id=run.id,
            scenario_id=dset.scenario_id,
            complex_id=d.complex_id,
            option_key=d.option_key,
            prob=_fact_v(d.prob),
            chosen=bool(o.chosen) if o else False,
            tie=bool(o.tie) if o else False,
            req_access_pre=_pre_json(pre["access"]),
            req_regulation_pre=_pre_json(pre["regulation"]),
            req_funds_pre=_pre_json(pre["funds"]),
            req_access_judge=judge["access"],
            req_regulation_judge=judge["regulation"],
            req_funds_judge=judge["funds"],
            mismatch=mismatch,
            confidence=to_dec(conf),
            warnings=list(dset.warnings),
            judgment_seq=seq(d.judgment_seq),
        )
        session.add(row)
        out.append(row)
    session.flush()
    return out


# ---------------------------------------------------------------- claim


def save_claims(session: Session, claims: Iterable[ClaimDTO], seq: SeqResolver) -> list[Claim]:
    out: list[Claim] = []
    for c in claims:
        if c.snapshot_id is None:
            continue
        stmt = select(Claim).where(
            Claim.snapshot_id == c.snapshot_id, Claim.section == c.section, Claim.text == c.text
        )
        stmt = stmt.where(
            Claim.complex_id.is_(None) if c.complex_id is None else Claim.complex_id == c.complex_id
        )
        row = session.scalars(stmt).first()
        if row is None:
            row = Claim(snapshot_id=c.snapshot_id, section=c.section, complex_id=c.complex_id, text=c.text)
            session.add(row)
        row.evidence_text = c.evidence_text
        row.verify_status = c.verify_status
        row.judgment_seq = seq(c.judgment_seq)
        row.ordinal = c.ordinal
        out.append(row)
    session.flush()
    return out


def copy_claims(
    session: Session, src_snapshot_id: int, dst_snapshot_id: int, complex_ids: Iterable[int] | None
) -> int:
    """dst 에 주장이 없는 단지(None 이면 전부)만 src 주장을 복사."""
    stmt = select(Claim).where(Claim.snapshot_id == src_snapshot_id)
    ids = None if complex_ids is None else list(complex_ids)
    if ids is not None:
        if not ids:
            return 0
        stmt = stmt.where(Claim.complex_id.in_(ids))
    have = {
        c
        for (c,) in session.execute(
            select(Claim.complex_id).where(Claim.snapshot_id == dst_snapshot_id).distinct()
        )
    }
    n = 0
    for src in session.scalars(stmt.order_by(Claim.id)):
        if src.complex_id in have:
            continue
        session.add(
            Claim(
                snapshot_id=dst_snapshot_id,
                section=src.section,
                complex_id=src.complex_id,
                text=src.text,
                evidence_text=src.evidence_text,
                verify_status=src.verify_status,
                judgment_seq=src.judgment_seq,
                ordinal=src.ordinal,
            )
        )
        n += 1
    session.flush()
    return n


# ---------------------------------------------------------------- intake


def copy_intake(session: Session, src_snapshot_id: int, dst_snapshot_id: int) -> int:
    """dst 에 (단지, 경로) 행이 없으면 src 의 그 경로 최신 행을 복사(확인 시각 유지 — D±로 낡음이 보인다)."""
    have = {
        (c, p)
        for c, p in session.execute(
            select(IntakeStatus.complex_id, IntakeStatus.path).where(
                IntakeStatus.snapshot_id == dst_snapshot_id
            )
        )
    }
    latest: dict[tuple[int, str], IntakeStatus] = {}
    for r in session.scalars(
        select(IntakeStatus).where(IntakeStatus.snapshot_id == src_snapshot_id).order_by(IntakeStatus.id)
    ):
        latest[(r.complex_id, r.path)] = r
    n = 0
    for (cid, path), r in sorted(latest.items()):
        if (cid, path) in have:
            continue
        session.add(
            IntakeStatus(
                complex_id=cid,
                snapshot_id=dst_snapshot_id,
                status=r.status,
                path=path,
                evidence_url=r.evidence_url,
                screenshot_path=r.screenshot_path,
                raw_document_id=r.raw_document_id,
                http_status=r.http_status,
                checked_at=r.checked_at,
                reason=r.reason,
                note=r.note,
                entered_by=r.entered_by,
            )
        )
        n += 1
    session.flush()
    return n


# ---------------------------------------------------------------- 변경 없는 날


def carry_forward(
    session: Session, src_snapshot_id: int, dst_snapshot_id: int, *, created_at: str
) -> dict[str, int]:
    """이전 스냅샷의 판정·점수 파생 행을 그대로 복사한다(같은 사실 = 같은 판정, 판정기 호출 0 — T8).

    score_run 은 시나리오마다 src 의 마지막 run 을 복사하고 prev_score_run_id 로 원본을 가리킨다.
    """
    stats = {"ladder": 0, "score_run": 0, "decision": 0, "claim": 0, "comparable_set": 0}
    cids = [
        c
        for (c,) in session.execute(
            select(Ladder.complex_id).where(Ladder.snapshot_id == src_snapshot_id).distinct()
        )
    ]
    stats["ladder"] = copy_ladders(session, src_snapshot_id, dst_snapshot_id, cids)
    stats["claim"] = copy_claims(session, src_snapshot_id, dst_snapshot_id, None)
    latest: dict[int, ScoreRun] = {}
    for run in session.scalars(
        select(ScoreRun).where(ScoreRun.snapshot_id == src_snapshot_id).order_by(ScoreRun.id)
    ):
        latest[run.scenario_id] = run
    for scenario_id, src in sorted(latest.items()):
        dst = ScoreRun(
            snapshot_id=dst_snapshot_id,
            scenario_id=scenario_id,
            weights=dict(src.weights or {}),
            rerank_judgment_seq=src.rerank_judgment_seq,
            prev_score_run_id=src.id,
            created_at=created_at,
        )
        session.add(dst)
        session.flush()
        stats["score_run"] += 1
        for c in session.scalars(select(ScoreComponent).where(ScoreComponent.score_run_id == src.id)):
            session.add(
                ScoreComponent(
                    score_run_id=dst.id,
                    complex_id=c.complex_id,
                    component=c.component,
                    raw_value=c.raw_value,
                    score_0_10=c.score_0_10,
                    formula_text=c.formula_text,
                    label=c.label,
                    reason=c.reason,
                    delta=c.delta,
                    flags=list(c.flags or []),
                )
            )
        for t in session.scalars(select(ScoreTotal).where(ScoreTotal.score_run_id == src.id)):
            session.add(
                ScoreTotal(
                    score_run_id=dst.id,
                    complex_id=t.complex_id,
                    total=t.total,
                    rank=t.rank,
                    tie_group=t.tie_group,
                    unstable=t.unstable,
                    judge_scope=t.judge_scope,
                )
            )
        for d in session.scalars(select(Decision).where(Decision.score_run_id == src.id)):
            session.add(
                Decision(
                    score_run_id=dst.id,
                    scenario_id=d.scenario_id,
                    complex_id=d.complex_id,
                    option_key=d.option_key,
                    prob=d.prob,
                    chosen=d.chosen,
                    tie=d.tie,
                    req_access_pre=d.req_access_pre,
                    req_regulation_pre=d.req_regulation_pre,
                    req_funds_pre=d.req_funds_pre,
                    req_access_judge=d.req_access_judge,
                    req_regulation_judge=d.req_regulation_judge,
                    req_funds_judge=d.req_funds_judge,
                    mismatch=d.mismatch,
                    confidence=d.confidence,
                    warnings=list(d.warnings or []),
                    judgment_seq=d.judgment_seq,
                )
            )
            stats["decision"] += 1
    for cs in session.scalars(select(ComparableSet).where(ComparableSet.snapshot_id == src_snapshot_id)):
        session.add(
            ComparableSet(
                complex_id=cs.complex_id,
                snapshot_id=dst_snapshot_id,
                member_apt_name=cs.member_apt_name,
                completed_year=cs.completed_year,
                substitute=cs.substitute,
                adjusted=cs.adjusted,
                coef_used=cs.coef_used,
                n_trades=cs.n_trades,
                low_won=cs.low_won,
                median_won=cs.median_won,
                adjusted_median_won=cs.adjusted_median_won,
                high_won=cs.high_won,
                outliers_excluded=cs.outliers_excluded,
                excluded_reason=cs.excluded_reason,
                note=cs.note,
            )
        )
        stats["comparable_set"] += 1
    session.flush()
    return stats

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

from collections.abc import Callable, Iterable, Mapping, Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.gap import is_unadjusted_tag, unadjusted_from_flags
from app.analysis.scenarios import requirement_mismatch
from app.analysis.scope import INTAKE_PRIORITY, pick_intake
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
    "COLLECTED_INTAKE_PATHS",
    "SeqResolver",
    "carry_forward",
    "copy_claims",
    "copy_intake",
    "copy_ladders",
    "copy_runs",
    "save_claims",
    "save_comparables",
    "save_decisions",
    "save_ladders",
    "save_score_run",
    "to_dec",
]

_Q4 = Decimal("0.0001")
COLLECTED_INTAKE_PATHS: Final = frozenset({"official_popup", "headless_shot"})
"""공식 홈페이지 수집(``collect.intake_rows``)이 만드는 접수 행 경로 — ``scheduler.intake.INTAKE_PATHS`` 와 같다."""


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
        # 미보정 갭%·중앙값(gap 성분): 엔진이 flags 태그로 싣는다 → 계약 2026-10-09.4 컬럼에 저장(R3 W7)
        un_gap, un_median = unadjusted_from_flags(c.flags)
        session.add(
            ScoreComponent(
                score_run_id=run.id,
                complex_id=c.complex_id,
                component=c.component,
                raw_value=to_dec(c.raw_value, Decimal("0.000001")),
                score_0_10=to_dec(c.score_0_10),  # 엔진 정밀도 4자리(analysis.score.SCORE_DECIMALS, R3 W12b)
                formula_text=c.formula_text,
                label=c.label,
                reason=(c.reason or None) and str(c.reason)[:120],
                delta=to_dec(c.delta),
                flags=[f for f in c.flags or [] if not is_unadjusted_tag(f)],
                unadjusted_gap_pct=to_dec(un_gap, Decimal("0.000001")) if un_gap is not None else None,
                unadjusted_median_won=un_median,
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
    # 점수 밖 단지(미해결·제외)도 이 실행의 판정 범위를 남긴다(총점·순위 없음) — 화면·KPI 는 저장값만 보인다(D10-1)
    scored = {t.complex_id for t in res.totals}
    for cid, scope in sorted((scopes or {}).items()):
        if cid not in scored:
            session.add(
                ScoreTotal(
                    score_run_id=run.id, complex_id=cid, total=None, rank=None, tie_group=None,
                    unstable=False, judge_scope=scope,
                )
            )  # fmt: skip
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
        # 주장이 생성된 DB 사실(계약 2026-10-09.6, D10-3) — P9 사실 문장 주장만
        row.entity, row.entity_id, row.field = c.entity, c.entity_id, c.field
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
    # 분할 재검증 연결(parent_claim_id)도 새 id 로 옮긴다 — 끊기면 해결된 contradicted 가 다시 '남은' 것이 되어
    # publish 가 막힌다(R3 M8). 부모가 자식보다 먼저 만들어지므로 id 순서로 대응표를 채운다.
    new_ids: dict[int, int] = {}
    for src in session.scalars(stmt.order_by(Claim.id)):
        if src.complex_id in have:
            continue
        row = Claim(
            snapshot_id=dst_snapshot_id,
            section=src.section,
            complex_id=src.complex_id,
            text=src.text,
            evidence_text=src.evidence_text,
            verify_status=src.verify_status,
            judgment_seq=src.judgment_seq,
            parent_claim_id=new_ids.get(src.parent_claim_id) if src.parent_claim_id is not None else None,
            ordinal=src.ordinal,
            entity=src.entity,
            entity_id=src.entity_id,
            field=src.field,
        )
        session.add(row)
        session.flush()
        new_ids[src.id] = row.id
        n += 1
    session.flush()
    return n


# ---------------------------------------------------------------- intake


def copy_intake(session: Session, src_snapshot_id: int, dst_snapshot_id: int) -> int:
    """dst 에 (단지, 경로) 행이 없으면 src 의 그 경로 표시 행을 복사(확인 시각 유지 — D±로 낡음이 보인다).

    경로 안에서 고르는 기준은 ``analysis.scope.pick_intake``(확인 날짜 → id)와 같다 — id 만 보면 src 에서 표시되던 행과
    다른 행을 복사해 가짜 D9-3 접수 변경 이벤트가 생긴다(R3 재리뷰 F2).

    R7-FIX: dst 에 그 단지의 **수집 관측 행**(경로 official_popup·headless_shot + 원문 행 — 오늘 ``collect.intake_rows`` 가 만든
    행)이 이미 있으면, src 의 **수집 실패 행**(원문 있음, 응답 200 아님 — 'TLS'·'403' 등) 중 오늘 관측에 없는 원문을 가리키는 행은
    어느 경로든 복사하지 않는다 — 오늘 관측이 어제 실패를 대신한다. 예전에는 (단지, 경로) 단위로만 보아, 어제 실패 행(경로
    official_popup)이 오늘 성공 행(렌더 → headless_shot) 옆에 복사되고 표시 규칙(official_popup > headless_shot)이 낡은 실패 행을
    골랐다(인천 스냅샷 2 — 단지 7·8·22·37·38·72·75·87). 성공 행(분류된 팝업 근거 — 회귀 픽스처의 official_popup 행 등)·원문 없는
    적재 행·사람 확인(human_check)·비공식 참고(unofficial_ref) 행은 예전처럼 복사한다(T8 — 변경 없는 날·팝업 변경일 이벤트 수
    불변). 새 리비전(``snapshots.new_revision`` — dst 가 빈 스냅샷)은 전부 복사(변화 없음)."""
    have: set[tuple[int, str]] = set()
    observed: dict[int, set[int]] = {}
    for c, p, raw_id in session.execute(
        select(IntakeStatus.complex_id, IntakeStatus.path, IntakeStatus.raw_document_id).where(
            IntakeStatus.snapshot_id == dst_snapshot_id
        )
    ):
        have.add((c, p))
        if p in COLLECTED_INTAKE_PATHS and raw_id is not None:
            observed.setdefault(c, set()).add(raw_id)
    grouped: dict[tuple[int, str], list[IntakeStatus]] = {}
    for r in session.scalars(
        select(IntakeStatus).where(IntakeStatus.snapshot_id == src_snapshot_id).order_by(IntakeStatus.id)
    ):
        grouped.setdefault((r.complex_id, r.path), []).append(r)
    latest: dict[tuple[int, str], IntakeStatus] = {}
    for key, rows in grouped.items():
        picked = pick_intake(rows) if key[1] in INTAKE_PRIORITY else max(rows, key=lambda x: x.id)
        if picked is not None:
            latest[key] = picked
    n = 0
    for (cid, path), r in sorted(latest.items()):
        if (cid, path) in have:
            continue
        today = observed.get(cid)
        if (
            path in COLLECTED_INTAKE_PATHS
            and r.raw_document_id is not None
            and r.http_status != 200
            and today
            and r.raw_document_id not in today
        ):
            continue  # 어제 수집 실패 — 오늘 다른 원문을 관측했다(실패 행을 오늘 관측 옆에 두지 않는다)
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


def _copy_rows_sql(session: Session, model: Any, src_run_id: int, dst_run_id: int) -> None:
    """``model``(score_run_id 를 가진 점수 행) 의 src 실행 행을 dst 실행으로 복사(id 는 새로, 나머지 열 그대로)."""
    from sqlalchemy import insert, literal

    table = model.__table__
    cols = [c for c in table.columns if c.key not in ("id", "score_run_id")]
    sel = select(literal(dst_run_id).label("score_run_id"), *cols).where(table.c.score_run_id == src_run_id)
    session.flush()
    session.execute(insert(table).from_select(["score_run_id", *[c.key for c in cols]], sel))


def copy_runs(
    session: Session,
    src_snapshot_id: int,
    dst_snapshot_id: int,
    *,
    created_at: str,
    scenario_ids: Iterable[int] | None = None,
    checkpoint: Callable[[], None] | None = None,
) -> tuple[int, int]:
    """src 의 시나리오별 마지막 score_run(+component·total·decision)을 dst 로 복사(prev_score_run_id = 원본). dst 에 그
    시나리오 run 이 이미 있으면 건너뛴다. ``scenario_ids`` = 복사할 시나리오(없으면 전부). 반환 (run 수, decision 수).

    변경 없는 날(T8)·시나리오 지정 재판정의 새 리비전(D11-1 — 다른 시나리오의 저장 결과가 새 리비전에도 있어야 한다)."""
    stats = {"score_run": 0, "decision": 0}
    want = set(scenario_ids) if scenario_ids is not None else None
    have = set(session.scalars(select(ScoreRun.scenario_id).where(ScoreRun.snapshot_id == dst_snapshot_id)))
    latest: dict[int, ScoreRun] = {}
    for run in session.scalars(
        select(ScoreRun).where(ScoreRun.snapshot_id == src_snapshot_id).order_by(ScoreRun.id)
    ):
        latest[run.scenario_id] = run
    for scenario_id, src in sorted(latest.items()):
        if scenario_id in have or (want is not None and scenario_id not in want):
            continue
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
        # 성분·총점은 DB 안에서 한 문장으로 복사한다(INSERT … SELECT — 1000 단지 × 성분 7 을 ORM 으로 옮기면 그동안 쓰기 잠금이
        # 수 초, D14-5 'API 쓰기 잠금 1초 이하'). 값·순서는 ORM 복사와 같다(같은 SELECT)
        _copy_rows_sql(session, ScoreComponent, src.id, dst.id)
        _copy_rows_sql(session, ScoreTotal, src.id, dst.id)
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
        if (
            checkpoint is not None
        ):  # 시나리오 하나 = 한 트랜잭션(run·성분·총점·결정이 함께 — 다시 돌면 그 시나리오는 건너뛴다)
            session.flush()
            checkpoint()
    session.flush()
    return stats["score_run"], stats["decision"]


def carry_incomplete(session: Session, src_snapshot_id: int, dst_snapshot_id: int) -> bool:
    """dst 의 점수 실행이 모두 src 에서 복사한 것인데 src 의 시나리오 일부만 있다 = 나눠 하던 이월 복사가 중간에 멈췄다(R3h
    D14-5 — 이월 복사를 짧은 트랜잭션 여러 개로 나눈 뒤의 재시도 판단)."""
    src_runs = {
        int(r.id): int(r.scenario_id)
        for r in session.scalars(select(ScoreRun).where(ScoreRun.snapshot_id == src_snapshot_id))
    }
    dst = list(session.scalars(select(ScoreRun).where(ScoreRun.snapshot_id == dst_snapshot_id)))
    if not dst or any(r.prev_score_run_id not in src_runs for r in dst):
        return False
    return {int(r.scenario_id) for r in dst} < set(src_runs.values())


def carry_done(session: Session, src_snapshot_id: int, dst_snapshot_id: int) -> bool:
    """R3i D17-3: dst 의 점수 실행이 **이월 복사로만** 이루어졌고 src 의 시나리오를 모두 덮었다(= 이월 복사가 끝났다). src 에 실행이
    없으면 dst 도 없을 때 끝. dst 에 이월이 아닌 실행(재판정이 쓴 것)이 있으면 False — 그 판정이 발행한다."""
    src_runs = {
        int(r.id): int(r.scenario_id)
        for r in session.scalars(select(ScoreRun).where(ScoreRun.snapshot_id == src_snapshot_id))
    }
    dst = list(session.scalars(select(ScoreRun).where(ScoreRun.snapshot_id == dst_snapshot_id)))
    if not src_runs:
        return not dst
    if not dst or any(r.prev_score_run_id not in src_runs for r in dst):
        return False
    return {int(r.scenario_id) for r in dst} >= set(src_runs.values())


def carry_forward(
    session: Session,
    src_snapshot_id: int,
    dst_snapshot_id: int,
    *,
    created_at: str,
    checkpoint: Callable[[], None] | None = None,
) -> dict[str, int]:
    """이전 스냅샷의 판정·점수 파생 행을 그대로 복사한다(같은 사실 = 같은 판정, 판정기 호출 0 — T8).

    score_run 은 시나리오마다 src 의 마지막 run 을 복사하고 prev_score_run_id 로 원본을 가리킨다.

    ``checkpoint``(R3h D14-5 'API 쓰기 대기 1초'): 주면 단계마다(사다리·주장 → 비교군 → 시나리오 하나씩) 부른다 — 호출자가
    commit 해 쓰기 잠금을 짧게 나눈다. 단계마다 이미 있는 것은 건너뛰므로(사다리·주장·비교군·그 시나리오 run) 중간에 멈춘 복사를
    다시 불러도 이어서 채운다(점수 실행이 마지막 — 완료 판단은 ``carry_incomplete``).
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
    if checkpoint is not None:
        session.flush()
        checkpoint()
    # 비교군은 DB 안에서 한 문장으로(INSERT … SELECT — 1000 단지면 ORM 복사 동안 쓰기 잠금이 길다, D14-5 'API 쓰기 대기 1초')
    from sqlalchemy import func as sa_func
    from sqlalchemy import insert, literal

    table: Any = ComparableSet.__table__
    cols = [c for c in table.columns if c.key not in ("id", "snapshot_id")]
    session.flush()
    stats["comparable_set"] = int(
        session.scalar(
            select(sa_func.count()).select_from(table).where(table.c.snapshot_id == src_snapshot_id)
        )
        or 0
    )
    already = session.scalar(select(table.c.id).where(table.c.snapshot_id == dst_snapshot_id).limit(1))
    if already is None:  # 다시 부른 복사(중간에 멈춘 뒤)는 비교군을 두 번 넣지 않는다
        session.execute(
            insert(table).from_select(
                ["snapshot_id", *[c.key for c in cols]],
                select(literal(dst_snapshot_id).label("snapshot_id"), *cols)
                .where(table.c.snapshot_id == src_snapshot_id)
                .order_by(table.c.id),
            )
        )
    if checkpoint is not None:
        session.flush()
        checkpoint()
    runs, decisions = copy_runs(
        session, src_snapshot_id, dst_snapshot_id, created_at=created_at, checkpoint=checkpoint
    )
    stats["score_run"] += runs
    stats["decision"] += decisions
    session.flush()
    return stats

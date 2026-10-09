"""두 스냅샷의 파생 테이블 비교 표 (RA §3 스냅샷 규칙, meta §2-4 '이전 → 현재').

비교 대상(같은 시나리오): score_total(종합 점수·순위·동점·unstable), ladder(입주 후 1년 p10·상태),
intake_status(표시값), decision(선택 결과), claim(검증 상태별 건수), judgment_log(도구별 호출 수).
값은 표시 문자열(점수는 소수 2자리 ROUND_HALF_UP)이고 라벨을 같이 둔다(규칙 5).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Claim,
    Complex,
    Decision,
    IntakeStatus,
    JudgmentLog,
    Ladder,
    Scenario,
    ScoreRun,
    ScoreTotal,
)
from app.reports.errors import ReportNotFound
from app.reports.fmt import round_half_up

__all__ = ["DiffRow", "SnapshotDiff", "diff_snapshots"]

Kind = Literal["added", "removed", "changed"]
INTAKE_PRIORITY = ("human_check", "official_popup", "headless_shot")


@dataclass(frozen=True, slots=True)
class DiffRow:
    table: str
    complex_id: int | None
    complex_name: str
    field: str
    old: str
    new: str
    kind: Kind
    label: str  # 값의 라벨(점수·확률 = 추정, 상태 = 원 행의 라벨 성격)


@dataclass(frozen=True, slots=True)
class SnapshotDiff:
    base_snapshot_id: int
    snapshot_id: int
    scenario_code: str
    rows: list[DiffRow]


def _score(v: Decimal | None) -> str:
    return "미판정" if v is None else f"{round_half_up(v, 2)}"


def _prob(v: Decimal | None) -> str:
    return "미판정" if v is None else f"{round_half_up(v, 2)}"


def _run(session: Session, snapshot_id: int, scenario_id: int) -> ScoreRun | None:
    stmt = (
        select(ScoreRun)
        .where(ScoreRun.snapshot_id == snapshot_id, ScoreRun.scenario_id == scenario_id)
        .order_by(ScoreRun.id.desc())
        .limit(1)
    )
    return session.scalars(stmt).first()


def _totals(session: Session, run: ScoreRun | None) -> dict[int, ScoreTotal]:
    if run is None:
        return {}
    return {
        t.complex_id: t for t in session.scalars(select(ScoreTotal).where(ScoreTotal.score_run_id == run.id))
    }


def _intake(session: Session, snapshot_id: int) -> dict[int, str]:
    rows = list(session.scalars(select(IntakeStatus).where(IntakeStatus.snapshot_id == snapshot_id)))
    out: dict[int, str] = {}
    for path in reversed(INTAKE_PRIORITY):
        for r in sorted((r for r in rows if r.path == path), key=lambda r: r.checked_at):
            reason = f"({r.reason or r.http_status})" if r.status == "확인 불가" else ""
            out[r.complex_id] = f"{r.status}{reason} · {path}"
    return out


def _ladders(session: Session, snapshot_id: int) -> dict[int, Ladder]:
    stmt = select(Ladder).where(Ladder.snapshot_id == snapshot_id, Ladder.horizon == "move_in_plus_1y")
    return {lad.complex_id: lad for lad in session.scalars(stmt)}


def _decisions(session: Session, snapshot_id: int, names: Mapping[int, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for sc in session.scalars(select(Scenario).order_by(Scenario.id)):
        run = _run(session, snapshot_id, sc.id)
        if run is None:
            continue
        chosen = [
            names.get(d.complex_id, str(d.complex_id)) if d.complex_id is not None else d.option_key
            for d in session.scalars(select(Decision).where(Decision.score_run_id == run.id, Decision.chosen))
        ]
        out[sc.code or str(sc.id)] = " = ".join(sorted(chosen)) or "선택 없음"
    return out


def diff_snapshots(
    session: Session, base_id: int, snapshot_id: int, *, scenario_code: str = "base"
) -> SnapshotDiff:
    """base(이전) → snapshot(현재) 파생 테이블 diff. 같은 값은 행을 내지 않는다."""
    scenario = session.scalars(select(Scenario).where(Scenario.code == scenario_code)).first()
    if scenario is None:
        raise ReportNotFound(f"시나리오 {scenario_code} 없음")
    names = {c.id: c.name for c in session.scalars(select(Complex))}
    rows: list[DiffRow] = []

    def name(cid: int | None) -> str:
        return names.get(cid, str(cid)) if cid is not None else "—"

    def add(table: str, cid: int | None, fld: str, old: str, new: str, label: str) -> None:
        if old == new:
            return
        kind: Kind = "added" if old == "—" else "removed" if new == "—" else "changed"
        rows.append(DiffRow(table, cid, name(cid), fld, old, new, kind, label))

    a = _totals(session, _run(session, base_id, scenario.id))
    b = _totals(session, _run(session, snapshot_id, scenario.id))
    for cid in sorted(set(a) | set(b)):
        ta, tb = a.get(cid), b.get(cid)
        if ta is None or tb is None:
            t = tb or ta
            assert t is not None
            v = f"{_score(t.total)} ({t.rank}위)" if t.rank else _score(t.total)
            add("score_total", cid, "total", "—" if ta is None else v, "—" if tb is None else v, "추정")
            continue
        add("score_total", cid, "total", _score(ta.total), _score(tb.total), "추정")
        add("score_total", cid, "rank", f"{ta.rank or '—'}", f"{tb.rank or '—'}", "추정")
        add("score_total", cid, "tie_group", f"{ta.tie_group or '없음'}", f"{tb.tie_group or '없음'}", "추정")
        add(
            "score_total",
            cid,
            "unstable",
            "예" if ta.unstable else "아니오",
            "예" if tb.unstable else "아니오",
            "추정",
        )

    la, lb = _ladders(session, base_id), _ladders(session, snapshot_id)
    for cid in sorted(set(la) | set(lb)):
        xa, xb = la.get(cid), lb.get(cid)
        add(
            "ladder",
            cid,
            "p10(입주 후 1년)",
            "—" if xa is None else _prob(xa.p10),
            "—" if xb is None else _prob(xb.p10),
            "추정",
        )
        if xa is not None and xb is not None:
            add("ladder", cid, "status", xa.status, xb.status, "추정")

    ia, ib = _intake(session, base_id), _intake(session, snapshot_id)
    for cid in sorted(set(ia) | set(ib)):
        add("intake_status", cid, "표시값", ia.get(cid, "—"), ib.get(cid, "—"), "접수 상태(경로 우선순위)")

    da, db = _decisions(session, base_id, names), _decisions(session, snapshot_id, names)
    for code in sorted(set(da) | set(db)):
        add(
            "decision", None, f"상황 {code} 선택", da.get(code, "—"), db.get(code, "—"), "추정(판정기 decide)"
        )

    def claim_counts(sid: int) -> Counter[str]:
        """분할 재검증된 복합 주장(자식이 있는 contradicted)은 따로 센다(§8과 같은 규칙)."""
        rows = list(session.scalars(select(Claim).where(Claim.snapshot_id == sid)))
        parents = {c.parent_claim_id for c in rows if c.parent_claim_id is not None}
        return Counter(
            "contradicted→분할 재검증" if c.id in parents else (c.verify_status or "미검증") for c in rows
        )

    ca, cb = claim_counts(base_id), claim_counts(snapshot_id)
    for st in sorted(set(ca) | set(cb)):
        add("claim", None, f"verify {st}", f"{ca.get(st, 0)}건", f"{cb.get(st, 0)}건", "판정기 verify 집계")

    def calls(sid: int) -> Counter[str]:
        return Counter(session.scalars(select(JudgmentLog.tool).where(JudgmentLog.snapshot_id == sid)))

    ja, jb = calls(base_id), calls(snapshot_id)
    for tool in sorted(set(ja) | set(jb)):
        add(
            "judgment_log",
            None,
            f"{tool} 호출",
            f"{ja.get(tool, 0)}회",
            f"{jb.get(tool, 0)}회",
            "호출 기록 집계",
        )

    return SnapshotDiff(
        base_snapshot_id=base_id, snapshot_id=snapshot_id, scenario_code=scenario_code, rows=rows
    )

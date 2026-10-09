"""WP8 테스트 fixture — ``app.api.devseed`` 재사용(R3 수정 F4).

기본 적재는 전부 ``devseed.seed``(사실·출처·판정 로그·사다리·호재·스냅샷 12 점수·decide·시장·예시)가 한다.
여기서는 devseed 가 만들지 않는 보고서 시험용 파생 행만 더한다(판정기 호출 없음):

- 스냅샷 11(인천 8단지, T7) 점수: devseed 의 점수 입력(``_score_inputs``)을 8단지·rerank #71 앵커
  (relevance_prev × 10)로 좁혀 devseed ``_load_scores`` 로 적재(내장 시나리오 5개 + decide).
- 스냅샷 11 접수 상태: 스냅샷 12 행을 이전 단지에 복사(파이프라인은 스냅샷마다 접수 상태를 남긴다).
- verify 봉투 → claim 행. #131 contradicted 복합 주장은 분할 자식 2개(verified)를 둔다(T6).

지역명은 픽스처에만 있다(코드에는 없음).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.scenarios import BUILTIN_SCENARIOS
from app.api import devseed
from app.core.contracts_gen import ComplexScoreInput, FixedComponents, RerankAnchor, RerankItem
from app.core.settings import Settings
from app.models import Claim, IntakeStatus, Region, ScoreRun, Snapshot

FIXTURE: Path = devseed.DEFAULT_FIXTURE
SNAP_PREV, SNAP_CUR = 11, 12
COMPONENTS6 = ("p10", "rerank", "gap", "benchmark", "supply", "liquidity")


def _load(name: str) -> Any:
    return json.loads((FIXTURE / name).read_text(encoding="utf-8"))


@dataclass
class SeedInfo:
    region_id: int = 1
    snapshots: tuple[int, int] = (SNAP_PREV, SNAP_CUR)
    score_runs: dict[tuple[int, str], int] = field(default_factory=dict)  # (snapshot, code) -> run id
    complex_ids: dict[int, list[int]] = field(default_factory=dict)  # snapshot -> complex ids


def _envelopes() -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for row in _load("judgments/_index.json"):
        env = _load(f"judgments/{row['file']}")
        env["_payload"] = row.get("payload") or {}
        out[int(row["judgment_seq"])] = env
    return out


def _prev_inputs(session: Session) -> tuple[Any, list[int]]:
    """스냅샷 11(T7 인천 8단지) 점수 입력 — devseed 입력을 좁힌다."""
    region = session.get(Region, 1)
    assert region is not None
    inputs = devseed._score_inputs(FIXTURE, region)  # 같은 저장소의 적재기 재사용(비공개 함수)
    assert inputs is not None
    expected = _load("expected_scores.json")
    by_key = {c["key"]: c for c in expected["complexes"]}
    t7 = expected["t7_incheon_only"]
    rows = {by_key[r["key"]]["complex_id"]: r for r in t7["rows"]}
    ids = sorted(rows)
    items = sorted(
        (
            RerankItem(candidate_id=f"complex:{cid}", complex_id=cid, relevance=r["relevance_prev"], rank=1)
            for cid, r in rows.items()
        ),
        key=lambda i: -i.relevance,
    )
    anchor = RerankAnchor(
        judgment_seq=t7["rerank_judgment_seq_prev"],
        status="ok",
        items=[it.model_copy(update={"rank": n + 1}) for n, it in enumerate(items)],
    )
    by_id = {c["complex_id"]: c for c in expected["complexes"]}
    complexes: list[ComplexScoreInput] = []
    for cx in inputs.complexes:
        if cx.complex_id not in rows:
            continue
        comps = dict(by_id[cx.complex_id]["components"])
        comps["rerank"] = round(rows[cx.complex_id]["relevance_prev"] * 10, 4)
        fixed = FixedComponents(source="보고서 §12-4-3 (T7)", **{k: comps[k] for k in COMPONENTS6})
        complexes.append(cx.model_copy(update={"fixed_components": fixed}))
    prev = inputs.model_copy(
        update={"snapshot_id": SNAP_PREV, "asof_date": "2026-10-07", "rerank": anchor, "complexes": complexes}
    )
    return prev, ids


def _copy_intake(session: Session, ids: list[int]) -> None:
    for row in list(
        session.scalars(
            select(IntakeStatus).where(IntakeStatus.snapshot_id == SNAP_CUR, IntakeStatus.complex_id.in_(ids))
        )
    ):
        session.add(
            IntakeStatus(
                complex_id=row.complex_id,
                snapshot_id=SNAP_PREV,
                status=row.status,
                path=row.path,
                evidence_url=row.evidence_url,
                screenshot_path=row.screenshot_path,
                raw_document_id=row.raw_document_id,
                http_status=row.http_status,
                checked_at=row.checked_at,
                reason=row.reason,
                note=row.note,
                entered_by=row.entered_by,
            )
        )
    session.flush()


def _claims(session: Session, envs: dict[int, dict[str, Any]]) -> None:
    for seq, e in sorted(envs.items()):
        if e["tool"] != "verify":
            continue
        known = e["_payload"].get("known_claims") or {}
        section = str(e["_payload"].get("section", ""))[:32]
        for n, c in enumerate((e.get("result") or {}).get("claims", [])):
            text = known.get(c["claim_id"]) or f"주장 {c['claim_id']} (보고서 미기재 — 집계로 만든 id)"
            row = Claim(
                snapshot_id=e["snapshot_id"],
                section=section,
                text=text,
                evidence_text=None,
                verify_status=c["verdict"],
                judgment_seq=seq,
                ordinal=n,
            )
            session.add(row)
            session.flush()
            if c["verdict"] == "contradicted":
                for k, child in enumerate(
                    (
                        "고촌센트럴자이 +10%·+20%와 롯데캐슬 +20% 명제는 unlikely이다",
                        "나머지 명제는 uncertain이다",
                    )
                ):
                    session.add(
                        Claim(
                            snapshot_id=e["snapshot_id"],
                            section=section,
                            text=child,
                            verify_status="verified",
                            parent_claim_id=row.id,
                            ordinal=k,
                        )
                    )
    session.flush()


def seed(settings: Settings, session_factory: Any) -> SeedInfo:
    """devseed 전체 적재(스키마 재생성) + 보고서 시험용 보충. 반환 = 시험이 쓰는 id 들."""
    devseed.seed(settings, reference="none", reset=True)
    info = SeedInfo()
    envs = _envelopes()
    with session_factory() as session:
        prev, prev_ids = _prev_inputs(session)
        snap_prev = session.get(Snapshot, SNAP_PREV)
        assert snap_prev is not None
        devseed._load_scores(session, prev, snap_prev, envs)
        _copy_intake(session, prev_ids)
        _claims(session, envs)
        session.commit()
        info.complex_ids[SNAP_PREV] = prev_ids
        region = session.get(Region, 1)
        assert region is not None
        cur_inputs = devseed._score_inputs(FIXTURE, region)
        assert cur_inputs is not None
        info.complex_ids[SNAP_CUR] = sorted(c.complex_id for c in cur_inputs.complexes)
        codes = {s.id: s.code or str(s.id) for s in BUILTIN_SCENARIOS}
        for run in session.scalars(select(ScoreRun)):
            info.score_runs[(run.snapshot_id, codes.get(run.scenario_id, str(run.scenario_id)))] = run.id
    return info


def add_contradicted_claim(session: Session, snapshot_id: int) -> int:
    """T15: 분할되지 않은 contradicted 주장 1건(생성 거부 시험용)."""
    row = Claim(
        snapshot_id=snapshot_id,
        section="8-F1",
        text="시험용 contradicted 주장",
        verify_status="contradicted",
        ordinal=99,
    )
    session.add(row)
    session.flush()
    return row.id

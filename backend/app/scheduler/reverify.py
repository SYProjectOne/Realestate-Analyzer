"""claim.reverify 잡 (계약 2026-10-09.4, R3 M8).

RA §10 '스냅샷 published 안 됨' → 문장 수정 → 원자 분할 재검증.

``PATCH /claims/{id}`` 가 등록한다(payload = ClaimReverifyPayload{snapshot_id, claim_id, text}).

1. 원 주장(부모)이 아직 contradicted 이고 분할 자식이 없을 때만 돈다(이미 처리됐으면 건너뛴다 — 멱등).
2. 고친 문장을 원자 주장으로 나눠(``RuleClaimSplitter``, T6) 원 주장과 같은 근거로 verify 한다
   (``judge.pipeline.p9_verify`` — 판정기 호출은 judge/ 안에서만, 같은 입력은 캐시).
   근거 = 그 단지의 현재 사실 출처 발췌(``scheduler.inputs.load_facts`` 의 evidence, P9 와 같음).
   단지가 없거나 발췌가 없으면 원 주장의 evidence_text("fp_1: …; fp_2: …")를 나눠 쓴다.
3. 결과를 ``parent_claim_id = 원 주장`` 인 새 주장 행으로 저장한다. 원 주장 행은 고치지 않는다.
4. 남은 contradicted 가 0 이면 ``snapshot.publish`` 를 등록한다.

판정기 장애면 JobError('judge_unavailable …') — 자식 행을 만들지 않는다(다시 등록하면 된다).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.protocols import JudgeUnavailable
from app.models import Claim, Region, Snapshot
from app.scheduler.jobs import JobError, enqueue

if TYPE_CHECKING:
    from app.models import JobRun
    from app.scheduler.context import SchedulerContext

__all__ = ["handle_claim_reverify", "parse_evidence"]


def parse_evidence(text: str | None) -> list[tuple[str, str]]:
    """``"fp_1: 발췌; fp_2: 발췌"`` → [(id, 발췌)]. id 가 없는 조각은 ``claim`` 으로."""
    out: list[tuple[str, str]] = []
    for part in (text or "").split("; "):
        part = part.strip()
        if not part:
            continue
        head, sep, body = part.partition(": ")
        if sep and head and " " not in head:
            out.append((head, body))
        else:
            out.append(("claim", part))
    return out


def _evidence(session: Any, parent: Claim) -> list[tuple[str, str]]:
    from app.scheduler.inputs import load_facts

    snap = session.get(Snapshot, parent.snapshot_id)
    region = session.get(Region, snap.region_id) if snap is not None else None
    if snap is not None and region is not None and parent.complex_id is not None:
        for f in load_facts(session, snap, region):
            if f.complex_id == parent.complex_id and f.evidence:
                return list(f.evidence)
    return parse_evidence(parent.evidence_text)


def handle_claim_reverify(ctx: SchedulerContext, job: JobRun) -> dict[str, Any]:
    from sqlalchemy import select

    from app.judge import pipeline as jp
    from app.judge.claims import remaining_contradicted
    from app.scheduler.persist import SeqResolver

    p = job.payload or {}
    claim_id, snapshot_id, text = int(p["claim_id"]), int(p["snapshot_id"]), str(p["text"])
    stats: dict[str, Any] = {"claim_id": claim_id, "snapshot_id": snapshot_id}
    with ctx.session_factory() as session:
        parent = session.get(Claim, claim_id)
        if parent is None or parent.snapshot_id != snapshot_id:
            raise JobError(f"not_found: claim {claim_id} (snapshot {snapshot_id})", stats)
        has_child = session.scalars(
            select(Claim.id).where(Claim.parent_claim_id == parent.id).limit(1)
        ).first()
        if parent.verify_status != "contradicted" or has_child is not None:
            stats["skipped"] = "이미 분할·재검증됨 또는 contradicted 아님"
            return stats
        evidence = _evidence(session, parent)
        if not evidence:
            raise JobError("no_evidence: 원 주장에 근거가 없어 재검증할 수 없다", stats)
        section, complex_id = parent.section, parent.complex_id
        session.commit()  # 어댑터는 자기 세션으로 judgment_log 를 쓴다 — 읽기 트랜잭션을 닫아 둔다
        try:
            claims = jp.p9_verify(
                ctx.adapter(),
                section=section,
                text=text,
                evidence=evidence,
                snapshot_id=snapshot_id,
                complex_id=complex_id,
            )
        except JudgeUnavailable as exc:
            ctx.reset_adapter()
            raise JobError(f"judge_unavailable: {str(exc)[:200]}", stats) from exc
        except ValueError as exc:  # 근거 없음·복합 문장 등 — 판정기에 보내지 않았다
            raise JobError(f"invalid_claim: {type(exc).__name__}", stats) from exc
        seq = SeqResolver(session)
        rows = []
        for n, c in enumerate(claims):
            row = Claim(
                snapshot_id=snapshot_id,
                section=section,
                complex_id=complex_id,
                text=c.text,
                evidence_text=c.evidence_text,
                verify_status=c.verify_status,
                judgment_seq=seq(c.judgment_seq),
                parent_claim_id=claim_id,
                ordinal=n,
            )
            session.add(row)
            rows.append(row)
        session.flush()
        left = len(remaining_contradicted(session, snapshot_id))
        stats.update(
            children=len(rows),
            verdicts={
                s: sum(1 for r in rows if r.verify_status == s) for s in {r.verify_status for r in rows}
            },
            remaining_contradicted=left,
        )
        if left == 0:
            pub = enqueue(
                session, "snapshot.publish", {"snapshot_id": snapshot_id}, kind="scheduled", now=ctx.now()
            )
            stats["publish_job_id"] = pub.id
        session.commit()
    return stats

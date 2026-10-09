"""원자 주장 목록·문장 수정 (G7, RA §10 '스냅샷 published 안 됨', 계약 2026-10-09.4 — R3 M8).

- ``GET /snapshots/{sid}/claims?status=``: 스냅샷 주장 + remaining + child_count + pending_job_id.
  remaining = 분할 자식 없는 contradicted = publish 를 막는 주장
  (``judge.claims.remaining_contradicted`` 와 같은 규칙).
  pending_job_id = 그 주장의 claim.reverify 잡 중 queued·running.
- ``PATCH /claims/{id}``: 사람이 고친 문장 → ``claim.reverify`` 잡(202). api 는 판정기를 부르지 않는다 —
  worker 가 원자 분할 → 원 주장 근거로 verify → parent_claim_id 자식 행. 원 주장 행은 고치지 않는다.
  문장은 판정기로 가므로 guard(전화번호·주민번호·이메일·비밀값)를 먼저 통과해야 한다(422).
"""

from __future__ import annotations

from collections import Counter
from typing import Annotated, Any

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.contract import check_body
from app.api.deps import DB, get_snapshot
from app.api.errors import conflict, not_found, validation_error
from app.api.jobs import enqueue, job_view
from app.models import Claim, Complex, JobRun

router = APIRouter(tags=["ops"])

REVERIFY = "claim.reverify"


def pending_reverify(session: Session, claim_ids: set[int] | None = None) -> dict[int, int]:
    """claim_id → queued·running 인 claim.reverify 잡 id(가장 최근)."""
    out: dict[int, int] = {}
    stmt = (
        select(JobRun)
        .where(JobRun.job_name == REVERIFY, JobRun.status.in_(("queued", "running")))
        .order_by(JobRun.id)
    )
    for job in session.scalars(stmt):
        cid = (job.payload or {}).get("claim_id")
        if isinstance(cid, int) and (claim_ids is None or cid in claim_ids):
            out[cid] = job.id
    return out


def _children(session: Session, snapshot_id: int) -> Counter[int]:
    return Counter(
        pid
        for (pid,) in session.execute(
            select(Claim.parent_claim_id).where(
                Claim.snapshot_id == snapshot_id, Claim.parent_claim_id.is_not(None)
            )
        )
        if pid is not None
    )


def claim_view(
    c: Claim, names: dict[int, str], children: Counter[int], pending: dict[int, int]
) -> dict[str, Any]:
    n = children.get(c.id, 0)
    return {
        "id": c.id,
        "snapshot_id": c.snapshot_id,
        "section": c.section,
        "complex_id": c.complex_id,
        "complex_name": names.get(c.complex_id) if c.complex_id is not None else None,
        "text": c.text,
        "evidence_text": c.evidence_text,
        "verify_status": c.verify_status,
        "judgment_seq": c.judgment_seq,
        "prov": f"jl_{c.judgment_seq}" if c.judgment_seq is not None else None,
        "parent_claim_id": c.parent_claim_id,
        "ordinal": c.ordinal,
        "child_count": n,
        "remaining": c.verify_status == "contradicted" and n == 0,
        "pending_job_id": pending.get(c.id),
    }


@router.get("/snapshots/{sid}/claims")
def list_claims(
    session: DB,
    sid: int,
    status: Annotated[str | None, Query(pattern="^(verified|contradicted|unsupported|review)$")] = None,
) -> JSONResponse:
    snap = get_snapshot(session, sid)
    stmt = select(Claim).where(Claim.snapshot_id == snap.id)
    if status:
        stmt = stmt.where(Claim.verify_status == status)
    rows = list(session.scalars(stmt.order_by(Claim.id)))
    ids = {c.complex_id for c in rows if c.complex_id is not None}
    names: dict[int, str] = {}
    if ids:
        stmt_names = select(Complex.id, Complex.name).where(Complex.id.in_(ids))
        names = {cid: name for cid, name in session.execute(stmt_names)}
    children = _children(session, snap.id)
    pending = pending_reverify(session, {c.id for c in rows})
    return JSONResponse([claim_view(c, names, children, pending) for c in rows])


@router.patch("/claims/{id}", status_code=202)
def revise_claim(session: DB, id: int, body: Annotated[Any, Body()] = None) -> JSONResponse:
    claim = session.get(Claim, id)
    if claim is None:
        raise not_found(f"claim {id}")
    check_body("reviseClaim", body)
    text = str(body["text"]).strip()
    if not text:
        raise validation_error("text 가 비었다", ("body", "text"))
    from app.judge.guard import check_payload

    guard = check_payload({"text": text})
    if not guard.ok:
        raise validation_error(
            f"문장에 공개할 수 없는 정보가 있다({', '.join(guard.kinds())}) — 판정기로 보내지 않는다",
            ("body", "text"),
        )
    if claim.verify_status != "contradicted":
        raise conflict(f"claim {id} is not contradicted (verify_status={claim.verify_status})")
    child = session.scalars(select(Claim.id).where(Claim.parent_claim_id == claim.id).limit(1)).first()
    if child is not None:
        raise conflict(f"claim {id} already has re-verified child claims")
    waiting = pending_reverify(session, {claim.id}).get(claim.id)
    if waiting is not None:
        raise conflict(f"claim {id} re-verification is already queued (job {waiting})")
    job = enqueue(session, REVERIFY, {"snapshot_id": claim.snapshot_id, "claim_id": claim.id, "text": text})
    session.commit()
    return JSONResponse(job_view(job), status_code=202)

"""원자 주장 목록·문장 수정 (G7, RA §10 '스냅샷 published 안 됨', 계약 2026-10-09.4 — R3 M8).

- ``GET /snapshots/{sid}/claims?status=``: 스냅샷 주장 + remaining + child_count + pending_job_id.
  remaining = 분할 자식 없는 contradicted = publish 를 막는 주장
  (``judge.claims.remaining_contradicted`` 와 같은 규칙).
  pending_job_id = 그 주장의 claim.reverify 잡 중 queued·running.
- ``PATCH /claims/{id}``: 사람이 고친 문장 → ``claim.reverify`` 잡(202). api 는 판정기를 부르지 않는다 —
  worker 가 원자 분할 → 원 주장 근거로 verify → parent_claim_id 자식 행. 원 주장 행은 고치지 않는다.
  문장은 판정기로 가므로 guard(전화번호·주민번호·이메일·비밀값)를 먼저 통과해야 한다(422).
- D10-3(계약 2026-10-09.6, R3 재리뷰 N-C3 — ``app.api.demotion``): 고친 문장은 원 주장과 같은 대상(section·complex·
  field)만(422). 원 주장이 DB 사실에서 생성됐으면 접수와 함께 그 사실을 강등한다(값 비움·'확인 불가(검증 모순)'·
  체크리스트 '사실 재확인'·change_event critical·그 단지 rejudge 잡 — rejudge 를 claim.reverify 보다 먼저 넣는다:
  worker 가 등록 순서로 집으므로 재검증 뒤 publish 가 강등 전 점수로 나가지 않는다).
  목록은 ``entity·entity_id·field·field_name·demotion`` 을 싣는다. GET 은 DB 를 쓰지 않는다(minor 13) — 강등 상태는
  ``app.facts_view`` 오버레이로 읽는 순간 계산한다(새 출처 다른 값·사람 확인이면 'restored').
- D11-3(계약 .8): 강등은 사실 값을 지우지 않는 읽기 시점 오버레이. 대상이 불완전한 주장(사실 행을 못 찾음)은 422(minor 14).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections import Counter
from typing import Annotated, Any

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.contract import check_body, has_visible
from app.api.demotion import (
    FIELD_NAMES,
    ClaimTarget,
    TargetMismatch,
    check_same_target,
    claim_target,
    demote,
    demotion_view,
    latest_demotions,
)
from app.api.deps import DB, get_snapshot
from app.api.errors import conflict, not_found, validation_error
from app.api.jobs import enqueue, job_view
from app.facts_view import DemotionOverlay, load_overlay
from app.models import Claim, Complex, FactDemotion, JobRun

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
    c: Claim,
    names: dict[int, str],
    children: Counter[int],
    pending: dict[int, int],
    target: ClaimTarget | None = None,
    demotion: FactDemotion | None = None,
    overlay: DemotionOverlay | None = None,
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
        "entity": target.entity if target is not None else None,
        "entity_id": target.entity_id if target is not None else None,
        "field": target.field if target is not None else None,
        "field_name": FIELD_NAMES.get(target.logical, target.logical) if target is not None else None,
        "demotion": demotion_view(demotion, overlay),
    }


@router.get("/snapshots/{sid}/claims")
def list_claims(
    session: DB,
    sid: int,
    status: Annotated[str | None, Query(pattern="^(verified|contradicted|unsupported|review)$")] = None,
) -> JSONResponse:
    """D14-1(계약 .11, R3 6차 m1): 발행 리비전은 발행 순간 저장한 목록(강등 상태·대상·대기 잡 포함)을 그대로 — 이후
    PATCH /claims·강등·사람 확인이 옛 리비전 목록을 바꾸지 않는다. 발행 전 리비전만 지금 값."""
    snap = get_snapshot(session, sid)  # GET 은 DB 를 쓰지 않는다(minor 13) — 강등 상태는 오버레이로 읽는다
    from app import snapshot_view as sv

    rows = sv.claims(session, snap)
    if status:
        rows = [r for r in rows if r.get("verify_status") == status]
    return JSONResponse(rows)


def claims_body(session: Session, snap: Any) -> list[dict[str, Any]]:
    """그 스냅샷 주장 목록 전체(실시간 — 발행 리비전은 이 결과를 저장한다, D14-1)."""
    rows = list(session.scalars(select(Claim).where(Claim.snapshot_id == snap.id).order_by(Claim.id)))
    ids = {c.complex_id for c in rows if c.complex_id is not None}
    names: dict[int, str] = {}
    if ids:
        stmt_names = select(Complex.id, Complex.name).where(Complex.id.in_(ids))
        names = {cid: name for cid, name in session.execute(stmt_names)}
    children = _children(session, snap.id)
    pending = pending_reverify(session, {c.id for c in rows})
    targets = {c.id: claim_target(session, c) for c in rows}
    demotions = latest_demotions(session, rows, targets)
    overlay = load_overlay(session, complex_ids=ids) if demotions else None
    return [
        claim_view(c, names, children, pending, targets[c.id], demotions.get(c.id), overlay) for c in rows
    ]


@router.patch("/claims/{id}", status_code=202)
def revise_claim(session: DB, id: int, body: Annotated[Any, Body()] = None) -> JSONResponse:
    claim = session.get(Claim, id)
    if claim is None:
        raise not_found(f"claim {id}")
    check_body("reviseClaim", body)
    text = str(body["text"]).strip()
    if not has_visible(text):  # 계약 .19: 스키마 pattern 과 같은 규칙(보이는 글자 1자 이상)
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
    target = claim_target(session, claim)
    try:
        check_same_target(session, claim, text, target)
    except TargetMismatch as exc:
        raise validation_error(f"{exc} (D10-3 같은 대상만)", ("body", "text")) from exc
    if target is not None:
        if not target.complete:  # minor 14: 대상 행을 못 찾으면 강등 없이 reverify(→ publish 해제)하지 않는다
            raise validation_error(
                f"원 주장의 사실({target.name}) 행을 찾을 수 없다 — 사람 확인(POST /ops/human-checks)으로 값을 먼저 입력한다",
                ("body", "text"),
            )
        demote(session, claim, target)  # rejudge 잡이 claim.reverify 보다 먼저 등록된다(모듈 설명)
    job = enqueue(session, REVERIFY, {"snapshot_id": claim.snapshot_id, "claim_id": claim.id, "text": text})
    session.commit()
    return JSONResponse(job_view(job), status_code=202)

"""호재 URL 사람 입력 (DECISIONS D1-6, 계약 2026-10-09.4 — R3 M6).

``POST /catalysts``: 공개 기사·공고 URL + 제목(+발췌) → 호재 후보 행 → 분류 잡.

- 후보 행은 F1a 의 ``app.normalize.catalyst`` 공개 함수가 만든다(정규화 소유 — api 는 행 모양을 정하지
  않는다). 가져오기는 지연한다(``candidate_factory``): 모듈·함수가 없으면 ``CandidateUnavailable``
  → 500 internal(사유).
  기대 시그니처::

      catalyst_from_url(session, *, region_id: int, url: str, title: str, excerpt: str | None,
                        checked_at: str) -> Catalyst   # flush 된 행(stage '미확정', location_confirmed=False)

- 분류(kind·stage)는 판정기 classify 가 한다(규칙 3): 지역 최신 스냅샷에 rejudge(complex_ids=[] → P4 호재
  classify·점수 재계산)를 등록한다 — 같은 스냅샷에 대기 중인 rejudge 가 있으면 그 잡에 합친다
  (``scheduler.rejudge.enqueue_rejudge``). 스냅샷이 없으면 job=null(다음 파이프라인 P4 가 분류).
- 같은 지역·같은 URL 이 이미 있으면 그 행을 돌려준다(후보 함수를 다시 부르지 않는다).
- 제목·발췌는 guard(전화번호·주민번호·이메일·비밀값)를 통과해야 한다 — 판정기 payload 로 가는 문장이다(422).
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.contract import check_body
from app.api.deps import DB, default_snapshot, get_region, settings_of
from app.api.errors import ApiError, validation_error
from app.api.facts import FactMaker, ProvIndex
from app.api.jobs import job_view, now_iso
from app.api.routers.complexes import catalyst_view
from app.models import Catalyst, Snapshot

__all__ = ["CANDIDATE_FUNCTION", "CANDIDATE_MODULE", "CandidateUnavailable", "candidate_factory", "router"]

router = APIRouter(tags=["market"])

CANDIDATE_MODULE = "app.normalize.catalyst"
CANDIDATE_FUNCTION = "catalyst_from_url"


class CandidateUnavailable(RuntimeError):
    """F1a 의 후보 함수가 아직 없다(라운드 병렬 진행 — 머지 전)."""


def candidate_factory() -> Callable[..., Any]:
    """``app.normalize.catalyst.catalyst_from_url`` 을 지연 import 한다(테스트는 대역으로 바꾼다)."""
    try:
        module = importlib.import_module(CANDIDATE_MODULE)
    except ModuleNotFoundError as exc:
        raise CandidateUnavailable(f"{CANDIDATE_MODULE} 모듈 없음(호재 후보 함수 미머지)") from exc
    fn = getattr(module, CANDIDATE_FUNCTION, None)
    if not callable(fn):
        raise CandidateUnavailable(f"{CANDIDATE_MODULE}.{CANDIDATE_FUNCTION} 없음")
    return fn  # type: ignore[no-any-return]


def _snapshot_for(session: Session, region_id: int) -> Snapshot | None:
    snap = default_snapshot(session, region_id)
    if snap is not None:
        return snap
    return session.scalars(
        select(Snapshot)
        .where(Snapshot.region_id == region_id)
        .order_by(Snapshot.asof_date.desc(), Snapshot.id.desc())
        .limit(1)
    ).first()


@router.post("/catalysts", status_code=201)
def create_catalyst(session: DB, request: Request, body: Annotated[Any, Body()] = None) -> JSONResponse:
    check_body("createCatalyst", body)
    region = get_region(session, int(body["region_id"]))
    url = str(body["url"]).strip()
    title = str(body["title"]).strip()
    excerpt = (str(body.get("excerpt") or "").strip()) or None
    if not title:
        raise validation_error("title 이 비었다", ("body", "title"))
    from app.judge.guard import check_payload

    guard = check_payload({"title": title, "excerpt": excerpt or "", "url": url})
    if not guard.ok:
        raise validation_error(
            f"공개할 수 없는 정보가 있다({', '.join(guard.kinds())}) — 판정기로 보내지 않는다",
            ("body",),
        )
    row = session.scalars(
        select(Catalyst).where(Catalyst.region_id == region.id, Catalyst.source_url == url).limit(1)
    ).first()
    if row is None:
        try:
            make = candidate_factory()
        except CandidateUnavailable as exc:
            raise ApiError(500, "internal", str(exc)) from exc
        made = make(session, region_id=region.id, url=url, title=title, excerpt=excerpt, checked_at=now_iso())
        row = made if isinstance(made, Catalyst) else session.get(Catalyst, int(made))
        if row is None:
            raise ApiError(500, "internal", f"{CANDIDATE_MODULE}.{CANDIDATE_FUNCTION}: 행 없음")
    session.flush()
    snap = _snapshot_for(session, region.id)
    job_out: dict[str, Any] | None = None
    if snap is not None:
        from app.scheduler.rejudge import enqueue_rejudge

        job = enqueue_rejudge(session, snap.id, [], f"호재 URL 입력: {title}"[:200])
        job_out = job_view(job)
    session.commit()
    checked = (snap.asof_date if snap is not None else now_iso())[:10]
    fm = FactMaker(settings_of(request), ProvIndex().load(session, "catalyst", [row.id]))
    view = catalyst_view(row, checked, fm=fm)
    return JSONResponse({"catalyst": view, "job": job_out}, status_code=201)

"""읽기 전용 공유 링크 발급·목록·회수 (RA §10 보안 5, 계약 2026-10-09.4 — R3 M9).

모두 쓰기 토큰만(``require_write``) — 읽기 전용 토큰·공유 링크 토큰은 GET 목록도 403.
만료 기간은 ``SHARE_TOKEN_TTL_DAYS``(기본 30일)로만 정한다. 토큰은 발급 응답에서 한 번만 나간다.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.contract import check_body
from app.api.deps import DB, require_write, settings_of
from app.api.errors import not_found
from app.api.jobs import now_iso
from app.api.share import issue, link_view
from app.models import ShareLink

router = APIRouter(tags=["ops"], dependencies=[Depends(require_write)])


@router.get("/share-links")
def list_share_links(session: DB) -> JSONResponse:
    rows = session.scalars(select(ShareLink).order_by(ShareLink.id.desc()))
    return JSONResponse([link_view(r) for r in rows])


@router.post("/share-links", status_code=201)
def create_share_link(session: DB, request: Request, body: Annotated[Any, Body()] = None) -> JSONResponse:
    check_body("createShareLink", body)
    label = body.get("label") if isinstance(body, dict) else None
    row, token = issue(session, ttl_days=settings_of(request).share_token_ttl_days, label=label or None)
    session.commit()
    return JSONResponse({"link": link_view(row), "token": token}, status_code=201)


@router.delete("/share-links/{id}")
def revoke_share_link(session: DB, id: int) -> JSONResponse:
    row = session.get(ShareLink, id)
    if row is None:
        raise not_found(f"share_link {id}")
    if row.revoked_at is None:
        row.revoked_at = now_iso()
        session.commit()
    return JSONResponse(link_view(row))

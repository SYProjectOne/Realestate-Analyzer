"""읽기 전용 공유 링크 (RA §10 보안 5, ADR-9, 계약 2026-10-09.4 — R3 M9).

- 발급: 무작위 토큰(``secrets.token_urlsafe(32)``) → DB 에는 sha256 hex 만(``share_link.token_sha256``).
  만료 = 발급 시각 + ``SHARE_TOKEN_TTL_DAYS``(기본 30일).
- 검증(``lookup``): sha256 이 맞는 행 → 회수됐으면 'revoked', 만료됐으면 'expired', 아니면 'active'.
  ``deps.require_auth`` 가 환경 토큰(API_TOKEN·READONLY_TOKEN)이 아닌 Bearer 토큰에 대해 부른다.
- 상태는 조회 시각으로 계산한다(컬럼 아님).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import now_kst
from app.models import ShareLink

__all__ = ["ShareStatus", "issue", "link_status", "link_view", "lookup", "token_digest"]

ShareStatus = Literal["active", "expired", "revoked"]


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def link_status(row: ShareLink, now: datetime | None = None) -> ShareStatus:
    if row.revoked_at:
        return "revoked"
    current = now or now_kst()
    try:
        expires = datetime.fromisoformat(row.expires_at)
    except ValueError:
        return "expired"
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=current.tzinfo)
    return "expired" if expires <= current else "active"


def link_view(row: ShareLink, now: datetime | None = None) -> dict[str, Any]:
    return {
        "id": row.id,
        "label": row.label,
        "created_at": row.created_at,
        "expires_at": row.expires_at,
        "revoked_at": row.revoked_at,
        "status": link_status(row, now),
    }


def issue(session: Session, *, ttl_days: int, label: str | None = None) -> tuple[ShareLink, str]:
    """새 공유 링크(flush, commit 은 호출자) + 토큰 원문(이 반환값에서만)."""
    token = secrets.token_urlsafe(32)
    now = now_kst()
    row = ShareLink(
        token_sha256=token_digest(token),
        label=label,
        created_at=_iso(now),
        expires_at=_iso(now + timedelta(days=ttl_days)),
        revoked_at=None,
    )
    session.add(row)
    session.flush()
    return row, token


def lookup(session: Session, token: str) -> ShareLink | None:
    return session.scalars(select(ShareLink).where(ShareLink.token_sha256 == token_digest(token))).first()

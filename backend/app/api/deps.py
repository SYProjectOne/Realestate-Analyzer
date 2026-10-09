"""의존성: Bearer 인증(ADR-9), DB 세션, 스냅샷·시나리오 해석 (RA §4-2, openapi 공통 규칙).

- 쓰기 토큰(API_TOKEN) = 전부, 읽기 전용 토큰(READONLY_TOKEN)·공유 링크 토큰 = GET 만(그 밖 403 forbidden),
  없거나 틀리면 401. 공유 링크 토큰(POST /share-links 발급, 계약 2026-10-09.4)은 sha256 으로 찾고,
  만료·회수면 401.
  두 환경 토큰이 모두 비어 있으면(개발 기본값) 인증 없이 열되 루프백(127.0.0.1·::1) 접속만 받는다(R3 M11) —
  ENV=prod 는 설정 검증이 API_TOKEN 을 강제한다. ``app.serve`` 도 그때는 127.0.0.1 에만 바인드한다.
- ``require_write``: 쓰기 토큰만(공유 링크 관리처럼 GET 이라도 읽기 전용 토큰에 보이면 안 되는 것).
- ``?snapshot=`` 이 없으면 지역의 최신 published, 없으면 최신 ready 스냅샷.
- ``?scenario=`` 는 내장 code(base|A|B|C|D) 또는 사용자 시나리오 숫자 id, 생략 시 base.
"""

from __future__ import annotations

import hmac
import ipaddress
from typing import Annotated, Literal

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError, not_found
from app.core.db import session_dependency
from app.core.logging import get_logger
from app.core.settings import Settings, get_settings
from app.models import Complex, Region, Scenario, Snapshot

__all__ = [
    "DB",
    "Role",
    "default_snapshot",
    "get_complex",
    "get_region",
    "get_snapshot",
    "in_db_range",
    "require_auth",
    "require_write",
    "resolve_scenario",
    "settings_of",
    "strict_query",
]

log = get_logger("app.api")

Role = Literal["write", "read"]
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

DB = Annotated[Session, Depends(session_dependency)]


def settings_of(request: Request) -> Settings:
    s = getattr(request.app.state, "settings", None)
    return s if isinstance(s, Settings) else get_settings()


def _secret(value: object) -> str | None:
    raw = value.get_secret_value() if hasattr(value, "get_secret_value") else None
    return raw or None


def _same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    if host in _LOOPBACK:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _unauthorized(detail: str) -> ApiError:
    return ApiError(401, "unauthorized", detail, headers={"WWW-Authenticate": "Bearer"})


def _read_only(request: Request) -> Role:
    if request.method.upper() not in _READ_METHODS:
        raise ApiError(403, "forbidden", "읽기 전용 토큰은 GET 만 허용한다")
    return "read"


def _share_link_role(request: Request, token: str) -> Role:
    """공유 링크 토큰(계약 2026-10-09.4). 없으면 401, 만료·회수면 401(사유), 유효하면 읽기 전용."""
    from sqlalchemy.exc import SQLAlchemyError

    from app.api.share import link_status, lookup
    from app.core.db import get_sessionmaker

    try:
        with get_sessionmaker(settings_of(request))() as session:
            row = lookup(session, token)
            status = link_status(row) if row is not None else None
    except SQLAlchemyError:  # share_link 테이블 없음(마이그레이션 전) 등 — 공유 링크 없음으로 본다
        status = None
    if status is None:
        raise _unauthorized("토큰이 맞지 않는다")
    if status == "expired":
        raise _unauthorized("공유 링크가 만료됐다")
    if status == "revoked":
        raise _unauthorized("공유 링크가 회수됐다")
    request.state.share_link = True
    return _read_only(request)


def require_auth(request: Request) -> Role:
    """라우터 공통 의존성. 본문 검증보다 먼저 돈다(읽기 전용 토큰 POST → 403)."""
    s = settings_of(request)
    write = _secret(s.api_token)
    read = _secret(s.readonly_token)
    if write is None and read is None:
        client = request.client.host if request.client is not None else None
        if not _is_loopback(client):
            raise _unauthorized("토큰이 설정되지 않은 서버는 루프백(127.0.0.1) 접속만 받는다")
        return "write"
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized("Bearer 토큰이 필요하다")
    if write is not None and _same(token, write):
        return "write"
    if read is not None and _same(token, read):
        return _read_only(request)
    return _share_link_role(request, token)


def require_write(role: Annotated[Role, Depends(require_auth)]) -> Role:
    """쓰기 토큰만. 읽기 전용 토큰·공유 링크 토큰이면 GET 이라도 403(공유 링크 목록 등)."""
    if role != "write":
        raise ApiError(403, "forbidden", "쓰기 토큰만 볼 수 있다(읽기 전용·공유 링크 토큰 불가)")
    return role


def get_region(session: Session, region_id: int) -> Region:
    region = session.get(Region, region_id)
    if region is None:
        raise not_found(f"region {region_id}")
    return region


def get_snapshot(session: Session, sid: int) -> Snapshot:
    snap = session.get(Snapshot, sid)
    if snap is None:
        raise not_found(f"snapshot {sid}")
    return snap


def get_complex(session: Session, complex_id: int) -> Complex:
    cx = session.get(Complex, complex_id)
    if cx is None:
        raise not_found(f"complex {complex_id}")
    return cx


def default_snapshot(session: Session, region_id: int) -> Snapshot | None:
    """지역의 최신 published, 없으면 최신 ready(기준일 내림차순, 같은 날이면 id 큰 것)."""
    for status in ("published", "ready"):
        snap = session.scalars(
            select(Snapshot)
            .where(Snapshot.region_id == region_id, Snapshot.status == status)
            .order_by(Snapshot.asof_date.desc(), Snapshot.id.desc())
            .limit(1)
        ).first()
        if snap is not None:
            return snap
    return None


def resolve_scenario(session: Session, value: str | int | None) -> Scenario:
    """내장 code 또는 숫자 id → scenario 행. 없으면 404."""
    key = "base" if value is None or value == "" else str(value)
    if key.isdigit():
        sc = session.get(Scenario, int(key))
    else:
        sc = session.scalars(select(Scenario).where(Scenario.code == key)).first()
    if sc is None:
        raise not_found(f"scenario {key}")
    return sc


INT64_MAX = 2**63 - 1


def in_db_range(value: int | None) -> bool:
    """DB 정수 컬럼(64비트)에 들어가는 값인가. 아니면 그런 행은 없다."""
    return value is None or -INT64_MAX - 1 <= value <= INT64_MAX


def strict_query(request: Request) -> None:
    """계약에 없는 조회 파라미터는 받지 않는다(계약을 그대로 구현 — 오타·잘못된 필터를 조용히 무시하지 않음).

    deepObject(``filter[...]``) 이름은 해당 operation 이 선언한 것만. 인증 뒤, 라우터 검증 전에 돈다."""
    from app.api.contract import query_names

    s = settings_of(request)
    prefix = s.api_prefix.rstrip("/")
    path = str(request.scope.get("path") or request.url.path)
    if prefix and path.startswith(prefix + "/"):
        path = path[len(prefix) :]
    names = query_names(request.method, path)
    if names is None:
        return
    plain, deep = names
    bad = []
    seen: set[str] = set()
    for key, _ in request.query_params.multi_items():
        base = key.split("[", 1)[0] if "[" in key else key
        known = (key in plain) or (base in deep and key.endswith("]") and key != base)
        if not known or key in seen:  # 모르는 이름, 또는 단일 값 파라미터를 여러 번(배열) 보냄
            bad.append(key)
        seen.add(key)
    if bad:
        from fastapi.exceptions import RequestValidationError

        raise RequestValidationError(
            [
                {"loc": ("query", k), "msg": "계약에 없는 조회 파라미터", "type": "extra_forbidden"}
                for k in bad[:20]
            ]
        )

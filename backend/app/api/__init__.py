"""REST API (WP5) — contracts/openapi.yaml 의 operation 전부(``/health`` 는 app.main).

``router``: ``app.main.create_app()`` 이 ``API_PREFIX``(기본 ``/api``) 아래에 붙인다. 모든 경로에 Bearer 인증
(``deps.require_auth``)이 걸린다. ``install(app)``: 오류 본문을 계약 ``Error`` 로 맞추는 처리기를 단다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI

from app.api.deps import require_auth, strict_query
from app.api.errors import install_handlers
from app.api.routers import (
    analysis,
    catalysts,
    claims,
    complexes,
    jobs,
    market,
    ops,
    regions,
    reports,
    share_links,
    snapshots,
)

__all__ = ["install", "router"]

router = APIRouter(dependencies=[Depends(require_auth), Depends(strict_query)])
for _module in (
    regions,
    snapshots,
    complexes,
    analysis,
    market,
    jobs,
    ops,
    reports,
    claims,  # 계약 2026-10-09.4 (R3 M8)
    catalysts,  # (R3 M6)
    share_links,  # (R3 M9)
):
    router.include_router(_module.router)


def install(app: FastAPI) -> None:
    """앱 단위 설정(오류 처리기). ``app.main.create_app`` 이 라우터를 붙인 뒤 부른다."""
    install_handlers(app)
    # 계약 번들(openapi.bundled.yaml) 파싱·경로 표를 기동 때 만든다
    # — 첫 요청이 ~0.9초를 내지 않게(R3 minor 9, T16 cold)
    from app.api.contract import query_names

    query_names("GET", "/regions")
    # '/api/jobs/' 같은 끝 슬래시 경로를 다른 operation 으로 돌리지 않는다(계약에 없는 경로 = 404)
    app.router.redirect_slashes = False

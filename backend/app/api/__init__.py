"""REST API (WP5) — contracts/openapi.yaml 의 operation 전부(``/health`` 는 app.main).

``router``: ``app.main.create_app()`` 이 ``API_PREFIX``(기본 ``/api``) 아래에 붙인다. 모든 경로에 Bearer 인증
(``deps.require_auth``)이 걸린다. ``install(app)``: 오류 본문을 계약 ``Error`` 로 맞추는 처리기를 단다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI

from app.api.deps import require_auth, strict_query
from app.api.errors import install_handlers
from app.api.routers import analysis, complexes, jobs, market, ops, regions, reports, snapshots

__all__ = ["install", "router"]

router = APIRouter(dependencies=[Depends(require_auth), Depends(strict_query)])
for _module in (regions, snapshots, complexes, analysis, market, jobs, ops, reports):
    router.include_router(_module.router)


def install(app: FastAPI) -> None:
    """앱 단위 설정(오류 처리기). ``app.main.create_app`` 이 라우터를 붙인 뒤 부른다."""
    install_handlers(app)
    # '/api/jobs/' 같은 끝 슬래시 경로를 다른 operation 으로 돌리지 않는다(계약에 없는 경로 = 404)
    app.router.redirect_slashes = False

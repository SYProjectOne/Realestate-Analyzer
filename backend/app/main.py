"""FastAPI app factory (api 프로세스).

- ``/health`` (와 ``{API_PREFIX}/health``): 계약 ``Health``
  ``{status, contract_version, app_version, db, judge, time}`` (계약 2026-10-09.3).
  DB 가 안 되면 503 + 같은 본문(``status=degraded, db=error, judge=unknown``).
  judge = 지역마다 최신 스냅샷의 ``degraded`` 플래그(하나라도 true 면 degraded,
  스냅샷이 있고 모두 정상이면 ok, 없으면 unknown) — 판정기 장애만이면 200(수집·조회는 계속된다).
- ``app.api`` 패키지에 ``router`` 가 있으면 ``API_PREFIX``(기본 ``/api``) 아래에 붙인다(WP5).
  없으면 건너뛴다. 인증 의존성은 WP5 가 router 쪽에 단다.
- nginx(web)는 ``/api/*`` 를 경로 그대로 api:8000 으로 넘긴다 → 개발·운영 경로가 같다.
- ``/docs``·``/redoc``·``/openapi.json``(R3 minor 19): ENV=prod 는 끈다(404). dev 는 API 와 같은 인증
  (``api.deps.require_auth`` — 토큰이 없으면 루프백 전용)을 건다. 계약 원본은 contracts/openapi.yaml 이다.
- 기동은 ``python -m app.serve``(R3 M11 — 토큰이 없으면 127.0.0.1 바인드).
"""

from __future__ import annotations

import gc
import importlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from typing import Literal

from fastapi import APIRouter, FastAPI, Response
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.contracts_gen import Health
from app.core.db import get_engine, ping, reset_engine, sqlite_api_checkpointer
from app.core.logging import configure_logging, get_logger
from app.core.protocols import CONTRACT_VERSION
from app.core.settings import Settings, get_settings
from app.core.time import now_kst

log = get_logger("app.main")


def app_version() -> str:
    try:
        return version("subscription-analyzer")
    except PackageNotFoundError:
        return "0.0.0+unknown"


JudgeHealth = Literal["ok", "degraded", "unknown"]


def judge_health(engine: Engine) -> JudgeHealth:
    """지역마다 최신 스냅샷(asof_date 최대)의 degraded 플래그. 읽을 수 없으면 unknown."""
    from app.models import Snapshot

    latest = (
        select(Snapshot.region_id, func.max(Snapshot.asof_date).label("asof"))
        .group_by(Snapshot.region_id)
        .subquery()
    )
    stmt = select(Snapshot.degraded).join(
        latest, (Snapshot.region_id == latest.c.region_id) & (Snapshot.asof_date == latest.c.asof)
    )
    try:
        with Session(engine) as session:
            flags = [bool(v) for v in session.scalars(stmt)]
    except SQLAlchemyError:
        return "unknown"
    if not flags:
        return "unknown"
    return "degraded" if any(flags) else "ok"


def _load_api_router() -> APIRouter | None:
    try:
        module = importlib.import_module("app.api")
    except ModuleNotFoundError as exc:
        if exc.name == "app.api":
            return None
        raise
    router = getattr(module, "router", None)
    return router if isinstance(router, APIRouter) else None


def _install_docs(app: FastAPI) -> None:
    """dev 전용 API 문서. 인증은 API 라우터와 같은 ``require_auth``(R3 minor 19)."""
    from fastapi import Depends
    from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
    from fastapi.responses import HTMLResponse, JSONResponse

    from app.api.deps import require_auth

    auth = [Depends(require_auth)]

    def openapi_json() -> JSONResponse:
        return JSONResponse(app.openapi())

    def docs() -> HTMLResponse:
        return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{app.title} — docs")

    def redoc() -> HTMLResponse:
        return get_redoc_html(openapi_url="/openapi.json", title=f"{app.title} — redoc")

    for path, endpoint in (("/openapi.json", openapi_json), ("/docs", docs), ("/redoc", redoc)):
        app.add_api_route(path, endpoint, methods=["GET"], dependencies=auth, include_in_schema=False)


GC_GEN0_THRESHOLD = 50_000
"""순환 GC 1세대 문턱(기본 700). 목록 화면 1,000단지 응답은 객체 수십만 개를 만들고 버린다 — 기본
문턱이면 요청 한 번에 GC 가 여러 번 돌아 응답이 0.1초가량 늦다(T16, R3 3차 성능). 짧게 사는 객체가
대부분이라 문턱만 올린다."""


def tune_gc() -> None:
    """순환 GC 문턱을 올린다(이미 더 높으면 그대로). 프로세스 전역 — api·worker 시작 때 한 번."""
    g0, g1, g2 = gc.get_threshold()
    if g0 < GC_GEN0_THRESHOLD:
        gc.set_threshold(GC_GEN0_THRESHOLD, max(g1, 50), max(g2, 100))


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        tune_gc()
        configure_logging(s)
        log.info("api.start", extra={"env": s.env, "version": app_version()})
        # R3h(D14-5): SQLite 개발 모드에서 요청 커밋이 WAL 체크포인트(fsync)를 떠안지 않게
        with sqlite_api_checkpointer(get_engine(s)):
            yield
        reset_engine()

    app = FastAPI(
        title="subscription-analyzer",
        version=app_version(),
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = s

    def health(response: Response) -> Health:
        engine = get_engine(s)
        db_ok = ping(engine)
        judge: JudgeHealth = judge_health(engine) if db_ok else "unknown"
        if not db_ok:
            response.status_code = 503
        return Health(
            status="ok" if db_ok and judge != "degraded" else "degraded",
            contract_version=CONTRACT_VERSION,
            app_version=app_version(),
            db="ok" if db_ok else "error",
            judge=judge,
            time=now_kst().isoformat(timespec="seconds"),
        )

    app.add_api_route("/health", health, methods=["GET"], response_model=Health, tags=["ops"])
    prefix = s.api_prefix.rstrip("/")
    if prefix:
        app.add_api_route(
            f"{prefix}/health",
            health,
            methods=["GET"],
            response_model=Health,
            tags=["ops"],
            include_in_schema=False,
        )

    router = _load_api_router()
    if router is not None and s.env == "dev":
        _install_docs(app)
    if router is not None:
        app.include_router(router, prefix=prefix)
        # WP5: 오류 본문을 계약 Error 로 맞추는 처리기(app.api.install) — 라우터 연결에 필요한 최소 수정
        install = getattr(importlib.import_module("app.api"), "install", None)
        if callable(install):
            install(app)
    return app


app = create_app()

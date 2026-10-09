"""FastAPI app factory (api 프로세스).

- ``/health`` (와 ``{API_PREFIX}/health``): ``{status, version, env, db}``. DB 가 안 되면 503 + ``degraded``.
- ``app.api`` 패키지에 ``router`` 가 있으면 ``API_PREFIX``(기본 ``/api``) 아래에 붙인다(WP5).
  없으면 건너뛴다. 인증 의존성은 WP5 가 router 쪽에 단다.
- nginx(web)는 ``/api/*`` 를 경로 그대로 api:8000 으로 넘긴다 → 개발·운영 경로가 같다.
"""

from __future__ import annotations

import importlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from typing import Literal

from fastapi import APIRouter, FastAPI, Response
from pydantic import BaseModel

from app.core.db import get_engine, ping, reset_engine
from app.core.logging import configure_logging, get_logger
from app.core.settings import Settings, get_settings

log = get_logger("app.main")


def app_version() -> str:
    try:
        return version("subscription-analyzer")
    except PackageNotFoundError:
        return "0.0.0+unknown"


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    env: str
    db: Literal["ok", "error"]


def _load_api_router() -> APIRouter | None:
    try:
        module = importlib.import_module("app.api")
    except ModuleNotFoundError as exc:
        if exc.name == "app.api":
            return None
        raise
    router = getattr(module, "router", None)
    return router if isinstance(router, APIRouter) else None


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        configure_logging(s)
        log.info("api.start", extra={"env": s.env, "version": app_version()})
        yield
        reset_engine()

    app = FastAPI(title="subscription-analyzer", version=app_version(), lifespan=lifespan)
    app.state.settings = s

    def health(response: Response) -> Health:
        db_ok = ping(get_engine(s))
        if not db_ok:
            response.status_code = 503
        return Health(
            status="ok" if db_ok else "degraded",
            version=app_version(),
            env=s.env,
            db="ok" if db_ok else "error",
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
    if router is not None:
        app.include_router(router, prefix=prefix)
        # WP5: 오류 본문을 계약 Error 로 맞추는 처리기(app.api.install) — 라우터 연결에 필요한 최소 수정
        install = getattr(importlib.import_module("app.api"), "install", None)
        if callable(install):
            install(app)
    return app


app = create_app()

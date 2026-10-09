"""완료 기준: schemathesis 가 contracts/openapi(.bundled).yaml 대비 전 엔드포인트 통과 (devseed DB 위에서).

``contracts/openapi.bundled.yaml`` 은 ``openapi.yaml`` 의 외부 $ref 를 푼 생성물(같은 계약)이다.
operation 마다 hypothesis 예시를 만들어 ASGI 앱을 직접 부르고 schemathesis 기본 검사(5xx 없음·상태 코드·
Content-Type·응답 스키마 등)를 돌린다. 쓰기 토큰을 쓰고, DB 는 모듈 단위 복사본이다.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from typing import Any

import pytest
import schemathesis
from hypothesis import HealthCheck, settings

from app.core.db import reset_engine
from app.core.settings import set_settings

from ._support import OPENAPI_BUNDLED, WRITE
from .conftest import Seeded, make_settings

schema = schemathesis.openapi.from_path(OPENAPI_BUNDLED)


@pytest.fixture(scope="module")
def st_app(seeded_db: Seeded, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Any]:
    from app.main import create_app

    base = tmp_path_factory.mktemp("schemathesis")
    db = base / "st.db"
    shutil.copyfile(seeded_db.db, db)
    s = make_settings(db, seeded_db.raw_dir, base / "reports")
    set_settings(s)
    try:
        yield create_app(s)
    finally:
        set_settings(None)
        reset_engine()


def _base_url(path: str) -> str:
    return "http://testserver" if path == "/health" else "http://testserver/api"


@schema.parametrize()
@settings(max_examples=30, deadline=None, suppress_health_check=list(HealthCheck))
def test_contract(case: Any, st_app: Any) -> None:
    case.call_and_validate(app=st_app, headers=dict(WRITE), base_url=_base_url(case.path))


def test_all_operations_covered() -> None:
    """openapi 의 operation 수와 앱 라우트가 맞는지(빠진 엔드포인트 없음)."""
    from app.main import create_app

    ops = {(op.method.upper(), op.path) for op in (r.ok() for r in schema.get_all_operations())}
    assert len(ops) == 31
    app = create_app()
    routes = set()
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", "")
        for m in methods:
            if m in {"HEAD", "OPTIONS"}:
                continue
            routes.add((m, path.removeprefix("/api") if path != "/health" else path))
    missing = sorted(o for o in ops if o not in routes)
    assert not missing, missing

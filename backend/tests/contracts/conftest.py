"""계약 테스트 픽스처 (WP0-A): 스키마 레지스트리·번들 문서·Postgres(pgserver 임베디드 또는 TEST_POSTGRES_URL)."""

# ruff: noqa: E501  (한국어 assertion 메시지·표)
from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from typing import Any

import pytest
from referencing import Registry

from ._support import OPENAPI_BUNDLED, OPENAPI_SRC, build_schema_registry, load_yaml, pgserver_database_url


@pytest.fixture(scope="session")
def schema_registry() -> Registry[Any]:
    return build_schema_registry()


@pytest.fixture(scope="session")
def bundled() -> dict[str, Any]:
    doc = load_yaml(OPENAPI_BUNDLED)
    assert isinstance(doc, dict)
    return doc


@pytest.fixture(scope="session")
def source_openapi() -> dict[str, Any]:
    doc = load_yaml(OPENAPI_SRC)
    assert isinstance(doc, dict)
    return doc


@pytest.fixture(scope="session")
def postgres_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Postgres 16 URL. TEST_POSTGRES_URL이 있으면 그것(CI: postgres 서비스 컨테이너, D25-8), 없으면 pgserver(임베디드
    Postgres — 로컬)를 띄운다. CI(``CI`` 환경변수)에서 둘 다 안 되면 skip 이 아니라 실패한다(조용한 공회전 금지)."""
    given = os.environ.get("TEST_POSTGRES_URL")
    if given:
        yield given
        return
    if os.environ.get("CI"):
        pytest.fail(
            "CI 에 TEST_POSTGRES_URL 없음 — .github/workflows/ci.yml backend-tests 의 postgres 서비스(D25-8)"
        )
    pgserver = pytest.importorskip("pgserver", reason="pgserver not installed and TEST_POSTGRES_URL not set")
    logging.getLogger("pgserver").setLevel(logging.WARNING)  # atexit 정리 로그가 닫힌 캡처 스트림에 쓰지 않게
    pgdata = tmp_path_factory.mktemp("pgdata")
    try:
        server = pgserver.get_server(pgdata, cleanup_mode="stop")
    except Exception as exc:  # pragma: no cover - 환경 의존
        pytest.skip(f"embedded Postgres could not start: {exc}")
    try:
        server.psql("CREATE DATABASE contracts_test;")
        yield pgserver_database_url(server.get_uri(), "contracts_test")
    finally:
        server.cleanup()

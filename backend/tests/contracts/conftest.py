"""계약 테스트 픽스처 (WP0-A): 스키마 레지스트리·번들 문서·Postgres(pgserver 임베디드 또는 TEST_POSTGRES_URL)."""

# ruff: noqa: E501  (한국어 assertion 메시지·표)
from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import pytest
from referencing import Registry

from ._support import OPENAPI_BUNDLED, OPENAPI_SRC, build_schema_registry, load_yaml


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
    """Postgres 16 URL. TEST_POSTGRES_URL이 있으면 그것, 없으면 pgserver(임베디드 Postgres)를 띄운다."""
    given = os.environ.get("TEST_POSTGRES_URL")
    if given:
        yield given
        return
    pgserver = pytest.importorskip("pgserver", reason="pgserver not installed and TEST_POSTGRES_URL not set")
    pgdata = tmp_path_factory.mktemp("pgdata")
    try:
        server = pgserver.get_server(pgdata, cleanup_mode="stop")
    except Exception as exc:  # pragma: no cover - 환경 의존
        pytest.skip(f"embedded Postgres could not start: {exc}")
    try:
        server.psql("CREATE DATABASE contracts_test;")
        uri: str = server.get_uri()
        base, _, _ = uri.rpartition("/")
        yield base.replace("postgresql://", "postgresql+psycopg://", 1) + "/contracts_test"
    finally:
        server.cleanup()

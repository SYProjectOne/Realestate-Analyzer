"""R5-OPS (D25) — 계약 테스트 쪽.

| 항목 | 테스트 |
| --- | --- |
| OPS-1 CI 실패: 리눅스 pgserver URL(유닉스 소켓 ``?host=/tmp/...``)에서 DB 이름을 바꾸다 소켓 경로를 망가뜨렸다 | ``test_pgserver_database_url_keeps_unix_socket_host`` · ``test_pgserver_database_url_tcp`` |
| OPS-5 마이그레이션 버전 파일은 앱(``app``)을 import 하지 않는다(D14-9) | ``test_migration_versions_do_not_import_app`` · ``test_app_import_detector_catches_synthetic`` |
"""

# ruff: noqa: E501  (한국어 assertion 메시지·표)

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from ._support import CONTRACTS

VERSIONS = CONTRACTS / "migrations" / "versions"


# ====================================================================== OPS-1 pgserver URL


def test_pgserver_database_url_keeps_unix_socket_host() -> None:
    """GitHub 리눅스(run 38326346203): pgserver 는 ``postgresql://postgres:@/postgres?host=/tmp/.../pgdata0`` 을 준다.

    예전 conftest 는 ``uri.rpartition('/')`` 로 DB 이름을 바꿔 소켓 폴더 경로의 마지막 조각을 DB 이름으로 덮었다
    (→ ``host=/tmp/pytest-of-runner/pytest-0/contracts_test`` — 'No such file or directory').
    """
    from ._support import pgserver_database_url

    uri = "postgresql://postgres:@/postgres?host=/tmp/pytest-of-runner/pytest-0/pgdata0"
    got = make_url(pgserver_database_url(uri, "contracts_test"))
    assert got.drivername == "postgresql+psycopg"
    assert got.database == "contracts_test"
    assert got.query.get("host") == "/tmp/pytest-of-runner/pytest-0/pgdata0"
    assert got.username == "postgres"


def test_pgserver_database_url_tcp() -> None:
    """Windows(로컬) pgserver 는 TCP URI — 같은 함수가 DB 이름만 바꾼다(로컬 경로 유지, D25-8)."""
    from ._support import pgserver_database_url

    got = make_url(pgserver_database_url("postgresql://postgres:@localhost:54321/postgres", "contracts_test"))
    assert (got.drivername, got.host, got.port, got.database) == (
        "postgresql+psycopg",
        "localhost",
        54321,
        "contracts_test",
    )


# ====================================================================== OPS-5 마이그레이션 ↛ app (D14-9)


def app_imports(source: str) -> list[str]:
    """``app`` 패키지 import(정적·``import_module``·``__import__`` 문자열) 목록."""
    out: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            out += [f"{node.lineno}: import {a.name}" for a in node.names if a.name.split(".")[0] == "app"]
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and (node.module or "").split(".")[0] == "app":
                out.append(f"{node.lineno}: from {node.module} import …")
        elif isinstance(node, ast.Call):
            f = node.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            if name in {"import_module", "__import__"} and node.args:
                arg = node.args[0]
                if (
                    isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and arg.value.split(".")[0] == "app"
                ):
                    out.append(f"{node.lineno}: {name}({arg.value!r})")
    return out


def _version_files() -> list[Path]:
    files = sorted(VERSIONS.glob("*.py"))
    assert len(files) >= 16, "마이그레이션 버전 파일을 못 찾았다"
    return files


@pytest.mark.parametrize("path", _version_files(), ids=lambda p: p.name)
def test_migration_versions_do_not_import_app(path: Path) -> None:
    """D14-9: 마이그레이션은 앱 코드를 import 하지 않는다 — 앱 모델이 바뀌어도 옛 마이그레이션의 의미가 그대로다."""
    assert app_imports(path.read_text(encoding="utf-8")) == []


def test_app_import_detector_catches_synthetic() -> None:
    for src in (
        "from app.models import Base",
        "import app.core.settings",
        "import app",
        "import importlib\nimportlib.import_module('app.snapshot_view')",
        "def f():\n    from app.snapshot_view import backfill\n",
        "__import__('app.models')",
    ):
        assert app_imports(src), src
    assert app_imports("import sqlalchemy as sa\nfrom alembic import op\nimport application") == []

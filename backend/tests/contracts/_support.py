"""계약 테스트 공용 경로·로더 (WP0-A). 픽스처는 conftest.py."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from alembic.config import Config
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
CONTRACTS = REPO / "contracts"
SCHEMAS = CONTRACTS / "schemas"
EXAMPLES = CONTRACTS / "examples"
FIXTURE = CONTRACTS / "fixtures" / "incheon_gimpo_2026-10-08"
OPENAPI_SRC = CONTRACTS / "openapi.yaml"
OPENAPI_BUNDLED = CONTRACTS / "openapi.bundled.yaml"
MIGRATION_0001 = CONTRACTS / "migrations" / "versions" / "0001_init.py"


def pgserver_database_url(uri: str, database: str) -> str:
    """pgserver ``get_uri()`` → 같은 서버의 ``database`` DB SQLAlchemy URL(psycopg 드라이버).

    리눅스 pgserver 는 유닉스 소켓 URI(``postgresql://postgres:@/postgres?host=/tmp/.../pgdata0``)를,
    Windows 는 TCP URI 를 준다. 문자열 자르기(``rpartition('/')``)로 DB 이름을 바꾸면 소켓 폴더 경로가
    깨진다(R5-OPS 1, CI run 38326346203) — URL 로 다룬다.
    """
    from sqlalchemy.engine import make_url

    url = make_url(uri).set(drivername="postgresql+psycopg", database=database)
    return url.render_as_string(hide_password=False)


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def schema_paths() -> list[Path]:
    return sorted(p for p in SCHEMAS.rglob("*.json"))


def schema_rel(path: Path) -> str:
    return path.relative_to(SCHEMAS).as_posix()


def build_schema_registry() -> Registry[Any]:
    """각 스키마를 schemas/ 기준 상대 경로로 등록한다($id가 상대 경로라 $ref도 그 기준으로 풀린다)."""
    registry: Registry[Any] = Registry()
    for path in schema_paths():
        resource = Resource.from_contents(load_json(path), default_specification=DRAFT202012)
        registry = registry.with_resource(schema_rel(path), resource)
    return registry


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg

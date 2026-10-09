"""contracts/migrations — upgrade/downgrade/upgrade(SQLite·Postgres 16), models ↔ migration diff 0, 시드, 유일 제약."""

# ruff: noqa: E501  (한국어 assertion 메시지·표)
from __future__ import annotations

import importlib.util
import json
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.engine import Engine

from app.models import Base

from ._support import EXAMPLES, MIGRATION_0001, alembic_config, load_json

# RA §3 의 모든 테이블 + DECISIONS D2-1 참조 테이블 4개
RA_TABLES = {
    "region", "snapshot", "complex", "complex_type", "payment_terms", "competition", "remaining_event",
    "intake_status", "raw_document", "field_provenance", "benchmark", "rtms_trade", "comparable_set", "catalyst",
    "catalyst_link", "supply", "unsold", "judgment_log", "claim", "scenario", "score_run", "score_component",
    "score_total", "ladder", "decision", "human_check", "checklist_item", "change_event", "job_run",
}  # fmt: skip
D2_TABLES = {"legal_dong", "admin_dong", "admin_legal_map", "household_stat"}
RA_WEIGHTS = {
    "base": {"p10": 0.35, "rerank": 0.20, "gap": 0.15, "benchmark": 0.10, "supply": 0.10, "liquidity": 0.10},
    "A": {"p10": 0.35, "rerank": 0.20, "gap": 0.15, "benchmark": 0.10, "supply": 0.10, "move_in": 0.10},
    "B": {"p10": 0.30, "rerank": 0.15, "gap": 0.20, "benchmark": 0.10, "supply": 0.10, "liquidity": 0.15},
    "C": {"p10": 0.45, "rerank": 0.15, "gap": 0.15, "benchmark": 0.05, "supply": 0.05, "liquidity": 0.15},
    "D": {"p10": 0.35, "rerank": 0.20, "gap": 0.15, "benchmark": 0.10, "supply": 0.10, "move_in": 0.10},
}


def migration_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("contract_migration_0001", MIGRATION_0001)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sqlite_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'contracts.db').as_posix()}"


def upgrade_downgrade_upgrade(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = alembic_config(url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    engine = sa.create_engine(url)
    try:
        left = set(sa.inspect(engine).get_table_names()) - {"alembic_version"}
    finally:
        engine.dispose()
    assert left == set(), f"downgrade base 후 남은 테이블: {left}"
    command.upgrade(cfg, "head")


@pytest.fixture
def sqlite_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    url = sqlite_url(tmp_path)
    upgrade_downgrade_upgrade(url, monkeypatch)
    engine = sa.create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def pg_engine(postgres_url: str) -> Iterator[Engine]:
    mp = pytest.MonkeyPatch()
    try:
        upgrade_downgrade_upgrade(postgres_url, mp)
    finally:
        mp.undo()
    engine = sa.create_engine(postgres_url)
    yield engine
    engine.dispose()


def autogen_diff(engine: Engine) -> list[Any]:
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        return list(compare_metadata(ctx, Base.metadata))


def check_tables(engine: Engine) -> None:
    tables = set(sa.inspect(engine).get_table_names()) - {"alembic_version"}
    assert tables == RA_TABLES | D2_TABLES


def check_seeds(engine: Engine) -> None:
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text("SELECT id, code, name, is_builtin, weights FROM scenario ORDER BY id")
        ).all()
    assert [r.code for r in rows] == ["base", "A", "B", "C", "D"]
    assert [r.id for r in rows] == [1, 2, 3, 4, 5]
    for r in rows:
        weights = r.weights if isinstance(r.weights, dict) else json.loads(r.weights)
        assert bool(r.is_builtin) is True
        assert weights == RA_WEIGHTS[r.code], r.code
        assert sum(Decimal(str(v)) for v in weights.values()) == Decimal("1"), r.code
        assert ("move_in" in weights) is (r.code in ("A", "D")), "A·D는 liquidity → move_in"


UNIQUE_REQUIRED = {
    ("judgment_log", ("input_hash",)),
    ("raw_document", ("sha256",)),
    ("snapshot", ("region_id", "asof_date")),
    ("complex", ("applyhome_id",)),
    ("complex_type", ("complex_id", "type_code")),
    ("payment_terms", ("complex_id", "notice_no")),
    ("admin_legal_map", ("admin_code", "legal_code")),
    ("ladder", ("snapshot_id", "complex_id", "horizon")),
    ("score_total", ("score_run_id", "complex_id")),
    ("score_component", ("score_run_id", "complex_id", "component")),
    ("catalyst_link", ("catalyst_id", "complex_id")),
    ("scenario", ("code",)),
}


def check_uniques(engine: Engine) -> None:
    insp = sa.inspect(engine)
    found = set()
    for table in {t for t, _ in UNIQUE_REQUIRED}:
        for uq in insp.get_unique_constraints(table):
            found.add((table, tuple(uq["column_names"])))
        for ix in insp.get_indexes(table):
            if ix.get("unique"):
                found.add((table, tuple(ix["column_names"])))
    assert UNIQUE_REQUIRED - found == set()


def check_input_hash_rejects_duplicates(engine: Engine) -> None:
    table = Base.metadata.tables["judgment_log"]
    row = {
        "tool": "decide", "purpose": "decide:scenario_B", "input_hash": "sha256:" + "a" * 64, "input_json": {},
        "output_json": {}, "status": "ok", "created_at": "2026-10-08T00:00:00+09:00", "adapter_version": "t",
    }  # fmt: skip
    with engine.begin() as conn:
        conn.execute(table.insert(), row)
    with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
        conn.execute(table.insert(), row)
    with engine.begin() as conn:
        conn.execute(table.delete())


def check_enum_check_rejects(engine: Engine) -> None:
    table = Base.metadata.tables["job_run"]
    bad = {
        "job_name": "report.md",
        "kind": "manual",
        "payload": {},
        "scheduled_at": "2026-10-08",
        "stats": {},
    }
    with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
        conn.execute(table.insert(), bad)


# ---------------------------------------------------------------- SQLite


def test_sqlite_upgrade_downgrade_upgrade(sqlite_engine: Engine) -> None:
    check_tables(sqlite_engine)


def test_sqlite_models_match_migration(sqlite_engine: Engine) -> None:
    assert autogen_diff(sqlite_engine) == []


def test_sqlite_builtin_scenarios_seeded(sqlite_engine: Engine) -> None:
    check_seeds(sqlite_engine)


def test_sqlite_unique_constraints(sqlite_engine: Engine) -> None:
    check_uniques(sqlite_engine)
    check_input_hash_rejects_duplicates(sqlite_engine)
    check_enum_check_rejects(sqlite_engine)


def test_sqlite_check_constraints_match_models(sqlite_engine: Engine) -> None:
    """마이그레이션의 CHECK 리터럴이 app.models.enums 와 같다(autogenerate는 CHECK를 비교하지 않으므로 따로)."""
    insp = sa.inspect(sqlite_engine)
    for table in Base.metadata.sorted_tables:
        model = {
            str(c.name): " ".join(str(c.sqltext).split())
            for c in table.constraints
            if isinstance(c, sa.CheckConstraint)
        }
        db = {
            str(c["name"]): " ".join(str(c["sqltext"]).split())
            for c in insp.get_check_constraints(table.name)
        }
        assert db == model, table.name


def test_seed_matches_openapi_scenarios_example() -> None:
    example = load_json(EXAMPLES / "scenarios_list.json")["value"]
    seeds = migration_module().BUILTIN_SCENARIOS
    assert [{k: v for k, v in s.items() if k != "id"} for s in example] == seeds


def test_region_has_d2_2_columns() -> None:
    cols = {c.name for c in Base.metadata.tables["region"].columns}
    need = {"query_text", "selections", "sigungu_codes", "sido_codes", "legal_dong_codes", "supply_ref_pct", "status",
            "created_at", "living_areas", "age_premium_coef", "applyhome_query"}  # fmt: skip
    assert need <= cols


def test_column_type_policy() -> None:
    """금액 *_won = BigInteger, 면적 *_m2 = Numeric(8,2), 날짜·시각 문자열 = String(10|7|32)."""
    problems = []
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            name, typ = col.name, col.type
            if name.endswith("_won") and not isinstance(typ, sa.BigInteger):
                problems.append(f"{table.name}.{name} {typ}")
            if name.endswith("_m2") and not (
                isinstance(typ, sa.Numeric) and (typ.precision, typ.scale) == (8, 2)
            ):
                problems.append(f"{table.name}.{name} {typ}")
            if name.endswith(("_date", "_from")) and not (isinstance(typ, sa.String) and typ.length == 10):
                problems.append(f"{table.name}.{name} {typ}")
            if name.endswith("_ym") and not (isinstance(typ, sa.String) and typ.length == 7):
                problems.append(f"{table.name}.{name} {typ}")
            if name.endswith("_at") and not (isinstance(typ, sa.String) and typ.length == 32):
                problems.append(f"{table.name}.{name} {typ}")
    assert problems == []


# ---------------------------------------------------------------- Postgres 16


@pytest.mark.postgres
def test_postgres_upgrade_downgrade_upgrade(pg_engine: Engine) -> None:
    with pg_engine.connect() as conn:
        version = conn.execute(sa.text("SHOW server_version")).scalar_one()
    assert str(version).startswith("16"), version
    check_tables(pg_engine)


@pytest.mark.postgres
def test_postgres_models_match_migration(pg_engine: Engine) -> None:
    assert autogen_diff(pg_engine) == []


@pytest.mark.postgres
def test_postgres_seeds_and_constraints(pg_engine: Engine) -> None:
    check_seeds(pg_engine)
    check_uniques(pg_engine)
    check_input_hash_rejects_duplicates(pg_engine)
    check_enum_check_rejects(pg_engine)

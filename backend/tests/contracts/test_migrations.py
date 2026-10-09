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
R3_TABLES = {"share_link", "fact_demotion"}  # 계약 2026-10-09.4 · 2026-10-09.6
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
    assert tables == RA_TABLES | D2_TABLES | R3_TABLES


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
    ("complex", ("region_id", "applyhome_id")),  # 0004 (W4)
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
    spec = importlib.util.spec_from_file_location(
        "contract_migration_0005", MIGRATION_0001.with_name("0005_wait_new.py")
    )
    assert spec is not None and spec.loader is not None
    m5 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m5)
    # 0005(계약 2026-10-09.5): policy.include_wait_new 명시(A 만 true) — 0001 시드 + 0005 = 예시
    seeds = [
        {**s, "policy": {**s["policy"], "include_wait_new": m5.BUILTIN_WAIT_NEW[s["code"]]}} for s in seeds
    ]
    assert [{k: v for k, v in s.items() if k != "id"} for s in example] == seeds


R1_COLUMNS = {
    ("field_provenance", "value_norm"),
    ("field_provenance", "observed_on"),
    ("complex_type", "notice_type_code"),
    ("payment_terms", "price_by_type"),
    ("raw_document", "table_path"),
    ("raw_document", "meta"),
}


def _columns(engine: Engine) -> set[tuple[str, str]]:
    insp = sa.inspect(engine)
    return {(t, c["name"]) for t, _ in R1_COLUMNS for c in insp.get_columns(t)}


def check_0001_0002_roundtrip(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """0002(계약 2026-10-09.2): head → 0001(컬럼 제거, 행 유지) → head(컬럼 복구)."""
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = alembic_config(url)
    command.upgrade(cfg, "head")
    engine = sa.create_engine(url)
    try:
        assert _columns(engine) >= R1_COLUMNS
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO raw_document (source_kind, url, fetched_at, sha256, table_path, meta) "
                    "VALUES ('notice_pdf', 'u', '2026-10-09T00:00:00+09:00', :sha, 't.json', :meta)"
                ),
                {"sha": "b" * 64, "meta": json.dumps({"pages": 3})},
            )
        command.downgrade(cfg, "0001")
        assert _columns(engine) & R1_COLUMNS == set()
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT count(*) FROM raw_document")).scalar_one() == 1
        command.upgrade(cfg, "head")
        assert _columns(engine) >= R1_COLUMNS
        with engine.begin() as conn:
            row = conn.execute(sa.text("SELECT table_path, meta FROM raw_document")).one()
            assert tuple(row) == (None, None)
            conn.execute(sa.text("DELETE FROM raw_document"))
    finally:
        engine.dispose()


def test_sqlite_0001_0002_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    check_0001_0002_roundtrip(sqlite_url(tmp_path), monkeypatch)


def test_migration_head_is_0007() -> None:
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(alembic_config("sqlite://"))
    assert script.get_heads() == ["0007"]
    assert script.get_revision("0007").down_revision == "0006"
    assert script.get_revision("0006").down_revision == "0005"
    assert script.get_revision("0005").down_revision == "0004"
    assert script.get_revision("0004").down_revision == "0003"
    assert script.get_revision("0003").down_revision == "0002"
    assert script.get_revision("0002").down_revision == "0001"


R2_COLUMNS = {("judgment_log", "result_json"), ("score_total", "judge_scope")}


def _r2_columns(engine: Engine) -> set[tuple[str, str]]:
    insp = sa.inspect(engine)
    have = {(t, c["name"]) for t in {t for t, _ in R2_COLUMNS} for c in insp.get_columns(t)}
    return have & R2_COLUMNS


def check_0002_0003_roundtrip(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """0003(계약 2026-10-09.3): head → 0002(컬럼 제거, 행 유지) → head(컬럼 복구, 값 NULL)."""
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = alembic_config(url)
    command.upgrade(cfg, "head")
    engine = sa.create_engine(url)
    table = Base.metadata.tables["judgment_log"]
    row = {
        "tool": "classify", "purpose": "classify:intake", "input_hash": "sha256:" + "c" * 64, "input_json": {},
        "output_json": {}, "status": "ok", "created_at": "2026-10-09T00:00:00+09:00", "adapter_version": "t",
        "result_json": {"label": "batch", "items": []},
    }  # fmt: skip
    try:
        assert _r2_columns(engine) == R2_COLUMNS
        with engine.begin() as conn:
            conn.execute(table.insert(), row)
        command.downgrade(cfg, "0002")
        assert _r2_columns(engine) == set()
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT count(*) FROM judgment_log")).scalar_one() == 1
        command.upgrade(cfg, "head")
        assert _r2_columns(engine) == R2_COLUMNS
        with engine.begin() as conn:
            assert conn.execute(sa.text("SELECT result_json FROM judgment_log")).scalar_one() is None
            conn.execute(sa.text("DELETE FROM judgment_log"))
    finally:
        engine.dispose()


def test_sqlite_0002_0003_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    check_0002_0003_roundtrip(sqlite_url(tmp_path), monkeypatch)


def _job_row(job_name: str) -> dict[str, Any]:
    return {
        "job_name": job_name, "kind": "manual", "payload": {}, "scheduled_at": "2026-10-09T00:00:00+09:00",
        "status": "queued", "stats": {},
    }  # fmt: skip


def check_0003_0004_roundtrip(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """0004(계약 2026-10-09.4): share_link 테이블 + job_run.job_name CHECK 에 claim.reverify.

    head → 0003(share_link 제거, claim.reverify 잡 행 삭제 — 옛 CHECK 를 통과할 수 없다, 다른 잡 행 유지) → head.
    """
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = alembic_config(url)
    command.upgrade(cfg, "head")
    engine = sa.create_engine(url)
    jobs = Base.metadata.tables["job_run"]
    links = Base.metadata.tables["share_link"]
    try:
        with engine.begin() as conn:
            conn.execute(jobs.insert(), [_job_row("claim.reverify"), _job_row("rejudge")])
            conn.execute(
                links.insert(),
                {"token_sha256": "d" * 64, "label": None, "created_at": "2026-10-09T00:00:00+09:00",
                 "expires_at": "2026-11-08T00:00:00+09:00", "revoked_at": None},
            )  # fmt: skip
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
            conn.execute(jobs.insert(), _job_row("claim.verify"))
        cols = {c["name"] for c in sa.inspect(engine).get_columns("score_component")}
        assert {"unadjusted_gap_pct", "unadjusted_median_won"} <= cols
        command.downgrade(cfg, "0003")
        assert "share_link" not in sa.inspect(engine).get_table_names()
        cols = {c["name"] for c in sa.inspect(engine).get_columns("score_component")}
        assert not {"unadjusted_gap_pct", "unadjusted_median_won"} & cols
        with engine.connect() as conn:
            names = [r[0] for r in conn.execute(sa.text("SELECT job_name FROM job_run"))]
        assert names == ["rejudge"]
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
            conn.execute(jobs.insert(), _job_row("claim.reverify"))
        command.upgrade(cfg, "head")
        assert "share_link" in sa.inspect(engine).get_table_names()
        with engine.begin() as conn:
            conn.execute(jobs.insert(), _job_row("claim.reverify"))
            conn.execute(sa.text("DELETE FROM job_run"))
    finally:
        engine.dispose()


def test_sqlite_0003_0004_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    check_0003_0004_roundtrip(sqlite_url(tmp_path), monkeypatch)


def _policies(engine: Engine) -> dict[str, dict[str, object]]:
    with engine.connect() as conn:
        rows = conn.execute(sa.text("SELECT code, policy FROM scenario ORDER BY id")).all()
    return {str(r.code): r.policy if isinstance(r.policy, dict) else json.loads(r.policy) for r in rows}


def check_0004_0005_roundtrip(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """0005(계약 2026-10-09.5): 내장 시나리오 policy.include_wait_new(A 만 true) — head → 0004(키 제거) → head."""
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = alembic_config(url)
    command.upgrade(cfg, "head")
    engine = sa.create_engine(url)
    try:
        pol = _policies(engine)
        assert {c: p.get("include_wait_new") for c, p in pol.items()} == {
            "base": False, "A": True, "B": False, "C": False, "D": False,
        }  # fmt: skip
        command.downgrade(cfg, "0004")
        assert all("include_wait_new" not in p for p in _policies(engine).values())
        command.upgrade(cfg, "head")
        assert _policies(engine)["A"]["include_wait_new"] is True
    finally:
        engine.dispose()


def test_sqlite_0004_0005_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    check_0004_0005_roundtrip(sqlite_url(tmp_path), monkeypatch)


@pytest.mark.postgres
def test_postgres_0004_0005_roundtrip(pg_engine: Engine, postgres_url: str) -> None:
    mp = pytest.MonkeyPatch()
    try:
        check_0004_0005_roundtrip(postgres_url, mp)
    finally:
        mp.undo()


def check_0005_0006_roundtrip(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """0006(계약 2026-10-09.6): claim 대상 컬럼·fact_demotion·checklist '사실 재확인'·benchmark.snapshot_id —
    head(행 넣기) → 0005('사실 재확인' → '법적 확인', 컬럼·테이블 제거) → head."""
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = alembic_config(url)
    command.upgrade(cfg, "head")
    engine = sa.create_engine(url)
    try:
        insp = sa.inspect(engine)
        assert {"entity", "entity_id", "field"} <= {c["name"] for c in insp.get_columns("claim")}
        assert "snapshot_id" in {c["name"] for c in insp.get_columns("benchmark")}
        assert "fact_demotion" in insp.get_table_names()
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO checklist_item (kind, title, status) VALUES ('사실 재확인', 't', 'open')"
                )
            )
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
            conn.execute(
                sa.text("INSERT INTO checklist_item (kind, title, status) VALUES ('없는 값', 't', 'open')")
            )
        command.downgrade(cfg, "0005")
        insp = sa.inspect(engine)
        assert "fact_demotion" not in insp.get_table_names()
        assert not {"entity", "entity_id", "field"} & {c["name"] for c in insp.get_columns("claim")}
        assert "snapshot_id" not in {c["name"] for c in insp.get_columns("benchmark")}
        with engine.connect() as conn:
            kinds = [r[0] for r in conn.execute(sa.text("SELECT kind FROM checklist_item"))]
        assert kinds == ["법적 확인"]
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO checklist_item (kind, title, status) VALUES ('사실 재확인', 't', 'open')"
                )
            )
        command.upgrade(cfg, "head")
        with engine.begin() as conn:
            conn.execute(sa.text("DELETE FROM checklist_item"))
    finally:
        engine.dispose()


def test_sqlite_0005_0006_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    check_0005_0006_roundtrip(sqlite_url(tmp_path), monkeypatch)
    engine = sa.create_engine(sqlite_url(tmp_path))
    try:
        assert autogen_diff(engine) == []
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_postgres_0005_0006_roundtrip(pg_engine: Engine, postgres_url: str) -> None:
    mp = pytest.MonkeyPatch()
    try:
        check_0005_0006_roundtrip(postgres_url, mp)
    finally:
        mp.undo()
    assert autogen_diff(pg_engine) == []


def check_0006_0007_roundtrip(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """0007(계약 2026-10-09.7): benchmark.substitute — 0006 에서 note 표식 행·일반 행을 넣고 head(note → 컬럼 채움)
    → 0006(컬럼 제거, note 그대로) → head."""
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = alembic_config(url)
    command.upgrade(cfg, "head")  # 공유 DB(Postgres)는 이미 head — 0006 으로 내려 시작한다
    command.downgrade(cfg, "0006")
    engine = sa.create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO region (id, name, query_text, selections, sido_codes, sigungu_codes, "
                    "legal_dong_codes, living_areas, age_premium_coef, applyhome_query, status, created_at) "
                    "VALUES (901, 't', 't', '[]', '[]', '[]', '[]', '[]', '{}', '{}', 'ready', "
                    "'2026-10-10T00:00:00+09:00')"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO benchmark (id, region_id, name, note) VALUES "
                    "(1, 901, '대체', '[bm:1:1:la_2] · 추정(대체: 지역 전체) — 생활권 la_2 자체 표본 0'), "
                    "(2, 901, '자기', '[bm:1:1] · 분양가 = 청약홈'), (3, 901, '수동', NULL)"
                )
            )
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            rows = dict(conn.execute(sa.text("SELECT id, substitute FROM benchmark ORDER BY id")).all())
        assert {k: bool(v) for k, v in rows.items()} == {1: True, 2: False, 3: False}
        with engine.begin() as conn:  # 새 행 기본값 false
            conn.execute(sa.text("INSERT INTO benchmark (id, region_id, name) VALUES (4, 901, '새 행')"))
            assert not conn.execute(sa.text("SELECT substitute FROM benchmark WHERE id = 4")).scalar_one()
        command.downgrade(cfg, "0006")
        insp = sa.inspect(engine)
        assert "substitute" not in {c["name"] for c in insp.get_columns("benchmark")}
        with engine.connect() as conn:
            notes = conn.execute(sa.text("SELECT note FROM benchmark WHERE id = 1")).scalar_one()
        assert "추정(대체: 지역 전체)" in notes  # 대체 표식(note)은 남는다
        command.upgrade(cfg, "head")
        with engine.begin() as conn:
            assert conn.execute(sa.text("SELECT substitute FROM benchmark WHERE id = 1")).scalar_one()
            conn.execute(sa.text("DELETE FROM benchmark"))
            conn.execute(sa.text("DELETE FROM region WHERE id = 901"))
    finally:
        engine.dispose()


def test_sqlite_0006_0007_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    check_0006_0007_roundtrip(sqlite_url(tmp_path), monkeypatch)
    engine = sa.create_engine(sqlite_url(tmp_path))
    try:
        assert autogen_diff(engine) == []
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_postgres_0006_0007_roundtrip(pg_engine: Engine, postgres_url: str) -> None:
    mp = pytest.MonkeyPatch()
    try:
        check_0006_0007_roundtrip(postgres_url, mp)
    finally:
        mp.undo()
    assert autogen_diff(pg_engine) == []


@pytest.mark.postgres
def test_postgres_0003_0004_roundtrip(pg_engine: Engine, postgres_url: str) -> None:
    mp = pytest.MonkeyPatch()
    try:
        check_0003_0004_roundtrip(postgres_url, mp)
    finally:
        mp.undo()
    assert autogen_diff(pg_engine) == []


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
def test_postgres_0001_0002_roundtrip(pg_engine: Engine, postgres_url: str) -> None:
    mp = pytest.MonkeyPatch()
    try:
        check_0001_0002_roundtrip(postgres_url, mp)
    finally:
        mp.undo()
    assert autogen_diff(pg_engine) == []


@pytest.mark.postgres
def test_postgres_0002_0003_roundtrip(pg_engine: Engine, postgres_url: str) -> None:
    mp = pytest.MonkeyPatch()
    try:
        check_0002_0003_roundtrip(postgres_url, mp)
    finally:
        mp.undo()
    assert autogen_diff(pg_engine) == []


@pytest.mark.postgres
def test_postgres_seeds_and_constraints(pg_engine: Engine) -> None:
    check_seeds(pg_engine)
    check_uniques(pg_engine)
    check_input_hash_rejects_duplicates(pg_engine)
    check_enum_check_rejects(pg_engine)

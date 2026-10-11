"""R3f CORE4 — 마이그레이션 0010·0011 + backfill 왕복을 **단지·시나리오가 있는 픽스처**로 (R3 6차 m28 · m2 · D14-4 · D14-9).

devseed(인천·김포 픽스처 — 단지 16·시나리오 5·발행 스냅샷 11·12)를 SQLite 에 만들고, 그 행을 그대로 대상 DB(SQLite·
임베디드 Postgres 16)에 옮긴 뒤:

1. head → 0009(저장본 삭제·빈 snapshot_state) → head: 0010·0011 은 앱 코드 없이 테이블만(발행 리비전 저장본 0행 — GET 503)
2. ``snapshot_view.backfill`` → 발행 스냅샷마다 저장본 종류 전부(시나리오 5 × 단지 상세 등), 계약 버전 = 현재
3. backfill 다시 → 0행(멱등)
4. 0011 → 0010 downgrade: provenance·claims 행 삭제, contract_version 열 삭제 → head 다시 → 기존 행 = 식별 변환(현재 계약 버전)
   → backfill 은 새 종류만 채운다
5. autogenerate diff 0
"""

# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.engine import Engine

from app.models import Base

from ._support import alembic_config

BACKEND = Path(__file__).resolve().parents[2]
FIXTURE = BACKEND.parent / "contracts" / "fixtures" / "incheon_gimpo_2026-10-08"


@pytest.fixture(scope="module")
def seeded_sqlite(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    from app.api import devseed
    from app.core.db import reset_engine
    from app.core.settings import Settings, set_settings

    base = tmp_path_factory.mktemp("m28seed")
    db = base / "seed.db"
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        env="dev",
        database_url=f"sqlite:///{db.as_posix()}",
        raw_dir=base / "raw",
        reference_dir=base / "reference",
        report_dir=base / "reports",
        judge_adapter="mock",
        log_json=False,
    )
    set_settings(settings)
    try:
        devseed.seed(settings, fixture_dir=FIXTURE, reference="region")
    finally:
        set_settings(None)
        reset_engine()
    yield db


def _copy_rows(src_url: str, dst: Engine) -> dict[str, int]:
    """devseed SQLite 의 모든 모델 테이블 행 → 대상 DB(같은 head 스키마). Postgres 는 id 시퀀스를 맞춘다."""
    src = sa.create_engine(src_url)
    counts: dict[str, int] = {}
    _wipe(dst)  # 0001 시드 시나리오 등 — devseed 행으로 바꾼다
    try:
        with src.connect() as s, dst.begin() as d:
            for table in Base.metadata.sorted_tables:
                rows = [dict(r._mapping) for r in s.execute(sa.select(table))]
                if rows:
                    d.execute(table.insert(), rows)
                counts[table.name] = len(rows)
            if dst.dialect.name == "postgresql":
                for table in Base.metadata.sorted_tables:
                    if "id" in table.c and isinstance(table.c.id.type, sa.Integer) and counts.get(table.name):
                        d.execute(
                            sa.text(
                                f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), "
                                f"(SELECT MAX(id) FROM {table.name}))"
                            )
                        )
    finally:
        src.dispose()
    return counts


def _wipe(engine: Engine) -> None:
    with engine.begin() as d:
        for table in reversed(Base.metadata.sorted_tables):
            if table.name in sa.inspect(d).get_table_names():
                d.execute(table.delete())


def _view_counts(engine: Engine) -> dict[tuple[int, str], int]:
    with engine.connect() as c:
        return {
            (int(sid), str(kind)): int(n)
            for sid, kind, n in c.execute(
                sa.text("SELECT snapshot_id, kind, COUNT(*) FROM snapshot_view GROUP BY snapshot_id, kind")
            )
        }


def check_0010_0011_backfill_roundtrip(url: str, seed_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.db import reset_engine
    from app.core.protocols import CONTRACT_VERSION
    from app.core.settings import Settings, set_settings
    from app.snapshot_view import KINDS, backfill

    monkeypatch.setenv("DATABASE_URL", url)
    cfg = alembic_config(url)
    command.upgrade(cfg, "head")
    engine = sa.create_engine(url)
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        env="dev",
        database_url=url,
        raw_dir=seed_db.parent / "raw",
        reference_dir=seed_db.parent / "reference",
        report_dir=seed_db.parent / "reports",
        judge_adapter="mock",
        log_json=False,
    )
    set_settings(settings)
    try:
        counts = _copy_rows(f"sqlite:///{seed_db.as_posix()}", engine)
        assert counts["complex"] >= 10 and counts["scenario"] >= 5 and counts["snapshot_view"] > 0
        with engine.connect() as c:
            published = sorted(
                int(i)
                for i in c.execute(sa.text("SELECT id FROM snapshot WHERE status = 'published'")).scalars()
            )
        assert published

        # 1. head → 0009 → head (0010·0011 은 테이블만 — 저장본은 backfill 몫)
        command.downgrade(cfg, "0009")
        insp = sa.inspect(engine)
        assert "snapshot_view" not in insp.get_table_names() and "snapshot_state" in insp.get_table_names()
        command.upgrade(cfg, "head")
        assert not _view_counts(engine)
        with engine.connect() as c:
            cols = {col["name"] for col in sa.inspect(c).get_columns("snapshot_view")}
        assert "contract_version" in cols

        # 2. backfill — 발행 스냅샷마다 종류 전부, 시나리오 5
        reset_engine()
        res = backfill(engine, settings=settings)
        assert sorted(res["snapshots"]) == published and res["rows"] > 0
        views = _view_counts(engine)
        with engine.connect() as c:
            n_cx = c.execute(sa.text("SELECT COUNT(*) FROM complex WHERE region_id = 1")).scalar_one()
            n_sc = c.execute(sa.text("SELECT COUNT(*) FROM scenario")).scalar_one()
            versions = set(
                c.execute(sa.text("SELECT DISTINCT contract_version FROM snapshot_view")).scalars()
            )
        for sid in published:
            have = {k for (s, k) in views if s == sid}
            assert have >= set(KINDS) - {"report"}, (sid, set(KINDS) - have)
            assert views[(sid, "complex")] == n_cx * n_sc
            assert views[(sid, "dashboard")] == n_sc
        assert versions == {CONTRACT_VERSION}

        # 3. 멱등
        again = backfill(engine, settings=settings)
        assert again["snapshots"] == [] and again["rows"] == 0
        assert _view_counts(engine) == views

        # 4. 0011 downgrade(새 종류·버전 열 삭제) → head(식별 변환) → backfill 은 새 종류만
        command.downgrade(cfg, "0010")
        with engine.connect() as c:
            kinds_0010 = set(c.execute(sa.text("SELECT DISTINCT kind FROM snapshot_view")).scalars())
            assert "contract_version" not in {
                col["name"] for col in sa.inspect(c).get_columns("snapshot_view")
            }
        assert kinds_0010.isdisjoint({"provenance", "claims"})
        command.upgrade(cfg, "head")
        with (
            engine.connect() as c
        ):  # 0011 = 식별 변환('.11' 기록) · 0012 = 모양 버전 1(D15-3 — 읽기 호환은 이것)
            assert set(
                c.execute(sa.text("SELECT DISTINCT contract_version FROM snapshot_view")).scalars()
            ) == {"2026-10-09.11"}
            assert set(c.execute(sa.text("SELECT DISTINCT shape_version FROM snapshot_view")).scalars()) == {
                1
            }
        refill = backfill(engine, settings=settings)
        assert sorted(refill["snapshots"]) == published
        after = _view_counts(engine)
        assert after == views

        # kind CHECK — 새 종류는 받고 모르는 종류는 거부
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as c:
            c.execute(
                sa.text(
                    "INSERT INTO snapshot_view (snapshot_id, kind, key, scenario, body, sha256, contract_version) "
                    "SELECT snapshot_id, 'nope', 'x', scenario, body, sha256, contract_version FROM snapshot_view WHERE kind = 'claims'"
                )
            )
        with engine.connect() as c:
            ctx = MigrationContext.configure(c, opts={"compare_type": True})
            assert compare_metadata(ctx, Base.metadata) == []
    finally:
        set_settings(None)
        reset_engine()
        command.upgrade(cfg, "head")
        _wipe(engine)  # 같은 Postgres DB 를 쓰는 다음 계약 테스트를 위해 비우고 처음(base)으로
        command.downgrade(cfg, "base")
        engine.dispose()


def test_sqlite_0010_0011_backfill_roundtrip_with_fixture(
    seeded_sqlite: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    check_0010_0011_backfill_roundtrip(
        f"sqlite:///{(tmp_path / 'm28.db').as_posix()}", seeded_sqlite, monkeypatch
    )


@pytest.mark.postgres
def test_postgres_0010_0011_backfill_roundtrip_with_fixture(seeded_sqlite: Path, postgres_url: str) -> None:
    mp = pytest.MonkeyPatch()
    try:
        check_0010_0011_backfill_roundtrip(postgres_url, seeded_sqlite, mp)
    finally:
        mp.undo()

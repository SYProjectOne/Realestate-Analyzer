"""R3g CORE5 — 마이그레이션 0012(완료 표식·저장 모양 버전·발행 임대) 왕복 + 표식 재구성 + backfill 재개
(R3 7차 M2·m9 · D15-3), **단지·시나리오가 있는 픽스처**(devseed 인천·김포 — 단지 16·시나리오 5·발행 11·12)로 SQLite·임베디드
Postgres 16 둘 다.

1. head(표식 있음) → 0011(표·열 삭제) → head: 0012 데이터 단계가 기존 행 묶음을 done 표식으로(rows = 행 수) — 표식이 head 의
   것과 같고 GET 할 저장본은 그대로(backfill 0행)
2. 0011 에서 행 일부를 지운 DB(0012 이전 backfill 이 묶음 쓰기 중간에 멈춘 모양 — 한 시나리오 단지 상세 일부·다른 시나리오
   대시보드 전체·출처 서랍 묶음 1개) → head: 그 단위들은 done=false(rows = 기대) → ``backfill`` 이 빠진 키만 채운다(남은 행
   바이트 그대로, 행 수 = 처음과 같음) → 다시 backfill 0행
3. autogenerate diff 0, 표식 kind CHECK·유일
"""

# ruff: noqa: E501

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.models import Base

from ._support import alembic_config
from .test_r3f_migrations import _copy_rows, _wipe, seeded_sqlite  # noqa: F401  (픽스처 재사용)

SNAP = 12


def _units(engine: sa.Engine) -> dict[tuple[int, str, str], tuple[bool, int]]:
    with engine.connect() as c:
        return {
            (int(s), str(k), str(sc)): (bool(d), int(r))
            for s, k, sc, d, r in c.execute(
                sa.text("SELECT snapshot_id, kind, scenario, done, rows FROM snapshot_view_unit")
            )
        }


def _rows(engine: sa.Engine, sid: int) -> dict[tuple[str, str, str], bytes]:
    with engine.connect() as c:
        return {
            (str(k), str(key), str(sc)): bytes(b)
            for k, key, sc, b in c.execute(
                sa.text("SELECT kind, key, scenario, body FROM snapshot_view WHERE snapshot_id = :s"),
                {"s": sid},
            )
        }


def check_0012_roundtrip_and_resume(url: str, seed_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.db import reset_engine
    from app.core.settings import Settings, set_settings
    from app.snapshot_view import SHAPE_VERSION, backfill, pending_count

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
        assert counts["complex"] >= 10 and counts["scenario"] >= 5 and counts["snapshot_view_unit"] > 0
        head_units = _units(engine)
        rows0 = _rows(engine, SNAP)
        assert head_units and all(d for d, _ in head_units.values())

        # 1. head → 0011 → head: 표식 재구성 = head 의 것(done·rows), 저장본 그대로
        command.downgrade(cfg, "0011")
        insp = sa.inspect(engine)
        assert "snapshot_view_unit" not in insp.get_table_names()
        assert "shape_version" not in {c["name"] for c in insp.get_columns("snapshot_view")}
        assert "publish_lease" not in {c["name"] for c in insp.get_columns("snapshot")}
        command.upgrade(cfg, "head")
        assert _units(engine) == head_units
        with engine.connect() as c:
            assert set(c.execute(sa.text("SELECT DISTINCT shape_version FROM snapshot_view")).scalars()) == {
                SHAPE_VERSION
            }
        reset_engine()
        assert backfill(engine, settings=settings)["snapshots"] == []
        assert _rows(engine, SNAP) == rows0

        # 2. 0011 에서 행 일부 삭제(중간에 멈춘 0012 이전 backfill 모양) → head: 미완 표식 → backfill 이 빠진 키만
        command.downgrade(cfg, "0011")
        with engine.connect() as c:
            scs = sorted({sc for (_k, _key, sc) in rows0 if sc}, key=int)
            cx_keys = sorted(key for (k, key, sc) in rows0 if k == "complex" and sc == scs[1])
            buckets = sorted(key for (k, key, _sc) in rows0 if k == "provenance" and key != "idx")
        gone = (
            {("complex", key, scs[1]) for key in cx_keys[-3:]}
            | {("dashboard", "", scs[2])}
            | {("provenance", buckets[0], "")}
        )
        with engine.begin() as c:
            for k, key, sc in gone:
                c.execute(
                    sa.text(
                        "DELETE FROM snapshot_view WHERE snapshot_id = :s AND kind = :k AND key = :key AND scenario = :sc"
                    ),
                    {"s": SNAP, "k": k, "key": key, "sc": sc},
                )
        command.upgrade(cfg, "head")
        units = _units(engine)
        assert units[(SNAP, "complex", scs[1])] == (False, head_units[(SNAP, "complex", scs[1])][1])
        assert units[(SNAP, "dashboard", scs[2])][0] is False
        assert units[(SNAP, "provenance", "")] == (False, head_units[(SNAP, "provenance", "")][1])
        assert units[(SNAP, "complex", scs[0])] == head_units[(SNAP, "complex", scs[0])]
        from sqlalchemy.orm import Session

        with Session(bind=engine) as s:
            assert pending_count(s) == 1
        reset_engine()
        res = backfill(engine, settings=settings)
        assert res["snapshots"] == [SNAP] and not res["failed"], res
        after = _rows(engine, SNAP)
        assert set(after) == set(rows0)
        kept = set(rows0) - gone
        assert all(
            after[k] == rows0[k] for k in kept if k[0] != "provenance"
        )  # 남은 행은 발행 순간 바이트 그대로
        assert all(d for d, _ in _units(engine).values())
        with Session(bind=engine) as s:
            assert pending_count(s) == 0
        assert backfill(engine, settings=settings)["snapshots"] == []

        # 3. 표식 CHECK·유일 · autogenerate diff 0
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as c:
            c.execute(
                sa.text(
                    "INSERT INTO snapshot_view_unit (snapshot_id, kind, scenario, shape_version, rows, done) "
                    "VALUES (:s, 'nope', '', 1, 0, false)"
                ),
                {"s": SNAP},
            )
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as c:
            c.execute(
                sa.text(
                    "INSERT INTO snapshot_view_unit (snapshot_id, kind, scenario, shape_version, rows, done) "
                    "VALUES (:s, 'claims', '', 1, 0, false)"
                ),
                {"s": SNAP},
            )
        with engine.connect() as c:
            ctx = MigrationContext.configure(c, opts={"compare_type": True})
            assert compare_metadata(ctx, Base.metadata) == []
    finally:
        set_settings(None)
        reset_engine()
        command.upgrade(cfg, "head")
        _wipe(engine)
        command.downgrade(cfg, "base")
        engine.dispose()


def test_sqlite_0012_roundtrip_and_backfill_resume(
    seeded_sqlite: Path,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check_0012_roundtrip_and_resume(
        f"sqlite:///{(tmp_path / 'r3g.db').as_posix()}", seeded_sqlite, monkeypatch
    )


@pytest.mark.postgres
def test_postgres_0012_roundtrip_and_backfill_resume(seeded_sqlite: Path, postgres_url: str) -> None:  # noqa: F811
    mp = pytest.MonkeyPatch()
    try:
        check_0012_roundtrip_and_resume(postgres_url, seeded_sqlite, mp)
    finally:
        mp.undo()

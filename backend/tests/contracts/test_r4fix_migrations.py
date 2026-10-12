"""R4-FIX 계약 .15 (DECISIONS D20-1) — 마이그레이션 ``0015``(judgment_log.model·provider) 왕복과 alembic ``ENV_FILE`` 폴백.

| 결정 | 테스트 |
| --- | --- |
| D20-1 / D18-1 응답의 실제 모델·provider 를 judgment_log 행에 따로 | ``test_*_0015_backfills_model_provider_and_roundtrips`` — 0014 행(output_json 에만 있음) → 0015 가 열을 채움, 0014 로 내려도·다시 올려도 autogenerate diff 0 |
| D20-1 / R4 M4 env.py 가 ``ENV_FILE`` 을 존중 | ``test_alembic_env_file_fallback`` — DATABASE_URL 없이 ENV_FILE 만 주면 그 DB 를 마이그레이션(조용한 dev.db 금지) |
"""

# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from app.models import Base

from ._support import BACKEND, alembic_config

ROWS = [
    ("extract", {"tool": "jev_extract", "model": "jev-latest", "provider": "none"}, "ok"),
    ("screen", {"tool": "jev_screen", "model": "jev-1.13.0", "provider": "typesafe"}, "ok"),
    ("screen", {"reason": "guard"}, "blocked"),
]


def _insert_0014_rows(engine: sa.Engine) -> None:
    with engine.begin() as c:
        for i, (tool, out, status) in enumerate(ROWS):
            c.execute(
                sa.text(
                    "INSERT INTO judgment_log (tool, purpose, input_hash, input_len, input_json, output_json, status, "
                    "created_at, adapter_version) VALUES (:t, :p, :h, 1, :i, :o, :s, '2026-10-12T06:00:00+09:00', 'v')"
                ),
                {
                    "t": tool,
                    "p": f"p{i}",
                    "h": f"sha256:{i:064d}",
                    "i": "{}",
                    "o": json.dumps(out),
                    "s": status,
                },
            )


def check_0015(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENV_FILE", raising=False)
    cfg = alembic_config(url)
    command.upgrade(cfg, "0014")
    engine = sa.create_engine(url)
    try:
        _insert_0014_rows(engine)
        command.upgrade(cfg, "head")
        with engine.connect() as c:
            got = [
                tuple(r) for r in c.execute(sa.text("SELECT model, provider FROM judgment_log ORDER BY seq"))
            ]
            assert got == [("jev-latest", "none"), ("jev-1.13.0", "typesafe"), (None, None)]
            ctx = MigrationContext.configure(c, opts={"compare_type": True})
            assert compare_metadata(ctx, Base.metadata) == []
        command.downgrade(cfg, "0014")
        with engine.connect() as c:
            cols = {col["name"] for col in sa.inspect(c).get_columns("judgment_log")}
        assert not cols & {"model", "provider"}
        command.upgrade(cfg, "head")
        with engine.connect() as c:
            ctx = MigrationContext.configure(c, opts={"compare_type": True})
            assert compare_metadata(ctx, Base.metadata) == []
    finally:
        command.downgrade(cfg, "base")
        engine.dispose()


def test_sqlite_0015_backfills_model_provider_and_roundtrips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    check_0015(f"sqlite:///{(tmp_path / 'r4fix.db').as_posix()}", monkeypatch)


@pytest.mark.postgres
def test_postgres_0015_backfills_model_provider_and_roundtrips(postgres_url: str) -> None:
    mp = pytest.MonkeyPatch()
    try:
        check_0015(postgres_url, mp)
    finally:
        mp.undo()


def test_alembic_env_file_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """R4: ``ENV_FILE=../r4/.env uv run alembic upgrade head`` 가 조용히 backend/dev.db(SQLite)를 마이그레이션했다."""
    from app.core.settings import set_settings

    target = tmp_path / "r4.db"
    env = tmp_path / "r4.env"
    env.write_text(f"DATABASE_URL=sqlite:///{target.as_posix()}\nENV=dev\n", encoding="utf-8")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ENV_FILE", str(env))
    cfg = Config(
        str(BACKEND / "alembic.ini")
    )  # sqlalchemy.url = sqlite:///./dev.db (ini 기본) — 쓰이면 안 된다
    cfg.attributes["configure_logger"] = False
    set_settings(None)
    try:
        command.upgrade(cfg, "head")
        tables = set(sa.inspect(sa.create_engine(f"sqlite:///{target.as_posix()}")).get_table_names())
        assert {"alembic_version", "complex", "judgment_log"} <= tables, (
            "ENV_FILE 이 가리킨 DB 를 마이그레이션해야 한다"
        )
        command.downgrade(cfg, "base")
    finally:
        set_settings(None)

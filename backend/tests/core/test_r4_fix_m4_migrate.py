"""R4-FIX M4 (D18-7) — 마이그레이션은 ``ENV_FILE`` 을 존중한다.

R4: ``export ENV_FILE=../r4/.env; uv run alembic upgrade head`` 가 조용히 ``backend/dev.db``(SQLite)를 마이그레이션했다
(``Context impl SQLiteImpl``) — alembic env.py 는 환경변수 DATABASE_URL 만 읽는다. ``python -m app.migrate`` 는 앱 설정
(ENV_FILE)의 DATABASE_URL 을 넘긴다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

from app.core.settings import set_settings


def test_migrate_uses_env_file_database_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.migrate import main

    target = tmp_path / "r4.db"
    env = tmp_path / "r4.env"
    env.write_text(f"DATABASE_URL=sqlite:///{target.as_posix()}\nENV=dev\n", encoding="utf-8")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ENV_FILE", str(env))
    set_settings(None)
    try:
        assert main(["upgrade", "head"]) == 0
    finally:
        set_settings(None)
    tables = set(inspect(create_engine(f"sqlite:///{target.as_posix()}")).get_table_names())
    assert {"alembic_version", "complex", "judgment_log"} <= tables, (
        "ENV_FILE 이 가리킨 DB 를 마이그레이션해야 한다"
    )
    out = capsys.readouterr().out
    assert "sqlite" in out and str(target) not in out and target.as_posix() not in out, (
        "URL 은 출력하지 않는다"
    )

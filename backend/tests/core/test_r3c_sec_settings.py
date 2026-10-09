"""R3c SEC — D11-9: ENV=prod 에서 SQLite DATABASE_URL 거부."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.settings import Settings, env_var_names

PG = "postgresql+psycopg://sa:pw@db:5432/subscription"


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in env_var_names():
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def make(**kwargs: object) -> Settings:
    return Settings(_env_file=None, **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "url", ["sqlite:///./dev.db", "sqlite://", "sqlite+pysqlite:///x.db", "SQLITE:///x.db", " sqlite:///x.db"]
)
def test_d11_9_prod_rejects_sqlite(clean_env: pytest.MonkeyPatch, url: str) -> None:
    with pytest.raises(ValidationError, match="SQLite"):
        make(env="prod", api_token="t" * 32, database_url=url)


def test_d11_9_prod_default_database_url_rejected(clean_env: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="SQLite"):
        make(env="prod", api_token="t" * 32)  # 기본값은 sqlite:///./dev.db


def test_d11_9_prod_postgres_and_dev_sqlite_allowed(clean_env: pytest.MonkeyPatch) -> None:
    assert make(env="prod", api_token="t" * 32, database_url=PG).env == "prod"
    assert make(env="dev").is_sqlite


def test_d11_9_env_var_prod_sqlite_rejected(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("ENV", "prod")
    clean_env.setenv("API_TOKEN", "t" * 32)
    clean_env.setenv("DATABASE_URL", "sqlite:///./prod.db")
    with pytest.raises(ValidationError, match="SQLite"):
        Settings(_env_file=None)  # type: ignore[call-arg]

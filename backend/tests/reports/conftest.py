"""WP8 테스트 fixture: 픽스처 DB(스냅샷 11·12)와 생성한 보고서 파일(세션 1회)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import get_engine, load_metadata, reset_engine
from app.core.settings import Settings, env_var_names, set_settings

from ._seed import SeedInfo, seed


@pytest.fixture(scope="session")
def report_env(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Settings, Engine, SeedInfo]]:
    """세션 공용: 임시 sqlite 에 devseed 픽스처 적재 + 보고서 보충(_seed). 테스트는 읽기만(바꾸면 rollback)."""
    import os

    saved = {n: os.environ.pop(n) for n in env_var_names() if n in os.environ}
    base = tmp_path_factory.mktemp("wp8")
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        env="dev",
        database_url=f"sqlite:///{(base / 'report.db').as_posix()}",
        raw_dir=base / "raw",
        reference_dir=base / "reference",
        report_dir=base / "reports",
        judge_adapter="mock",
    )
    set_settings(settings)
    engine = get_engine(settings)
    metadata = load_metadata()
    assert metadata is not None
    info = seed(settings, sessionmaker(bind=engine, expire_on_commit=False))
    try:
        yield settings, engine, info
    finally:
        set_settings(None)
        reset_engine()
        os.environ.update(saved)


@pytest.fixture
def report_settings(report_env: tuple[Settings, Engine, SeedInfo]) -> Settings:
    set_settings(report_env[0])
    return report_env[0]


@pytest.fixture
def factory(
    report_env: tuple[Settings, Engine, SeedInfo], report_settings: Settings
) -> sessionmaker[Session]:
    return sessionmaker(bind=report_env[1], expire_on_commit=False)


@pytest.fixture
def seed_info(report_env: tuple[Settings, Engine, SeedInfo]) -> SeedInfo:
    return report_env[2]


@pytest.fixture
def out_dir(tmp_path: Path) -> Path:
    return tmp_path / "out"

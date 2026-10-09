"""공용 fixture (WP0 소유). 모든 WP 테스트가 쓴다.

- ``test_settings``: 임시 sqlite DB·RAW_DIR·REFERENCE_DIR·REPORT_DIR를 가리키는 Settings.
  ``app.core.settings.get_settings()`` 가 이 값을 돌려주도록 덮어쓴다(.env 무시).
- ``raw_dir``: 비어 있는 임시 원문 저장 디렉터리.
- ``db_engine``: 임시 sqlite 엔진(WAL·foreign_keys). ``app.models`` 가 있으면 create_all.
- ``db_session``: 테스트마다 새 Session, 끝나면 rollback·close.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.db import get_engine, load_metadata, reset_engine
from app.core.settings import Settings, env_var_names, set_settings


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """``live`` 마커 테스트(실제 외부 사이트 접속)는 ``-m live`` 로 고를 때만 돈다."""
    if "live" in (config.getoption("markexpr", "") or ""):
        return
    skip_live = pytest.mark.skip(reason="live: 실제 외부 접속 — `pytest -m live` 로 실행")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture
def test_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    for name in env_var_names():
        monkeypatch.delenv(name, raising=False)
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        env="dev",
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        raw_dir=tmp_path / "raw",
        reference_dir=tmp_path / "reference",
        report_dir=tmp_path / "reports",
        judge_adapter="mock",
    )
    set_settings(settings)
    try:
        yield settings
    finally:
        set_settings(None)
        reset_engine()


@pytest.fixture
def raw_dir(test_settings: Settings) -> Path:
    test_settings.raw_dir.mkdir(parents=True, exist_ok=True)
    return test_settings.raw_dir


@pytest.fixture
def db_engine(test_settings: Settings) -> Iterator[Engine]:
    engine = get_engine(test_settings)
    metadata = load_metadata()
    if metadata is not None:
        metadata.create_all(engine)
    yield engine


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    session = Session(db_engine)
    try:
        yield session
    finally:
        session.rollback()
        session.close()

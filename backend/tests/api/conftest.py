"""API 테스트 fixture (WP5).

- ``seeded_db``(세션 1회): 임시 디렉터리에 devseed(인천·김포 픽스처 + 참조 데이터 일부)로
  SQLite DB와 RAW_DIR을 만든다.
- ``api_settings``: 테스트마다 그 DB 파일을 복사해 쓰는 Settings(쓰기 테스트가 서로 영향 없게).
- ``client``: ``app.main.create_app(settings)`` 의 TestClient. ``WRITE``/``READ`` 헤더는 ``_support``.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.db import reset_engine
from app.core.settings import Settings, env_var_names, set_settings

from ._support import FIXTURE, READ_TOKEN, WRITE_TOKEN


@dataclass(frozen=True)
class Seeded:
    db: Path
    raw_dir: Path
    report_dir: Path


def make_settings(db: Path, raw_dir: Path, report_dir: Path, *, env: str = "dev") -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        env=env,  # type: ignore[arg-type]
        database_url=f"sqlite:///{db.as_posix()}",
        raw_dir=raw_dir,
        reference_dir=db.parent / "reference",
        report_dir=report_dir,
        # ENV=prod 는 mock 판정기를 거부한다(R3 minor 31) — API 테스트는 판정기를 부르지 않는다
        judge_adapter="jev" if env == "prod" else "mock",
        api_token=WRITE_TOKEN,  # type: ignore[arg-type]
        readonly_token=READ_TOKEN,  # type: ignore[arg-type]
        log_json=False,
    )


@pytest.fixture(scope="session")
def seeded_db(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Seeded]:
    from app.api import devseed

    base = tmp_path_factory.mktemp("devseed")
    seeded = Seeded(db=base / "seed.db", raw_dir=base / "raw", report_dir=base / "reports")
    settings = make_settings(seeded.db, seeded.raw_dir, seeded.report_dir)
    set_settings(settings)
    try:
        devseed.seed(settings, fixture_dir=FIXTURE, reference="region")
    finally:
        set_settings(None)
        reset_engine()
    yield seeded


@pytest.fixture
def api_settings(seeded_db: Seeded, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    for name in env_var_names():
        monkeypatch.delenv(name, raising=False)
    db = tmp_path / "api.db"
    shutil.copyfile(seeded_db.db, db)
    settings = make_settings(db, seeded_db.raw_dir, tmp_path / "reports")
    set_settings(settings)
    try:
        yield settings
    finally:
        set_settings(None)
        reset_engine()


@pytest.fixture
def client(api_settings: Settings) -> Iterator[TestClient]:
    from app.main import create_app

    with TestClient(create_app(api_settings), raise_server_exceptions=False) as c:
        yield c

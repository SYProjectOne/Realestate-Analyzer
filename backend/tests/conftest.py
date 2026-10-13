"""공용 fixture (WP0 소유). 모든 WP 테스트가 쓴다.

- ``test_settings``: 임시 sqlite DB·RAW_DIR·REFERENCE_DIR·REPORT_DIR를 가리키는 Settings.
  ``app.core.settings.get_settings()`` 가 이 값을 돌려주도록 덮어쓴다(.env 무시).
- ``raw_dir``: 비어 있는 임시 원문 저장 디렉터리.
- ``db_engine``: 임시 sqlite 엔진(WAL·foreign_keys). ``app.models`` 가 있으면 create_all.
- ``db_session``: 테스트마다 새 Session, 끝나면 rollback·close.

환경 격리(R5-OPS 2, D25): 테스트는 ``.env``·사용자 환경변수에 기대지 않는다.
``-m live``(실제 외부 접속 — 키가 필요하다)가 아니면 세션 시작(``pytest_configure``)에서
- Settings 가 읽는 환경변수 전부·``ENV_FILE``·판정기 자격 증명 이름(``DEFAULT_JUDGE_SECRET_ENV_NAMES``)을
  지우고(CI 워크플로 env ``JUDGE_ADAPTER=mock`` 이 prod 가드 테스트로 샌 run 38326346203,
  사용자 PC 의 ``TYPESAFE_API_KEY``),
- ``Settings()`` 의 암묵적 ``.env`` 읽기(``model_config.env_file``)와 ``ENV_FILE`` 이 없을 때의 기본
  경로(``settings.DEFAULT_ENV_FILE`` → 존재하지 않는 경로)를 막는다.
  ``_env_file=``·``ENV_FILE`` 을 명시한 읽기는 그대로다.
``TEST_POSTGRES_URL``·``CI`` 처럼 Settings 밖 이름은 건드리지 않는다.
테스트 안에서 바꾸려면 ``monkeypatch.setenv``.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import app.core.settings as settings_module
from app.core.db import get_engine, load_metadata, reset_engine
from app.core.settings import DEFAULT_JUDGE_SECRET_ENV_NAMES, Settings, env_var_names, set_settings

# 테스트 세션의 '기본 .env' 경로 — 만들지 않는다(존재하면 격리가 깨지므로 시작에서 거부)
NO_DOTENV = Path(tempfile.gettempdir()) / "subscription-analyzer-tests-no-dotenv" / ".env"
_ISOLATION = pytest.StashKey[pytest.MonkeyPatch]()


def _is_live_run(config: pytest.Config) -> bool:
    expr = config.getoption("markexpr", "") or ""
    return "live" in expr.replace("not live", "")


def hermetic_env_names() -> list[str]:
    """테스트 세션에서 지우는 환경변수 이름(대문자)."""
    return sorted({*env_var_names(), "ENV_FILE", *(n.upper() for n in DEFAULT_JUDGE_SECRET_ENV_NAMES)})


def pytest_configure(config: pytest.Config) -> None:
    if _is_live_run(config):
        return
    if NO_DOTENV.exists():
        raise pytest.UsageError(f"{NO_DOTENV} 가 있다 — 테스트 환경 격리용 '없는 경로'이므로 지운다")
    mp = pytest.MonkeyPatch()
    for name in hermetic_env_names():
        mp.delenv(name, raising=False)
    mp.setitem(Settings.model_config, "env_file", None)
    mp.setattr(settings_module, "DEFAULT_ENV_FILE", str(NO_DOTENV))
    set_settings(None)
    config.stash[_ISOLATION] = mp


def pytest_unconfigure(config: pytest.Config) -> None:
    mp = config.stash.get(_ISOLATION, None)
    if mp is not None:
        mp.undo()
        set_settings(None)


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

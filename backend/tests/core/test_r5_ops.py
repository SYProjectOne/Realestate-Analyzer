"""R5-OPS (DECISIONS D25, ``docs/design/wp/R5_FINAL.md`` =====OPS) — core 쪽 테스트.

| 항목 | 테스트 |
| --- | --- |
| OPS-2 CI 실패: 테스트가 ``.env``·사용자 환경에 기대지 않는다 | ``test_settings_env_vars_are_absent_during_tests`` · ``test_cwd_dotenv_is_invisible_to_settings`` · ``test_cwd_dotenv_is_invisible_to_judge_child_env`` · ``test_explicit_env_file_still_works`` |
| OPS-5 공유 링크 TTL 상한 30일 | ``test_share_token_ttl_days_is_capped_at_30`` |
| OPS-5 Collector Protocol 적합성(8개) | ``test_collector_conforms_to_protocol`` · ``test_every_collector_class_is_covered`` |
| OPS-3 ``PG_DUMP_PATH`` 설정 | ``test_pg_dump_path_setting`` |
"""

# ruff: noqa: E501  (한국어 assertion 메시지·표)

from __future__ import annotations

import ast
import importlib
import inspect
import os
import typing
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.contracts_gen import RawDocument
from app.core.protocols import Collector
from app.core.settings import (
    DEFAULT_JUDGE_SECRET_ENV_NAMES,
    Settings,
    env_file_path,
    env_var_names,
    get_settings,
    load_settings,
    set_settings,
)

BACKEND = Path(__file__).resolve().parents[2]
COLLECTORS_DIR = BACKEND / "app" / "collectors"

# ====================================================================== OPS-2 환경 격리


def _hermetic_names() -> list[str]:
    return sorted({*env_var_names(), "ENV_FILE", *(n.upper() for n in DEFAULT_JUDGE_SECRET_ENV_NAMES)})


def test_settings_env_vars_are_absent_during_tests() -> None:
    """CI(run 38326346203)는 워크플로 env ``JUDGE_ADAPTER=mock`` 이 Settings 로 새어 prod 가드가 터졌다.

    테스트 세션(``-m live`` 제외)에서는 Settings 가 읽는 환경변수·``ENV_FILE``·판정기 자격 증명이 모두 비어 있어야
    한다(``tests/conftest.py`` ``pytest_configure``). 사용자 PC 의 ``TYPESAFE_API_KEY`` 같은 값도 테스트에 보이지 않는다.
    """
    upper_env = {k.upper() for k in os.environ}
    leaked = [n for n in _hermetic_names() if n in upper_env]
    assert leaked == [], f"테스트 세션에 새어 든 환경변수(이름만): {leaked}"


def _write_hostile_dotenv(directory: Path) -> Path:
    path = directory / ".env"
    path.write_text(
        "HTTP_RATE_PER_HOST=7\n"
        "NEWS_API_PROVIDER=naver_developers\n"
        "DATABASE_URL=postgresql+psycopg://hostile:hostile@db.invalid:5432/hostile\n"
        "TYPESAFE_API_KEY=fake-judge-key-from-dotenv\n",
        encoding="utf-8",
    )
    return path


def test_cwd_dotenv_is_invisible_to_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """작업 디렉터리에 ``.env``(운영 Postgres 주소 등)가 있어도 테스트의 Settings 는 기본값이다."""
    _write_hostile_dotenv(tmp_path)
    monkeypatch.chdir(tmp_path)
    s = Settings()
    assert s.http_rate_per_host == 1.0 and s.news_api_provider == "ncp"
    assert s.database_url.startswith("sqlite"), "작업 디렉터리 .env 의 DATABASE_URL 을 읽었다"
    assert env_file_path() != Path(".env"), "기본 .env 경로가 테스트에서 작업 디렉터리 .env 를 가리킨다"
    assert load_settings().http_rate_per_host == 1.0
    set_settings(None)
    try:
        assert get_settings().http_rate_per_host == 1.0
    finally:
        set_settings(None)


def test_cwd_dotenv_is_invisible_to_judge_child_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """판정기 자식 env(``jev_mcp.subprocess_env``)도 작업 디렉터리 ``.env`` 의 자격 증명을 테스트에서 읽지 않는다."""
    from app.judge.jev_mcp import subprocess_env

    _write_hostile_dotenv(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert "TYPESAFE_API_KEY" not in {k.upper() for k in subprocess_env()}


def test_explicit_env_file_still_works(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """격리는 '암묵적' 읽기만 막는다 — ``ENV_FILE``·``_env_file`` 을 명시하면 그대로 읽는다(기능 회귀 없음)."""
    env = _write_hostile_dotenv(tmp_path)
    assert Settings(_env_file=env).http_rate_per_host == 7.0  # type: ignore[call-arg]
    monkeypatch.setenv("ENV_FILE", str(env))
    assert env_file_path() == env
    assert load_settings().news_api_provider == "naver_developers"


# ====================================================================== OPS-5 공유 링크 TTL


def test_share_token_ttl_days_is_capped_at_30() -> None:
    """RA·계약: 공유 링크 만료 30일(``SHARE_TOKEN_TTL_DAYS``). 설정으로 30일을 넘길 수 없다(``le=30``)."""
    assert Settings(_env_file=None).share_token_ttl_days == 30  # type: ignore[call-arg]
    assert Settings(_env_file=None, share_token_ttl_days=7).share_token_ttl_days == 7  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Settings(_env_file=None, share_token_ttl_days=31)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Settings(_env_file=None, share_token_ttl_days=0)  # type: ignore[call-arg]


# ====================================================================== OPS-3 PG_DUMP_PATH


def test_pg_dump_path_setting(tmp_path: Path) -> None:
    """D19-2·D25: ``PG_DUMP_PATH``(실행 파일 또는 bin 폴더)를 설정으로 받는다. 비면 None(PATH 의 pg_dump)."""
    assert "PG_DUMP_PATH" in env_var_names()
    assert Settings(_env_file=None).pg_dump_path is None  # type: ignore[call-arg, attr-defined]
    assert Settings(_env_file=None, pg_dump_path="").pg_dump_path is None  # type: ignore[call-arg, attr-defined]
    exe = tmp_path / "pg_dump.exe"
    assert Settings(_env_file=None, pg_dump_path=str(exe)).pg_dump_path == exe  # type: ignore[call-arg, attr-defined]
    # .env 에서 큰따옴표로 감싼 Windows 경로는 역슬래시+b 가 백스페이스로 읽힌다 — 깨진 경로를 조용히 쓰지 않는다
    win_path = "\\".join(["C:", "Program Files", "PostgreSQL", "17", "bin", "pg_dump.exe"])
    env = tmp_path / "pg.env"
    env.write_text(f'PG_DUMP_PATH="{win_path}"\n', encoding="utf-8")
    with pytest.raises(ValidationError, match="PG_DUMP_PATH"):
        Settings(_env_file=env)  # type: ignore[call-arg]
    env.write_text(f"PG_DUMP_PATH={win_path}\n", encoding="utf-8")
    assert str(Settings(_env_file=env).pg_dump_path) == win_path  # type: ignore[call-arg, attr-defined]


# ====================================================================== OPS-5 Collector Protocol 적합성

COLLECTORS: dict[str, tuple[str, str]] = {
    "applyhome": ("app.collectors.applyhome", "ApplyhomeCollector"),
    "notice_pdf": ("app.collectors.notice_pdf", "NoticePdfCollector"),
    "official_site": ("app.collectors.official_site", "OfficialSiteCollector"),
    "rtms": ("app.collectors.rtms", "RtmsCollector"),
    "stats_unsold": ("app.collectors.stats", "UnsoldCollector"),
    "stats_households": ("app.collectors.stats", "HouseholdCollector"),
    "news": ("app.collectors.news", "NewsCollector"),
    "reference": ("app.collectors.reference", "ReferenceCollector"),
}
SOURCE_KINDS = set(typing.get_args(typing.get_type_hints(RawDocument, include_extras=False)["source_kind"]))


def _load(key: str) -> type[Any]:
    module, name = COLLECTORS[key]
    cls = getattr(importlib.import_module(module), name)
    assert isinstance(cls, type)
    return cls


@pytest.mark.parametrize("key", sorted(COLLECTORS))
def test_collector_conforms_to_protocol(key: str, test_settings: Settings) -> None:
    """RA §4-3 ``Collector.fetch(region, snapshot, since) -> list[RawDocument]`` — 이름·순서·타입이 같고,
    인자 없이 만들 수 있으며(운영 기본 구성), ``isinstance(…, Collector)`` 이고, source_kind 가 계약 enum 안이다."""
    cls = _load(key)
    want = inspect.signature(Collector.fetch)
    got = inspect.signature(cls.fetch)
    assert list(got.parameters) == list(want.parameters), f"{cls.__name__}.fetch 인자: {list(got.parameters)}"
    want_hints = typing.get_type_hints(Collector.fetch)
    got_hints = typing.get_type_hints(cls.fetch)
    assert got_hints == want_hints, f"{cls.__name__}.fetch 타입: {got_hints} != {want_hints}"
    instance = cls()
    assert isinstance(instance, Collector)
    kinds = set(getattr(cls, "source_kinds", ())) | (
        {cls.source_kind} if hasattr(cls, "source_kind") else set()
    )
    assert kinds, f"{cls.__name__}: source_kind(s) 없음"
    assert kinds <= SOURCE_KINDS, f"{cls.__name__}: 계약 밖 source_kind {kinds - SOURCE_KINDS}"
    assert get_settings() is test_settings


def _fetch_classes() -> set[str]:
    """app/collectors 안에서 ``fetch(self, region, snapshot, since)`` 를 정의한 클래스 이름(AST)."""
    found: set[str] = set()
    for path in COLLECTORS_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "fetch":
                    names = [a.arg for a in item.args.args]
                    if names[:4] == ["self", "region", "snapshot", "since"]:
                        found.add(node.name)
    return found


def test_every_collector_class_is_covered() -> None:
    """새 수집기가 생기면 위 parametrize 목록에도 들어가야 한다(적합성 검사에서 빠지지 않게)."""
    assert _fetch_classes() == {name for _, name in COLLECTORS.values()}
    assert len(COLLECTORS) == 8

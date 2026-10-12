"""D21-8·D19-3 — 판정기 자격 증명은 ``.env``(설정 파일)에만 있어도 판정기 자식 프로세스 env 로 넘어간다(값은 로그·오류에서 가림).

R4 재시험 전: 사람이 판정기 키를 루트 ``.env`` 의 ``TYPESAFE_API_KEY`` 에 넣었지만 ``judge.jev_mcp.subprocess_env`` 는 **프로세스
환경변수만** 자식에게 넘겨, 사용자 환경변수(``setx``)가 없으면 ``.env`` 값이 판정기에 가지 않았다(프로그램이 사용자 환경변수에
기댐). 이 테스트는 사용자 환경변수 없이 ``ENV_FILE`` 의 ``.env`` 만으로 (가짜) 판정기가 뜨는지, 그 값이 기동 실패 stderr·오류에서
가려지는지, 판정기와 무관한 비밀(공공데이터 키)은 넘어가지 않는지 본다. 실제 판정기는 부르지 않는다.
"""

# ruff: noqa: E501

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.core.protocols import JudgeUnavailable
from app.core.settings import Settings, env_var_names, load_settings, set_settings
from app.judge.jev_mcp import McpStdioTransport, subprocess_env

from .conftest import FakeServer

DOTENV_JUDGE_KEY = "tsk_dotenv_only_value_7Qx"
DOTENV_DATA_KEY = "datagokr_dotenv_value_9Zy"


@pytest.fixture
def dotenv_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in [*env_var_names(), "TYPESAFE_API_KEY", "OPENROUTER_API_KEY", "JEV_API_KEY", "ENV_FILE"]:
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / "r4.env"
    env.write_text(
        "# 판정기 자격 증명은 .env 에만\n"
        f"TYPESAFE_API_KEY={DOTENV_JUDGE_KEY}\n"
        f'DATA_GO_KR_KEY="{DOTENV_DATA_KEY}"\n'
        "JUDGE_ADAPTER=jev\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ENV_FILE", str(env))
    set_settings(load_settings())
    yield env
    set_settings(None)


def test_dotenv_judge_credential_is_forwarded_but_other_secrets_are_not(dotenv_only: Path) -> None:
    env = subprocess_env()
    assert env.get("TYPESAFE_API_KEY") == DOTENV_JUDGE_KEY, (
        "'.env' 의 판정기 자격 증명 이름(JUDGE_SECRET_ENV_NAMES)은 자식 env 로"
    )
    assert DOTENV_DATA_KEY not in env.values() and "DATA_GO_KR_KEY" not in env, (
        "판정기와 무관한 비밀은 넘기지 않는다"
    )


def test_process_env_wins_over_dotenv(dotenv_only: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "from_process_env")
    assert subprocess_env()["TYPESAFE_API_KEY"] == "from_process_env"


def test_judge_starts_with_dotenv_only(dotenv_only: Path, fake_server: FakeServer) -> None:
    """가짜 판정기는 TYPESAFE_API_KEY 가 없으면 기동하지 않는다(실제 JEV 0.14.1 처럼 키 없이 모델을 부를 수 없음)."""
    fake_server.configure(require_env="TYPESAFE_API_KEY")
    transport = McpStdioTransport(fake_server.cmd, startup_timeout_s=30)
    try:
        assert transport.server_version() == "0.14.1"
    finally:
        transport.close()


def test_dotenv_credential_is_masked_in_startup_error(dotenv_only: Path, tmp_path: Path) -> None:
    script = tmp_path / "leaky_judge.py"
    script.write_text(
        "import os, sys\n"
        "sys.stderr.write('boot failed key=' + os.environ['TYPESAFE_API_KEY'] + chr(10))\n"
        "sys.stderr.flush()\n"
        "sys.exit(3)\n",
        encoding="utf-8",
    )
    transport = McpStdioTransport(f'"{sys.executable}" "{script}"', startup_timeout_s=20)
    try:
        with pytest.raises(JudgeUnavailable) as info:
            transport.server_version()
    finally:
        transport.close()
    message = str(info.value)
    assert "KeyError" not in message and "boot failed key=" in message, (
        f"판정기 자식이 .env 의 키를 받았다(stderr 에 찍힘): {message}"
    )
    assert DOTENV_JUDGE_KEY not in message and "[REDACTED" in message, message


def test_settings_type_is_untouched(dotenv_only: Path) -> None:
    """.env 의 판정기 자격 증명은 Settings 필드가 아니다(이름 목록 ``judge_secret_env_names`` 로만 고른다)."""
    s = load_settings()
    assert isinstance(s, Settings) and "TYPESAFE_API_KEY" in [n.upper() for n in s.judge_secret_env_names]

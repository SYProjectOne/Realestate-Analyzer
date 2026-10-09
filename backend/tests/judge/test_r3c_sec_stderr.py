"""R3c SEC — minor 32: 판정기 기동 실패 stderr 를 판정기 자격 증명 값까지 가린다.

자식 프로세스에는 판정기 자격 증명(OPENROUTER_*·TYPESAFE_* …)이 넘어간다. 판정기가 그 값을 stderr 에 찍고
죽으면 ``JudgeUnavailable`` 메시지(→ judgment_log.error_text·로그)에 원문이 실리면 안 된다.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.core.protocols import JudgeUnavailable
from app.core.settings import Settings, set_settings
from app.judge.jev_mcp import McpStdioTransport, judge_secret_values, subprocess_env

OPENROUTER = "sk-or-v1-plainlowercasevalue"
TYPESAFE = "tsk_live_mixedValueQQ"
CF = "cfplainvaluezzzz"
DATA_KEY = "datagokrsecretvalue"


@pytest.fixture
def judge_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("OPENROUTER_API_KEY", OPENROUTER)
    monkeypatch.setenv("TYPESAFE_TOKEN", TYPESAFE)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", CF)
    monkeypatch.setenv("JEV_MCP_MODEL", "jev-latest-model")
    set_settings(Settings(_env_file=None, data_go_kr_key=DATA_KEY))  # type: ignore[call-arg, arg-type]
    yield
    set_settings(None)


def test_judge_secret_values_lists_forwarded_credentials(judge_env: None) -> None:
    values = judge_secret_values(subprocess_env())
    assert {OPENROUTER, TYPESAFE, CF, DATA_KEY} <= set(values)
    assert "jev-latest-model" not in values  # 설정값(비밀 아님)은 진단용으로 남긴다


def test_startup_stderr_masks_judge_credentials(judge_env: None, tmp_path: Path) -> None:
    script = tmp_path / "leaky_judge.py"
    script.write_text(
        "import os, sys\n"
        "sys.stderr.write('boot failed key=' + os.environ['OPENROUTER_API_KEY'] + ' tok '"
        " + os.environ['TYPESAFE_TOKEN'] + ' cf ' + os.environ['CLOUDFLARE_API_TOKEN']"
        " + ' model ' + os.environ['JEV_MCP_MODEL'] + '\\n')\n"
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
    assert "stderr:" in message and "boot failed" in message, message
    for secret in (OPENROUTER, TYPESAFE, CF):
        assert secret not in message, message
    assert "[REDACTED" in message
    assert "jev-latest-model" in message

"""JEV 실제 연결 smoke (``pytest -m live tests/judge/test_live.py -s``).

결과는 docs/adr/ADR-05-judge-smoke.md.

실제 ``JEV_MCP_CMD``(기본 ``npx -y @jkudish/jev-mcp@latest``)를 띄워 initialize·tools/list를 확인하고,
(R4 m1: ``test_settings`` 가 환경변수를 지우기 전에 읽어 둔 ``JEV_MCP_CMD`` 를 쓴다 — 고정 버전 시험)
합성 공개 텍스트 1건을 어댑터 전체 경로(guard → hash → 호출 → judgment_log)로 보낸 뒤
같은 입력이 캐시되는지 본다.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import Settings
from app.judge.jev_mcp import JevMcpAdapter, McpStdioTransport

_ENV_CMD = os.environ.get("JEV_MCP_CMD")
"""수집 시점(모듈 import)의 ``JEV_MCP_CMD`` — ``test_settings`` fixture 가 환경변수를 지우기 전 값."""


def live_cmd(environ: Mapping[str, str | None], default: str) -> str:
    """smoke 가 띄울 명령: 환경변수 ``JEV_MCP_CMD`` 가 있으면 그것(운영과 같은 고정 버전), 없으면 설정 기본값."""
    value = (environ.get("JEV_MCP_CMD") or "").strip()
    return value or default


def test_live_cmd_respects_env() -> None:
    """m1: 고정 버전(@0.14.1)을 환경변수로 주면 smoke 가 @latest 가 아니라 그 명령을 띄운다."""
    default = "npx -y @jkudish/jev-mcp@latest"
    assert live_cmd({"JEV_MCP_CMD": "npx -y @jkudish/jev-mcp@0.14.1"}, default).endswith("@0.14.1")
    assert live_cmd({"JEV_MCP_CMD": "  "}, default) == default
    assert live_cmd({}, default) == default


REQUIRED = {
    f"jev_{t}"
    for t in ("screen", "extract", "audit", "classify", "compare", "noul", "rerank", "decide", "verify")
}


@pytest.mark.live
def test_jev_live_smoke(test_settings: Settings, session_factory: sessionmaker[Session]) -> None:
    cmd = live_cmd({"JEV_MCP_CMD": _ENV_CMD}, test_settings.jev_mcp_cmd)
    t0 = time.monotonic()
    transport = McpStdioTransport(cmd, timeout_s=120, startup_timeout_s=300)
    try:
        version = transport.server_version()
        startup_ms = int((time.monotonic() - t0) * 1000)
        tools = transport.list_tool_names()
        assert set(tools) >= REQUIRED

        adapter = JevMcpAdapter(transport=transport, session_factory=session_factory)
        payload = {
            "text": "전용 84㎡ 공급금액 최고가 608,000,000원, 계약금 10%",
            "purpose": "청약 공고 가격 확인",
        }
        t1 = time.monotonic()
        first = adapter.screen(payload, "screen:smoke")
        call_ms = int((time.monotonic() - t1) * 1000)
        second = adapter.screen(payload, "screen:smoke")
    finally:
        transport.close()

    assert first.cached is False and second.cached is True
    assert first.status in {"ok", "review"}
    print(
        "\nJEV_SMOKE "
        + json.dumps(
            {
                "cmd": cmd,
                "server_version": version,
                "adapter_version": first.adapter_version,
                "tools": sorted(tools),
                "startup_ms": startup_ms,
                "screen_call_ms": call_ms,
                "screen_status": first.status,
                "screen_result": first.result,
                "model": first.raw.get("model"),
                "thresholds": first.raw.get("thresholds"),
            },
            ensure_ascii=False,
        )
    )

"""JEV 실제 연결 smoke (``pytest -m live tests/judge/test_live.py -s``).

결과는 docs/adr/ADR-05-judge-smoke.md.

실제 ``JEV_MCP_CMD``(기본 ``npx -y @jkudish/jev-mcp@latest``)를 띄워 initialize·tools/list를 확인하고,
합성 공개 텍스트 1건을 어댑터 전체 경로(guard → hash → 호출 → judgment_log)로 보낸 뒤
같은 입력이 캐시되는지 본다.
"""

from __future__ import annotations

import json
import time

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import Settings
from app.judge.jev_mcp import JevMcpAdapter, McpStdioTransport

REQUIRED = {
    f"jev_{t}"
    for t in ("screen", "extract", "audit", "classify", "compare", "noul", "rerank", "decide", "verify")
}


@pytest.mark.live
def test_jev_live_smoke(test_settings: Settings, session_factory: sessionmaker[Session]) -> None:
    cmd = test_settings.jev_mcp_cmd
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

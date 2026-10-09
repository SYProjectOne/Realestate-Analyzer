"""테스트용 가짜 JEV MCP 서버 (stdio). 실제 JEV 응답 녹화(fixtures/jev_samples.json)를 그대로 돌려준다.

사용: ``python fake_jev_server.py <config.json>``. 설정 파일(어댑터가 자식 프로세스에 환경변수를 골라 넘기므로
환경변수 대신 파일)은 기동 시와 도구 호출마다 다시 읽는다.
- version: initialize.serverInfo.version (기본 0.14.1)
- mode: normal | sleep(도구 호출이 멈춤 → 타임아웃) | die(도구 호출 중 프로세스 종료) | error(isError 응답)
- counter: 경로가 있으면 실제 도구 호출마다 도구 이름 한 줄을 덧붙인다(호출 수 확인용)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import anyio
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLES: dict[str, Any] = json.loads((FIXTURES / "jev_samples.json").read_text(encoding="utf-8"))["calls"]
TOOLS: list[dict[str, Any]] = json.loads((FIXTURES / "jev_tools.json").read_text(encoding="utf-8"))["tools"]
CONFIG = Path(sys.argv[1]) if len(sys.argv) > 1 else None


def config() -> dict[str, Any]:
    if CONFIG is None or not CONFIG.exists():
        return {}
    data: dict[str, Any] = json.loads(CONFIG.read_text(encoding="utf-8"))
    return data


async def list_tools(ctx: Any, params: Any) -> types.ListToolsResult:
    return types.ListToolsResult(
        tools=[
            types.Tool(name=t["name"], description=t.get("description"), input_schema=t["input_schema"])
            for t in TOOLS
        ]
    )


async def call_tool(ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
    cfg = config()
    if cfg.get("counter"):
        with open(cfg["counter"], "a", encoding="utf-8") as f:
            f.write(params.name + "\n")
    mode = cfg.get("mode", "normal")
    if mode == "sleep":
        await anyio.sleep(60)
    if mode == "die":
        os._exit(3)
    if mode == "error":
        body = json.dumps({"tool": params.name, "error": "provider unavailable"})
        return types.CallToolResult(content=[types.TextContent(type="text", text=body)], is_error=True)
    response = SAMPLES[params.name]["response"]
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(response, ensure_ascii=False))]
    )


async def main() -> None:
    server: Server[Any] = Server(
        "jev-mcp", version=config().get("version", "0.14.1"), on_list_tools=list_tools, on_call_tool=call_tool
    )
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    anyio.run(main)

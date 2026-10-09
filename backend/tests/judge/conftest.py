"""WP3 판정기 테스트 공용 fixture.

- ``samples``: 실제 JEV 0.14.1 응답 녹화(fixtures/jev_samples.json, 도구당 1회 · 합성 공개 텍스트).
- ``FakeTransport``: 녹화 응답을 돌려주는 메모리 전송. 호출 수를 센다(T17).
- ``session_factory``: 임시 sqlite(모델 create_all)에 붙는 sessionmaker.
- ``fake_server_cmd``: 가짜 stdio MCP 서버(fake_jev_server.py) 실행 명령 — 실제 프로세스 경로 테스트용.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.protocols import JudgeUnavailable
from app.judge.base import ToolResponse

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"


def load_samples() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / "jev_samples.json").read_text(encoding="utf-8"))
    return data


@pytest.fixture
def samples() -> dict[str, Any]:
    return load_samples()["calls"]


@dataclass
class FakeTransport:
    """녹화 응답을 돌려주는 전송. ``responses[tool_name]`` 이 있으면 그것, 없으면 녹화."""

    version: str = "0.14.1"
    responses: dict[str, dict[str, Any]] = field(default_factory=dict)
    fail: str | None = None  # "unavailable" | "is_error"
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    closed: bool = False

    def server_version(self) -> str:
        if self.fail == "down":
            raise JudgeUnavailable("server down")
        return self.version

    def call(self, tool_name: str, arguments: dict[str, Any]) -> ToolResponse:
        self.calls.append((tool_name, arguments))
        if self.fail in {"unavailable", "down"}:
            raise JudgeUnavailable("timeout")
        if self.fail == "is_error":
            return ToolResponse(
                raw={"tool": tool_name, "error": "provider unavailable"}, is_error=True, duration_ms=5
            )
        raw = self.responses.get(tool_name) or load_samples()["calls"][tool_name]["response"]
        return ToolResponse(raw=json.loads(json.dumps(raw)), is_error=False, duration_ms=12)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def session_factory(db_engine: Engine) -> sessionmaker[Session]:
    """임시 DB + 지역 1개·단지 1~20(judgment_log.complex_id FK 용 최소 행)."""
    from app.models import Complex, Region

    factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    with factory() as s:
        s.add(
            Region(
                id=1, name="테스트 지역", query_text="테스트", selections=[], sido_codes=[], sigungu_codes=[],
                legal_dong_codes=[], living_areas=[], age_premium_coef={}, applyhome_query={}, status="ready",
                created_at="2026-10-08T00:00:00+09:00",
            )
        )  # fmt: skip
        s.flush()
        for i in range(1, 21):
            s.add(
                Complex(
                    id=i, region_id=1, name=f"단지{i}", former_names=[], apply_dates=[], contract_dates=[]
                )
            )
        s.commit()
    return factory


@pytest.fixture
def make_adapter(
    session_factory: sessionmaker[Session],
) -> Callable[..., Any]:
    from app.judge.jev_mcp import JevMcpAdapter

    def _make(transport: FakeTransport, secrets: list[str] | None = None) -> JevMcpAdapter:
        return JevMcpAdapter(transport=transport, session_factory=session_factory, secrets=secrets or [])

    return _make


@dataclass
class FakeServer:
    """가짜 stdio 서버 실행 명령 + 설정 파일(버전·모드·호출 카운터)."""

    cmd: str
    config_path: Path
    counter: Path

    def configure(self, **cfg: Any) -> None:
        current = (
            json.loads(self.config_path.read_text(encoding="utf-8")) if self.config_path.exists() else {}
        )
        current.update(cfg)
        self.config_path.write_text(json.dumps(current), encoding="utf-8")

    def calls(self) -> list[str]:
        return self.counter.read_text(encoding="utf-8").splitlines() if self.counter.exists() else []


@pytest.fixture
def fake_server(tmp_path: Path) -> FakeServer:
    server = (HERE / "fake_jev_server.py").as_posix()
    exe = Path(sys.executable).as_posix()
    cfg = tmp_path / "fake_jev.json"
    fs = FakeServer(
        cmd=f'"{exe}" "{server}" "{cfg.as_posix()}"', config_path=cfg, counter=tmp_path / "calls.txt"
    )
    fs.configure(version="0.14.1", mode="normal", counter=fs.counter.as_posix())
    return fs

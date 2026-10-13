"""R5-OPS 4 (D25-1 major): API 는 판정기를 직접 부르지 않는다(RA §1, AGENTS 규칙 4) — AST 경계 테스트.

| 규칙 | 테스트 |
| --- | --- |
| ``app/api/**``·``app/main.py``·``app/serve.py`` 가 어댑터(JevMcpAdapter·MockAdapter·CachedJudgeAdapter·MCP 전송·``get_adapter``)와 어댑터 모듈(``judge.mock``·``judge.base``)을 import 하지 않는다 | ``test_api_does_not_import_judge_adapters`` |
| ``judge/`` 밖에서 어댑터·전송을 만들거나 상속하지 않는다. ``get_adapter`` 는 worker(scheduler)만 부른다 | ``test_no_adapter_construction_outside_judge`` |
| API 앱을 만든 프로세스에 어댑터 모듈·MCP SDK 가 올라오지 않는다(런타임 확인) | ``test_api_process_does_not_load_adapter_modules`` |
| 검사기 자체가 위반을 잡는다(음성 대조 — 공회전 방지) | ``test_detector_catches_synthetic_violations`` |

예외 1건: ``app/api/views.py`` 가 옛 판정 행(result_json NULL)을 다시 정규화하려고 ``app.judge.jev_mcp`` 의 순수 함수
``normalize`` 만 지연 import 한다(판정기 호출 없음). 이 예외는 이름 단위로만 허용한다 — ``normalize`` 를 어댑터 모듈
밖(예 ``judge/normalize.py``)으로 옮기는 것은 judge 주인(WP3)에게 제안으로 남긴다.
"""

# ruff: noqa: E501  (한국어 assertion 메시지·표)

from __future__ import annotations

import ast
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
APP = BACKEND / "app"

ADAPTER_NAMES = frozenset(
    {"JevMcpAdapter", "MockAdapter", "CachedJudgeAdapter", "McpStdioTransport", "Transport", "get_adapter"}
)
CONSTRUCTED_NAMES = frozenset({"JevMcpAdapter", "MockAdapter", "CachedJudgeAdapter", "McpStdioTransport"})
FORBIDDEN_MODULES = frozenset({"app.judge.mock", "app.judge.base", "mcp"})
# app.judge.jev_mcp 에서 API 가 가져와도 되는 이름(순수 함수) — 모듈 docstring 참고
JEV_MCP_ALLOWED = frozenset({"normalize"})
ADAPTER_MODULE_RE = re.compile(r"\bapp\.judge\.(mock|base|jev_mcp)\b")


def _module_of(path: Path) -> str:
    rel = path.relative_to(BACKEND).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resolve(module: str | None, level: int, current: str, is_pkg: bool) -> str:
    if level == 0:
        return module or ""
    base = current.split(".") if is_pkg else current.split(".")[:-1]
    base = base[: len(base) - (level - 1)]
    return ".".join([*base, module] if module else base)


def violations_in_source(source: str, module: str = "app.api.synthetic", *, is_pkg: bool = False) -> list[str]:
    """API 쪽 파일 1개의 경계 위반(사람이 읽는 문자열 목록)."""
    out: list[str] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name in FORBIDDEN_MODULES or name.startswith("mcp.") or name == "app.judge.jev_mcp" or (
                    name.startswith(("app.judge.mock.", "app.judge.base.", "app.judge.jev_mcp."))
                ):
                    out.append(f"{node.lineno}: import {name}")
        elif isinstance(node, ast.ImportFrom):
            mod = _resolve(node.module, node.level, module, is_pkg)
            names = {a.name for a in node.names}
            if mod in FORBIDDEN_MODULES or mod.startswith("mcp."):
                out.append(f"{node.lineno}: from {mod} import {sorted(names)}")
            elif mod == "app.judge.jev_mcp" and not names <= JEV_MCP_ALLOWED:
                out.append(f"{node.lineno}: from {mod} import {sorted(names - JEV_MCP_ALLOWED)}")
            elif mod == "app.judge" and names & {"get_adapter", "jev_mcp", "mock", "base", "*"}:
                out.append(f"{node.lineno}: from app.judge import {sorted(names)}")
            elif names & ADAPTER_NAMES:
                out.append(f"{node.lineno}: from {mod} import {sorted(names & ADAPTER_NAMES)}")
        elif isinstance(node, ast.Name) and node.id in ADAPTER_NAMES:
            out.append(f"{node.lineno}: 이름 {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in ADAPTER_NAMES:
            out.append(f"{node.lineno}: 속성 .{node.attr}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # importlib.import_module("app.judge.mock") 같은 우회
            if ADAPTER_MODULE_RE.search(node.value) and "import_module" in source:
                out.append(f"{node.lineno}: 문자열 모듈 {node.value!r}")
    return out


def _api_files() -> Iterator[Path]:
    yield from sorted((APP / "api").rglob("*.py"))
    yield APP / "main.py"
    yield APP / "serve.py"


def test_api_does_not_import_judge_adapters() -> None:
    found: dict[str, list[str]] = {}
    for path in _api_files():
        v = violations_in_source(path.read_text(encoding="utf-8"), _module_of(path), is_pkg=path.name == "__init__.py")
        if v:
            found[str(path.relative_to(BACKEND))] = v
    assert found == {}, f"API 가 판정기 어댑터에 닿는다(RA §1·규칙 4): {found}"


def _calls(tree: ast.AST) -> Iterator[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                yield node.lineno, f.id
            elif isinstance(f, ast.Attribute):
                yield node.lineno, f.attr


def construction_violations(source: str, rel: str) -> list[str]:
    out: list[str] = []
    tree = ast.parse(source)
    for lineno, name in _calls(tree):
        if name in CONSTRUCTED_NAMES:
            out.append(f"{rel}:{lineno}: {name}(...)")
        elif name == "get_adapter" and not rel.startswith(("app/scheduler/", "app/worker.py")):
            out.append(f"{rel}:{lineno}: get_adapter(...) — worker(scheduler) 밖")
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                bname = base.id if isinstance(base, ast.Name) else base.attr if isinstance(base, ast.Attribute) else ""
                if bname in CONSTRUCTED_NAMES:
                    out.append(f"{rel}:{node.lineno}: class {node.name}({bname})")
    return out


def test_no_adapter_construction_outside_judge() -> None:
    found: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        rel = path.relative_to(BACKEND).as_posix()
        if rel.startswith("app/judge/"):
            continue
        found += construction_violations(path.read_text(encoding="utf-8"), rel)
    assert found == [], f"judge/ 밖에서 판정기 어댑터를 만든다(규칙 4): {found}"


def test_api_process_does_not_load_adapter_modules() -> None:
    """API 앱(``create_app``)을 만든 새 프로세스에 판정기 어댑터 모듈·MCP SDK 가 없다."""
    code = (
        "import sys\n"
        "from app.core.settings import Settings, set_settings\n"
        "set_settings(Settings(_env_file=None, env='dev', database_url='sqlite://', judge_adapter='mock'))\n"
        "import app.main as m\n"
        "m.create_app()\n"
        "bad = sorted(k for k in sys.modules if k in ('app.judge.jev_mcp','app.judge.mock','app.judge.base')"
        " or k == 'mcp' or k.startswith('mcp.'))\n"
        "print('LOADED=' + ','.join(bad))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, encoding="utf-8", timeout=180
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    line = next(x for x in proc.stdout.splitlines() if x.startswith("LOADED="))
    assert line == "LOADED=", f"API 프로세스에 어댑터 모듈이 올라왔다: {line}"


def test_detector_catches_synthetic_violations() -> None:
    bad_imports = [
        "from app.judge.mock import MockAdapter",
        "from app.judge.jev_mcp import JevMcpAdapter",
        "from app.judge.jev_mcp import McpStdioTransport, normalize",
        "import app.judge.jev_mcp",
        "from app.judge import get_adapter",
        "from app.judge.base import CachedJudgeAdapter",
        "from ...judge import mock",
        "import mcp.client.stdio",
        "import app.judge\nx = app.judge.get_adapter()",
        "import importlib\nm = importlib.import_module('app.judge.mock')",
    ]
    for src in bad_imports:
        assert violations_in_source(src, "app.api.routers.synthetic"), src
    ok = [
        "from app.judge.jev_mcp import normalize",
        "from app.judge.guard import check_payload",
        "from app.judge.claims import remaining_contradicted",
    ]
    for src in ok:
        assert violations_in_source(src, "app.api.views") == [], src
    assert construction_violations("a = MockAdapter(d)", "app/api/x.py")
    assert construction_violations("from app import judge\na = judge.get_adapter(s)", "app/api/x.py")
    assert construction_violations("class X(CachedJudgeAdapter):\n    pass", "app/reports/x.py")
    assert construction_violations("a = get_adapter(s)", "app/scheduler/context.py") == []

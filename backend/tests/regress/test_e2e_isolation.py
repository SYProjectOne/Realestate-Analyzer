"""회귀 러너의 e2e 실행 격리(WP9) — 실행마다 빈 포트·고유 임시 폴더, 끝나면 폴더 정리.

여러 worktree 에서 ``python scripts/tasks.py regress`` 를 동시에 돌려도 포트(18865 등)·데이터 폴더
(``%TEMP%/sa-e2e-flows``)가 겹치지 않아야 한다. e2e 설정(e2e/env.ts, perf 설정)은 이 환경변수를 읽고,
없으면 기존 고정값을 쓴다(수동 실행 호환).
"""

from __future__ import annotations

import importlib.util
import socket
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]


def load_tasks() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sa_tasks_iso", ROOT / "scripts" / "tasks.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sa_tasks_iso"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_free_ports_distinct_and_bindable() -> None:
    tasks = load_tasks()
    ports = tasks.free_ports(4)
    assert len(set(ports)) == 4
    for p in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", p))  # 반환 뒤에는 비어 있어야 한다


def test_isolation_env_unique_per_run_and_cleaned() -> None:
    tasks = load_tasks()
    a = tasks.E2EIsolation.create({})
    b = tasks.E2EIsolation.create({})
    try:
        for var in tasks.E2E_PORT_VARS:
            assert a.env[var].isdigit() and b.env[var].isdigit()
        ports_a = {a.env[v] for v in tasks.E2E_PORT_VARS}
        assert len(ports_a) == len(tasks.E2E_PORT_VARS)
        assert a.root != b.root
        assert a.env["E2E_FLOW_DATA"] != b.env["E2E_FLOW_DATA"]
        assert a.env["E2E_PERF_DATA"] != b.env["E2E_PERF_DATA"]
        assert a.env["E2E_RESULTS_JSON"] != b.env["E2E_RESULTS_JSON"]
        assert a.env["E2E_OUTPUT_DIR"] != b.env["E2E_OUTPUT_DIR"]
        assert Path(a.env["E2E_FLOW_DATA"]).is_relative_to(a.root)
        assert a.junit.is_relative_to(a.root)
        (Path(a.env["E2E_FLOW_DATA"]) / "e2e.db").write_bytes(b"x")
    finally:
        a.cleanup(keep_output=False)
        b.cleanup(keep_output=False)
    assert not a.root.exists() and not b.root.exists()
    assert not Path(a.env["E2E_OUTPUT_DIR"]).exists()


def test_isolation_respects_explicit_env() -> None:
    """사용자가 직접 준 포트·폴더는 그대로 둔다."""
    tasks = load_tasks()
    iso = tasks.E2EIsolation.create({"E2E_FLOW_API_PORT": "18865", "E2E_FLOW_DATA": "C:/x"})
    try:
        assert "E2E_FLOW_API_PORT" not in iso.env
        assert "E2E_FLOW_DATA" not in iso.env
        assert iso.env["E2E_FLOW_WEB_PORT"].isdigit()
    finally:
        iso.cleanup(keep_output=False)


def test_regress_step_uses_run_junit() -> None:
    tasks = load_tasks()
    iso = tasks.E2EIsolation.create({})
    try:
        # 앞에 frontend npm ci 가 올 수 있다(R3 4차 — T13 lint 전에 설치)
        step = next(s for s in tasks.t_regress(["--no-e2e"]) if "pytest" in s.cmd)
        cmd, env = iso.apply(step)
        assert f"--junitxml={iso.junit}" in cmd
        assert env["E2E_FLOW_DATA"] == iso.env["E2E_FLOW_DATA"]
    finally:
        iso.cleanup(keep_output=False)

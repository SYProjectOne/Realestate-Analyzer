"""R3 수정 F3 — 설정·기동·인프라·CI.

리뷰 항목: M11(토큰 없으면 127.0.0.1 바인드 + 경고, compose 는 토큰 필수, .env.example 기본 prod),
minor 31(prod + mock 거부), minor 2(CI: chromium·e2e·PDF), M15(Lighthouse CI 잡), minor 34(백업 스크립트).
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.core.settings import Settings, env_var_names

ROOT = Path(__file__).resolve().parents[3]
INFRA = ROOT / "infra"


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in env_var_names():
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def make(**kwargs: object) -> Settings:
    return Settings(_env_file=None, **kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------- minor 31


def test_minor31_prod_rejects_mock_judge(clean_env: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="JUDGE_ADAPTER=mock"):
        make(env="prod", api_token="t" * 32, judge_adapter="mock")
    assert make(env="prod", api_token="t" * 32, judge_adapter="jev").env == "prod"
    assert make(env="dev", judge_adapter="mock").judge_adapter == "mock"


# ---------------------------------------------------------------- M11


def test_m11_serve_binds_loopback_without_tokens(
    clean_env: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from app.serve import bind_host

    with caplog.at_level(logging.WARNING):
        assert bind_host(make(env="dev")) == "127.0.0.1"
    assert any("127.0.0.1" in r.getMessage() for r in caplog.records), "토큰 없는 기동은 경고를 남긴다"
    # API_HOST 를 0.0.0.0 으로 줘도 토큰이 없으면 루프백
    assert bind_host(make(env="dev", api_host="0.0.0.0")) == "127.0.0.1"
    assert bind_host(make(env="dev", api_token="w" * 32, api_host="0.0.0.0")) == "0.0.0.0"
    assert bind_host(make(env="dev", readonly_token="r" * 32, api_host="0.0.0.0")) == "0.0.0.0"
    assert make().api_host == "127.0.0.1", "기본 바인드도 루프백"


def test_m11_serve_command(clean_env: pytest.MonkeyPatch) -> None:
    from app.serve import uvicorn_kwargs

    kw = uvicorn_kwargs(make(env="dev", api_token="w" * 32, api_host="0.0.0.0", api_port=8001))
    assert kw["host"] == "0.0.0.0" and kw["port"] == 8001 and kw["app"] == "app.main:app"
    assert uvicorn_kwargs(make(env="dev"))["host"] == "127.0.0.1"


def test_m11_compose_requires_token_and_binds_api_to_loopback() -> None:
    text = (INFRA / "docker-compose.yml").read_text(encoding="utf-8")
    assert re.search(r"API_TOKEN:\s*\$\{API_TOKEN:\?", text), "compose 는 API_TOKEN 이 비면 기동하지 않는다"
    compose = yaml.safe_load(text)
    ports = [str(p) for p in compose["services"]["api"]["ports"]]
    assert ports and all(p.startswith("${API_BIND:-127.0.0.1}:") for p in ports), ports
    api_docker = (INFRA / "Dockerfile.api").read_text(encoding="utf-8")
    assert "app.serve" in api_docker and "API_HOST=0.0.0.0" in api_docker


def test_m11_env_example_defaults_to_prod() -> None:
    env = {}
    for raw in (INFRA / ".env.example").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    assert env["ENV"] == "prod"
    assert env["JUDGE_ADAPTER"] == "jev"
    assert "API_HOST" in env and "API_PORT" in env


# ---------------------------------------------------------------- minor 2 · M15 CI


def _ci() -> dict[str, object]:
    data = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _runs(job: dict[str, object]) -> str:
    steps = job.get("steps")
    assert isinstance(steps, list)
    return "\n".join(str(s.get("run", "")) + str(s.get("uses", "")) for s in steps)


def test_minor2_ci_installs_chromium_and_runs_e2e() -> None:
    jobs = _ci()["jobs"]
    assert isinstance(jobs, dict)
    e2e = _runs(jobs["frontend-e2e"])
    assert "playwright install" in e2e and "chromium" in e2e
    assert "playwright test" in e2e and "e2e/pages" in e2e
    assert "--ignore-snapshots" in e2e, "차트 스크린샷 기준 이미지는 win32 전용 — CI(linux)는 비교를 끈다"
    backend = _runs(jobs["backend-tests"])
    assert "playwright install" in backend and "chromium" in backend, "보고서 PDF 테스트용 chromium"


def test_m15_ci_runs_lighthouse() -> None:
    jobs = _ci()["jobs"]
    assert isinstance(jobs, dict)
    assert "npm run lighthouse" in _runs(jobs["frontend-lighthouse"])


def test_contract_generated_files_checked_in_ci() -> None:
    """minor 5: 계약 생성물 최신성(gen_contracts --check, 프론트 gen:api 비교)은 CI 에서 강제한다."""
    jobs = _ci()["jobs"]
    assert isinstance(jobs, dict)
    lint = _runs(jobs["backend-lint"])
    assert "gen_contracts.py --check" in lint


# ---------------------------------------------------------------- minor 34 백업


def test_minor34_backup_script() -> None:
    script = INFRA / "backup.sh"
    text = script.read_text(encoding="utf-8")
    assert "pg_dump" in text and "-Fc" in text
    assert "rawdata" in text or "/data/raw" in text
    assert "set -euo pipefail" in text
    bash = shutil.which("bash")
    if bash:
        proc = subprocess.run([bash, "-n", str(script)], capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stderr
    archive = INFRA / "raw_archive.sh"
    atext = archive.read_text(encoding="utf-8")
    assert "tar -C" in atext and "tar -tzf" in atext, "월별 압축은 RAW_DIR 기준 상대 경로로 넣고 검증한다"
    runbook = (ROOT / "docs" / "runbook.md").read_text(encoding="utf-8")
    assert "infra/backup.sh" in runbook and "infra/raw_archive.sh" in runbook

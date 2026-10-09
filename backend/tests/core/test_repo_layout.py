"""저장소 뼈대 검증.

패키지 README(주인), infra(compose·Dockerfile·nginx·.env.example), CI, pre-commit, 작업 러너.

Docker가 없는 환경에서도 compose 구조를 YAML 파싱으로 검증한다.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from app.core.settings import env_var_names

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
INFRA = ROOT / "infra"

WP_PACKAGES = {
    "collectors": "WP1",
    "normalize": "WP2",
    "judge": "WP3",
    "analysis": "WP4",
    "api": "WP5",
    "scheduler": "WP7",
    "reports": "WP8",
}
BACKEND_TEST_MODULES = {"core", "models", *WP_PACKAGES}


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- 패키지·README


@pytest.mark.parametrize(("pkg", "owner"), sorted(WP_PACKAGES.items()))
def test_wp_package_has_init_and_owner_readme(pkg: str, owner: str) -> None:
    d = BACKEND / "app" / pkg
    assert (d / "__init__.py").is_file()
    readme = (d / "README.md").read_text(encoding="utf-8")
    assert re.search(rf"주인[^\n]*{owner}\b", readme), f"{pkg}/README.md 에 주인 {owner} 없음"
    assert "읽기 허용" in readme


def test_core_readme_owner() -> None:
    readme = (BACKEND / "app" / "core" / "README.md").read_text(encoding="utf-8")
    assert re.search(r"주인[^\n]*WP0", readme)


def test_empty_package_markers() -> None:
    for rel in ["app/__init__.py", "app/core/__init__.py"]:
        assert (BACKEND / rel).read_text(encoding="utf-8").strip() == ""


# ---------------------------------------------------------------- docker compose (RA §10)


def test_compose_services_and_volumes() -> None:
    compose = load_yaml(INFRA / "docker-compose.yml")
    services = compose["services"]
    assert set(services) == {"db", "api", "worker", "web"}
    assert set(compose["volumes"]) == {"pgdata", "rawdata"}

    db = services["db"]
    assert str(db["image"]).startswith("postgres:16")
    assert any(str(v).startswith("pgdata:") for v in db["volumes"])
    assert "ports" not in db  # 5432 내부 전용

    api = services["api"]
    assert api["build"]["dockerfile"].endswith("Dockerfile.api")
    assert any("8000" in str(p) for p in api["ports"])
    assert any(str(v).startswith("rawdata:") and str(v).endswith(":ro") for v in api["volumes"])

    worker = services["worker"]
    assert worker["build"]["dockerfile"].endswith("Dockerfile.worker")
    assert any(str(v).startswith("rawdata:") and not str(v).endswith(":ro") for v in worker["volumes"])
    assert "ports" not in worker

    web = services["web"]
    assert web["build"]["dockerfile"].endswith("Dockerfile.web")
    assert any("8080" in str(p) for p in web["ports"])
    assert "api" in web["depends_on"]

    for name in ("api", "worker"):
        env = services[name]["environment"]
        assert str(env["DATABASE_URL"]).startswith("postgresql+psycopg://")
        assert env["RAW_DIR"] == "/data/raw"
        assert "db" in services[name]["depends_on"]


def test_compose_has_no_inline_secrets() -> None:
    text = (INFRA / "docker-compose.yml").read_text(encoding="utf-8")
    for key in ("API_TOKEN", "READONLY_TOKEN", "DATA_GO_KR_KEY", "NEWS_API_KEY", "POSTGRES_PASSWORD"):
        for m in re.finditer(rf"^\s*-?\s*{key}\s*[:=]\s*(\S+)", text, re.M):
            assert m.group(1).startswith("${"), f"{key} 는 변수 치환만 허용: {m.group(0)}"


def test_dockerfiles() -> None:
    api = (INFRA / "Dockerfile.api").read_text(encoding="utf-8")
    assert "uvicorn" in api and "app.main:app" in api
    worker = (INFRA / "Dockerfile.worker").read_text(encoding="utf-8")
    assert "playwright install" in worker and "chromium" in worker
    assert "npx" in worker and "node" in worker
    assert "app.worker" in worker
    web = (INFRA / "Dockerfile.web").read_text(encoding="utf-8")
    assert re.search(r"FROM node:\S+ AS build", web)
    assert "npm run build" in web
    assert "FROM nginx" in web and "nginx.conf" in web
    for text in (api, worker, web):
        assert ".env" not in text.replace(".env.example", "")


def test_nginx_proxies_api() -> None:
    conf = (INFRA / "nginx.conf").read_text(encoding="utf-8")
    assert re.search(r"location\s+/api/\s*\{[^}]*proxy_pass\s+http://api:8000", conf, re.S)
    assert "try_files" in conf  # SPA 라우팅
    assert "listen 8080" in conf


def parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def test_env_example_covers_settings_and_has_no_secrets() -> None:
    env = parse_env_file(INFRA / ".env.example")
    missing = set(env_var_names()) - set(env)
    assert not missing, f".env.example 에 없음: {sorted(missing)}"
    assert env["JEV_MCP_CMD"] == '"npx -y @jkudish/jev-mcp@latest"'
    assert "REFERENCE_DIR" in env and "TZ" in env
    for key in ("API_TOKEN", "READONLY_TOKEN", "DATA_GO_KR_KEY", "NEWS_API_KEY", "WEBHOOK_URL"):
        assert env[key] == "" or "change-me" in env[key], f"{key} 예시값만 허용"
    assert not (INFRA / ".env").exists() or ".env" in (ROOT / ".gitignore").read_text(encoding="utf-8")


# ---------------------------------------------------------------- CI·pre-commit


def test_ci_workflow() -> None:
    ci = load_yaml(ROOT / ".github" / "workflows" / "ci.yml")
    triggers = ci.get("on", ci.get(True))  # PyYAML 은 'on' 을 True 로 읽는다
    assert "push" in triggers and "pull_request" in triggers
    jobs = ci["jobs"]
    assert {"changes", "backend-lint", "backend-tests", "frontend"} <= set(jobs)

    step = next(s for s in jobs["changes"]["steps"] if "paths-filter" in str(s.get("uses", "")))
    filters = yaml.safe_load(step["with"]["filters"])
    assert "contracts/**" in str(filters["contracts"])

    matrix = jobs["backend-tests"]["strategy"]["matrix"]["module"]
    assert set(matrix) >= BACKEND_TEST_MODULES
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "tests/${{ matrix.module }}" in text or "tests/$MODULE" in text
    assert "needs.changes.outputs.contracts" in text  # contracts 변경 → 전체

    lint_steps = " ".join(str(s.get("run", "")) for s in jobs["backend-lint"]["steps"])
    assert "ruff check" in lint_steps and "mypy" in lint_steps
    fe_steps = " ".join(str(s.get("run", "")) for s in jobs["frontend"]["steps"])
    for cmd in ("npm run lint", "npm run typecheck", "npm test"):
        assert cmd in fe_steps


def test_precommit_config() -> None:
    cfg = load_yaml(ROOT / ".pre-commit-config.yaml")
    hook_ids = {h["id"] for repo in cfg["repos"] for h in repo["hooks"]}
    assert {"ruff", "mypy", "eslint", "check-added-large-files", "detect-private-key", "gitleaks"} <= hook_ids


# ---------------------------------------------------------------- 작업 러너


def load_tasks() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sa_tasks", ROOT / "scripts" / "tasks.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sa_tasks"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("task", ["regress", "test", "lint", "typecheck", "gen", "dev", "migrate", "worker"])
def test_tasks_dry_run(task: str, capsys: pytest.CaptureFixture[str]) -> None:
    tasks = load_tasks()
    assert tasks.main(["--dry-run", task]) == 0
    assert capsys.readouterr().out.strip()


def test_tasks_test_module_selection(capsys: pytest.CaptureFixture[str]) -> None:
    tasks = load_tasks()
    assert tasks.main(["--dry-run", "test", "core"]) == 0
    out = capsys.readouterr().out
    assert "pytest" in out and "tests/core" in out


def test_tasks_unknown_command() -> None:
    tasks = load_tasks()
    with pytest.raises(SystemExit):
        tasks.main(["nope"])


def test_makefile_wraps_tasks() -> None:
    mk = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "scripts/tasks.py" in mk
    for target in ("regress", "test", "lint", "gen", "dev"):
        assert re.search(rf"^{target}:", mk, re.M)
    assert "\n\t" in mk  # make 는 탭 들여쓰기


# ---------------------------------------------------------------- 문서


def test_docs_exist() -> None:
    adr = sorted(p.name for p in (ROOT / "docs" / "adr").glob("ADR-*.md"))
    for n in range(1, 12):
        assert any(name.startswith(f"ADR-{n:02d}-") for name in adr), f"ADR-{n:02d} 없음"
    runbook = (ROOT / "docs" / "runbook.md").read_text(encoding="utf-8")
    situations = ("청약홈", "403", "판정기 장애", "판정기 버전", "지역 추가", "디스크", "published", "Docker")
    for situation in situations:
        assert situation in runbook
    assert "G0" in (ROOT / "docs" / "region-add.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Docker" in readme and "uv sync" in readme

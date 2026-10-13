"""R5-OPS (D25) — CI·pre-commit·README 주인 배선.

| 항목 | 테스트 |
| --- | --- |
| OPS-1 CI 의 Postgres 테스트는 postgres 서비스 컨테이너 + ``TEST_POSTGRES_URL``(D25-8) | ``test_ci_backend_tests_use_postgres_service`` |
| OPS-5 CI matrix 의 빈 ``models`` 항목 정리 — matrix = 실제 ``tests/<모듈>`` | ``test_ci_matrix_matches_backend_test_dirs`` |
| OPS-5 pre-commit 에 ``tsc --noEmit``(``npm run typecheck``) 훅 | ``test_precommit_has_typecheck_hook`` |
| OPS-5 ``backend/app/models``·``contracts``·``infra`` README 주인 줄 | ``tests/core/test_repo_layout.py::test_owner_lines`` |
| OPS-6 차트 리눅스 기준 이미지 커밋 + CI 는 ``--update-snapshots`` 없이 비교(D25-9) | ``test_linux_chart_baselines_committed`` · ``test_ci_compares_chart_snapshots_without_update`` |
| OPS-6 보고서 ECharts 인라인 테스트가 CI 에서 skip 되지 않게 번들 준비 | ``test_ci_reports_job_prepares_echarts_bundle`` |
"""

# ruff: noqa: E501  (한국어 assertion 메시지·표)

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
CI = ROOT / ".github" / "workflows" / "ci.yml"
SNAPSHOTS = ROOT / "frontend" / "tests" / "e2e" / "charts-gallery.spec.ts-snapshots"
# 회귀(tests/regress)는 별도 regress 잡(python scripts/tasks.py regress)이 돈다
NOT_IN_MATRIX = {"regress"}


def _ci() -> dict[str, Any]:
    doc = yaml.safe_load(CI.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    return doc


def _test_dirs() -> set[str]:
    return {
        d.name
        for d in (BACKEND / "tests").iterdir()
        if d.is_dir() and not d.name.startswith((".", "_")) and any(d.rglob("test_*.py"))
    }


def test_ci_matrix_matches_backend_test_dirs() -> None:
    jobs = _ci()["jobs"]
    matrix = set(jobs["backend-tests"]["strategy"]["matrix"]["module"])
    assert "models" not in matrix, "tests/models 가 없다 — 빈 matrix 항목(매번 '없음'으로 통과)"
    assert matrix == _test_dirs() - NOT_IN_MATRIX, (
        f"matrix {sorted(matrix)} != tests/ {sorted(_test_dirs() - NOT_IN_MATRIX)}"
    )
    outputs = set(jobs["changes"]["outputs"])
    assert "models" not in outputs, "changes 잡의 models 필터도 정리(app/models 는 shared 필터가 본다)"
    assert matrix <= outputs, "matrix 모듈마다 paths-filter 출력이 있어야 한다"


def test_ci_backend_tests_use_postgres_service() -> None:
    """GitHub 리눅스에서 pgserver 소켓 경로가 깨졌다(run 38326346203) — CI 는 서비스 컨테이너로 돈다(D25-8)."""
    job = _ci()["jobs"]["backend-tests"]
    services = job.get("services") or {}
    pg = services.get("postgres")
    assert pg, "backend-tests 에 postgres 서비스 없음"
    assert str(pg["image"]).startswith("postgres:16"), "계약·compose 기준 Postgres 16"
    assert "pg_isready" in str(pg.get("options", "")), "준비될 때까지 기다리는 healthcheck"
    ports = [str(p) for p in pg.get("ports", [])]
    assert any(p.startswith("5432:5432") for p in ports)
    env_text = str(job.get("env", {})) + " ".join(str(s.get("env", "")) for s in job["steps"])
    assert "TEST_POSTGRES_URL" in env_text and "postgresql+psycopg://" in env_text
    text = CI.read_text(encoding="utf-8")
    # 일회용 CI DB(trust 인증, 비밀번호 없음) — 저장소 비밀값을 쓰지 않는다
    assert "secrets." not in text.split("backend-tests:", 1)[1].split("\n  infra:", 1)[0]


def test_precommit_has_typecheck_hook() -> None:
    cfg = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hooks = {h["id"]: h for repo in cfg["repos"] for h in repo["hooks"]}
    hook = hooks.get("typecheck")
    assert hook, "pre-commit 에 typecheck(tsc --noEmit) 훅 없음"
    assert "npm --prefix frontend run typecheck" in hook["entry"]
    assert hook["pass_filenames"] is False
    assert re.search(hook["files"], "frontend/src/pages/Home.tsx")
    assert re.search(hook["files"], "frontend/src/api/schema.d.ts")
    pkg = (ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    assert re.search(r'"typecheck"\s*:\s*"[^"]*tsc[^"]*--noEmit', pkg) or re.search(
        r'"typecheck"\s*:\s*"[^"]*tsc -b', pkg
    ), "package.json typecheck 가 tsc 가 아니다"


def test_linux_chart_baselines_committed() -> None:
    """D25-9: win32 기준 이미지마다 같은 이름의 linux 기준 이미지(CI 산출물 chart-snapshots-linux)."""
    win = {p.name.removesuffix("-win32.png") for p in SNAPSHOTS.glob("*-chromium-win32.png")}
    linux = {p.name.removesuffix("-linux.png") for p in SNAPSHOTS.glob("*-chromium-linux.png")}
    assert win, "win32 기준 이미지 없음"
    assert linux == win, (
        f"linux 기준 이미지 누락: {sorted(win - linux)[:5]} / 여분: {sorted(linux - win)[:5]}"
    )
    for p in SNAPSHOTS.glob("*-chromium-linux.png"):
        assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", p.name


def test_ci_compares_chart_snapshots_without_update() -> None:
    job = _ci()["jobs"]["frontend-e2e"]
    runs = "\n".join(str(s.get("run", "")) for s in job["steps"])
    assert "--update-snapshots" not in runs, "CI 가 기준 이미지를 새로 만들면 비교가 아니다(D25-9)"
    assert "npx playwright test" in runs


def test_ci_reports_job_prepares_echarts_bundle() -> None:
    """보고서 HTML 의 ECharts 인라인 테스트(tests/reports/test_html.py)가 CI 에서 skip 되지 않게 번들을 준비한다."""
    job = _ci()["jobs"]["backend-tests"]
    steps = job["steps"]
    text = "\n".join(f"{s.get('if', '')} || {s.get('uses', '')} || {s.get('run', '')}" for s in steps)
    assert re.search(r"matrix\.module == 'reports'.*\|\| .*setup-node", text), "reports 에 Node 준비 없음"
    assert re.search(r"matrix\.module == 'reports'.*npm ci", text), "reports 에 frontend npm ci(echarts) 없음"
    html_test = (BACKEND / "tests" / "reports" / "test_html.py").read_text(encoding="utf-8")
    assert 'os.environ.get("CI")' in html_test, "CI 에서는 번들 없음이 skip 이 아니라 실패여야 한다"

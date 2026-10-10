"""T13 출처 없는 수치 (RA §9).

기대: provenance 행을 지운 픽스처 → dev: ``contract_violation`` 500; prod: 라벨 "확인 불가(출처 누락)" + 경고 로그;
프론트 lint가 FactCell 밖 숫자 렌더 감지.

시스템 경계: devseed DB 에 ``devseed.replace_bundles``(T13 픽스처, 출처 4행 삭제)로 적재 → 실제 HTTP 서버(uvicorn
서브프로세스가 아니라 같은 앱 팩토리의 TestClient, ENV 만 dev/prod) → 응답·로그. 프론트는 실제 eslint 설정으로
FactCell 밖 숫자 렌더 소스를 stdin 으로 넣어 규칙 오류를 확인한다(파일을 만들지 않는다).
"""

# ruff: noqa: E501

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.db import reset_engine
from app.core.settings import set_settings

from .conftest import FIXTURE, REPO, SNAP, WRITE, RegressEnv, load_json, make_settings

pytestmark = pytest.mark.regress

T13 = FIXTURE / "raw" / "t13_missing_provenance"
CID = 2  # 엘리프


def _replace(env: RegressEnv) -> None:
    from app.api import devseed

    devseed.replace_bundles(
        env.settings, bundles_path=T13 / "complexes.json", provenance_path=T13 / "provenance.json"
    )
    reset_engine()


def _client(env: RegressEnv, mode: str) -> TestClient:
    from app.main import create_app

    db = Path(env.settings.database_url.removeprefix("sqlite:///"))
    s = make_settings(db, env.settings.raw_dir, env.tmp / "reports", env=mode)
    set_settings(s)
    return TestClient(create_app(s), raise_server_exceptions=False)


def test_t13_dev_contract_violation(env: RegressEnv) -> None:
    _replace(env)
    with _client(env, "dev") as c:
        r = c.get(f"/api/complexes/{CID}", headers=WRITE)
        assert r.status_code == 500, r.text
        assert r.json()["code"] == "contract_violation"
        r = c.get(f"/api/snapshots/{SNAP}/complexes", headers=WRITE)
        assert r.status_code == 500 and r.json()["code"] == "contract_violation"
        assert c.get("/api/complexes/3", headers=WRITE).status_code == 200  # 다른 단지는 영향 없음


def test_t13_prod_unknown_label_and_warning(env: RegressEnv, caplog: pytest.LogCaptureFixture) -> None:
    exp = load_json(T13 / "expected.json")
    _replace(env)
    with _client(env, "prod") as c, caplog.at_level(logging.WARNING):
        r = c.get(f"/api/complexes/{CID}", headers=WRITE)
        assert r.status_code == 200, r.text
        body = r.json()
        t84a = next(t for t in body["types"] if t["type_code"] == "84A")
        got = {
            "complex.units_total": body["header"]["units_total"],
            "types[84A].max_price_won": t84a["max_price_won"],
            "types[84A].balcony_won": t84a["balcony_won"],
            "payment_terms[0].down_payment_pct": body["payment"][0]["down_payment_pct"],
        }
        assert set(got) == set(exp["fields"])
        for name, fact in got.items():
            assert (fact["label"], fact.get("reason"), fact["v"], fact["prov"]) == (
                "확인 불가",
                "출처 누락",
                None,
                None,
            ), name
        warned = [r for r in caplog.records if r.levelno >= logging.WARNING and "출처 누락" in r.getMessage()]
        assert len(warned) >= len(exp["fields"])
        # 리스트·대시보드도 500 없이
        assert c.get(f"/api/snapshots/{SNAP}/complexes", headers=WRITE).status_code == 200
        assert c.get(f"/api/snapshots/{SNAP}/dashboard", headers=WRITE).status_code == 200


def test_t13_frontend_lint_flags_raw_number_outside_factcell() -> None:
    frontend = REPO / "frontend"
    npx = shutil.which("npx")
    if npx is None or not (frontend / "node_modules" / "eslint").is_dir():
        pytest.skip("frontend node_modules 없음(npm ci 전) — 프론트 lint 검사 생략")
    probe = "export function Probe({ total }: { total: number }) {\n  return <span>{total}</span>;\n}\n"
    ok = "import { FactCell } from '../../components/FactCell';\nexport function Probe({ f }: { f: Parameters<typeof FactCell>[0]['fact'] }) {\n  return <FactCell fact={f} />;\n}\n"
    out = {}
    for name, code in (("raw", probe), ("factcell", ok)):
        p = subprocess.run(
            [npx, "eslint", "--stdin", "--stdin-filename", "src/pages/dashboard/index.tsx", "-f", "json"],
            input=code,
            cwd=frontend,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
            check=False,
        )
        # eslint 종료 코드: 0 = 위반 없음, 1 = 위반 있음(둘 다 stdout 에 JSON). 그 밖(2 = 설정·실행 오류 — 같은 frontend 에서
        # 'npm ci' 가 node_modules 를 다시 쓰는 중이면 모듈을 못 찾는다, R3 4차 리뷰가 확정한 간헐 실패 원인)은 stdout 이
        # 비어 있다 — JSON 해석 오류 대신 stderr 를 담아 실패시킨다. 순서: frontend 'npm ci' 를 끝낸 뒤 regress 를 돈다
        # (runbook·scripts/tasks.py regress).
        if p.returncode not in (0, 1) or not p.stdout.strip():
            pytest.fail(
                f"eslint 실행 실패(exit {p.returncode}) — frontend 'npm ci' 가 끝난 뒤 다시 돌린다. stderr: {p.stderr.strip()[:500]}"
            )
        out[name] = [m["ruleId"] for m in json.loads(p.stdout)[0]["messages"]]
    assert "local/no-raw-number-render" in out["raw"], out
    assert "local/no-raw-number-render" not in out["factcell"], out

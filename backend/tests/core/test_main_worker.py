from __future__ import annotations

import logging
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from app import worker
from app.core.settings import Settings
from app.main import create_app

BACKEND = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------- /health


def test_health_ok(test_settings: Settings) -> None:
    """계약 Health(2026-10-09.3): contract_version·app_version·judge·time."""
    from app.core.contracts_gen import Health
    from app.core.protocols import CONTRACT_VERSION

    with TestClient(create_app(test_settings)) as client:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        Health.model_validate(body)  # extra 금지 — 계약 키만
        assert body["status"] == "ok"
        assert body["db"] == "ok"
        assert body["contract_version"] == CONTRACT_VERSION
        assert body["app_version"]
        assert body["judge"] == "unknown"  # 스냅샷 없음
        assert body["time"].endswith("+09:00")
        # 프록시 경로(/api/health)도 같은 모양
        assert set(client.get(f"{test_settings.api_prefix}/health").json()) == set(body)


def test_health_judge_follows_latest_snapshot_degraded(test_settings: Settings, db_engine: Engine) -> None:
    from sqlalchemy.orm import Session

    from app.models import Region, Snapshot

    engine = db_engine
    with Session(engine) as s:
        s.add(Region(id=1, name="r", query_text="r", selections=[], sido_codes=[], sigungu_codes=[],
                     legal_dong_codes=[], living_areas=[], applyhome_query={}, status="ready",
                     age_premium_coef={}, created_at="2026-10-09T00:00:00+09:00"))  # fmt: skip
        s.flush()
        s.add(Snapshot(region_id=1, asof_date="2026-10-07", status="ready", degraded=True,
                       created_at="2026-10-07T06:00:00+09:00"))  # fmt: skip
        s.add(Snapshot(region_id=1, asof_date="2026-10-08", status="ready", degraded=False,
                       created_at="2026-10-08T06:00:00+09:00"))  # fmt: skip
        s.commit()
    with TestClient(create_app(test_settings)) as client:
        assert client.get("/health").json()["judge"] == "ok"  # 최신 스냅샷 기준
        with Session(engine) as s:
            snap = s.query(Snapshot).filter_by(asof_date="2026-10-08").one()
            snap.degraded = True
            s.commit()
        r = client.get("/health")
        assert r.status_code == 200  # 판정기 장애만이면 200
        assert r.json()["judge"] == "degraded" and r.json()["status"] == "degraded"


def test_health_db_down(tmp_path: Path, test_settings: Settings) -> None:
    from app.core.contracts_gen import Health

    broken = test_settings.model_copy(update={"database_url": f"sqlite:///{tmp_path.as_posix()}"})
    with TestClient(create_app(broken)) as client:
        r = client.get("/health")
        assert r.status_code == 503
        body = r.json()
        Health.model_validate(body)
        assert body["db"] == "error" and body["status"] == "degraded" and body["judge"] == "unknown"


def test_api_router_included_when_present(test_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    router = APIRouter()

    @router.get("/ping")
    def ping() -> dict[str, str]:
        return {"pong": "1"}

    fake = types.ModuleType("app.api")
    fake.router = router  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "app.api", fake)
    with TestClient(create_app(test_settings)) as client:
        assert client.get(f"{test_settings.api_prefix}/ping").json() == {"pong": "1"}


def test_api_router_absent_is_skipped(test_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "app.api", types.ModuleType("app.api"))
    app = create_app(test_settings)
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/health" in paths


# ---------------------------------------------------------------- worker


def test_worker_once_heartbeat(
    test_settings: Settings, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setitem(sys.modules, "app.scheduler.runner", None)  # import → ModuleNotFoundError
    caplog.set_level(logging.INFO)
    assert worker.main(["--once"]) == 0
    assert any(r.getMessage() == "worker.heartbeat" for r in caplog.records)


def test_worker_delegates_to_scheduler_runner(
    test_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[list[str] | None] = []

    def fake_main(argv: list[str] | None = None) -> int:
        seen.append(argv)
        return 7

    fake = types.ModuleType("app.scheduler.runner")
    fake.main = fake_main  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "app.scheduler.runner", fake)
    assert worker.main(["--once"]) == 7
    assert seen == [["--once"]]


def test_worker_module_cli_once(tmp_path: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k not in {"API_TOKEN", "ENV"}}
    env.update(
        {
            "DATABASE_URL": f"sqlite:///{(tmp_path / 'w.db').as_posix()}",
            "RAW_DIR": str(tmp_path / "raw"),
            "ENV": "dev",
        }
    )
    proc = subprocess.run(
        [sys.executable, "-m", "app.worker", "--once"],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "worker." in proc.stderr

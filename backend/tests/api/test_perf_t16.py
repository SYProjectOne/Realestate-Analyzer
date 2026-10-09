"""T16 성능 (RA §9): 합성 1,000단지(contracts/fixtures/tools/synth.py) → /complexes 첫 페이지 1초 이내."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.db import reset_engine
from app.core.settings import set_settings

from ._support import WRITE, validate
from .conftest import Seeded, make_settings


def test_t16_first_page_under_1s(seeded_db: Seeded, tmp_path: Path) -> None:
    from app.api import devseed
    from app.main import create_app

    db = tmp_path / "t16.db"
    shutil.copyfile(seeded_db.db, db)
    settings = make_settings(db, seeded_db.raw_dir, tmp_path / "reports")
    set_settings(settings)
    try:
        n = devseed.load_synth(settings, n=1000, snapshot_id=12)
        assert n == 1000
        with TestClient(create_app(settings), raise_server_exceptions=False) as client:
            client.get("/api/snapshots/12/complexes", headers=WRITE)  # 워밍업(임포트·커넥션)
            for params in ({}, {"sort": "-price_mid"}, {"filter[living_area]": "la_2", "sort": "name"}):
                t0 = time.perf_counter()
                r = client.get("/api/snapshots/12/complexes", params=params, headers=WRITE)
                elapsed = time.perf_counter() - t0
                assert r.status_code == 200, r.text
                body = r.json()
                assert elapsed < 1.0, f"{params}: {elapsed:.3f}s"
                assert body["total"] >= 250
                assert len(body["items"]) == 50
            validate("listComplexes", 200, body)
            t0 = time.perf_counter()
            r = client.get("/api/snapshots/12/complexes", params={"size": 1000}, headers=WRITE)
            assert r.status_code == 200 and len(r.json()["items"]) == 1000
            assert time.perf_counter() - t0 < 5.0
    finally:
        set_settings(None)
        reset_engine()

"""T13 출처 없는 수치 (RA §9): provenance 행을 지운 픽스처 → dev = 500 contract_violation,
prod = 라벨 '확인 불가', reason '출처 누락' + 경고 로그. 픽스처: raw/t13_missing_provenance/."""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.db import reset_engine
from app.core.settings import Settings, set_settings

from ._support import FIXTURE, WRITE, as_live, validate
from .conftest import Seeded, make_settings

T13 = FIXTURE / "raw" / "t13_missing_provenance"


def _expected() -> dict[str, object]:
    data: dict[str, object] = json.loads((T13 / "expected.json").read_text(encoding="utf-8"))
    return data


@pytest.fixture
def t13_settings(seeded_db: Seeded, tmp_path: Path) -> Iterator[tuple[Path, Path]]:
    """시드 DB 복사본에서 단지 2(엘리프)를 T13 픽스처(출처 4행 삭제)로 다시 적재한다."""
    from app.api import devseed

    db = tmp_path / "t13.db"
    shutil.copyfile(seeded_db.db, db)
    settings = make_settings(db, seeded_db.raw_dir, tmp_path / "reports")
    set_settings(settings)
    try:
        devseed.replace_bundles(
            settings, bundles_path=T13 / "complexes.json", provenance_path=T13 / "provenance.json"
        )
        as_live()  # D13-1: 출처 누락은 실시간 계산(발행 전 리비전)·발행(materialize) 때 드러난다
    finally:
        set_settings(None)
        reset_engine()
    yield db, seeded_db.raw_dir


def _client(db: Path, raw: Path, tmp_path: Path, env: str) -> tuple[TestClient, Settings]:
    from app.main import create_app

    settings = make_settings(db, raw, tmp_path / "reports", env=env)
    set_settings(settings)
    return TestClient(create_app(settings), raise_server_exceptions=False), settings


def test_t13_dev_contract_violation(t13_settings: tuple[Path, Path], tmp_path: Path) -> None:
    client, _ = _client(*t13_settings, tmp_path, "dev")
    try:
        with client:
            r = client.get("/api/complexes/2", headers=WRITE)
            assert r.status_code == 500
            body = r.json()
            assert body["code"] == "contract_violation"
            validate("getComplex", 500, body)
            assert "provenance" in body["detail"] or "출처" in body["detail"]
            # 다른 단지는 영향 없음
            assert client.get("/api/complexes/3", headers=WRITE).status_code == 200
            r = client.get("/api/snapshots/12/complexes", headers=WRITE)
            assert r.status_code == 500 and r.json()["code"] == "contract_violation"
    finally:
        set_settings(None)
        reset_engine()


def test_t13_prod_label_and_warning(
    t13_settings: tuple[Path, Path], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client, _ = _client(*t13_settings, tmp_path, "prod")
    try:
        with client, caplog.at_level(logging.WARNING):
            r = client.get("/api/complexes/2", headers=WRITE)
            assert r.status_code == 200, r.text
            body = r.json()
            validate("getComplex", 200, body)
            missing = {
                "complex.units_total": body["header"]["units_total"],
                "types[84A].max_price_won": next(t for t in body["types"] if t["type_code"] == "84A")[
                    "max_price_won"
                ],
                "types[84A].balcony_won": next(t for t in body["types"] if t["type_code"] == "84A")[
                    "balcony_won"
                ],
                "payment_terms[0].down_payment_pct": body["payment"][0]["down_payment_pct"],
            }
            assert set(missing) == set(_expected()["fields"])  # type: ignore[arg-type]
            for name, fact in missing.items():
                assert fact["label"] == "확인 불가", name
                assert fact["reason"] == "출처 누락", name
                assert fact["v"] is None and fact["prov"] is None, name
            warned = [
                rec
                for rec in caplog.records
                if rec.levelno >= logging.WARNING and "출처 누락" in rec.getMessage()
            ]
            assert len(warned) >= 4
            # 출처가 있는 값은 그대로
            assert body["header"]["housing_type"]["label"] == "확인됨"
            r = client.get("/api/snapshots/12/complexes", headers=WRITE)
            assert r.status_code == 200
            validate("listComplexes", 200, r.json())
    finally:
        set_settings(None)
        reset_engine()


def test_t13_publish_stores_missing_provenance_label_in_any_env(
    t13_settings: tuple[Path, Path], tmp_path: Path
) -> None:
    """D13-1: 출처 누락은 발행을 막지 않는다 — 저장본은 ENV 와 무관하게 '확인 불가(출처 누락)'(prod 규칙). 발행 뒤 dev 에서도
    발행 리비전 GET 은 그 라벨(dev 의 500 은 발행 전 리비전 실시간 GET 에서 — 위 테스트)."""
    from app.core.db import get_session
    from app.main import create_app
    from app.scheduler.snapshots import publish

    db, raw = t13_settings
    settings = make_settings(db, raw, tmp_path / "reports", env="dev")
    set_settings(settings)
    try:
        with get_session() as s:
            assert publish(s, 12, now="2026-10-09T09:00:00+09:00")[0]
        with TestClient(create_app(settings), raise_server_exceptions=False) as client:
            r = client.get("/api/complexes/2", params={"snapshot": 12}, headers=WRITE)
            assert r.status_code == 200, r.text
            facts = [f for f in _facts(r.json()) if f.get("reason") == "출처 누락"]
            assert facts and all(f["label"] == "확인 불가" for f in facts)
    finally:
        set_settings(None)
        reset_engine()


def _facts(obj: object) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    if isinstance(obj, dict):
        if {"v", "label", "prov"} <= set(obj):
            out.append(obj)
        for v in obj.values():
            out.extend(_facts(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_facts(v))
    return out

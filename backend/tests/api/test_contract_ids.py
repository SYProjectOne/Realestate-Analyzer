"""R3 minor 8: 경로 id 가 있는 operation 을 **유효한 id**로 불러 200(2xx) 본문을 계약으로 검증한다.

schemathesis(``test_schemathesis``)는 경로 id 를 무작위로 만들어 대부분 404 만 본다 — 여기서는
devseed DB 의 실제 id 로 각 operation 의 성공 응답 스키마·Fact 라벨 규칙을 확인한다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_session
from app.models import ChecklistItem, Claim, FieldProvenance, JobRun, RawDocument, Scenario

from ._support import WRITE, assert_facts_labelled, validate

SNAP = 12


def _first(model: Any, *where: Any) -> int:
    with get_session() as s:
        row = s.scalars(select(model.id).where(*where).order_by(model.id).limit(1)).first()
    assert row is not None, model.__name__
    return int(row)


def _fp() -> str:
    with get_session() as s:
        fid = s.scalars(select(FieldProvenance.id).where(FieldProvenance.chosen.is_(True)).limit(1)).first()
    return f"fp_{fid}"


def _job() -> int:
    with get_session() as s:
        job = JobRun(
            job_name="reference.refresh", kind="manual", payload={}, scheduled_at="2026-10-09T00:00:00+09:00",
            status="queued", stats={},
        )  # fmt: skip
        s.add(job)
        s.flush()
        return int(job.id)


def _scenario_b() -> int:
    with get_session() as s:
        sid = s.scalars(select(Scenario.id).where(Scenario.code == "B")).one()
    return int(sid)


GETS: list[tuple[str, Callable[[], str]]] = [
    ("getRegion", lambda: "/api/regions/1"),
    ("listSnapshots", lambda: "/api/regions/1/snapshots"),
    ("getDashboard", lambda: f"/api/snapshots/{SNAP}/dashboard"),
    ("listComplexes", lambda: f"/api/snapshots/{SNAP}/complexes"),
    ("getComplex", lambda: "/api/complexes/2"),
    ("getProvenance", lambda: f"/api/provenance/{_fp()}"),
    ("getCompare", lambda: f"/api/snapshots/{SNAP}/compare?ids=1,2,4"),
    ("getSensitivity", lambda: f"/api/snapshots/{SNAP}/sensitivity"),
    ("previewScenario", lambda: f"/api/scenarios/{_scenario_b()}/preview?snapshot={SNAP}"),
    ("getJob", lambda: f"/api/jobs/{_job()}"),
    ("getMarket", lambda: f"/api/snapshots/{SNAP}/market"),
    ("listChanges", lambda: f"/api/snapshots/{SNAP}/changes"),
    ("listClaims", lambda: f"/api/snapshots/{SNAP}/claims"),
]


@pytest.mark.parametrize(("op_id", "url"), GETS, ids=[g[0] for g in GETS])
def test_get_with_valid_ids_returns_contract_body(
    client: TestClient, op_id: str, url: Callable[[], str]
) -> None:
    r = client.get(url(), headers=WRITE)
    assert r.status_code == 200, f"{op_id}: {r.status_code} {r.text[:300]}"
    body = r.json()
    validate(op_id, 200, body)
    assert_facts_labelled(body)


def test_csv_and_raw_with_valid_ids(client: TestClient) -> None:
    r = client.get(f"/api/snapshots/{SNAP}/complexes.csv", headers=WRITE)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    raw_id = _first(RawDocument, RawDocument.path.is_not(None))
    r = client.get(f"/api/raw/{raw_id}", headers=WRITE)
    assert r.status_code == 200 and r.content


def test_writes_with_valid_ids(client: TestClient) -> None:
    item = _first(ChecklistItem)
    r = client.patch(f"/api/ops/checklist/{item}", json={"status": "done"}, headers=WRITE)
    assert r.status_code == 200, r.text
    validate("updateChecklistItem", 200, r.json())
    with get_session() as s:
        c = Claim(snapshot_id=SNAP, section="x", complex_id=2, text="틀린 문장", verify_status="contradicted")
        s.add(c)
        s.flush()
        cid = c.id
    r = client.patch(f"/api/claims/{cid}", json={"text": "고친 문장"}, headers=WRITE)
    assert r.status_code == 202, r.text
    validate("reviseClaim", 202, r.json())
    link = client.post("/api/share-links", json={}, headers=WRITE).json()["link"]
    r = client.delete(f"/api/share-links/{link['id']}", headers=WRITE)
    assert r.status_code == 200
    validate("revokeShareLink", 200, r.json())

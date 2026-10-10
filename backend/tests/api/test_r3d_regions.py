"""R3d CORE2 — PATCH /regions minor: 이름 guard, 이름만 바꾸면 region.expand·change_event 없음(계약 .9)."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.db import get_session
from app.models import ChangeEvent, JobRun

from ._support import WRITE, validate


def _selections(client: TestClient) -> list[dict[str, Any]]:
    region = client.get("/api/regions/1", headers=WRITE).json()
    return [{"kind": s["kind"], "code": s["code"], "full_name": s["full_name"]} for s in region["selections"]]


def test_name_only_patch_has_no_expand_job_or_change_event(client: TestClient) -> None:
    with get_session() as s:
        jobs = int(s.scalar(select(func.count()).select_from(JobRun)) or 0)
        events = int(s.scalar(select(func.count()).select_from(ChangeEvent)) or 0)
    r = client.patch(
        "/api/regions/1", json={"selections": _selections(client), "name": "새 이름"}, headers=WRITE
    )
    assert r.status_code == 200, r.text
    body = r.json()
    validate("updateRegion", 200, body)
    assert body["region"]["name"] == "새 이름"
    assert body["change_event"] is None and body["job_id"] is None and body["added"] == body["removed"] == []
    with get_session() as s:
        assert int(s.scalar(select(func.count()).select_from(JobRun)) or 0) == jobs, "region.expand 없음"
        assert int(s.scalar(select(func.count()).select_from(ChangeEvent)) or 0) == events


def test_region_name_guard_rejects_personal_info(client: TestClient) -> None:
    for bad in ("담당 010-1234-5678", "문의 someone@example.com"):
        r = client.patch(
            "/api/regions/1", json={"selections": _selections(client), "name": bad}, headers=WRITE
        )
        assert r.status_code == 422, (bad, r.text)
        validate("updateRegion", 422, r.json())

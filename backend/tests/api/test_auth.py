"""인증 (ADR-9, openapi bearerAuth): 쓰기 토큰 = 전부, 읽기 전용 토큰 = GET만(그 밖 403), 없으면 401."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from ._support import READ, WRITE, validate


def test_health_needs_no_token(client: TestClient) -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/api/health").status_code == 200


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer nope"}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer"}],
)
def test_missing_or_wrong_token_is_401(client: TestClient, headers: dict[str, str]) -> None:
    r = client.get("/api/regions", headers=headers)
    assert r.status_code == 401
    assert r.json()["code"] == "unauthorized"
    validate("listRegions", 401, r.json())


def test_readonly_token_can_read(client: TestClient) -> None:
    r = client.get("/api/regions", headers=READ)
    assert r.status_code == 200
    validate("listRegions", 200, r.json())


WRITES: list[tuple[str, str, str, dict[str, Any]]] = [
    (
        "post",
        "/api/regions",
        "createRegion",
        {
            "name": "x",
            "query_text": "x",
            "selections": [{"kind": "sigungu", "code": "28245", "full_name": "인천광역시 계양구"}],
        },
    ),
    ("put", "/api/regions/1/living-areas", "updateLivingAreas", {"living_areas": []}),
    ("post", "/api/scenarios", "createScenario", {}),
    ("post", "/api/jobs", "createJob", {"job_name": "reference.refresh", "payload": {}}),
    ("patch", "/api/ops/checklist/1", "updateChecklistItem", {"status": "done"}),
    ("post", "/api/ops/human-checks", "createHumanCheck", {}),
    ("post", "/api/reports", "createReport", {"snapshot_id": 12, "format": "html"}),
]


@pytest.mark.parametrize(("method", "url", "op", "body"), WRITES)
def test_readonly_token_cannot_write(
    client: TestClient, method: str, url: str, op: str, body: dict[str, Any]
) -> None:
    """읽기 전용 토큰으로 GET 이외 → 403 forbidden (본문 검증보다 먼저)."""
    r = client.request(method.upper(), url, headers=READ, json=body)
    assert r.status_code == 403, r.text
    assert r.json()["code"] == "forbidden"
    validate(op, 403, r.json())


def test_write_token_can_write(client: TestClient) -> None:
    r = client.post("/api/jobs", headers=WRITE, json={"job_name": "reference.refresh", "payload": {}})
    assert r.status_code == 202, r.text
    validate("createJob", 202, r.json())


def test_unknown_route_is_contract_error(client: TestClient) -> None:
    r = client.get("/api/nope", headers=WRITE)
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"

"""지역 엔드포인트 4개 (DECISIONS D2-3) + GET /regions, /regions/{id}/snapshots."""

from __future__ import annotations

import copy
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_session
from app.models import ChangeEvent, JobRun, Region

from ._support import WRITE, assert_facts_labelled, validate


def test_resolve_songdo_exact_legal_dong_first(client: TestClient) -> None:
    r = client.get("/api/regions/resolve", params={"q": "송도"}, headers=WRITE)
    assert r.status_code == 200, r.text
    body = r.json()
    validate("resolveRegion", 200, body)
    assert body, "송도 후보 없음"
    first = body[0]
    assert (first["kind"], first["code"], first["match"]) == ("legal_dong", "2818510600", "exact")
    assert first["legal_dong_codes"] == ["2818510600"]


def test_resolve_geomdan_has_new_sigungu_only(client: TestClient) -> None:
    body = client.get("/api/regions/resolve", params={"q": "검단"}, headers=WRITE).json()
    validate("resolveRegion", 200, body)
    sgg = [c for c in body if c["kind"] == "sigungu"]
    assert any(c["code"] == "28290" for c in sgg)
    assert not any(c["code"] == "28260" for c in body), "폐지된 서구 코드가 후보로 나오면 안 된다"


def test_resolve_multi_word_and_limits(client: TestClient) -> None:
    body = client.get("/api/regions/resolve", params={"q": "인천 연수구"}, headers=WRITE).json()
    assert any(c["kind"] == "sigungu" and c["code"] == "28185" for c in body)
    assert len(body) <= 50


def test_resolve_requires_q(client: TestClient) -> None:
    r = client.get("/api/regions/resolve", headers=WRITE)
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"
    validate("resolveRegion", 422, r.json())


def test_list_and_get_region(client: TestClient) -> None:
    body = client.get("/api/regions", headers=WRITE).json()
    validate("listRegions", 200, body)
    assert [r["id"] for r in body] == [1]
    region = body[0]
    assert region["latest_snapshot"]["id"] == 12
    la2 = next(a for a in region["living_areas"] if a["id"] == "la_2")
    names = {d["code"]: d["name"] for d in la2["legal_dongs"]}
    assert names["2829010300"] == "마전동"
    assert la2["legal_dong_codes"] == [d["code"] for d in la2["legal_dongs"]]

    one = client.get("/api/regions/1", headers=WRITE).json()
    validate("getRegion", 200, one)
    assert_facts_labelled(one)
    assert client.get("/api/regions/999", headers=WRITE).status_code == 404


def test_list_snapshots(client: TestClient) -> None:
    body = client.get("/api/regions/1/snapshots", headers=WRITE).json()
    validate("listSnapshots", 200, body)
    assert [s["id"] for s in body] == [12, 11]
    assert body[0]["complex_count"] == 16
    assert body[0]["contradicted_claims"] == 0
    assert client.get("/api/regions/999/snapshots", headers=WRITE).status_code == 404


def test_create_region_registers_bootstrap_job(client: TestClient) -> None:
    req = {
        "name": "테스트 계양",
        "query_text": "계양구",
        "selections": [{"kind": "sigungu", "code": "28245", "full_name": "인천광역시 계양구"}],
    }
    r = client.post("/api/regions", headers=WRITE, json=req)
    assert r.status_code == 201, r.text
    body = r.json()
    validate("createRegion", 201, body)
    region = body["region"]
    assert region["status"] == "bootstrapping"
    assert region["sigungu_codes"] == ["28245"] and region["sido_codes"] == ["28"]
    assert len(region["living_areas"]) == 1 and region["living_areas"][0]["id"] == "la_1"
    assert set(region["living_areas"][0]["legal_dong_codes"]) == set(region["legal_dong_codes"])
    with get_session() as s:
        job = s.get(JobRun, body["job_id"])
        assert job is not None
        assert (job.job_name, job.status, job.payload) == (
            "region.bootstrap",
            "queued",
            {"region_id": region["id"]},
        )


def test_create_region_unknown_selection_422(client: TestClient) -> None:
    req = {
        "name": "x",
        "query_text": "x",
        "selections": [{"kind": "sigungu", "code": "99999", "full_name": "없음"}],
    }
    r = client.post("/api/regions", headers=WRITE, json=req)
    assert r.status_code == 422
    validate("createRegion", 422, r.json())


def _areas(client: TestClient) -> list[dict[str, Any]]:
    region = client.get("/api/regions/1", headers=WRITE).json()
    return [
        {"id": a["id"], "name": a["name"], "legal_dong_codes": a["legal_dong_codes"]}
        for a in region["living_areas"]
    ]


def test_living_areas_split_ok(client: TestClient) -> None:
    areas = _areas(client)
    la2 = next(a for a in areas if a["id"] == "la_2")
    moved = la2["legal_dong_codes"][:3]
    la2["legal_dong_codes"] = la2["legal_dong_codes"][3:]
    areas.append({"id": None, "name": "검단 북부", "legal_dong_codes": moved})
    r = client.put("/api/regions/1/living-areas", headers=WRITE, json={"living_areas": areas})
    assert r.status_code == 200, r.text
    body = r.json()
    validate("updateLivingAreas", 200, body)
    assert body["change_event"]["severity"] == "critical"
    assert body["change_event"]["entity"] == "region" and body["change_event"]["field"] == "living_areas"
    assert body["change_event"]["triggers_rejudge"] is True
    new = [a for a in body["region"]["living_areas"] if a["name"] == "검단 북부"]
    assert new and new[0]["id"] == "la_5"
    with get_session() as s:
        job = s.get(JobRun, body["job_id"])
        assert job is not None and job.job_name == "rejudge" and job.status == "queued"
        assert job.payload["snapshot_id"] == 12
        assert s.get(ChangeEvent, body["change_event"]["id"]) is not None
        region = s.scalars(select(Region).where(Region.id == 1)).one()
        assert any(a["name"] == "검단 북부" for a in region.living_areas)


def test_living_areas_missing_code_422(client: TestClient) -> None:
    areas = _areas(client)
    areas[0] = {**areas[0], "legal_dong_codes": areas[0]["legal_dong_codes"][:-1] or ["2818510600"]}
    areas[1] = {**areas[1], "legal_dong_codes": areas[1]["legal_dong_codes"][1:]}
    r = client.put("/api/regions/1/living-areas", headers=WRITE, json={"living_areas": areas})
    assert r.status_code == 422
    body = r.json()
    validate("updateLivingAreas", 422, body)
    assert body["code"] == "validation_error" and body["field_errors"]


def test_living_areas_duplicate_and_unknown_422(client: TestClient) -> None:
    areas = _areas(client)
    dup = copy.deepcopy(areas)
    dup[0]["legal_dong_codes"] = [*dup[0]["legal_dong_codes"], dup[1]["legal_dong_codes"][0]]
    r = client.put("/api/regions/1/living-areas", headers=WRITE, json={"living_areas": dup})
    assert r.status_code == 422
    unk = copy.deepcopy(areas)
    unk[0]["legal_dong_codes"] = [*unk[0]["legal_dong_codes"], "1111010100"]
    r = client.put("/api/regions/1/living-areas", headers=WRITE, json={"living_areas": unk})
    assert r.status_code == 422
    validate("updateLivingAreas", 422, r.json())
    # 스키마 위반(빈 목록)도 422
    r = client.put("/api/regions/1/living-areas", headers=WRITE, json={"living_areas": []})
    assert r.status_code == 422
    assert (
        client.put("/api/regions/999/living-areas", headers=WRITE, json={"living_areas": areas}).status_code
        == 404
    )

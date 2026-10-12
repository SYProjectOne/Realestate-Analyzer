"""R4-FIX 계약 .15 (DECISIONS D20-1) — API·수집기 쪽.

| 결정 | 테스트 |
| --- | --- |
| `POST /regions` 선택 필드 `applyhome_query`(from_ym·to_ym) | ``test_create_region_accepts_applyhome_query`` · ``test_create_region_rejects_bad_from_ym`` |
| 기본 조회 창 = 지난 24개월 + 향후 12개월(meta §1-4) · `to_ym` | ``test_default_window_is_past_24_future_12`` · ``test_query_window_overrides`` |
| judgment_log `model`·`provider` → 봉투(G7 판정 로그) | ``test_envelope_carries_model_and_provider`` |
| 계약 버전 .15 | (CORE8 계약 .16 에서 ``tests/api/test_core8_d21_8.py::test_contract_version_is_16`` 으로 옮김) |
"""

# ruff: noqa: E501

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from app.core.db import get_session
from app.models import Region

from ._support import WRITE, validate

SEL = [{"kind": "sigungu", "code": "28245", "full_name": "인천광역시 계양구"}]


def test_create_region_accepts_applyhome_query(client: TestClient) -> None:
    req = {
        "name": "창 지정",
        "query_text": "계양구",
        "selections": SEL,
        "applyhome_query": {"from_ym": "2024-10", "to_ym": "2027-06"},
    }
    r = client.post("/api/regions", headers=WRITE, json=req)
    assert r.status_code == 201, r.text
    body = r.json()
    validate("createRegion", 201, body)
    assert body["region"]["applyhome_query"] == {"from_ym": "2024-10", "to_ym": "2027-06"}
    with get_session() as s:
        row = s.get(Region, body["region"]["id"])
        assert row is not None and row.applyhome_query == {"from_ym": "2024-10", "to_ym": "2027-06"}


def test_create_region_rejects_bad_from_ym(client: TestClient) -> None:
    req = {"name": "x", "query_text": "x", "selections": SEL, "applyhome_query": {"from_ym": "2024-1"}}
    r = client.post("/api/regions", headers=WRITE, json=req)
    assert r.status_code == 422
    validate("createRegion", 422, r.json())


def _windows(query: dict[str, str], today: date) -> list[tuple[str, str]]:
    from app.collectors.applyhome import ApplyhomeCollector
    from app.core.contracts_gen import Region as RegionDTO

    c = ApplyhomeCollector(today=lambda: today, service_key=None)
    region = RegionDTO.model_validate(
        {
            "id": 1, "name": "t", "query_text": "t", "selections": SEL, "sido_codes": ["28"], "sigungu_codes": ["28245"],
            "legal_dong_codes": [], "living_areas": [], "age_premium_coef": {"c_per_year": 0.015, "cap_years": 8, "label": "추정"},
            "supply_ref_pct": 0.08, "applyhome_query": query, "status": "ready", "created_at": "2026-10-12T06:00:00+09:00",
        }
    )  # fmt: skip
    return c._windows(region)


def test_default_window_is_past_24_future_12() -> None:
    """R4 D18-8: 기본 −10개월이라 2025-06·07 공고(오퍼스 한강 스위첸·해링턴플레이스 풍무)가 빠졌다."""
    w = _windows({}, date(2026, 10, 12))
    assert w[0][0] == "202410" and w[-1][1] == "202710"


def test_query_window_overrides() -> None:
    w = _windows({"from_ym": "2025-06", "to_ym": "2027-03"}, date(2026, 10, 12))
    assert (w[0][0], w[-1][1]) == ("202506", "202703")


def test_envelope_carries_model_and_provider(client: TestClient) -> None:
    from app.judge.cache import envelope_from_row
    from app.models import JudgmentLog

    with get_session() as s:
        row = JudgmentLog(
            tool="extract", purpose="extract:t", input_hash="sha256:" + "f" * 64, input_len=1, input_json={},
            output_json={"model": "jev-latest", "provider": "none"}, status="ok", created_at="2026-10-12T06:00:00+09:00",
            adapter_version="0.2.0+jev-mcp@0.14.1+jev-1.13.0", model="jev-latest", provider="none",
        )  # fmt: skip
        s.add(row)
        s.flush()
        env = envelope_from_row(row, cached=False, result={})
    assert (env.model, env.provider) == ("jev-latest", "none")
    body = client.get("/api/ops/judgments", params={"tool": "extract"}, headers=WRITE).json()
    validate("getJudgmentOps", 200, body)
    item = next(i for i in body["items"] if i["input_hash"] == "sha256:" + "f" * 64)
    assert (item["model"], item["provider"]) == ("jev-latest", "none")

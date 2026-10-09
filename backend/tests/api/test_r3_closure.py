"""R3 마무리 — API: 가상 후보 '모집공고 대기'(계약 2026-10-09.5)와 내장 시나리오 policy.include_wait_new."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ._support import WRITE, assert_facts_labelled, validate


def test_compare_shows_wait_new_virtual_candidate(client: TestClient) -> None:
    """상황 A decide(devseed = 보고서 #126 wait_new .94) → C7 데이터에 가상 후보: complex_id null · 이름 키 · 요건 판정."""
    r = client.get("/api/snapshots/12/compare", params={"ids": "2,7", "scenario": "A"}, headers=WRITE)
    assert r.status_code == 200, r.text
    body = r.json()
    validate("getCompare", 200, body)
    assert_facts_labelled(body)
    items = body["decisions"]["A"]["items"]
    wait = [i for i in items if i["option_key"] == "wait_new"]
    assert len(wait) == 1, items
    w = wait[0]
    assert w["complex_id"] is None and w["label"] == "모집공고 대기"
    assert w["chosen"] is True and w["prob"]["v"] == 0.94 and w["prob"]["prov"].startswith("jl_")
    assert w["requirements"] is not None and set(w["requirements"]) == {"access", "regulation", "funds"}


def test_builtin_scenarios_policy_include_wait_new(client: TestClient) -> None:
    body = client.get("/api/scenarios", headers=WRITE).json()
    validate("listScenarios", 200, body)
    flags = {s["code"]: s["policy"].get("include_wait_new") for s in body if s["is_builtin"]}
    assert flags == {"base": False, "A": True, "B": False, "C": False, "D": False}

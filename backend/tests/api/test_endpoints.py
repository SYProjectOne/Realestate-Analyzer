"""엔드포인트별 정상 경로 — devseed DB 위에서 응답이 openapi.bundled.yaml 스키마(형식 포함)를 통과하고,
모든 Fact 에 라벨·출처가 있는지(AGENTS 규칙 5). 값은 회귀 픽스처(인천·김포)의 것."""

from __future__ import annotations

import csv
import io

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_session
from app.models import JobRun

from ._support import WRITE, assert_facts_labelled, validate


def test_dashboard_base_t1_order(client: TestClient) -> None:
    r = client.get("/api/snapshots/12/dashboard", headers=WRITE)
    assert r.status_code == 200, r.text
    body = r.json()
    validate("getDashboard", 200, body)
    assert assert_facts_labelled(body) > 20
    assert body["scenario_code"] == "base" and body["degraded"] is False
    top = [(row["complex_id"], row["total"]["v"], row["rank"]) for row in body["top5"]]
    # RA §9 T1: 그란테르 5.87 > 엘리프 5.70 > 한내들 5.33 > 스위첸 5.00 > 센트레빌 = 더샵 AB23 4.61
    assert top == [(1, 5.87, 1), (2, 5.7, 2), (3, 5.33, 3), (4, 5.0, 4), (5, 4.61, 5), (6, 4.61, 5)]
    for row in body["top5"]:
        contrib = sum(c["contribution"] or 0 for c in row["components"].values())
        assert abs(contrib - row["total"]["v"]) <= 0.01
    # D9-1(R3 C2): 픽스처 사실로 판정 대상 = 12 − 스위첸(classify review → 미해결) = 11.
    # 기대값 갱신(R3 마무리): 9 → 11 — 그란테르(W1 골든 v2 정렬)·마리나베이(CEO 결정)의 접수가 '불가'에서
    # '미정'(공고 이력 있음 + 추가 공급 미정, meta §1-3-4)이 되어 '참고' → '판정 대상'.
    # 기대값 갱신(R3b G2, D10-1): KPI = 점수 실행의 저장 judge_scope('판정 대상') 수 = 12 —
    # TOP 5 의 스위첸(4위)도 저장값은 '판정 대상'(현재 사실 classify review → 미해결은 '재판정 필요'로만).
    assert body["kpis"]["judged_count"]["v"] == 12


def test_dashboard_scenario_b_tie(client: TestClient) -> None:
    body = client.get("/api/snapshots/12/dashboard", params={"scenario": "B"}, headers=WRITE).json()
    validate("getDashboard", 200, body)
    assert body["scenario_code"] == "B"
    badges = {row["complex_id"]: row["decision"] for row in body["top5"] if row["decision"]}
    # RA §9 T2: 칸타빌 0.54 · 엘리프 0.42 · confidence 0.48 → 둘 다 tie·chosen
    if 2 in badges:
        assert badges[2]["tie"] and badges[2]["chosen"]


def test_dashboard_404_and_bad_scenario(client: TestClient) -> None:
    assert client.get("/api/snapshots/999/dashboard", headers=WRITE).status_code == 404
    r = client.get("/api/snapshots/12/dashboard", params={"scenario": "Z"}, headers=WRITE)
    assert r.status_code in (404, 422)
    r = client.get("/api/snapshots/12/dashboard", params={"scenario": "9999"}, headers=WRITE)
    assert r.status_code == 404


def test_complexes_page_filter_sort(client: TestClient) -> None:
    r = client.get("/api/snapshots/12/complexes", headers=WRITE)
    body = r.json()
    validate("listComplexes", 200, body)
    assert assert_facts_labelled(body) > 100
    assert body["total"] == 16 and body["page"] == 1 and body["size"] == 50
    assert [i["complex_id"] for i in body["items"][:2]] == [1, 2]
    switzen = next(i for i in body["items"] if i["complex_id"] == 4)
    assert switzen["intake"]["status"] == "확인 불가" and switzen["intake"]["http_status"] == 403
    assert switzen["total"]["v"] == 5.0

    r = client.get(
        "/api/snapshots/12/complexes",
        params={"filter[intake_status]": "가능", "sort": "name", "size": 2, "page": 1},
        headers=WRITE,
    )
    body = r.json()
    validate("listComplexes", 200, body)
    assert body["total"] == 3 and len(body["items"]) == 2
    assert all(i["intake"]["status"] == "가능" for i in body["items"])
    names = [i["name"] for i in body["items"]]
    assert names == sorted(names)

    body = client.get(
        "/api/snapshots/12/complexes",
        params={"filter[living_area]": "la_4,la_3", "sort": "-price_mid"},
        headers=WRITE,
    ).json()
    assert {i["living_area"] for i in body["items"]} <= {"la_3", "la_4"}
    body = client.get(
        "/api/snapshots/12/complexes",
        params={"filter[price_max]": 700000000, "filter[q]": "검단"},
        headers=WRITE,
    ).json()
    assert all("검단" in i["name"] for i in body["items"])
    r = client.get("/api/snapshots/12/complexes", params={"sort": "bogus"}, headers=WRITE)
    assert r.status_code == 422
    r = client.get("/api/snapshots/12/complexes", params={"filter[nope]": "1"}, headers=WRITE)
    assert r.status_code == 422


def test_complexes_csv(client: TestClient) -> None:
    r = client.get("/api/snapshots/12/complexes.csv", params={"filter[living_area]": "la_4"}, headers=WRITE)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.content.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows and all(row["living_area"] for row in rows)
    for col in ("price_low", "total"):
        assert f"{col}_label" in rows[0] and f"{col}_checked_at" in rows[0]
    assert all(row["price_low_label"] for row in rows)


def test_complex_detail_elif(client: TestClient) -> None:
    r = client.get("/api/complexes/2", headers=WRITE)
    assert r.status_code == 200, r.text
    body = r.json()
    validate("getComplex", 200, body)
    assert assert_facts_labelled(body) > 40
    assert body["header"]["name"] == "엘리프 검단 포레듀"
    assert body["header"]["living_area_name"] == "검단구"
    assert body["price"]["basis_type_code"] == "84A"
    assert body["price"]["price_low"]["v"] == 578140000
    assert body["intake_current"]["status"] == "가능"
    assert len(body["types"]) == 4 and sum(t["is_basis"] for t in body["types"]) == 1
    assert body["ladder"] and body["ladder"][0]["horizon"] == "move_in_plus_1y"
    assert body["judgments"] and all(j["tool"] for j in body["judgments"])
    assert body["score"]["complex_id"] == 2
    assert client.get("/api/complexes/999", headers=WRITE).status_code == 404


def test_complex_detail_pre_notice(client: TestClient) -> None:
    body = client.get("/api/complexes/15", params={"snapshot": 12}, headers=WRITE).json()
    validate("getComplex", 200, body)
    assert body["price"]["price_low"]["label"] == "확인 불가"
    assert body["gap"]["empty_reason"]


def test_provenance_kinds(client: TestClient) -> None:
    detail = client.get("/api/complexes/2", headers=WRITE).json()
    fp = detail["header"]["units_total"]["prov"]
    r = client.get(f"/api/provenance/{fp}", headers=WRITE)
    assert r.status_code == 200, r.text
    body = r.json()
    validate("getProvenance", 200, body)
    assert body["kind"] == "field" and body["entity"] == "complex" and body["entity_id"] == 2
    for prov in (
        detail["score"]["total"]["prov"],
        detail["score"]["components"]["gap"]["score"]["prov"],
        detail["header"]["inclusion_prob"]["prov"],
    ):
        r = client.get(f"/api/provenance/{prov}", headers=WRITE)
        assert r.status_code == 200, (prov, r.text)
        validate("getProvenance", 200, r.json())
    assert client.get("/api/provenance/fp_99999999", headers=WRITE).status_code == 404
    assert client.get("/api/provenance/rd_9059", headers=WRITE).json()["http_status"] == 403


def test_raw_document(client: TestClient) -> None:
    r = client.get("/api/raw/9001", headers=WRITE)
    assert r.status_code == 200
    r = client.get("/api/raw/9001", params={"as": "text"}, headers=WRITE)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert "주택유형" in r.text
    assert client.get("/api/raw/9059", headers=WRITE).status_code == 404  # 실패 행(path=null)
    assert client.get("/api/raw/999999", headers=WRITE).status_code == 404  # 없는 id


def test_compare(client: TestClient) -> None:
    r = client.get("/api/snapshots/12/compare", params={"ids": "2,7,4", "scenario": "B"}, headers=WRITE)
    assert r.status_code == 200, r.text
    body = r.json()
    validate("getCompare", 200, body)
    assert_facts_labelled(body)
    assert body["ids"] == [2, 7, 4] and [row["complex_id"] for row in body["rows"]] == [2, 7, 4]
    assert set(body["ladders"]) == {"2", "7", "4"} and set(body["gaps"]) == {"2", "7", "4"}
    dec = body["decisions"]["B"]
    assert dec["tie"] is True and dec["confidence"]["v"] == 0.48
    tied = {i["complex_id"] for i in dec["items"] if i["tie"]}
    assert tied == {7, 2}
    for bad in ("2", "1,2,3,4,5,6,7", "a,b"):
        r = client.get("/api/snapshots/12/compare", params={"ids": bad}, headers=WRITE)
        assert r.status_code == 422, bad


def test_sensitivity(client: TestClient) -> None:
    r = client.get("/api/snapshots/12/sensitivity", headers=WRITE)
    assert r.status_code == 200, r.text
    body = r.json()
    validate("getSensitivity", 200, body)
    assert len(body["cells"]) == 12 and body["unstable"] is True
    assert set(body["base_top5"]) == {1, 2, 3, 4, 5, 6}
    assert body["complex_names"]["1"] == "더샵 송도그란테르"
    assert all(rk["name"] for c in body["cells"] for rk in c["ranks"])


def test_scenarios_list_create_preview(client: TestClient) -> None:
    body = client.get("/api/scenarios", headers=WRITE).json()
    validate("listScenarios", 200, body)
    assert [s["code"] for s in body[:5]] == ["base", "A", "B", "C", "D"]
    req = {
        "name": "내 조건",
        "params": {"equity_won": 250000000, "loan_limit_won": 600000000, "holding_years": 4},
        "weights": {"p10": 0.3, "rerank": 0.15, "gap": 0.2, "benchmark": 0.1, "supply": 0.1, "move_in": 0.15},
        "requirements": None,
        "policy": None,
    }
    r = client.post("/api/scenarios", headers=WRITE, json=req)
    assert r.status_code == 201, r.text
    created = r.json()
    validate("createScenario", 201, created)
    assert created["is_builtin"] is False and created["code"] is None
    bad = {**req, "weights": {**req["weights"], "p10": 0.5}}
    r = client.post("/api/scenarios", headers=WRITE, json=bad)
    assert r.status_code == 422
    both = {**req, "weights": {**req["weights"], "liquidity": 0.0}}
    assert client.post("/api/scenarios", headers=WRITE, json=both).status_code == 422

    b = next(s for s in body if s["code"] == "B")
    r = client.get(f"/api/scenarios/{b['id']}/preview", params={"snapshot": 12}, headers=WRITE)
    assert r.status_code == 200, r.text
    prev = r.json()
    validate("previewScenario", 200, prev)
    assert prev["requirements_pre"] and prev["cache_hits"] + prev["cache_misses"] >= 1
    assert (
        client.get(f"/api/scenarios/{b['id']}/preview", params={"snapshot": 999}, headers=WRITE).status_code
        == 404
    )
    assert (
        client.get("/api/scenarios/9999/preview", params={"snapshot": 12}, headers=WRITE).status_code == 404
    )


def test_jobs(client: TestClient) -> None:
    req = {
        "job_name": "rejudge",
        "payload": {"snapshot_id": 12, "scenario_id": 3, "complex_ids": None, "reason": "G5"},
    }
    r = client.post("/api/jobs", headers=WRITE, json=req)
    assert r.status_code == 202, r.text
    job = r.json()
    validate("createJob", 202, job)
    assert job["kind"] == "rejudge" and job["status"] == "queued"
    got = client.get(f"/api/jobs/{job['id']}", headers=WRITE).json()
    validate("getJob", 200, got)
    lst = client.get("/api/jobs", params={"status": "queued"}, headers=WRITE).json()
    validate("listJobs", 200, lst)
    assert lst[0]["id"] == job["id"]
    bad = {"job_name": "rejudge", "payload": {"snapshot_id": 12}}
    assert client.post("/api/jobs", headers=WRITE, json=bad).status_code == 422
    assert client.get("/api/jobs/99999", headers=WRITE).status_code == 404


def test_market(client: TestClient) -> None:
    r = client.get("/api/snapshots/12/market", headers=WRITE)
    assert r.status_code == 200, r.text
    body = r.json()
    validate("getMarket", 200, body)
    assert_facts_labelled(body)
    assert {a["id"] for a in body["living_areas"]} == {"la_1", "la_2", "la_3", "la_4"}
    assert body["unsold"] and body["benchmarks"] and body["supply"] and body["move_in_markers"]
    assert {p["living_area"] for p in body["living_area_prices"]} >= {"la_1", "la_2", "la_4"}
    assert body["regulation"]["items"] and body["catalysts"]
    one = client.get("/api/snapshots/12/market", params={"living_area": "la_4"}, headers=WRITE).json()
    validate("getMarket", 200, one)
    assert all(b["living_area"] == "la_4" for b in one["benchmarks"])


def test_changes(client: TestClient) -> None:
    body = client.get("/api/snapshots/12/changes", headers=WRITE).json()
    validate("listChanges", 200, body)
    both = client.get("/api/snapshots/12/changes", params={"compare_snapshot": 11}, headers=WRITE).json()
    validate("listChanges", 200, both)
    since = client.get("/api/snapshots/12/changes", params={"since": "2000-01-01"}, headers=WRITE).json()
    validate("listChanges", 200, since)
    assert len(since) >= len(body)


def test_ops(client: TestClient) -> None:
    src = client.get("/api/ops/sources", headers=WRITE).json()
    validate("listSourceStatus", 200, src)
    site = next(s for s in src if s["source_kind"] == "official_site")
    assert any(t["http_status"] == 403 for t in site["failing_targets"])
    news = next(s for s in src if s["source_kind"] == "news")
    assert news["enabled"] is False  # NEWS_API_KEY 없음
    j = client.get("/api/ops/judgments", params={"since": "2026-01-01", "size": 10}, headers=WRITE).json()
    validate("getJudgmentOps", 200, j)
    assert j["total"] == 132 and len(j["items"]) == 10
    assert j["stats"]["total_calls"] == 132
    ck = client.get("/api/ops/checklist", headers=WRITE).json()
    validate("listChecklist", 200, ck)
    assert ck
    r = client.patch(
        f"/api/ops/checklist/{ck[0]['id']}", headers=WRITE, json={"status": "done", "note": "확인"}
    )
    assert r.status_code == 202, r.text  # 계약 .14(D17-5): 보고서 본문이 바뀌므로 발행 잡
    validate("updateChecklistItem", 202, r.json())
    assert r.json()["status"] == "done" and isinstance(r.json()["job_id"], int)
    assert client.patch("/api/ops/checklist/99999", headers=WRITE, json={"status": "done"}).status_code == 404
    assert client.patch(f"/api/ops/checklist/{ck[0]['id']}", headers=WRITE, json={}).status_code == 422


def test_reports(client: TestClient) -> None:
    r = client.post(
        "/api/reports", headers=WRITE, json={"snapshot_id": 12, "format": "pdf", "compare_snapshot_id": 11}
    )
    assert r.status_code == 202, r.text
    job = r.json()
    validate("createReport", 202, job)
    assert job["job_name"] == "report"
    lst = client.get("/api/reports", headers=WRITE).json()
    validate("listReports", 200, lst)
    assert lst[0]["id"] == job["id"] and lst[0]["status"] == "queued"
    r = client.get(f"/api/reports/{job['id']}", headers=WRITE)
    assert r.status_code == 409 and r.json()["code"] == "conflict"
    assert (
        client.post("/api/reports", headers=WRITE, json={"snapshot_id": 999, "format": "html"}).status_code
        == 404
    )
    assert (
        client.post("/api/reports", headers=WRITE, json={"snapshot_id": 12, "format": "md"}).status_code
        == 422
    )
    assert client.get("/api/reports/99999", headers=WRITE).status_code == 404


def test_report_download_done(client: TestClient, api_settings: object) -> None:
    from app.core.settings import get_settings

    s = get_settings()
    s.report_dir.mkdir(parents=True, exist_ok=True)
    f = s.report_dir / "r.html"
    f.write_text("<html><body>보고서</body></html>", encoding="utf-8")
    job = client.post("/api/reports", headers=WRITE, json={"snapshot_id": 12, "format": "html"}).json()
    with get_session() as session:
        row = session.scalars(select(JobRun).where(JobRun.id == job["id"])).one()
        row.status = "done"
        row.finished_at = "2026-10-08T08:01:12+09:00"
        row.stats = {
            "path": "r.html",
            "filename": "r.html",
            "size_bytes": f.stat().st_size,
            "sha256": "0" * 64,
            "content_type": "text/html",
        }
    r = client.get(f"/api/reports/{job['id']}", headers=WRITE)
    assert r.status_code == 200 and "보고서" in r.text
    lst = client.get("/api/reports", params={"snapshot_id": 12}, headers=WRITE).json()
    validate("listReports", 200, lst)


def test_report_blocked_by_contradicted_claim(client: TestClient) -> None:
    from app.models import Claim

    with get_session() as session:
        session.add(Claim(snapshot_id=12, section="8", text="x", verify_status="contradicted"))
    r = client.post("/api/reports", headers=WRITE, json={"snapshot_id": 12, "format": "html"})
    assert r.status_code == 409
    assert r.json()["code"] == "publish_blocked"
    validate("createReport", 409, r.json())

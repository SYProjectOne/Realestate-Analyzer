"""R3 수정 F3 — API (계약 2026-10-09.4).

리뷰 항목: M8(주장 목록·문장 수정), M6(호재 URL 입력), M9(공유 링크 30일), M11(토큰 없는 서버는 루프백만),
M4(부분합 금지), minor 15(entered_by 역할), 18(CSV 수식 인젝션·prov 열), 19(/docs 인증), 22(출처 링크),
23(cached_hits 집계), 38(facts 예외 dev 만).
"""

from __future__ import annotations

import csv
import io
import logging
import shutil
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.db import get_session, reset_engine
from app.core.settings import Settings, set_settings
from app.models import (
    Catalyst,
    Claim,
    Complex,
    FieldProvenance,
    JobRun,
    ShareLink,
    Supply,
    Unsold,
)

from ._support import READ, WRITE, as_live, validate

SNAP = 12


# ====================================================================== M8 주장


def _claim(**kw: Any) -> int:
    row = {
        "snapshot_id": SNAP,
        "section": "complex:2",
        "complex_id": 2,
        "text": "엘리프 검단 포레듀 기준 타입 최고 공급금액은 999원이다",
        "evidence_text": "fp_1: 최고 공급금액 578,000,000원",
        "verify_status": "contradicted",
        "judgment_seq": None,
        "parent_claim_id": None,
        "ordinal": 0,
    }
    row.update(kw)
    with get_session() as s:
        c = Claim(**row)
        s.add(c)
        s.flush()
        return int(c.id)


def test_m8_list_contradicted_claims(client: TestClient) -> None:
    bad = _claim()
    ok = _claim(text="엘리프 검단 포레듀 입주 예정 시기는 2028-06이다", verify_status="verified")
    split_parent = _claim(text="복합 주장이다")
    _claim(text="고친 주장이다", verify_status="verified", parent_claim_id=split_parent)
    r = client.get(f"/api/snapshots/{SNAP}/claims", params={"status": "contradicted"}, headers=READ)
    assert r.status_code == 200, r.text
    body = r.json()
    validate("listClaims", 200, body)
    by_id = {c["id"]: c for c in body}
    assert {bad, split_parent} <= set(by_id) and ok not in by_id
    assert all(c["verify_status"] == "contradicted" for c in body)
    assert by_id[bad]["remaining"] is True and by_id[bad]["child_count"] == 0
    assert by_id[bad]["complex_name"] == "엘리프 검단 포레듀"
    assert by_id[split_parent]["remaining"] is False and by_id[split_parent]["child_count"] == 1
    every = client.get(f"/api/snapshots/{SNAP}/claims", headers=WRITE).json()
    assert ok in {c["id"] for c in every}
    assert client.get("/api/snapshots/999999/claims", headers=WRITE).status_code == 404
    bad_q = client.get(f"/api/snapshots/{SNAP}/claims", params={"status": "nope"}, headers=WRITE)
    assert bad_q.status_code == 422


def test_m8_revise_claim_enqueues_reverify_job(client: TestClient) -> None:
    cid = _claim()
    text = "엘리프 검단 포레듀 기준 타입 최고 공급금액은 578,000,000원이다"
    r = client.patch(f"/api/claims/{cid}", json={"text": text}, headers=WRITE)
    assert r.status_code == 202, r.text
    job = r.json()
    validate("reviseClaim", 202, job)
    assert job["job_name"] == "claim.reverify" and job["status"] == "queued"
    assert job["payload"] == {"snapshot_id": SNAP, "claim_id": cid, "text": text}
    # 원 주장 행은 그대로(자식은 worker 가 verify 후 만든다)
    with get_session() as s:
        row = s.get(Claim, cid)
        assert row is not None and row.text != text and row.verify_status == "contradicted"
    # 대기 중이면 다시 못 고친다
    again = client.patch(f"/api/claims/{cid}", json={"text": text + "."}, headers=WRITE)
    assert again.status_code == 409 and again.json()["code"] == "conflict"
    validate("reviseClaim", 409, again.json())
    listed = client.get(f"/api/snapshots/{SNAP}/claims", headers=WRITE).json()
    assert next(c for c in listed if c["id"] == cid)["pending_job_id"] == job["id"]


def test_m8_split_claim_no_longer_blocks_report(client: TestClient) -> None:
    """남은 contradicted = 분할 자식 없는 것 — 문장 수정·재검증(자식 행) 뒤에는 보고서·스냅샷 수가 풀린다."""
    req = {"snapshot_id": SNAP, "format": "html"}

    def blocked_count() -> int:
        snaps = client.get("/api/regions/1/snapshots", headers=WRITE).json()
        return int(next(s for s in snaps if s["id"] == SNAP)["contradicted_claims"] or 0)

    base = blocked_count()
    cid = _claim()
    assert blocked_count() == base + 1
    r = client.post("/api/reports", json=req, headers=WRITE)
    assert r.status_code == 409 and r.json()["code"] == "publish_blocked"
    _claim(text="고친 원자 주장", verify_status="verified", parent_claim_id=cid)
    assert blocked_count() == base
    if base == 0:
        assert client.post("/api/reports", json=req, headers=WRITE).status_code == 202


def test_m8_revise_claim_rejects(client: TestClient) -> None:
    verified = _claim(verify_status="verified")
    r = client.patch(f"/api/claims/{verified}", json={"text": "x"}, headers=WRITE)
    assert r.status_code == 409
    parent = _claim()
    _claim(text="자식", verify_status="verified", parent_claim_id=parent)
    assert client.patch(f"/api/claims/{parent}", json={"text": "x"}, headers=WRITE).status_code == 409
    cid = _claim()
    assert client.patch(f"/api/claims/{cid}", json={"text": ""}, headers=WRITE).status_code == 422
    assert client.patch(f"/api/claims/{cid}", json={"text": "x", "y": 1}, headers=WRITE).status_code == 422
    # 개인정보가 섞인 문장은 판정기로 가지 않는다(guard) → 422
    pii = client.patch(f"/api/claims/{cid}", json={"text": "문의 010-1234-5678 로 확인됨"}, headers=WRITE)
    assert pii.status_code == 422, pii.text
    assert client.patch("/api/claims/999999", json={"text": "x"}, headers=WRITE).status_code == 404
    ro = client.patch(f"/api/claims/{cid}", json={"text": "x"}, headers=READ)
    assert ro.status_code == 403


# ====================================================================== M6 호재 URL


def _fake_candidate(
    session: Any, region_id: int, *, url: str, title: str, excerpt: str | None = None
) -> Catalyst:
    """F1a ``catalyst_candidate`` 대역(같은 URL 이면 그 행)."""
    have = session.scalars(
        select(Catalyst).where(Catalyst.region_id == region_id, Catalyst.source_url == url)
    ).first()
    if have is not None:
        return have  # type: ignore[no-any-return]
    row = Catalyst(
        region_id=region_id,
        name=title,
        kind="기타",
        stage="미확정",
        location_confirmed=False,
        source_url=url,
        note=excerpt,
    )
    session.add(row)
    session.flush()
    return row


@pytest.fixture
def fake_catalyst(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[dict[str, Any]]]:
    from app.api.routers import catalysts

    calls: list[dict[str, Any]] = []

    def factory() -> Any:
        def fn(session: Any, region_id: int, **kw: Any) -> Catalyst:
            calls.append({"region_id": region_id, **kw})
            return _fake_candidate(session, region_id, **kw)

        return fn

    monkeypatch.setattr(catalysts, "candidate_factory", factory)
    yield calls


def test_m6_post_catalyst_creates_candidate_and_classify_job(
    client: TestClient, fake_catalyst: list[dict[str, Any]]
) -> None:
    body = {
        "region_id": 1,
        "url": "https://news.example.org/a/1",
        "title": "역 신설 기본계획 승인",
        "excerpt": "국토부가 기본계획을 승인했다.",
    }
    r = client.post("/api/catalysts", json=body, headers=WRITE)
    assert r.status_code == 201, r.text
    out = r.json()
    validate("createCatalyst", 201, out)
    assert fake_catalyst[0]["url"] == body["url"] and fake_catalyst[0]["title"] == body["title"]
    cat = out["catalyst"]
    assert cat["stage"] == "미확정" and cat["location_confirmed"] is False
    assert cat["source_url"] == body["url"]
    assert cat["stage_prob"]["label"] == "확인 불가"
    job = out["job"]
    assert job is not None and job["job_name"] == "rejudge"
    assert job["payload"]["snapshot_id"] == SNAP and job["payload"]["complex_ids"] == []
    # 같은 URL 다시 → 같은 행(새 후보 없음)
    again = client.post("/api/catalysts", json=body, headers=WRITE)
    assert again.status_code == 201
    assert again.json()["catalyst"]["id"] == cat["id"]


@pytest.mark.parametrize(
    "patch",
    [
        {"url": "javascript:alert(1)"},
        {"url": "ftp://x.example/y"},
        {"title": ""},
        {"excerpt": "담당자 010-1234-5678"},
        {"title": "문의 a@b.co"},
        {"extra": 1},
    ],
)
def test_m6_post_catalyst_rejects(
    client: TestClient, fake_catalyst: list[dict[str, Any]], patch: dict[str, Any]
) -> None:
    body = {"region_id": 1, "url": "https://news.example.org/a/1", "title": "t", "excerpt": None, **patch}
    r = client.post("/api/catalysts", json=body, headers=WRITE)
    assert r.status_code == 422, r.text
    assert fake_catalyst == []


def test_m6_post_catalyst_auth_and_region(client: TestClient, fake_catalyst: list[dict[str, Any]]) -> None:
    body = {"region_id": 1, "url": "https://news.example.org/a/1", "title": "t"}
    assert client.post("/api/catalysts", json=body, headers=READ).status_code == 403
    missing = client.post("/api/catalysts", json={**body, "region_id": 999}, headers=WRITE)
    assert missing.status_code == 404


def test_m6_candidate_function_missing_is_reported(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F1a 의 normalize.catalyst 가 아직 없으면 지연 import 가 실패를 계약 오류(500 internal)로 알린다."""
    from app.api.routers import catalysts

    def missing() -> Any:
        raise catalysts.CandidateUnavailable("app.normalize.catalyst.catalyst_from_url 없음")

    monkeypatch.setattr(catalysts, "candidate_factory", missing)
    body = {"region_id": 1, "url": "https://news.example.org/a/2", "title": "t"}
    r = client.post("/api/catalysts", json=body, headers=WRITE)
    assert r.status_code == 500 and r.json()["code"] == "internal"
    assert "normalize.catalyst" in r.json()["detail"]


def test_m6_uses_f1a_catalyst_candidate(client: TestClient) -> None:
    """대역 없이 F1a ``app.normalize.catalyst.catalyst_candidate`` 로(머지 후 실제 경로)."""
    from app.api.routers import catalysts

    assert catalysts.CANDIDATE_FUNCTION == "catalyst_candidate"
    body = {"region_id": 1, "url": "https://news.example.org/real/1", "title": "광역철도 기본계획 고시"}
    r = client.post("/api/catalysts", json=body, headers=WRITE)
    assert r.status_code == 201, r.text
    validate("createCatalyst", 201, r.json())
    cat = r.json()["catalyst"]
    assert cat["source_url"] == body["url"] and cat["stage"] == "미확정"
    assert cat["location_confirmed"] is False
    again = client.post("/api/catalysts", json=body, headers=WRITE)
    assert again.json()["catalyst"]["id"] == cat["id"]


def test_m6_candidate_input_error_is_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.routers import catalysts
    from app.normalize.catalyst import CatalystInputError

    def bad(*_a: Any, **_k: Any) -> Any:
        raise CatalystInputError("제목이 비어 있다")

    monkeypatch.setattr(catalysts, "candidate_factory", lambda: bad)
    body = {"region_id": 1, "url": "https://news.example.org/x", "title": "t"}
    r = client.post("/api/catalysts", json=body, headers=WRITE)
    assert r.status_code == 422 and "제목" in r.json()["detail"]


# ====================================================================== M9 공유 링크


def test_m9_share_link_lifecycle(client: TestClient, api_settings: Settings) -> None:
    r = client.post("/api/share-links", json={"label": "가족 공유"}, headers=WRITE)
    assert r.status_code == 201, r.text
    created = r.json()
    validate("createShareLink", 201, created)
    token, link = created["token"], created["link"]
    assert link["status"] == "active" and len(token) >= 32
    made = datetime.fromisoformat(link["created_at"])
    ttl = timedelta(days=api_settings.share_token_ttl_days)
    assert datetime.fromisoformat(link["expires_at"]) - made == ttl
    with get_session() as s:
        row = s.scalars(select(ShareLink)).one()
        assert token not in (row.token_sha256, row.label) and len(row.token_sha256) == 64
    share = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/regions", headers=share).status_code == 200
    w = client.post("/api/jobs", json={"job_name": "reference.refresh", "payload": {}}, headers=share)
    assert w.status_code == 403
    assert client.get("/api/share-links", headers=share).status_code == 403
    assert client.get("/api/share-links", headers=READ).status_code == 403
    lst = client.get("/api/share-links", headers=WRITE)
    assert lst.status_code == 200
    validate("listShareLinks", 200, lst.json())
    assert "token" not in lst.json()[0]
    rv = client.delete(f"/api/share-links/{link['id']}", headers=WRITE)
    assert rv.status_code == 200
    validate("revokeShareLink", 200, rv.json())
    assert rv.json()["status"] == "revoked"
    assert client.get("/api/regions", headers=share).status_code == 401
    assert client.delete("/api/share-links/999", headers=WRITE).status_code == 404


def test_m9_expired_share_link_is_401(client: TestClient) -> None:
    token = client.post("/api/share-links", json={}, headers=WRITE).json()["token"]
    with get_session() as s:
        row = s.scalars(select(ShareLink)).one()
        row.expires_at = (datetime.now().astimezone() - timedelta(seconds=1)).isoformat(timespec="seconds")
    r = client.get("/api/regions", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401 and "만료" in r.json()["detail"]
    assert client.get("/api/share-links", headers=WRITE).json()[0]["status"] == "expired"


def test_m9_ttl_follows_setting(api_settings: Settings) -> None:
    from app.main import create_app

    s = api_settings.model_copy(update={"share_token_ttl_days": 7})
    set_settings(s)
    with TestClient(create_app(s), raise_server_exceptions=False) as c:
        link = c.post("/api/share-links", json={}, headers=WRITE).json()["link"]
    span = datetime.fromisoformat(link["expires_at"]) - datetime.fromisoformat(link["created_at"])
    assert span == timedelta(days=7)


def test_m9_readonly_cannot_issue(client: TestClient) -> None:
    assert client.post("/api/share-links", json={}, headers=READ).status_code == 403
    assert client.delete("/api/share-links/1", headers=READ).status_code == 403
    assert client.post("/api/share-links", json={"label": "x" * 65}, headers=WRITE).status_code == 422


# ====================================================================== M11 토큰 없는 서버


@pytest.fixture
def open_settings(api_settings: Settings) -> Iterator[Settings]:
    s = api_settings.model_copy(update={"api_token": None, "readonly_token": None})
    set_settings(s)
    yield s
    set_settings(api_settings)
    reset_engine()


def test_m11_tokenless_server_accepts_loopback_only(open_settings: Settings) -> None:
    from app.main import create_app

    app = create_app(open_settings)
    with TestClient(app, client=("127.0.0.1", 50000), raise_server_exceptions=False) as local:
        assert local.get("/api/regions").status_code == 200
    with TestClient(app, client=("203.0.113.9", 50000), raise_server_exceptions=False) as remote:
        r = remote.get("/api/regions")
        assert r.status_code == 401, r.text
        assert "루프백" in r.json()["detail"]
    with TestClient(app, client=("::1", 50000), raise_server_exceptions=False) as local6:
        assert local6.get("/api/regions").status_code == 200


# ====================================================================== minor 15 entered_by


@pytest.mark.parametrize("who", ["홍길동", "운영자 홍길동", "operator"])
def test_minor15_entered_by_must_be_role(client: TestClient, who: str) -> None:
    body = {
        "complex_id": 4, "field": "intake_status", "value_text": "가능", "kind": "phone",
        "checked_at": "2026-10-09T10:20:00+09:00", "entered_by": who,
    }  # fmt: skip
    r = client.post("/api/ops/human-checks", json=body, headers=WRITE)
    assert r.status_code == 422, r.text
    ok = client.post("/api/ops/human-checks", json={**body, "entered_by": "검토자"}, headers=WRITE)
    assert ok.status_code == 201, ok.text


# ====================================================================== minor 18 CSV


def _csv(client: TestClient) -> list[dict[str, str]]:
    r = client.get(f"/api/snapshots/{SNAP}/complexes.csv", headers=WRITE)
    assert r.status_code == 200, r.text
    return list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))


@pytest.mark.parametrize("evil", ['=HYPERLINK("http://x")', "+1+1", "-2+3", "@SUM(A1)", "\tx", "\rx"])
def test_minor18_csv_formula_injection_is_neutralised(client: TestClient, evil: str) -> None:
    as_live()  # D13-1: 실시간 계산 경로(발행 전 리비전)를 본다
    with get_session() as s:
        cx = s.get(Complex, 2)
        assert cx is not None
        cx.name = evil
    rows = _csv(client)
    row = next(r for r in rows if r["complex_id"] == "2")
    assert row["name"] == "'" + evil
    for r in rows:
        for k, v in r.items():
            if k == "name" or not v:
                continue
            assert v[0] not in "=+@\t\r" or k.endswith("_won"), (k, v)


def test_minor18_csv_has_prov_and_rank_label_columns(client: TestClient) -> None:
    rows = _csv(client)
    head = set(rows[0])
    for col in ("price_low", "total", "p10", "gap_pct"):
        assert {f"{col}_label", f"{col}_checked_at", f"{col}_prov"} <= head, col
    assert {"rank", "rank_label", "rank_prov"} <= head
    ranked = [r for r in rows if r["rank"]]
    assert ranked and all(r["rank_label"] and r["rank_prov"].startswith("st_") for r in ranked)
    priced = [r for r in rows if r["price_low"]]
    assert priced and all(r["price_low_prov"].startswith("fp_") for r in priced)


# ====================================================================== minor 19 /docs


def test_minor19_docs_need_auth(client: TestClient) -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 401, path
        assert client.get(path, headers=READ).status_code == 200, path


def test_minor19_docs_off_in_prod(api_settings: Settings) -> None:
    from app.main import create_app

    s = api_settings.model_copy(update={"env": "prod", "judge_adapter": "jev"})
    with TestClient(create_app(s), raise_server_exceptions=False) as c:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert c.get(path, headers=WRITE).status_code == 404, path


# ====================================================================== M4 부분합


def test_m4_unsold_partial_sum_is_unknown(client: TestClient) -> None:
    as_live()  # D13-1: 실시간 계산 경로(발행 전 리비전)를 본다
    with get_session() as s:
        latest = s.scalars(select(Unsold.ym).order_by(Unsold.ym.desc())).first()
        group = list(s.scalars(select(Unsold).where(Unsold.ym == latest)))
        assert len(group) >= 2, "최근 월에 미분양 scope 가 2개 이상이어야 부분합을 검사할 수 있다"
        s.execute(
            delete(FieldProvenance).where(
                FieldProvenance.entity == "unsold",
                FieldProvenance.entity_id == group[0].id,
                FieldProvenance.field == "total",
            )
        )
        group[0].total = None
    body = client.get(f"/api/snapshots/{SNAP}/dashboard", headers=WRITE).json()
    point = next(p for p in body["unsold_series"] if p["ym"] == latest)
    assert point["total"]["label"] == "확인 불가"
    assert point["total"]["reason"] == "일부 누락 1건"
    kpi = body["kpis"]["unsold"]
    assert kpi["ym"] != latest or kpi["total"]["label"] == "확인 불가"


def test_m4_supply_partial_sum_is_unknown(api_settings: Settings) -> None:
    """supply.units 는 NOT NULL — 누락은 출처 행 없음(prod: '확인 불가(출처 누락)')으로만 생긴다."""
    from app.main import create_app

    as_live()  # D13-1: 실시간 계산 경로(발행 전 리비전)를 본다
    with get_session() as s:
        rows = list(s.scalars(select(Supply)))
        by_key: dict[tuple[str | None, int], list[Supply]] = {}
        for r in rows:
            by_key.setdefault((r.living_area, r.year), []).append(r)
        key, group = next((k, g) for k, g in by_key.items() if len(g) >= 2)
        s.execute(
            delete(FieldProvenance).where(
                FieldProvenance.entity == "supply", FieldProvenance.entity_id == group[0].id
            )
        )
    prod = api_settings.model_copy(update={"env": "prod", "judge_adapter": "jev"})
    set_settings(prod)
    with TestClient(create_app(prod), raise_server_exceptions=False) as c:
        market = c.get(f"/api/snapshots/{SNAP}/market", headers=WRITE).json()
        view = next(v for v in market["supply"] if (v["living_area"], v["year"]) == key)
        assert view["units"]["label"] == "확인 불가" and view["units"]["reason"] == "일부 누락 1건"
        dash = c.get(f"/api/snapshots/{SNAP}/dashboard", headers=WRITE).json()
        peak = dash["kpis"]["move_in_peak"]
        assert peak["units"]["label"] == "확인 불가" and "일부 누락" in peak["units"]["reason"]
        assert peak["year"]["label"] == "확인 불가"


# ====================================================================== minor 22 출처 링크


def test_minor22_kpi_count_prov_is_the_score_run(client: TestClient) -> None:
    body = client.get(f"/api/snapshots/{SNAP}/dashboard", headers=WRITE).json()
    kpi = body["kpis"]["judged_count"]
    assert kpi["prov"] == f"st_{body['score_run_id']}", kpi
    p = client.get(f"/api/provenance/{kpi['prov']}", headers=WRITE)
    assert p.status_code == 200, p.text
    validate("getProvenance", 200, p.json())
    assert p.json()["entity"] == "score_run"


def test_minor22_comparables_are_not_gap_labelled(client: TestClient) -> None:
    detail = client.get("/api/complexes/2", headers=WRITE).json()
    comps = detail["gap"]["comps"]
    assert comps
    for c in comps:
        for k in ("low", "median", "high"):
            f = c[k]
            if f["label"] != "확인 불가":
                assert f["label"] in ("재가공", "추정") and f["prov"].startswith("cs_"), f
                assert f["label"] == ("추정" if c["substitute"] else "재가공")


def test_minor22_catalyst_expected_ym_prov_is_field_provenance(client: TestClient) -> None:
    as_live()  # D13-1: 실시간 계산 경로(발행 전 리비전)를 본다
    with get_session() as s:
        cat = s.scalars(select(Catalyst).order_by(Catalyst.id)).first()
        assert cat is not None
        cat.expected_ym = "2027-12"
        fp = FieldProvenance(
            entity="catalyst", entity_id=cat.id, field="expected_ym", value_text="2027-12",
            value_norm="2027-12", label="비공식", source_rank=3, url="https://news.example.org/x",
            checked_at="2026-10-07", chosen=True,
        )  # fmt: skip
        s.add(fp)
        s.flush()
        cid, fid = cat.id, fp.id
    market = client.get(f"/api/snapshots/{SNAP}/market", headers=WRITE).json()
    view = next(c for c in market["catalysts"] if c["id"] == cid)
    assert view["expected_ym"]["prov"] == f"fp_{fid}" and view["expected_ym"]["label"] == "비공식"


def test_minor22_market_price_checked_at_is_trade_date(client: TestClient) -> None:
    market = client.get(f"/api/snapshots/{SNAP}/market", headers=WRITE).json()
    for p in market["living_area_prices"]:
        prov = p["median_won"]["prov"]
        fp = client.get(f"/api/provenance/{prov}", headers=WRITE).json()
        assert p["median_won"]["checked_at"] == (fp["checked_at"] or "")[:10]


# ====================================================================== minor 23 cached_hits


def test_minor23_cached_hits_come_from_job_stats(client: TestClient) -> None:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    with get_session() as s:
        for cached in (7, 5):
            s.add(
                JobRun(
                    job_name="rejudge", kind="rejudge", payload={}, scheduled_at=now, started_at=now,
                    finished_at=now, status="done", stats={"cached": cached, "judge_calls": 1},
                )
            )  # fmt: skip
    body = client.get("/api/ops/judgments", headers=WRITE).json()
    validate("getJudgmentOps", 200, body)
    stats = body["stats"]
    assert stats["cached_hits"] == 12
    assert stats["total_calls"] == stats["real_calls"] + 12


# ====================================================================== minor 38 facts


def test_minor38_fact_without_prov_raises_only_in_dev(
    api_settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    from app.api.errors import ContractViolation
    from app.api.facts import fact

    with pytest.raises(ContractViolation):
        fact(1, "확인됨", None, "2026-10-09")
    set_settings(api_settings.model_copy(update={"env": "prod", "judge_adapter": "jev"}))
    with caplog.at_level(logging.WARNING):
        out = fact(1, "확인됨", None, "2026-10-09")
    assert out["label"] == "확인 불가" and out["reason"] == "출처 누락" and out["v"] is None
    assert any("출처 누락" in r.getMessage() for r in caplog.records)


# ====================================================================== minor 34 월별 압축 원문


def test_minor34_raw_reads_from_monthly_archive(api_settings: Settings, tmp_path: Path) -> None:
    """runbook §6 월별 압축(`infra/raw_archive.sh`: RAW_DIR 기준 상대 경로) 뒤에도 /raw/{id} 가 읽힌다."""
    import tarfile

    from app.main import create_app
    from app.models import RawDocument

    with get_session() as s:
        doc = s.scalars(
            select(RawDocument).where(RawDocument.path.is_not(None)).order_by(RawDocument.id)
        ).first()
        assert doc is not None and doc.path
        rid, rel = doc.id, doc.path
    copy = tmp_path / "raw_copy"
    shutil.copytree(api_settings.raw_dir, copy)
    s2 = api_settings.model_copy(update={"raw_dir": copy})
    set_settings(s2)
    with TestClient(create_app(s2), raise_server_exceptions=False) as c:
        before = c.get(f"/api/raw/{rid}", headers=WRITE)
        assert before.status_code == 200, before.text
        parts = Path(rel).parts
        month = parts[1][:7] if len(parts) >= 3 else "misc"
        archive = copy / parts[0] / f"{month}.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(copy / rel, arcname=Path(rel).as_posix())
        (copy / rel).unlink()
        after = c.get(f"/api/raw/{rid}", headers=WRITE)
        assert after.status_code == 200, after.text
        assert after.content == before.content
        # 압축에도 없으면 404
        archive.unlink()
        assert c.get(f"/api/raw/{rid}", headers=WRITE).status_code == 404


# ====================================================================== W6 · W7 가격 갭


def test_w6_substitute_label_shows_annual_coef(client: TestClient) -> None:
    as_live()  # D13-1: 실시간 계산 경로(발행 전 리비전)를 본다
    from app.models import ComparableSet, Region

    with get_session() as s:
        region = s.get(Region, 1)
        assert region is not None
        c = float(region.age_premium_coef["c_per_year"])
        sub = s.scalars(select(ComparableSet).where(ComparableSet.snapshot_id == SNAP)).first()
        assert sub is not None
        sub.substitute = True
        sub.adjusted = True
        sub.coef_used = 0.12  # type: ignore[assignment]  # 총 보정률(c × 8년)
        sub.adjusted_median_won = (sub.median_won or 500_000_000) + 1
        cid = sub.complex_id
    detail = client.get(f"/api/complexes/{cid}", headers=WRITE).json()
    adj = [m["adjusted_median"] for m in detail["gap"]["comps"] if m["adjusted_median"]]
    assert adj and all(a["reason"] == f"대체·보정 c={c:g}" for a in adj), adj
    assert all("0.12" not in a["reason"] for a in adj)


def test_w7_gap_pct_unadjusted_reads_stored_value(client: TestClient) -> None:
    as_live()  # D13-1: 실시간 계산 경로(발행 전 리비전)를 본다
    from decimal import Decimal

    from app.models import ScoreComponent, ScoreRun

    with get_session() as s:
        run = s.scalars(
            select(ScoreRun).where(ScoreRun.snapshot_id == SNAP, ScoreRun.scenario_id == 1)
        ).first()
        assert run is not None
        row = s.scalars(
            select(ScoreComponent).where(
                ScoreComponent.score_run_id == run.id,
                ScoreComponent.component == "gap",
                ScoreComponent.raw_value.is_not(None),
            )
        ).first()
        assert row is not None
        row.unadjusted_gap_pct = Decimal("-7.25")
        cid, run_id = row.complex_id, run.id
    gap = client.get(f"/api/complexes/{cid}", headers=WRITE).json()["gap"]
    un = gap["gap_pct_unadjusted"]
    assert un is not None and un["v"] == -7.25 and un["prov"] == f"sc_{run_id}_{cid}_gap"
    assert un["reason"] == "미보정 중앙값 기준"


# ====================================================================== W11 · F4 요청 devseed


def test_w11_devseed_loads_household_stat(client: TestClient) -> None:
    from app.models import HouseholdStat

    with get_session() as s:
        rows = list(s.scalars(select(HouseholdStat)))
    assert rows, "참조 사본(jumin_households_*.csv)의 세대 현황을 적재한다"
    assert {r.scope_kind for r in rows} == {"sigungu", "admin_dong"}
    assert all(r.label == "추정" and r.reason for r in rows)
    region = client.get("/api/regions/1", headers=WRITE).json()
    assert any(a.get("households") for a in region["living_areas"])


def test_f4_devseed_prev_snapshot_scores_and_claims(client: TestClient) -> None:
    from app.judge.claims import remaining_contradicted
    from app.models import IntakeStatus, ScoreRun

    with get_session() as s:
        runs11 = list(s.scalars(select(ScoreRun).where(ScoreRun.snapshot_id == 11)))
        assert len(runs11) == 5
        assert s.scalars(select(IntakeStatus).where(IntakeStatus.snapshot_id == 11)).first() is not None
        claims = list(s.scalars(select(Claim)))
        assert any(c.verify_status == "contradicted" for c in claims)
        assert all(remaining_contradicted(s, sid) == [] for sid in (11, 12))
    dash = client.get("/api/snapshots/11/dashboard", headers=WRITE).json()
    assert len(dash["top5"]) >= 5


# ====================================================================== minor 30 devseed


def test_minor30_devseed_refuses_prod_and_postgres(api_settings: Settings) -> None:
    from app.api import devseed

    prod = api_settings.model_copy(update={"env": "prod", "judge_adapter": "jev"})
    with pytest.raises(RuntimeError, match="ENV=prod"):
        devseed.seed(prod, reset=False)
    with pytest.raises(RuntimeError, match="ENV=prod"):
        devseed.load_synth(prod, n=1)
    pg = api_settings.model_copy(update={"database_url": "postgresql+psycopg://u:p@127.0.0.1:1/x"})
    with pytest.raises(RuntimeError, match="SQLite"):
        devseed.seed(pg, reset=False)
    with pytest.raises(RuntimeError, match="SQLite"):
        devseed.load_synth(pg, n=1)
    set_settings(prod)
    with pytest.raises(RuntimeError, match="ENV=prod"):
        devseed.main(["--no-reset", "--synth", "1"])

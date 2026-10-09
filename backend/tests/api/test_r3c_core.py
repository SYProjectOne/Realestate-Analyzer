"""R3c CORE — API 쪽 3차 리뷰 재현·통합 (`docs/design/wp/R3_REVIEW3.md`, 계약 2026-10-09.8, DECISIONS D11).

spy 없이 실제 경로(TestClient → 라우터 → DB, 보고서 데이터 적재)만 쓴다(minor 21).

| 리뷰 | 테스트 |
| --- | --- |
| M-3 | 강등 즉시(창 없음) 목록·CSV·보고서 데이터에서 '확인 불가(검증 모순)' |
| M-4 | 가격 강등 대상 = 화면·점수가 쓰는 현재 공고 price_by_type, 상세 가격도 확인 불가 |
| minor 9·12·14 | 같은 사실 두 번째 주장 강등 표시 · 수동 done 뒤 재오픈 · 불완전 대상 422 |
| M-9 | 근거 사실 강등 → 자동 체크리스트 항목 닫힘(closed_by auto) → 복원 → 다시 열림, 사람 처리는 유지 |
| M-1 | 사다리 숨김은 그 시나리오 run 의 저장 범위 기준 |
| M-6 | 보고서 벤치마크 = 그 스냅샷 행만(미래 조립분 없음) |
| minor 2·5 | CSV rejudge_needed 열 · 점수 실행 뒤 가격·입주월 변경도 '재판정 필요', 과거 스냅샷은 비교 안 함 |
| D11-5 | PATCH /catalysts/{id} → catalyst_link(거리 null·weight 1·추정), false 면 연결 삭제 |
| D11-7 | PATCH /regions/{id} → 생활권 재계산·change_event·region.expand 잡, 그대로면 409 |
"""

# ruff: noqa: E501

from __future__ import annotations

import csv
import io
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_session
from app.models import (
    Benchmark,
    Catalyst,
    CatalystLink,
    ChangeEvent,
    ChecklistItem,
    Claim,
    Complex,
    ComplexType,
    FactDemotion,
    FieldProvenance,
    JobRun,
    Ladder,
    PaymentTerms,
    Region,
    ScoreRun,
    ScoreTotal,
    Snapshot,
)

from ._support import READ, WRITE, validate
from .test_r3b_g3 import CX, SNAP, _ensure_resale, _fact_claim


def _demote_resale(client: TestClient) -> int:
    _ensure_resale(12)
    cid = _fact_claim()
    with get_session() as s:
        name = s.get(Complex, CX).name  # type: ignore[union-attr]
    r = client.patch(f"/api/claims/{cid}", json={"text": f"{name} 전매제한 기간은 12개월이다"}, headers=WRITE)
    assert r.status_code == 202, r.text
    return cid


# ====================================================================== M-3


def test_m3_demotion_applies_to_list_csv_and_report_immediately(client: TestClient) -> None:
    cid = _demote_resale(client)
    with get_session() as s:  # 고친 문장의 재검증이 끝났다(분할 자식 verified) — 보고서 생성 가능
        s.add(Claim(snapshot_id=SNAP, section=f"complex:{CX}", complex_id=CX, text="재검증", verify_status="verified",
                    parent_claim_id=cid, ordinal=0))  # fmt: skip
    items = client.get(f"/api/snapshots/{SNAP}/complexes", params={"size": 100}, headers=READ).json()["items"]
    row = next(i for i in items if i["complex_id"] == CX)
    assert row["resale_end"]["label"] == "확인 불가" and row["resale_end"]["v"] is None, "목록 산술 값도 강등"
    r = client.get(f"/api/snapshots/{SNAP}/complexes.csv", headers=READ)
    assert r.status_code == 200
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
    crow = next(x for x in rows if int(x["complex_id"]) == CX)
    assert crow["resale_end"] == "" and crow["resale_end_label"].startswith("확인 불가(")
    from app.reports.data import load_report

    with get_session() as s:
        data = load_report(s, SNAP, scenario_id=None, compare_snapshot_id=None)
    view = next(c for c in data.complexes if c.id == CX)
    fact = view.facts["resale_months"]
    assert fact.v is None and fact.label == "확인 불가" and fact.reason == "검증 모순", (
        "보고서도 같은 오버레이"
    )


# ====================================================================== M-4


def _price_by_type(cx_id: int, won: int) -> tuple[int, str]:
    """단지의 현재 납부 조건에 기준 타입 가격(price_by_type)과 출처 행을 넣는다 → (payment_terms id, 기준 타입)."""
    from app.analysis.price_view import basis_type

    with get_session() as s:
        types = list(s.scalars(select(ComplexType).where(ComplexType.complex_id == cx_id)))
        basis = basis_type(types)
        assert basis is not None
        pt = s.scalars(
            select(PaymentTerms).where(PaymentTerms.complex_id == cx_id).order_by(PaymentTerms.id)
        ).first()
        assert pt is not None
        pt.price_by_type = {
            basis.type_code: {"max_price_won": won, "floor_sample_price_won": won - 10_000_000}
        }
        raw_url = "https://www.applyhome.co.kr/notice"
        for item, v in (("max_price_won", won), ("floor_sample_price_won", won - 10_000_000)):
            s.add(
                FieldProvenance(
                    entity="payment_terms", entity_id=pt.id, field=f"price_by_type.{basis.type_code}.{item}",
                    value_text=f"{v:,}", value_norm=str(v), url=raw_url, checked_at="2026-10-07", label="확인됨",
                    source_rank=1, chosen=True, excerpt=f"공급금액 {v:,}",
                )
            )  # fmt: skip
        return pt.id, basis.type_code


def test_m4_price_demotion_targets_current_notice_price(client: TestClient) -> None:
    pt_id, code = _price_by_type(CX, 655_000_000)
    with get_session() as s:
        name = s.get(Complex, CX).name  # type: ignore[union-attr]
    cid = _fact_claim(field_text="기준 타입 최고 공급금액은 655,000,000원이다")
    r = client.patch(
        f"/api/claims/{cid}",
        json={"text": f"{name} 기준 타입 최고 공급금액은 650,000,000원이다"},
        headers=WRITE,
    )
    assert r.status_code == 202, r.text
    with get_session() as s:
        d = s.scalars(select(FactDemotion).where(FactDemotion.claim_id == cid)).one()
        assert (d.entity, d.entity_id, d.field) == (
            "payment_terms",
            pt_id,
            f"price_by_type.{code}.max_price_won",
        ), "가격 강등은 점수·화면이 실제로 쓰는 현재 공고 가격에 건다(M-4)"
        assert d.value_norm == "655000000"
    detail = client.get(f"/api/complexes/{CX}", params={"snapshot": SNAP}, headers=READ).json()
    high = detail["price"]["price_high"]
    assert high["v"] is None and high["label"] == "확인 불가" and high["reason"] == "검증 모순"
    validate("getComplex", 200, detail)


# ====================================================================== minor 9 · 12 · 14


def test_minor9_second_claim_on_same_fact_shows_demotion(client: TestClient) -> None:
    first = _demote_resale(client)
    second = _fact_claim()
    rows = {c["id"]: c for c in client.get(f"/api/snapshots/{SNAP}/claims", headers=READ).json()}
    assert rows[first]["demotion"]["status"] == "demoted"
    assert rows[second]["demotion"] is not None and rows[second]["demotion"]["status"] == "demoted", (
        "같은 사실의 두 번째 주장도 강등을 보인다"
    )


def test_minor12_manual_done_reopens_while_demoted(client: TestClient) -> None:
    from app.api.demotion import sync_demotions

    _demote_resale(client)
    with get_session() as s:
        d = s.scalars(select(FactDemotion)).one()
        item_id = d.checklist_item_id
    r = client.patch(f"/api/ops/checklist/{item_id}", json={"status": "done"}, headers=WRITE)
    assert r.status_code == 200 and r.json()["closed_by"] == "human"
    with get_session() as s:
        sync_demotions(s)  # 쓰기 경로(파이프라인 시작·수집 끝)
        item = s.get(ChecklistItem, item_id)
        assert item is not None and item.status == "open", "강등이 남았으면 '사실 재확인'을 다시 연다"


def test_minor14_incomplete_target_is_422_not_reverify(client: TestClient) -> None:
    with get_session() as s:
        cx = s.scalars(
            select(Complex).where(Complex.name == "계양신도시 카이브 유보라")
        ).one()  # 타입·납부 조건 없음
        claim = Claim(
            snapshot_id=SNAP, section=f"complex:{cx.id}", complex_id=cx.id,
            text=f"{cx.name} 기준 타입 최고 공급금액은 500,000,000원이다", evidence_text="",
            verify_status="contradicted", entity=None, entity_id=None, field="max_price_won",
        )  # fmt: skip
        s.add(claim)
        s.flush()
        cid, name = claim.id, cx.name
    r = client.patch(
        f"/api/claims/{cid}",
        json={"text": f"{name} 기준 타입 최고 공급금액은 510,000,000원이다"},
        headers=WRITE,
    )
    assert r.status_code == 422, r.text
    with get_session() as s:
        assert s.scalars(select(JobRun).where(JobRun.job_name == "claim.reverify")).first() is None


# ====================================================================== M-9


def test_m9_checklist_closes_on_demotion_and_reopens_on_restore(client: TestClient) -> None:
    from app.normalize.checklist import sync_checklist

    with get_session() as s:
        cx = s.get(Complex, CX)
        assert cx is not None
        cx.winner_date = "2026-11-20"
        s.add(
            FieldProvenance(
                entity="complex", entity_id=CX, field="winner_date", value_text="2026-11-20", value_norm="2026-11-20",
                url="https://www.applyhome.co.kr/", checked_at="2026-10-07", label="확인됨", source_rank=1,
                chosen=True, excerpt="당첨자 발표 2026-11-20",
            )
        )  # fmt: skip
    _ensure_resale(12)
    with get_session() as s:
        sync_checklist(s, 1, asof_date="2026-10-08")
        item = s.scalars(
            select(ChecklistItem).where(
                ChecklistItem.complex_id == CX, ChecklistItem.title.startswith("전매제한 종료")
            )
        ).one()
        assert item.status == "open"
        item_id = item.id
    _demote_resale(client)  # 강등 → demote 가 체크리스트를 다시 맞춘다(쓰기 경로)
    with get_session() as s:
        item = s.get(ChecklistItem, item_id)
        assert item is not None and (item.status, item.closed_by) == ("na", "auto"), (
            "모순 날짜 항목은 동기화가 닫는다"
        )
    hc = client.post(
        "/api/ops/human-checks", headers=WRITE,
        json={"complex_id": CX, "field": "resale_months", "value_text": "24", "kind": "phone",
              "checked_at": "2026-10-09T10:00:00+09:00", "entered_by": "운영자"},
    )  # fmt: skip
    assert hc.status_code == 201, hc.text
    with get_session() as s:
        item = s.get(ChecklistItem, item_id)
        assert item is not None and item.status == "open" and item.closed_by is None, (
            "근거가 돌아오면 다시 연다"
        )
        assert "24개월" in item.title
    # 사람이 닫은 항목은 동기화가 다시 열지 않는다
    assert (
        client.patch(f"/api/ops/checklist/{item_id}", json={"status": "na"}, headers=WRITE).status_code == 200
    )
    with get_session() as s:
        sync_checklist(s, 1, asof_date="2026-10-08")
        item = s.get(ChecklistItem, item_id)
        assert item is not None and (item.status, item.closed_by) == ("na", "human")
    listed = client.get("/api/ops/checklist", params={"complex_id": CX}, headers=WRITE).json()
    validate("listChecklist", 200, listed)


# ====================================================================== M-1


def test_m1_ladder_hiding_follows_the_requested_scenario_run(client: TestClient) -> None:
    with get_session() as s:
        cid = s.scalars(select(Ladder.complex_id).where(Ladder.snapshot_id == SNAP)).first()
        assert cid is not None
        base_run = s.scalars(
            select(ScoreRun)
            .where(ScoreRun.snapshot_id == SNAP, ScoreRun.scenario_id == 1)
            .order_by(ScoreRun.id.desc())
        ).first()
        assert base_run is not None
        base_scope = s.scalars(
            select(ScoreTotal.judge_scope).where(
                ScoreTotal.score_run_id == base_run.id, ScoreTotal.complex_id == cid
            )
        ).first()
        assert base_scope == "판정 대상"
        # 시나리오 B 만 다시 판정해 그 단지 범위가 '참고'가 됐다(시나리오 지정 rejudge)
        run = ScoreRun(snapshot_id=SNAP, scenario_id=3, weights={}, created_at="2099-01-01T00:00:00+09:00")
        s.add(run)
        s.flush()
        s.add(ScoreTotal(score_run_id=run.id, complex_id=cid, total=None, rank=None, judge_scope="참고"))
    base = client.get(
        f"/api/complexes/{cid}", params={"snapshot": SNAP, "scenario": "base"}, headers=READ
    ).json()
    other = client.get(
        f"/api/complexes/{cid}", params={"snapshot": SNAP, "scenario": "B"}, headers=READ
    ).json()
    assert base["ladder"], "기본 시나리오 화면은 기본 run 범위(판정 대상) — 사다리 유지(M-1)"
    assert not other["ladder"], "B 시나리오 화면은 B run 범위(참고) — 사다리 숨김"


# ====================================================================== M-6


def test_m6_report_benchmarks_are_snapshot_scoped(client: TestClient) -> None:
    from app.reports.data import load_report

    with get_session() as s:
        future = Snapshot(
            region_id=1, asof_date="2099-01-01", status="ready", created_at="2099-01-01T00:00:00+09:00"
        )
        s.add(future)
        s.flush()
        s.add(
            Benchmark(
                region_id=1, living_area="la_1", name="미래 조립 행", snapshot_id=future.id, note="[bm:9:9]"
            )
        )
    with get_session() as s:
        data = load_report(s, SNAP, scenario_id=None, compare_snapshot_id=None)
    assert "미래 조립 행" not in {b.name for b in data.benchmarks}


# ====================================================================== minor 2 · 5


def test_minor2_minor5_rejudge_needed_csv_and_change_after_run(client: TestClient) -> None:
    with get_session() as s:
        run = s.scalars(
            select(ScoreRun).where(ScoreRun.snapshot_id == SNAP).order_by(ScoreRun.id.desc())
        ).first()
        assert run is not None
        s.add(
            ChangeEvent(
                snapshot_id=SNAP, entity="complex", entity_id=CX, field="move_in_ym", old_text="2028-12",
                new_text="2029-03", detected_at="2099-01-01T00:00:00+09:00", severity="critical",
                triggers_rejudge=True, complex_id=CX,
            )
        )  # fmt: skip
    items = client.get(f"/api/snapshots/{SNAP}/complexes", params={"size": 100}, headers=READ).json()["items"]
    assert next(i for i in items if i["complex_id"] == CX)["rejudge_needed"] is True, (
        "범위가 같아도 실행 뒤 변경"
    )
    rows = list(
        csv.DictReader(
            io.StringIO(
                client.get(f"/api/snapshots/{SNAP}/complexes.csv", headers=READ).content.decode("utf-8-sig")
            )
        )
    )
    assert next(x for x in rows if int(x["complex_id"]) == CX)["rejudge_needed"] == "1"
    # 지역에 더 새 스냅샷이 생기면 이 스냅샷은 과거 기록 — 오늘 사실과 비교하지 않는다
    with get_session() as s:
        s.add(
            Snapshot(
                region_id=1, asof_date="2099-12-31", status="ready", created_at="2099-12-31T00:00:00+09:00"
            )
        )
    items = client.get(f"/api/snapshots/{SNAP}/complexes", params={"size": 100}, headers=READ).json()["items"]
    assert not any(i["rejudge_needed"] for i in items)


# ====================================================================== D11-5


def test_d11_5_patch_catalyst_creates_links_and_unconfirm_removes(client: TestClient) -> None:
    with get_session() as s:
        cat = Catalyst(
            region_id=1, name="테스트 역 신설", kind="교통", stage="계획", location_confirmed=False
        )
        s.add(cat)
        s.flush()
        cat_id = cat.id
        la2 = sorted(c.id for c in s.scalars(select(Complex).where(Complex.living_area == "la_2")))
    body = {"location_confirmed": True, "lat": 37.59, "lon": 126.67, "living_area_ids": ["la_2"], "complex_ids": [1],
            "expected_ym": "2028-06"}  # fmt: skip
    r = client.patch(f"/api/catalysts/{cat_id}", json=body, headers=WRITE)
    assert r.status_code == 200, r.text
    out = r.json()
    validate("updateCatalyst", 200, out)
    linked = sorted(lk["complex_id"] for lk in out["links"])
    assert linked == sorted({1, *la2})
    assert all(
        lk["distance_m"] is None and lk["weight"] == 1 and lk["label"] == "추정" for lk in out["links"]
    )
    assert out["catalyst"]["location_confirmed"] is True and out["catalyst"]["lat"] == 37.59
    assert (
        out["catalyst"]["expected_ym"]["v"] == "2028-06"
        and out["catalyst"]["expected_ym"]["label"] == "확인됨"
    )
    assert out["job"] is not None and out["job"]["job_name"] == "rejudge", "연결이 바뀌면 점수 재계산"
    got = client.get(f"/api/complexes/{la2[0]}", params={"snapshot": SNAP}, headers=READ)
    assert got.status_code == 200, got.text
    detail = got.json()
    assert any(c["id"] == cat_id and c["linked"] for c in detail["catalysts"]), (
        "ComplexDetail.catalysts 가 채워진다"
    )
    r = client.patch(f"/api/catalysts/{cat_id}", json={"location_confirmed": False}, headers=WRITE)
    assert r.status_code == 200 and r.json()["links"] == []
    with get_session() as s:
        assert not list(s.scalars(select(CatalystLink).where(CatalystLink.catalyst_id == cat_id)))
    bad = client.patch(
        f"/api/catalysts/{cat_id}",
        json={"location_confirmed": True, "living_area_ids": ["la_99"]},
        headers=WRITE,
    )
    assert bad.status_code == 422
    none = client.patch(f"/api/catalysts/{cat_id}", json={"location_confirmed": True}, headers=WRITE)
    assert none.status_code == 422, "위치 확인에는 영향 범위가 있어야 한다"


# ====================================================================== D11-7


def test_d11_7_patch_region_expands_selection_and_enqueues_expand_job(client: TestClient) -> None:
    from app.models import LegalDong

    with get_session() as s:
        region = s.get(Region, 1)
        assert region is not None
        old_sel = list(region.selections)
        old_areas = {a["id"]: list(a["legal_dong_codes"]) for a in region.living_areas}
        have = set(region.sigungu_codes or [])
        new_sgg = s.scalars(
            select(LegalDong.sigungu_code).where(
                LegalDong.active.is_(True),
                LegalDong.eupmyeondong_name.is_not(None),
                LegalDong.sigungu_code.not_in(have),
            )
        ).first()
        assert new_sgg is not None, "참조 데이터에 지역 밖 시군구가 있어야 한다"
        sgg_name = s.scalars(select(LegalDong.sigungu_name).where(LegalDong.sigungu_code == new_sgg)).first()
    same = client.patch("/api/regions/1", json={"selections": old_sel}, headers=WRITE)
    assert same.status_code == 409
    add = {"kind": "sigungu", "code": new_sgg, "full_name": f"추가 {sgg_name}"}
    r = client.patch("/api/regions/1", json={"selections": [*old_sel, add]}, headers=WRITE)
    assert r.status_code == 200, r.text
    out = r.json()
    validate("updateRegion", 200, out)
    assert out["added"] == [add] and out["removed"] == []
    areas = {a["id"]: a for a in out["region"]["living_areas"]}
    for aid, codes in old_areas.items():
        assert areas[aid]["legal_dong_codes"] == codes, "기존 생활권은 그대로"
    fresh = [a for aid, a in areas.items() if aid not in old_areas]
    assert len(fresh) == 1 and all(c.startswith(new_sgg) for c in fresh[0]["legal_dong_codes"])
    assert out["change_event"]["severity"] == "critical" and out["change_event"]["field"] == "selections"
    with get_session() as s:
        job = s.get(JobRun, out["job_id"])
        assert job is not None and job.job_name == "region.expand" and job.payload["added"] == [add]
    unknown = client.patch(
        "/api/regions/1",
        json={"selections": [{"kind": "sigungu", "code": "99999", "full_name": "없음"}]},
        headers=WRITE,
    )
    assert unknown.status_code == 422
    jobs = client.post(
        "/api/jobs", json={"job_name": "region.expand", "payload": {"region_id": 1}}, headers=WRITE
    )
    assert jobs.status_code == 422, "region.expand 는 PATCH /regions 로만"


def test_d11_7_patch_on_literal_resolve_path_is_405(client: TestClient) -> None:
    """PATCH /regions/{id} 가 생긴 뒤에도 '/regions/resolve' PATCH 는 id 검증 422 가 아니라 405 + Allow(계약 메서드)."""
    r = client.patch("/api/regions/resolve", params={"q": "x"}, json={}, headers=WRITE)
    assert r.status_code == 405, r.text
    assert r.headers.get("allow") == "GET"


def test_minor7_every_scenario_p10_component_has_its_fact(client: TestClient) -> None:
    """devseed 상황 C(기준일+5년) p10 성분 3.9 인데 사실값 null 이던 것(R3 3차 minor 7) — 시나리오 전부에서 p10 성분이
    있으면 그 시점 사다리 사실값도 있다(성분과 사실값이 같은 사다리)."""
    bad = []
    for sc in ("base", "A", "B", "C", "D"):
        r = client.get(f"/api/snapshots/{SNAP}/dashboard", params={"scenario": sc}, headers=WRITE)
        assert r.status_code == 200, r.text
        for row in r.json()["top5"]:
            if row["components"]["p10"]["score"]["v"] is not None and row["p10"]["v"] is None:
                bad.append((sc, row["complex_id"], row["components"]["p10"]["score"]["v"]))
    assert not bad, bad


def test_minor17_missing_raw_does_not_rescan_archives_per_request(tmp_path: Any) -> None:
    """원본도 압축 구성원도 없는 원문을 반복 요청해도 압축을 다시 훑지 않는다(구성원 목록 캐시 — R3 3차 minor 17).
    압축이 바뀌면(크기·시각) 목록을 다시 만든다."""
    import tarfile

    from app.api.routers import complexes as cx_router

    src = tmp_path / "notice_pdf"
    src.mkdir()
    payload = tmp_path / "x.bin"
    payload.write_bytes(b"x" * 1000)
    archive = src / "2026-10.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(payload, arcname="notice_pdf/2026-10-08/present.pdf")
    cx_router._members.cache_clear()
    for _ in range(5):
        assert cx_router.archived_stream("notice_pdf/2026-10-08/missing.pdf", tmp_path) is None
    info = cx_router._members.cache_info()
    assert (info.misses, info.hits) == (1, 4), info
    assert cx_router.archived_member("notice_pdf/2026-10-08/present.pdf", tmp_path) == b"x" * 1000
    with tarfile.open(archive, "w:gz") as tar:  # 압축 교체 → 새 목록
        tar.add(payload, arcname="notice_pdf/2026-10-08/missing.pdf")
        tar.add(payload, arcname="notice_pdf/2026-10-08/present.pdf")
    assert cx_router.archived_member("notice_pdf/2026-10-08/missing.pdf", tmp_path) == b"x" * 1000


def _walk(obj: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        if {"v", "label"} <= set(obj):
            out.append(obj)
        for v in obj.values():
            out.extend(_walk(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_walk(v))
    return out

"""R3b G3 — API (계약 2026-10-09.6, R3 재리뷰 `docs/design/wp/R3_REVIEW2.md`).

리뷰 항목: N-C3(claims PATCH 같은 대상·사실 강등·복원·체크리스트 '사실 재확인'·POST /jobs claim.reverify 차단),
N-M3(벤치마크 없음 사유), N-M4(sample_n 자기 생활권만·대체 표시), D10-7(공유 토큰 GET 범위), F3 minor
(압축 원문 스트리밍, 호재 URL 정규화·중복, 프록시 헤더 허용 목록).
"""

# ruff: noqa: E501  (한국어 assertion 메시지)
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.db import get_session
from app.models import (
    Benchmark,
    ChangeEvent,
    ChecklistItem,
    Claim,
    Complex,
    FactDemotion,
    FieldProvenance,
    JobRun,
    RawDocument,
    RtmsTrade,
    Snapshot,
)

from ._support import READ, WRITE, validate

SNAP = 12
CX = 2  # 엘리프 검단 포레듀(devseed)


def _fact_claim(field_text: str = "전매제한 기간은 36개월이다", **kw: Any) -> int:
    """P9 사실 문장 형식(section complex:<id>)의 contradicted 주장 — 계약 컬럼 없이(0006 이전·P9 미갱신 행)."""
    with get_session() as s:
        cx = s.get(Complex, CX)
        assert cx is not None
        row = {
            "snapshot_id": SNAP,
            "section": f"complex:{CX}",
            "complex_id": CX,
            "text": f"{cx.name} {field_text}",
            "evidence_text": "fp_1: 근거 발췌",
            "verify_status": "contradicted",
            "judgment_seq": None,
            "parent_claim_id": None,
            "ordinal": 0,
        }
        row.update(kw)
        c = Claim(**row)
        s.add(c)
        s.flush()
        return int(c.id)


def _chosen(s: Any, entity: str, entity_id: int, field: str) -> list[FieldProvenance]:
    return list(
        s.scalars(
            select(FieldProvenance).where(
                FieldProvenance.entity == entity,
                FieldProvenance.entity_id == entity_id,
                FieldProvenance.field == field,
                FieldProvenance.chosen.is_(True),
            )
        )
    )


def _ensure_resale(value: int = 12) -> int:
    """단지 2 전매제한 값 + 원문 출처 행(chosen) — devseed 값이 없어도 같은 조건."""
    with get_session() as s:
        cx = s.get(Complex, CX)
        assert cx is not None
        raw = s.scalars(select(RawDocument).order_by(RawDocument.id)).first()
        assert raw is not None
        if cx.resale_months is None or not _chosen(s, "complex", CX, "resale_months"):
            for fp in _chosen(s, "complex", CX, "resale_months"):
                fp.chosen = False
            fp = FieldProvenance(
                entity="complex", entity_id=CX, field="resale_months", value_text=f"{value}개월",
                raw_document_id=raw.id, url=raw.url, checked_at="2026-10-07", label="확인됨",
                source_rank=1, chosen=True, excerpt=f"전매제한 {value}개월",
            )  # fmt: skip
            s.add(fp)
            cx.resale_months = value
        s.flush()
        return int(cx.resale_months or value)


# ====================================================================== N-C3


def test_nc3_patch_rejects_other_field_or_other_complex(client: TestClient) -> None:
    _ensure_resale()
    cid = _fact_claim()
    with get_session() as s:
        cx = s.get(Complex, CX)
        other = s.scalars(select(Complex).where(Complex.region_id == cx.region_id, Complex.id != CX)).first()  # type: ignore[union-attr]
        assert cx is not None and other is not None
        name, other_name = cx.name, other.name
    cases = [
        f"{name} 입주 예정 시기는 2028-06이다",  # 다른 필드만
        f"{name} 전매제한 기간은 12개월이고 입주 예정 시기는 2028-06이다",  # 원 필드 + 다른 필드
        f"{other_name} 전매제한 기간은 12개월이다",  # 다른 단지
        "날씨가 좋다",  # 대상 용어 없음
    ]
    for text in cases:
        r = client.patch(f"/api/claims/{cid}", json={"text": text}, headers=WRITE)
        assert r.status_code == 422, (text, r.text)
        body = r.json()
        validate("reviseClaim", 422, body)
        assert body["field_errors"][0]["loc"] == ["body", "text"]
    with get_session() as s:
        assert s.scalars(select(JobRun).where(JobRun.job_name == "claim.reverify")).first() is None
        assert s.scalars(select(FactDemotion)).first() is None, "거절된 수정은 강등하지 않는다"
        assert s.get(Complex, CX).resale_months is not None  # type: ignore[union-attr]


def test_nc3_patch_demotes_fact_and_restores_by_human_check(client: TestClient) -> None:
    before = _ensure_resale(12)
    cid = _fact_claim()
    with get_session() as s:
        name = s.get(Complex, CX).name  # type: ignore[union-attr]
        orig_ids = {fp.id for fp in _chosen(s, "complex", CX, "resale_months")}
    r = client.patch(
        f"/api/claims/{cid}", json={"text": f"{name} 전매제한 기간은 {before}개월이다"}, headers=WRITE
    )
    assert r.status_code == 202, r.text
    reverify_job = r.json()["id"]
    with get_session() as s:
        cx = s.get(Complex, CX)
        assert cx is not None and cx.resale_months is None, "강등 = 사실 값 비움(점수·요건 입력에서 빠짐)"
        chosen = _chosen(s, "complex", CX, "resale_months")
        assert [(fp.label, fp.reason) for fp in chosen] == [("확인 불가", "검증 모순")]
        assert all(not s.get(FieldProvenance, i).chosen for i in orig_ids), (
            "원래 출처 행은 chosen=false 로 보관"
        )  # type: ignore[union-attr]
        d = s.scalars(select(FactDemotion).where(FactDemotion.claim_id == cid)).one()
        assert (d.entity, d.entity_id, d.field, d.restored_at) == ("complex", CX, "resale_months", None)
        claim = s.get(Claim, cid)
        assert (claim.entity, claim.entity_id, claim.field) == ("complex", CX, "resale_months")  # type: ignore[union-attr]
        item = s.get(ChecklistItem, d.checklist_item_id)
        assert item is not None and item.kind == "사실 재확인" and item.status == "open"
        assert item.title == "사실 재확인: 전매제한 기간(검증 모순)"
        ce = s.scalars(
            select(ChangeEvent).where(ChangeEvent.field == "resale_months", ChangeEvent.complex_id == CX)
        ).all()[-1]
        assert ce.severity == "critical" and ce.triggers_rejudge and ce.new_text == "확인 불가(검증 모순)"
        rejudge = s.get(JobRun, d.rejudge_job_id)
        assert rejudge is not None and rejudge.job_name == "rejudge"
        assert CX in (rejudge.payload["complex_ids"] or [CX])
        assert rejudge.id < reverify_job, (
            "rejudge 가 claim.reverify 보다 먼저(재검증 publish 가 강등 전 점수로 나가지 않게)"
        )
    # 화면: 주장 목록·단지 상세
    listed = client.get(
        f"/api/snapshots/{SNAP}/claims", params={"status": "contradicted"}, headers=READ
    ).json()
    validate("listClaims", 200, listed)
    row = next(c for c in listed if c["id"] == cid)
    assert row["field"] == "resale_months" and row["field_name"] == "전매제한 기간"
    assert row["demotion"]["status"] == "demoted" and row["demotion"]["reason"] == "검증 모순"
    detail = client.get(f"/api/complexes/{CX}", params={"snapshot": SNAP}, headers=READ)
    assert detail.status_code == 200, detail.text
    facts = [f for f in _walk(detail.json()) if f.get("reason") == "검증 모순"]
    assert facts and all(f["label"] == "확인 불가" and f["v"] is None for f in facts)
    checklist = client.get("/api/ops/checklist", headers=READ).json()
    validate("listChecklist", 200, checklist)
    assert any(i["kind"] == "사실 재확인" and i["complex_id"] == CX for i in checklist)
    # 같은 사실의 다른 주장 수정은 강등을 겹치지 않는다
    # 사람 확인 → 복원
    hc = client.post(
        "/api/ops/human-checks",
        headers=WRITE,
        json={"complex_id": CX, "field": "resale_months", "value_text": "abc", "kind": "phone",
              "checked_at": "2026-10-09T10:00:00+09:00", "entered_by": "운영자"},
    )  # fmt: skip
    assert hc.status_code == 422, "숫자 필드에 숫자가 아닌 값"
    hc = client.post(
        "/api/ops/human-checks",
        headers=WRITE,
        json={"complex_id": CX, "field": "resale_months", "value_text": "12", "kind": "phone",
              "checked_at": "2026-10-09T10:00:00+09:00", "entered_by": "운영자", "note": "견본주택 통화"},
    )  # fmt: skip
    assert hc.status_code == 201, hc.text
    body = hc.json()
    validate("createHumanCheck", 201, body)
    assert body["suggested_job"]["job_name"] == "rejudge" and body["change_event_id"] is not None
    with get_session() as s:
        assert s.get(Complex, CX).resale_months == 12  # type: ignore[union-attr]
        chosen = _chosen(s, "complex", CX, "resale_months")
        assert [(fp.label, fp.reason) for fp in chosen] == [("확인됨", "사람 확인(phone)")]
        d = s.scalars(select(FactDemotion).where(FactDemotion.claim_id == cid)).one()
        assert d.restored_by == "human_check" and d.restored_at and d.human_check_id == body["id"]
        assert s.get(ChecklistItem, d.checklist_item_id).status == "done"  # type: ignore[union-attr]
    row = next(c for c in client.get(f"/api/snapshots/{SNAP}/claims", headers=READ).json() if c["id"] == cid)
    assert row["demotion"]["status"] == "restored" and row["demotion"]["restored_by"] == "human_check"


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


def test_nc3_new_source_restores_but_same_source_redemotes(client: TestClient) -> None:
    _ensure_resale(12)
    cid = _fact_claim()
    with get_session() as s:
        name = s.get(Complex, CX).name  # type: ignore[union-attr]
    assert (
        client.patch(
            f"/api/claims/{cid}", json={"text": f"{name} 전매제한 기간은 12개월이다"}, headers=WRITE
        ).status_code
        == 202
    )
    with get_session() as s:
        d = s.scalars(select(FactDemotion).where(FactDemotion.claim_id == cid)).one()
        orig = s.get(FieldProvenance, d.original_fp_id)
        assert orig is not None
        # 같은 원문을 다시 정규화(정규화가 원래 행을 다시 chosen 으로) → 새 원문이 아니다 → 다시 강등
        for fp in _chosen(s, "complex", CX, "resale_months"):
            fp.chosen = False
        orig.chosen = True
        s.get(Complex, CX).resale_months = 12  # type: ignore[union-attr]
    client.get(f"/api/snapshots/{SNAP}/claims", headers=READ)
    with get_session() as s:
        assert s.get(Complex, CX).resale_months is None  # type: ignore[union-attr]
        assert [fp.reason for fp in _chosen(s, "complex", CX, "resale_months")] == ["검증 모순"]
        assert s.get(FactDemotion, d.id).restored_at is None  # type: ignore[union-attr]
        # 다른 원문 출처가 chosen(새 공고문) → 복원(new_source)
        other_raw = s.scalars(
            select(RawDocument).where(RawDocument.id != orig.raw_document_id).order_by(RawDocument.id)
        ).first()
        assert other_raw is not None
        for fp in _chosen(s, "complex", CX, "resale_months"):
            fp.chosen = False
        s.add(
            FieldProvenance(
                entity="complex", entity_id=CX, field="resale_months", value_text="24개월",
                raw_document_id=other_raw.id, url=other_raw.url, checked_at="2026-10-10", label="확인됨",
                source_rank=1, chosen=True, excerpt="전매제한 24개월",
            )
        )  # fmt: skip
        s.get(Complex, CX).resale_months = 24  # type: ignore[union-attr]
    client.get("/api/ops/checklist", headers=READ)
    with get_session() as s:
        d2 = s.get(FactDemotion, d.id)
        assert d2 is not None and d2.restored_by == "new_source"
        assert s.get(Complex, CX).resale_months == 24  # type: ignore[union-attr]
        assert s.get(ChecklistItem, d2.checklist_item_id).status == "done"  # type: ignore[union-attr]


def test_nc3_report_claim_without_fact_target_only_checks_complex(client: TestClient) -> None:
    cid = _fact_claim(section="12-4", field_text="의 +10% 이상 명제는 likely로 판정되었다.")
    with get_session() as s:
        name = s.get(Complex, CX).name  # type: ignore[union-attr]
    r = client.patch(
        f"/api/claims/{cid}",
        json={"text": f"{name}의 +10% 이상 명제는 unlikely로 판정되었다."},
        headers=WRITE,
    )
    assert r.status_code == 202, r.text
    with get_session() as s:
        assert s.scalars(select(FactDemotion)).first() is None, "사실에서 생성되지 않은 주장은 강등 없음"
    listed = client.get(f"/api/snapshots/{SNAP}/claims", headers=READ).json()
    row = next(c for c in listed if c["id"] == cid)
    assert row["field"] is None and row["demotion"] is None


def test_nc3_post_jobs_cannot_enqueue_claim_reverify(client: TestClient) -> None:
    cid = _fact_claim()
    r = client.post(
        "/api/jobs",
        json={"job_name": "claim.reverify", "payload": {"snapshot_id": SNAP, "claim_id": cid, "text": "x"}},
        headers=WRITE,
    )
    assert r.status_code == 422, r.text
    with get_session() as s:
        assert s.scalars(select(JobRun).where(JobRun.job_name == "claim.reverify")).first() is None


# ====================================================================== N-M3 · N-M4 (벤치마크)


def test_nm4_sample_n_counts_own_rows_only_and_flags_substitute(client: TestClient) -> None:
    with get_session() as s:
        s.execute(delete(Benchmark))
        base = {"region_id": 1, "completed_year": 2022, "sale_year": 2019, "is_presale": False}
        s.add(Benchmark(**base, living_area="la_1", name="자기 표본", note="[bm:1:1] 입주 후 실거래"))
        s.add(
            Benchmark(
                **base,
                living_area="la_2",
                name="대체",
                note="[bm:1:1:la_2] · 추정(대체: 지역 전체) — 생활권 la_2 자체 표본 0, 원 생활권 la_1",
            )
        )
    body = client.get(f"/api/snapshots/{SNAP}/market", headers=READ).json()
    validate("getMarket", 200, body)
    flags = {f["living_area"]: f for f in body["benchmark_flags"]}
    assert flags["la_1"]["sample_n"] == 1 and flags["la_1"]["substituted"] is False
    assert flags["la_2"]["sample_n"] == 0 and flags["la_2"]["substituted"] is True, (
        "대체 행은 자기 표본이 아니다"
    )
    subs = {b["name"]: b["substitute"] for b in body["benchmarks"]}
    assert subs == {"자기 표본": False, "대체": True}
    assert body["benchmark_absence"] is None


@pytest.mark.parametrize(
    ("rows", "trades", "code"),
    [([], False, "not_collected"), ([], True, "no_sample"), (["presale"], True, "presale_only")],
)
def test_nm3_benchmark_absence_reason(client: TestClient, rows: list[str], trades: bool, code: str) -> None:
    with get_session() as s:
        s.execute(delete(Benchmark))
        if not trades:
            s.execute(delete(RtmsTrade))
        for _ in rows:
            s.add(Benchmark(region_id=1, living_area="la_1", name="분양권", is_presale=True))
    market = client.get(f"/api/snapshots/{SNAP}/market", headers=READ).json()
    validate("getMarket", 200, market)
    assert market["benchmark_absence"]["code"] == code and market["benchmark_absence"]["reason"]
    dash = client.get(f"/api/snapshots/{SNAP}/dashboard", headers=READ).json()
    validate("getDashboard", 200, dash)
    assert dash["benchmark_absence"] == market["benchmark_absence"]


def test_benchmark_rows_follow_snapshot_id(client: TestClient) -> None:
    """benchmark.snapshot_id(계약 .6): NULL 행(사람 입력·이전 행)은 늘 + 조립분은 그 스냅샷 것 → 없으면 그 전 최근 것(미래 것은 안 보임)."""
    with get_session() as s:
        s.execute(delete(Benchmark))
        common = {"region_id": 1, "living_area": "la_1", "is_presale": False}
        s.add(Benchmark(**common, name="옛 행", snapshot_id=None))
        s.add(Benchmark(**common, name="이 스냅샷", snapshot_id=SNAP))
        future = Snapshot(
            region_id=1, asof_date="2099-01-01", status="ready", created_at="2099-01-01T00:00:00+09:00"
        )
        s.add(future)
        s.flush()
        s.add(Benchmark(**common, name="미래", snapshot_id=future.id))
    names = {
        b["name"] for b in client.get(f"/api/snapshots/{SNAP}/market", headers=READ).json()["benchmarks"]
    }
    assert names == {"옛 행", "이 스냅샷"}
    with get_session() as s:
        s.execute(delete(Benchmark).where(Benchmark.snapshot_id == SNAP))
    names = {
        b["name"] for b in client.get(f"/api/snapshots/{SNAP}/market", headers=READ).json()["benchmarks"]
    }
    assert names == {"옛 행"}

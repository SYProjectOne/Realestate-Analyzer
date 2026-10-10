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

from ._support import READ, WRITE, as_live, validate

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
    """D10-3 + D11-3(계약 .8): 강등은 사실 값을 지우지 않는 읽기 시점 오버레이 — 화면·주장 목록은 즉시 '확인 불가(검증 모순)',
    사람 확인은 resolver 0순위 후보로 값을 바꾸고 강등을 복원한다."""
    as_live()  # D13-1: 실시간 계산 경로(발행 전 리비전)를 본다
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
        assert cx is not None and cx.resale_months == before, "강등은 사실 값을 지우지 않는다(D11-3 오버레이)"
        assert {fp.id for fp in _chosen(s, "complex", CX, "resale_months")} == orig_ids, "출처 행도 그대로"
        d = s.scalars(select(FactDemotion).where(FactDemotion.claim_id == cid)).one()
        assert (d.entity, d.entity_id, d.field, d.restored_at) == ("complex", CX, "resale_months", None)
        assert d.value_norm == str(before), "모순 값(value_norm) 기록"
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
    # 화면: 주장 목록·단지 상세 — 오버레이로 즉시(창 없음)
    listed = client.get(
        f"/api/snapshots/{SNAP}/claims", params={"status": "contradicted"}, headers=READ
    ).json()
    validate("listClaims", 200, listed)
    row = next(c for c in listed if c["id"] == cid)
    assert row["field"] == "resale_months" and row["field_name"] == "전매제한 기간"
    assert row["demotion"]["status"] == "demoted" and row["demotion"]["reason"] == "검증 모순"
    detail = client.get(f"/api/complexes/{CX}", params={"snapshot": SNAP}, headers=READ)
    assert detail.status_code == 200, detail.text
    resale = detail.json()["header"]["resale_months"]
    assert resale["label"] == "확인 불가" and resale["v"] is None and resale["reason"] == "검증 모순"
    assert detail.json()["header"]["resale_end"]["v"] is None, "강등 사실로 만든 산술 값도 확인 불가"
    checklist = client.get("/api/ops/checklist", headers=READ).json()
    validate("listChecklist", 200, checklist)
    assert any(i["kind"] == "사실 재확인" and i["complex_id"] == CX for i in checklist)
    # 사람 확인 → 복원(0순위 후보)
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
        json={"complex_id": CX, "field": "resale_months", "value_text": "24", "kind": "phone",
              "checked_at": "2026-10-09T10:00:00+09:00", "entered_by": "운영자", "note": "견본주택 통화"},
    )  # fmt: skip
    assert hc.status_code == 201, hc.text
    body = hc.json()
    validate("createHumanCheck", 201, body)
    assert (body["entity"], body["entity_id"]) == ("complex", CX)
    assert body["rejudge_job_id"] is not None and body["change_event_id"] is not None  # D12-5 자동 등록
    with get_session() as s:
        assert s.get(Complex, CX).resale_months == 24  # type: ignore[union-attr]
        chosen = _chosen(s, "complex", CX, "resale_months")
        assert [(fp.label, fp.reason, fp.source_rank) for fp in chosen] == [("확인됨", "사람 확인(phone)", 0)]
        d = s.scalars(select(FactDemotion).where(FactDemotion.claim_id == cid)).one()
        assert d.restored_by == "human_check" and d.restored_at and d.human_check_id == body["id"]
        assert s.get(ChecklistItem, d.checklist_item_id).status == "done"  # type: ignore[union-attr]
    row = next(c for c in client.get(f"/api/snapshots/{SNAP}/claims", headers=READ).json() if c["id"] == cid)
    assert row["demotion"]["status"] == "restored" and row["demotion"]["restored_by"] == "human_check"
    detail = client.get(f"/api/complexes/{CX}", params={"snapshot": SNAP}, headers=READ).json()
    assert (
        detail["header"]["resale_months"]["v"] == 24
        and detail["header"]["resale_months"]["label"] == "확인됨"
    )


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


def test_nc3_same_value_new_source_keeps_demotion_other_value_releases(client: TestClient) -> None:
    """C-4(R3 3차): 같은 값의 새 원문(sha 만 다름)·값 없는 행은 강등을 풀지 않는다. 다른 값을 낸 새 출처만 푼다.
    GET 은 DB 를 쓰지 않는다(minor 13) — 복원 기록은 쓰기 경로(``sync_demotions``)."""
    as_live()  # D13-1: 실시간 계산 경로(발행 전 리비전)를 본다
    from app.api.demotion import sync_demotions

    _ensure_resale(12)
    cid = _fact_claim()
    with get_session() as s:
        name = s.get(Complex, CX).name  # type: ignore[union-attr]
        for fp in _chosen(s, "complex", CX, "resale_months"):
            fp.value_norm = "12"  # 정규화 출처 행(계약 .2 이후)은 정준 값을 가진다
    assert (
        client.patch(
            f"/api/claims/{cid}", json={"text": f"{name} 전매제한 기간은 12개월이다"}, headers=WRITE
        ).status_code
        == 202
    )
    raws = []
    with get_session() as s:
        d = s.scalars(select(FactDemotion).where(FactDemotion.claim_id == cid)).one()
        orig = s.get(FieldProvenance, d.original_fp_id)
        assert orig is not None
        raws = [r.id for r in s.scalars(select(RawDocument).where(RawDocument.id != orig.raw_document_id))]
        assert len(raws) >= 2

    def new_source(raw_id: int, value: int | None) -> None:
        with get_session() as s:
            raw = s.get(RawDocument, raw_id)
            assert raw is not None
            for fp in _chosen(s, "complex", CX, "resale_months"):
                fp.chosen = False
            s.add(
                FieldProvenance(
                    entity="complex", entity_id=CX, field="resale_months",
                    value_text=f"{value}개월" if value is not None else None,
                    value_norm=str(value) if value is not None else None,
                    raw_document_id=raw.id, url=raw.url, checked_at="2026-10-10",
                    label="확인됨" if value is not None else "확인 불가", source_rank=1, chosen=True,
                    excerpt=f"전매제한 {value}개월",
                )
            )  # fmt: skip
            if value is not None:
                s.get(Complex, CX).resale_months = value  # type: ignore[union-attr]

    def shown() -> dict[str, Any]:
        detail = client.get(f"/api/complexes/{CX}", params={"snapshot": SNAP}, headers=READ).json()
        return detail["header"]["resale_months"]  # type: ignore[no-any-return]

    new_source(raws[0], 12)  # 같은 값 재수집(다른 원문)
    assert shown()["reason"] == "검증 모순" and shown()["v"] is None
    with get_session() as s:
        assert sync_demotions(s) == 0 or s.get(FactDemotion, d.id).restored_at is None  # type: ignore[union-attr]
        assert s.get(FactDemotion, d.id).restored_at is None  # type: ignore[union-attr]
    new_source(raws[1], 24)  # 다른 값 → 오버레이가 풀린다(GET 은 쓰지 않는다)
    assert shown()["v"] == 24
    row = next(c for c in client.get(f"/api/snapshots/{SNAP}/claims", headers=READ).json() if c["id"] == cid)
    assert row["demotion"]["status"] == "restored" and row["demotion"]["restored_at"] is None
    with get_session() as s:
        assert s.get(FactDemotion, d.id).restored_at is None, "GET 은 복원 기록을 쓰지 않는다"  # type: ignore[union-attr]
        sync_demotions(s)  # 쓰기 경로
        d2 = s.get(FactDemotion, d.id)
        assert d2 is not None and d2.restored_by == "new_source"
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
    as_live()  # D13-1: 실시간 계산 경로(발행 전 리비전)를 본다
    with get_session() as s:
        s.execute(delete(Benchmark))
        base = {"region_id": 1, "completed_year": 2022, "sale_year": 2019, "is_presale": False}
        s.add(Benchmark(**base, living_area="la_1", name="자기 표본", note="[bm:1:1] 입주 후 실거래"))
        s.add(
            Benchmark(
                **base,
                living_area="la_2",
                name="대체",
                substitute=True,  # 계약 2026-10-09.7 — 판별은 컬럼
                note="[bm:1:1:la_2] · 추정(대체: 지역 전체) — 생활권 la_2 자체 표본 0, 원 생활권 la_1",
            )
        )
        # note 에 표식 문구만 있고 컬럼이 false 인 행은 대체가 아니다(문자열 판별 금지)
        s.add(
            Benchmark(**base, living_area="la_1", name="문구만", note="사람 메모: 추정(대체: 지역 전체) 아님")
        )
    body = client.get(f"/api/snapshots/{SNAP}/market", headers=READ).json()
    validate("getMarket", 200, body)
    flags = {f["living_area"]: f for f in body["benchmark_flags"]}
    assert flags["la_1"]["sample_n"] == 2 and flags["la_1"]["substituted"] is False
    assert flags["la_2"]["sample_n"] == 0 and flags["la_2"]["substituted"] is True, (
        "대체 행은 자기 표본이 아니다"
    )
    subs = {b["name"]: b["substitute"] for b in body["benchmarks"]}
    assert subs == {"자기 표본": False, "대체": True, "문구만": False}
    assert body["benchmark_absence"] is None


@pytest.mark.parametrize(
    ("rows", "trades", "code"),
    [([], False, "not_collected"), ([], True, "no_sample"), (["presale"], True, "presale_only")],
)
def test_nm3_benchmark_absence_reason(client: TestClient, rows: list[str], trades: bool, code: str) -> None:
    as_live()  # D13-1: 실시간 계산 경로(발행 전 리비전)를 본다
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
    as_live()  # D13-1: 실시간 계산 경로(발행 전 리비전)를 본다
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


# ====================================================================== D10-7 공유 토큰 GET 범위


def test_d10_7_share_token_reads_screens_but_not_ops_or_jobs(client: TestClient) -> None:
    token = client.post("/api/share-links", json={"label": "공유"}, headers=WRITE).json()["token"]
    share = {"Authorization": f"Bearer {token}"}
    for path in (f"/api/snapshots/{SNAP}/dashboard", f"/api/snapshots/{SNAP}/complexes", "/api/regions"):
        assert client.get(path, headers=share).status_code == 200, path
    for path in ("/api/ops/sources", "/api/ops/judgments", "/api/ops/checklist", "/api/jobs", "/api/jobs/1"):
        r = client.get(path, headers=share)
        assert r.status_code == 403, (path, r.text)
        assert r.json()["code"] == "forbidden"
        # 운영자 열람용 READONLY_TOKEN 은 모든 GET
        assert client.get(path, headers=READ).status_code in (200, 404), path


def test_d10_7_share_link_allows_helper() -> None:
    from app.api.deps import share_link_allows

    assert share_link_allows("/api/snapshots/12/market")
    assert share_link_allows("/api/raw/3")
    assert share_link_allows("/api/jobsite")  # 접두어만 같은 다른 경로는 막지 않는다
    for denied in ("/api/ops", "/api/ops/", "/api/ops/checklist", "/api/jobs", "/api/jobs/", "/api/jobs/7"):
        assert not share_link_allows(denied), denied


# ====================================================================== F3 minor


def test_f3_archived_raw_is_streamed_in_chunks(
    api_settings: Any, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """압축 원문을 요청마다 통째로 메모리에 올리지 않는다 — 목록 전체(getmember)·read() 전체 대신 64KiB 조각 응답."""
    import shutil
    import tarfile
    from pathlib import Path

    from app.api.routers import complexes as cx_router
    from app.core.settings import set_settings
    from app.main import create_app

    with get_session() as s:
        doc = s.scalars(
            select(RawDocument).where(RawDocument.path.is_not(None)).order_by(RawDocument.id)
        ).first()
        assert doc is not None and doc.path
        rid, rel = doc.id, doc.path
    copy = tmp_path / "raw_copy"
    shutil.copytree(api_settings.raw_dir, copy)
    big = b"0123456789abcdef" * 20000  # 320KB → 64KiB 조각 여러 개
    (copy / rel).write_bytes(big)
    parts = Path(rel).parts
    month = parts[1][:7] if len(parts) >= 3 else "misc"
    archive = copy / parts[0] / f"{month}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(copy / rel, arcname=Path(rel).as_posix())
    (copy / rel).unlink()

    def no_getmember(self: Any, name: str) -> Any:
        raise AssertionError("getmember 는 구성원 목록 전체를 읽는다")

    monkeypatch.setattr(tarfile.TarFile, "getmember", no_getmember)
    stream = cx_router.archived_stream(rel, copy)
    assert stream is not None
    chunks = list(stream)
    assert len(chunks) >= 4 and max(map(len, chunks)) <= 64 * 1024 and b"".join(chunks) == big
    s2 = api_settings.model_copy(update={"raw_dir": copy})
    set_settings(s2)
    with TestClient(create_app(s2), raise_server_exceptions=False) as c:
        r = c.get(f"/api/raw/{rid}", headers=WRITE)
        assert r.status_code == 200 and r.content == big
        assert "attachment" in r.headers.get("content-disposition", "")


def test_f3_catalyst_url_normalized_and_not_rejudged_twice(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api.routers import catalysts
    from app.models import Catalyst

    calls: list[str] = []

    def factory() -> Any:
        def fn(session: Any, region_id: int, *, url: str, title: str, excerpt: str | None = None) -> Any:
            calls.append(url)
            row = Catalyst(
                region_id=region_id, name=title, kind="기타", stage="미확정",
                location_confirmed=False, source_url=url,
            )  # fmt: skip
            session.add(row)
            session.flush()
            return row

        return fn

    monkeypatch.setattr(catalysts, "candidate_factory", factory)
    norm = catalysts.normalize_url("HTTPS://News.Example.org:443/a/1/?utm_source=x&b=2&a=1#frag")
    assert norm == "https://news.example.org/a/1?a=1&b=2"
    body = {"region_id": 1, "url": "https://news.example.org/a/1?utm_source=kakao", "title": "역 신설"}
    first = client.post("/api/catalysts", json=body, headers=WRITE)
    assert first.status_code == 201, first.text
    assert first.json()["job"] is not None and calls == ["https://news.example.org/a/1"]
    body2 = {"region_id": 1, "url": "https://NEWS.example.org/a/1/#top", "title": "역 신설(다른 제목)"}
    again = client.post("/api/catalysts", json=body2, headers=WRITE)
    assert again.status_code == 201
    validate("createCatalyst", 201, again.json())
    assert again.json()["catalyst"]["id"] == first.json()["catalyst"]["id"], "같은 기사 = 같은 행"
    assert again.json()["job"] is None, "같은 URL 은 rejudge 를 다시 등록하지 않는다"
    assert len(calls) == 1

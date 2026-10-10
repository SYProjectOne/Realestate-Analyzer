"""R3d CORE2 — API 쪽 4차 리뷰 재현·통합 (`docs/design/wp/R3_REVIEW4.md`, 계약 2026-10-09.9, DECISIONS D12).

spy 없이 실제 경로(TestClient → 라우터 → DB, 정규화 ``store_raw_document``, 보고서 데이터 적재, 파이프라인 입력)만 쓴다.

| 리뷰 | 테스트 |
| --- | --- |
| C-1 · D12-2 | 강등 뒤 같은 모순 가격·계약금을 실은 새 공고 행 → 상세·목록·점수 입력 모두 강등 유지 |
"""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.contracts_gen import FieldCandidate
from app.core.contracts_gen import RawDocument as RawDocumentDTO
from app.core.db import get_session
from app.models import Complex, FactDemotion, PaymentTerms, RawDocument, Region, Snapshot

from ._support import READ, WRITE, as_live
from .test_r3b_g3 import CX, SNAP, _fact_claim
from .test_r3c_core import _price_by_type


class _TermsNotice:
    """새 공고 1건(payment_terms) 후보 — 정규화기(``store_raw_document``)가 새 납부 조건 행을 만든다."""

    def __init__(self, key: str, notice_no: str, values: dict[str, Any], *, kind: str = "notice_pdf",
                 observed_on: str = "2026-10-08") -> None:  # fmt: skip
        self.key, self.notice_no, self.values, self.kind, self.observed_on = (
            key,
            notice_no,
            values,
            kind,
            observed_on,
        )

    def parse(self, raw: RawDocumentDTO) -> list[FieldCandidate]:
        tk = f"{self.key}:{self.notice_no}"
        out: list[FieldCandidate] = []
        for f, v in self.values.items():
            c = FieldCandidate(
                entity="payment_terms", entity_id=None, entity_key=tk, field=f, value_text=str(v), value=v,
                source_rank=1, source_kind=self.kind, primary=True, label="확인됨", excerpt=f"{f} {v}",  # type: ignore[arg-type]
                excerpt_start=0, excerpt_end=1, raw_document_id=raw.id, url=raw.url, checked_at="2026-10-09",
                observed_on=self.observed_on,
            )  # fmt: skip
            out.append(c)
        return out


def store_notice(cx_id: int, notice_no: str, values: dict[str, Any], **kw: Any) -> list[int]:
    """새 공고 원문을 정규화 경로로 저장 → 바뀐 단지 id."""
    from app.normalize.store import store_raw_document

    with get_session() as s:
        cx = s.get(Complex, cx_id)
        assert cx is not None and cx.applyhome_id
        raw = RawDocument(
            source_kind=kw.get("kind", "notice_pdf"), url=f"https://www.applyhome.co.kr/notice/{notice_no}",
            fetched_at="2026-10-09T09:00:00+09:00", http_status=200,
            sha256=hashlib.sha256(f"{notice_no}{values}".encode()).hexdigest(), region_id=cx.region_id,
            complex_id=cx.id,
        )  # fmt: skip
        s.add(raw)
        s.flush()
        res = store_raw_document(s, raw, parser=_TermsNotice(cx.applyhome_id, notice_no, values, **kw))
        return list(res.complex_ids)


def _demote_price(client: TestClient, won: int) -> tuple[int, str, int]:
    pt_id, code = _price_by_type(CX, won)
    with get_session() as s:
        name = s.get(Complex, CX).name  # type: ignore[union-attr]
    claim = _fact_claim(field_text=f"기준 타입 최고 공급금액은 {won:,}원이다")
    r = client.patch(
        f"/api/claims/{claim}",
        json={"text": f"{name} 기준 타입 최고 공급금액은 {won - 5_000_000:,}원이다"},
        headers=WRITE,
    )
    assert r.status_code == 202, r.text
    return pt_id, code, claim


def _score_price(cx_id: int, snap_id: int = SNAP) -> tuple[int | None, str | None]:
    """파이프라인 점수 입력(``scheduler.inputs.load_facts``)의 구매가 상한·라벨."""
    from app.scheduler.inputs import load_facts

    with get_session() as s:
        snap = s.get(Snapshot, snap_id)
        assert snap is not None
        region = s.get(Region, snap.region_id)
        assert region is not None
        f = next(x for x in load_facts(s, snap, region) if x.row.id == cx_id)
        return f.price_high, f.price_label


# ====================================================================== C-1 · D12-2


def test_c1_new_notice_with_same_contradicted_price_stays_demoted(client: TestClient) -> None:
    as_live()  # D13-1: 실시간 계산 경로(발행 전 리비전)를 본다
    won = 658_140_000
    pt_id, code, _ = _demote_price(client, won)
    detail = client.get(f"/api/complexes/{CX}", params={"snapshot": SNAP}, headers=READ).json()
    assert detail["price"]["price_high"]["reason"] == "검증 모순"
    # 같은 모순 가격을 실은 새 공고(무순위) — 정규화기가 새 납부 조건 행을 만든다
    store_notice(CX, "2026990001", {"effective_from": "2026-10-08", "notice_kind": "무순위",
                                    f"price_by_type.{code}.max_price_won": won})  # fmt: skip
    with get_session() as s:
        new_pt = s.scalars(select(PaymentTerms).where(PaymentTerms.notice_no == "2026990001")).one()
        assert new_pt.id != pt_id and (new_pt.price_by_type or {})[code]["max_price_won"] == won
    detail = client.get(f"/api/complexes/{CX}", params={"snapshot": SNAP}, headers=READ).json()
    high = detail["price"]["price_high"]
    assert high["v"] is None and high["label"] == "확인 불가" and high["reason"] == "검증 모순", (
        f"새 공고 행에 같은 모순 가격 → 강등 유지(D12-2), 받은 값 {high}"
    )
    items = client.get(f"/api/snapshots/{SNAP}/complexes", params={"size": 200}, headers=READ).json()["items"]
    row = next(i for i in items if i["complex_id"] == CX)
    assert row["price_mid"]["v"] is None, "목록도 강등 유지"
    assert _score_price(CX)[0] is None, "점수 입력도 강등 유지"
    with get_session() as s:
        d = s.scalars(select(FactDemotion)).one()
        assert d.restored_at is None, "같은 값 새 공고는 강등을 풀지 않는다"


def test_c1_new_notice_with_same_contradicted_down_payment_stays_demoted(client: TestClient) -> None:
    as_live()  # D13-1: 실시간 계산 경로(발행 전 리비전)를 본다
    from app.analysis.price_view import current_terms
    from app.models import FieldProvenance

    with get_session() as s:
        pt = current_terms(list(s.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == CX))))
        assert pt is not None
        name = s.get(Complex, CX).name  # type: ignore[union-attr]

    with get_session() as s:
        pt = s.get(PaymentTerms, pt.id)
        assert pt is not None
        for fp in s.scalars(select(FieldProvenance).where(FieldProvenance.entity == "payment_terms",
                                                          FieldProvenance.entity_id == pt.id,
                                                          FieldProvenance.field == "down_payment_pct")):  # fmt: skip
            fp.chosen = False
        pt.down_payment_pct = 20  # type: ignore[assignment]
        s.add(FieldProvenance(entity="payment_terms", entity_id=pt.id, field="down_payment_pct", value_text="20%",
                              value_norm="20", url="https://www.applyhome.co.kr/", checked_at="2026-10-07",
                              label="확인됨", source_rank=1, chosen=True, excerpt="계약금 20%"))  # fmt: skip
    claim = _fact_claim(field_text="계약금 비율은 20%이다")
    r = client.patch(f"/api/claims/{claim}", json={"text": f"{name} 계약금 비율은 10%이다"}, headers=WRITE)
    assert r.status_code == 202, r.text
    store_notice(
        CX, "2026990002", {"effective_from": "2026-10-08", "notice_kind": "무순위", "down_payment_pct": 20.0}
    )
    detail = client.get(f"/api/complexes/{CX}", params={"snapshot": SNAP}, headers=READ).json()
    cur = next(p for p in detail["payment"] if p["notice_no"] == "2026990002")
    assert cur["is_current"], "새 공고가 현재 조건"
    assert cur["down_payment_pct"]["v"] is None and cur["down_payment_pct"]["reason"] == "검증 모순", (
        f"새 공고 행에 같은 모순 계약금 → 강등 유지(D12-2): {cur['down_payment_pct']}"
    )


# ====================================================================== C-2 · D12-1


class _CxField:
    """단지 필드 1개 후보(청약홈 목록·상세 — 같은 rank 다른 종류 = 채택 보류 → compare)."""

    def __init__(self, key: str, field: str, value: Any, kind: str, observed_on: str) -> None:
        self.key, self.field, self.value, self.kind, self.observed_on = key, field, value, kind, observed_on

    def parse(self, raw: RawDocumentDTO) -> list[FieldCandidate]:
        c = FieldCandidate(
            entity="complex", entity_id=None, entity_key=self.key, field=self.field, value_text=str(self.value),
            value=self.value, source_rank=1, source_kind=self.kind, primary=True, label="확인됨",  # type: ignore[arg-type]
            excerpt=f"{self.field} {self.value}", excerpt_start=0, excerpt_end=1, raw_document_id=raw.id, url=raw.url,
            checked_at=self.observed_on, observed_on=self.observed_on,
        )  # fmt: skip
        return [c]


def store_cx_field(cx_id: int, field: str, value: Any, kind: str, observed_on: str, tag: str) -> None:
    from app.normalize.store import store_raw_document

    with get_session() as s:
        cx = s.get(Complex, cx_id)
        assert cx is not None and cx.applyhome_id
        raw = RawDocument(
            source_kind=kind, url=f"https://www.applyhome.co.kr/{kind}/{tag}", fetched_at=f"{observed_on}T09:00:00+09:00",
            http_status=200, sha256=hashlib.sha256(f"{tag}{field}{value}".encode()).hexdigest(),
            region_id=cx.region_id, complex_id=cx.id,
        )  # fmt: skip
        s.add(raw)
        s.flush()
        store_raw_document(s, raw, parser=_CxField(cx.applyhome_id, field, value, kind, observed_on))


def human_check(
    client: TestClient, field: str, value: str, *, cx: int = CX, day: str = "2026-10-09"
) -> dict[str, Any]:
    r = client.post(
        "/api/ops/human-checks", headers=WRITE,
        json={"complex_id": cx, "field": field, "value_text": value, "kind": "phone",
              "checked_at": f"{day}T10:00:00+09:00", "entered_by": "운영자"},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return out


def test_c2_compare_adoption_after_human_check_does_not_win(client: TestClient) -> None:
    """같은 rank 다른 종류 상충(채택 보류) → 사람 확인 → compare 가 한쪽을 채택해도 사람 확인 값이 남는다(C-2)."""
    as_live()  # D13-1: 실시간 계산 경로(발행 전 리비전)를 본다
    from app.normalize.judged import apply_compare
    from app.scheduler.inputs import load_facts

    store_cx_field(CX, "move_in_ym", "2027-03", "applyhome_detail", "2026-09-01", "a")
    store_cx_field(CX, "move_in_ym", "2027-09", "applyhome_list", "2026-09-02", "b")
    with get_session() as s:
        assert s.get(Complex, CX).move_in_ym is None, "채택 보류(점수 미사용)"  # type: ignore[union-attr]
    human_check(client, "move_in_ym", "2027-06")
    with get_session() as s:
        res = apply_compare(
            s, f"complex:{CX}:move_in_ym", relation="contradicts", judgment_seq=None, snapshot_id=SNAP
        )
        assert res.chosen_id is not None
        assert s.get(Complex, CX).move_in_ym == "2027-06", "compare 채택이 사람 확인을 이기면 안 된다(C-2)"  # type: ignore[union-attr]
    detail = client.get(f"/api/complexes/{CX}", params={"snapshot": SNAP}, headers=READ).json()
    move_in = detail["header"]["move_in_ym"]
    assert move_in["v"] == "2027-06" and move_in["label"] == "확인됨", move_in
    with get_session() as s:
        snap = s.get(Snapshot, SNAP)
        assert snap is not None
        region = s.get(Region, snap.region_id)
        assert region is not None
        f = next(x for x in load_facts(s, snap, region) if x.row.id == CX)
        assert f.row.move_in_ym == "2027-06" and f.labels["move_in"] == "확인됨", "점수 입력도 사람 확인 값"


def test_d12_1_new_official_notice_after_human_check_is_adopted_with_review(client: TestClient) -> None:
    from app.models import ChangeEvent, ChecklistItem

    from .test_r3b_g3 import _ensure_resale

    _ensure_resale(12)
    human_check(client, "resale_months", "24")
    store_cx_field(CX, "resale_months", 36, "notice_pdf", "2026-10-12", "after")
    detail = client.get(f"/api/complexes/{CX}", params={"snapshot": SNAP}, headers=READ).json()
    assert detail["header"]["resale_months"]["v"] == 36, "사람 확인 이후 새 공식 공고 값 채택(D12-1)"
    with get_session() as s:
        crit = [e for e in s.scalars(select(ChangeEvent).where(ChangeEvent.complex_id == CX, ChangeEvent.field == "resale_months"))
                if e.severity == "critical" and e.new_text and "36" in e.new_text]  # fmt: skip
        assert crit, "critical change_event"
        items = [i for i in s.scalars(select(ChecklistItem).where(ChecklistItem.complex_id == CX))
                 if i.title.startswith("사람 확인 재검토")]  # fmt: skip
        assert len(items) == 1 and items[0].status == "open"
    listed = client.get("/api/ops/checklist", params={"complex_id": CX}, headers=WRITE).json()
    assert any(i["title"].startswith("사람 확인 재검토") for i in listed)


# ====================================================================== C-4 · M-16


def run_jobs(job_name: str) -> list[int]:
    """큐의 그 이름 잡을 실제 worker 실행 함수(``scheduler.runner.execute``)로 돌린다 → 잡 id."""
    from app.core.db import get_sessionmaker
    from app.models import JobRun
    from app.scheduler.context import SchedulerContext
    from app.scheduler.runner import claim, execute

    def no_judge() -> Any:
        raise AssertionError("판정기를 부르면 안 된다")

    ctx = SchedulerContext(session_factory=get_sessionmaker(), adapter_factory=no_judge, collectors={})
    with get_session() as s:
        ids = list(
            s.scalars(
                select(JobRun.id)
                .where(JobRun.job_name == job_name, JobRun.status == "queued")
                .order_by(JobRun.id)
            )
        )
    for jid in ids:
        assert claim(ctx, jid)
        execute(ctx, jid)
    return ids


def _revision_of(snap_id: int, *, publish: bool = True) -> int:
    from app.scheduler.snapshots import new_revision

    with get_session() as s:
        base = s.get(Snapshot, snap_id)
        assert base is not None
        rev = new_revision(s, base, reason="테스트 리비전", created_at="2026-10-09T09:00:00+09:00")
        if publish:  # 실제 발행 경로(파생 행 이월 → publish → 저장본, D13-1)
            from app.scheduler.persist import carry_forward
            from app.scheduler.snapshots import publish as do_publish

            carry_forward(s, base.id, rev.id, created_at="2026-10-09T09:01:00+09:00")
            rev.status = "ready"
            ok, n = do_publish(s, rev.id, now="2026-10-09T09:05:00+09:00")
            assert ok, n
        return int(rev.id)


def test_c4_report_files_of_same_asof_revisions_do_not_overwrite(client: TestClient) -> None:
    import hashlib as _h
    from pathlib import Path

    rev = _revision_of(SNAP)
    j1 = client.post("/api/reports", json={"snapshot_id": SNAP, "format": "html"}, headers=WRITE)
    j2 = client.post("/api/reports", json={"snapshot_id": rev, "format": "html"}, headers=WRITE)
    j3 = client.post("/api/reports", json={"snapshot_id": rev, "format": "html"}, headers=WRITE)
    assert j1.status_code == j2.status_code == j3.status_code == 202, (j1.text, j2.text)
    done = run_jobs("report")
    assert len(done) == 3
    reports = {r["id"]: r for r in client.get("/api/reports", headers=READ).json()}
    names = [reports[i]["filename"] for i in done]
    assert all(reports[i]["status"] == "done" for i in done), [reports[i] for i in done]
    assert len(set(names)) == 3, f"같은 기준일 리비전·잡끼리 파일 이름이 겹치면 덮어쓴다(C-4): {names}"
    assert "-r2" in names[1] and "-r1" in names[0], names
    for i in done:
        r = client.get(f"/api/reports/{i}", headers=READ)
        assert r.status_code == 200
        assert _h.sha256(r.content).hexdigest() == reports[i]["sha256"], "다운로드 내용 = 잡 stats sha256"
    from app.core.settings import get_settings

    assert len(list(Path(get_settings().report_dir).glob("report_*.html"))) == 3


def test_m16_building_revision_cannot_make_report(client: TestClient) -> None:
    rev = _revision_of(SNAP, publish=False)
    r = client.post("/api/reports", json={"snapshot_id": rev, "format": "html"}, headers=WRITE)
    assert r.status_code == 409 and "발행 전" in r.json()["detail"], r.text


# ====================================================================== M-1 · M-2 · M-3 · D12-5


def _event_after_run(cx_id: int, snapshot_id: int = SNAP) -> None:
    from app.models import ChangeEvent

    with get_session() as s:
        s.add(ChangeEvent(snapshot_id=snapshot_id, entity="complex", entity_id=cx_id, field="move_in_ym", old_text="2028-01",
                          new_text="2028-06", detected_at="2099-01-01T00:00:00+09:00", severity="notice",
                          triggers_rejudge=True, complex_id=cx_id))  # fmt: skip


def test_m1_building_revision_does_not_hide_rejudge_badge(client: TestClient) -> None:
    """계약 .10(D13-1·M6): 발행 리비전 응답은 저장본(배지도 발행 순간 값) — 이후 이벤트·새 리비전이 바꾸지 않는다. '재판정
    필요'는 실시간(발행 전) 리비전에서 늘 지금 사실과 비교하고, 더 새 판정 중 리비전이 생겨도 사라지지 않는다(M-1)."""
    from ._support import as_live

    before = client.get(f"/api/snapshots/{SNAP}/complexes", params={"size": 200}, headers=READ).content
    _event_after_run(CX)
    _revision_of(SNAP, publish=False)  # 판정 중인 새 리비전(미발행)
    assert (
        client.get(f"/api/snapshots/{SNAP}/complexes", params={"size": 200}, headers=READ).content == before
    )
    as_live()  # SNAP 을 판정 끝·발행 전으로 — 실시간 비교
    with get_session() as s:
        s.add(Snapshot(region_id=1, asof_date="2099-12-30", status="building", degraded=False,
                       created_at="2099-12-30T00:00:00+09:00", revision=1))  # fmt: skip
    items = client.get(f"/api/snapshots/{SNAP}/complexes", params={"size": 200}, headers=READ).json()["items"]
    row = next(i for i in items if i["complex_id"] == CX)
    assert row["rejudge_needed"] is True, "더 새 판정 중 리비전이 배지를 지우면 안 된다(M-1·M6)"


def test_m2_human_check_writes_to_newest_unpublished_asof_not_old_revision(client: TestClient) -> None:
    from app.models import ChangeEvent, JobRun

    with get_session() as s:
        base = s.get(Snapshot, SNAP)
        assert base is not None
        newer = Snapshot(region_id=base.region_id, asof_date="2026-10-20", status="building", degraded=False,
                         created_at="2026-10-20T06:00:00+09:00", revision=1)  # fmt: skip
        s.add(newer)
        s.flush()
        newer_id, region_id, asof = newer.id, base.region_id, base.asof_date
    from .test_r3b_g3 import _ensure_resale

    _ensure_resale(12)
    body = human_check(client, "resale_months", "24")
    with get_session() as s:
        ce = s.get(ChangeEvent, body["change_event_id"])
        assert ce is not None and ce.snapshot_id == newer_id, "더 새 기준일(미발행)에 기록(M-2)"
        revs = list(
            s.scalars(select(Snapshot).where(Snapshot.region_id == region_id, Snapshot.asof_date == asof))
        )
        assert len(revs) == 1, "옛 기준일에 리비전을 만들면 안 된다"
        job = s.get(JobRun, body["rejudge_job_id"])
        assert job is not None and job.job_name == "rejudge" and job.status == "queued", "자동 등록(D12-5)"
        assert job.payload["snapshot_id"] == newer_id and job.payload["complex_ids"] == [CX]
    assert body["suggested_job"] == {"job_name": "rejudge", "payload": job.payload}, (
        "호환: 자동 등록 잡과 같은 payload"
    )


def test_d12_5_human_check_on_published_latest_creates_revision_and_rejudge(client: TestClient) -> None:
    from app.models import ChangeEvent, JobRun

    from ._support import validate
    from .test_r3b_g3 import _ensure_resale

    _ensure_resale(12)
    r = client.post(
        "/api/ops/human-checks", headers=WRITE,
        json={"complex_id": CX, "field": "resale_months", "value_text": "24", "kind": "phone",
              "checked_at": "2026-10-09T10:00:00+09:00", "entered_by": "운영자"},
    )  # fmt: skip
    assert r.status_code == 201
    body = r.json()
    validate("createHumanCheck", 201, body)
    with get_session() as s:
        ce = s.get(ChangeEvent, body["change_event_id"])
        assert ce is not None and ce.snapshot_id != SNAP, (
            "발행 스냅샷에 change_event 를 붙이지 않는다(새 리비전)"
        )
        rev = s.get(Snapshot, ce.snapshot_id)
        assert rev is not None and rev.revision == 2 and rev.status == "building" and rev.revision_of == SNAP
        job = s.get(JobRun, body["rejudge_job_id"])
        assert job is not None and job.payload["snapshot_id"] == rev.id


def test_d12_5_carry_forward_rejudges_complexes_changed_after_previous_run(client: TestClient) -> None:
    """사람 확인 뒤 다음 날 수집에 변경이 없어도, 이전 판정 뒤 바뀐 사실이 있으면 옛 점수를 복사하지 않고 재판정(M-3)."""
    from app.core.db import get_sessionmaker
    from app.models import JobRun, ScoreRun
    from app.scheduler.context import SchedulerContext
    from app.scheduler.handlers import _after_daily

    # 사람 확인이 만든 리비전(판정 중 — 재판정이 아직 안 돈)에 붙은 변경: 다음 날 이월이 옛 점수를 복사하면 안 된다
    rev = _revision_of(SNAP, publish=False)
    _event_after_run(CX, snapshot_id=rev)
    with get_session() as s:
        base = s.get(Snapshot, SNAP)
        assert base is not None
        nxt = Snapshot(region_id=base.region_id, asof_date="2026-10-21", status="building", degraded=False,
                       created_at="2026-10-21T06:00:00+09:00", revision=1)  # fmt: skip
        s.add(nxt)
        s.flush()
        nid = nxt.id
    ctx = SchedulerContext(session_factory=get_sessionmaker(), adapter_factory=lambda: None, collectors={})  # type: ignore[arg-type,return-value]
    out = _after_daily(ctx, nid, [], [])
    assert "rejudge_job_id" in out, out
    with get_session() as s:
        assert not list(s.scalars(select(ScoreRun).where(ScoreRun.snapshot_id == nid))), "옛 점수 이월 없음"
        job = s.get(JobRun, out["rejudge_job_id"])
        assert job is not None and CX in job.payload["complex_ids"]


# ====================================================================== C-3 · D12-3


@pytest.mark.parametrize(("label", "applied"), [("추정", False), ("확인됨", True)])
def test_c3_discount_rule_is_the_same_on_every_price_path(
    client: TestClient, label: str, applied: bool
) -> None:
    """할인 차감(확인됨만)이 상세·목록(값·필터·정렬)·비교(계약금·자기자본)·보고서·점수 입력에서 같은 값(D12-3)."""
    as_live()  # D13-1: 실시간 계산 경로(발행 전 리비전)를 본다
    from app.reports.data import load_report
    from app.scheduler.inputs import load_facts

    from .test_discount_by_type import WON, _set_discount

    cx1 = 1

    def detail() -> dict[str, Any]:
        out: dict[str, Any] = client.get(
            f"/api/complexes/{cx1}", params={"snapshot": SNAP}, headers=READ
        ).json()
        return out

    base_low = detail()["price"]["price_low"]["v"]
    assert isinstance(base_low, int)
    _set_discount(label)
    want_low = base_low - (WON if applied else 0)
    price = detail()["price"]
    assert price["price_low"]["v"] == want_low, "상세"
    mid = price["price_mid"]["v"]
    items = client.get(f"/api/snapshots/{SNAP}/complexes", params={"size": 200}, headers=READ).json()["items"]
    row = next(i for i in items if i["complex_id"] == cx1)
    assert row["price_low"]["v"] == want_low and row["price_mid"]["v"] == mid, "목록 값"
    got = client.get(
        f"/api/snapshots/{SNAP}/complexes", params={"size": 200, "filter[price_min]": mid}, headers=READ
    ).json()
    assert cx1 in [i["complex_id"] for i in got["items"]], "목록 필터(하한 = 상세 mid)"
    got = client.get(
        f"/api/snapshots/{SNAP}/complexes", params={"size": 200, "filter[price_max]": mid - 1}, headers=READ
    ).json()
    assert cx1 not in [i["complex_id"] for i in got["items"]], "목록 필터(상한 = 상세 mid − 1)"
    sorted_rows = client.get(
        f"/api/snapshots/{SNAP}/complexes", params={"size": 200, "sort": "price_low"}, headers=READ
    ).json()["items"]
    lows = [r["price_low"]["v"] for r in sorted_rows if r["price_low"]["v"] is not None]
    assert lows == sorted(lows) and want_low in lows, "목록 정렬 키 = 같은 값"
    cmp = client.get(f"/api/snapshots/{SNAP}/compare", params={"ids": f"{cx1},{CX}"}, headers=READ).json()
    term = next(t for t in cmp["terms"] if t["complex_id"] == cx1)
    pct = term["down_payment_pct"]["v"]
    if pct is not None:
        assert term["down_payment_won"]["v"] == round(mid * pct / 100), "비교 계약금 = 상세 mid 기준"
    with get_session() as s:
        data = load_report(s, SNAP, scenario_id=None, compare_snapshot_id=None)
        view = next(c for c in data.complexes if c.id == cx1)
        assert view.price_low.v == want_low, f"보고서 {view.price_low.v} ≠ 상세 {want_low}"
        assert ("할인" in (view.price_low.reason or "")) is applied, view.price_low.reason
        snap = s.get(Snapshot, SNAP)
        assert snap is not None
        region = s.get(Region, snap.region_id)
        assert region is not None
        f = next(x for x in load_facts(s, snap, region) if x.row.id == cx1)
        assert f.price_low == want_low, "점수 입력"


# ====================================================================== M-11 · M-13 · 호재 minor


def test_m11_same_id_in_complex_type_and_payment_terms_targets_current_price_row(client: TestClient) -> None:
    from sqlalchemy import func

    from app.analysis.price_view import basis_type
    from app.models import ComplexType, FieldProvenance

    with get_session() as s:
        t = basis_type(list(s.scalars(select(ComplexType).where(ComplexType.complex_id == CX))))
        assert t is not None
        # 같은 번호(N)의 공고문 타입 행(소형 — 기준 타입 아님)과 납부 조건 행(현재 공고)을 같은 단지에 만든다
        n = 1 + max(
            s.scalar(select(func.max(ComplexType.id))) or 0, s.scalar(select(func.max(PaymentTerms.id))) or 0
        )
        s.add(ComplexType(id=n, complex_id=CX, type_code="39Z", area_m2=39))
        won = 660_000_000
        pt = PaymentTerms(id=n, complex_id=CX, notice_no="SAMEID", notice_kind="임의", effective_from="2026-10-01",
                          interim_schedule=[], price_by_type={t.type_code: {"max_price_won": won}})  # fmt: skip
        s.add(pt)
        s.flush()
        s.add(FieldProvenance(entity="payment_terms", entity_id=pt.id, field=f"price_by_type.{t.type_code}.max_price_won",
                              value_text=f"{won:,}", value_norm=str(won), url="https://www.applyhome.co.kr/", checked_at="2026-10-07",
                              label="확인됨", source_rank=1, chosen=True, excerpt=f"공급금액 {won:,}"))  # fmt: skip
        tid, code = n, t.type_code
    r = client.post(
        "/api/ops/human-checks", headers=WRITE,
        json={"complex_id": CX, "field": "max_price_won", "entity_id": tid, "value_text": "655000000", "kind": "phone",
              "checked_at": "2026-10-09T10:00:00+09:00", "entered_by": "운영자"},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["entity"], body["entity_id"]) == ("payment_terms", tid), (
        "화면·점수가 쓰는 현재 공고 가격 행(M-11)"
    )
    with get_session() as s:
        pt2 = s.get(PaymentTerms, tid)
        assert pt2 is not None and (pt2.price_by_type or {})[code]["max_price_won"] == 655_000_000, (
            "현재 공고 가격이 바뀐다"
        )
        t2 = s.get(ComplexType, tid)
        assert t2 is not None and t2.max_price_won is None, "같은 번호의 다른 타입 행은 그대로"


def test_m13_catalyst_nan_or_out_of_range_coordinates_are_422_without_writes(client: TestClient) -> None:
    from app.models import Catalyst

    with get_session() as s:
        cat = Catalyst(region_id=1, name="좌표 검사 역", kind="교통", stage="계획", location_confirmed=False)
        s.add(cat)
        s.flush()
        cat_id = cat.id
    for bad in ({"lat": float("nan")}, {"lon": float("inf")}, {"lat": 91.0}):
        r = client.patch(f"/api/catalysts/{cat_id}", content=__import__("json").dumps(
            {"location_confirmed": True, "complex_ids": [CX], **bad}), headers={**WRITE, "Content-Type": "application/json"})  # fmt: skip
        assert r.status_code == 422, (bad, r.status_code, r.text)
    with get_session() as s:
        c = s.get(Catalyst, cat_id)
        assert c is not None and c.lat is None and c.location_confirmed is False, "쓰기 전에 거부"
    assert client.get(f"/api/complexes/{CX}", params={"snapshot": SNAP}, headers=READ).status_code == 200


def test_minor_not_catalyst_cannot_be_linked_and_expected_ym_can_be_cleared(client: TestClient) -> None:
    from app.models import Catalyst

    with get_session() as s:
        no = Catalyst(
            region_id=1, name="호재 아님 후보", kind="기타", stage="호재 아님", location_confirmed=False
        )
        yes = Catalyst(region_id=1, name="예정월 지우기", kind="교통", stage="계획", location_confirmed=False)
        s.add_all([no, yes])
        s.flush()
        no_id, yes_id = no.id, yes.id
    r = client.patch(
        f"/api/catalysts/{no_id}", json={"location_confirmed": True, "complex_ids": [CX]}, headers=WRITE
    )
    assert r.status_code == 422, r.text
    r = client.patch(
        f"/api/catalysts/{yes_id}",
        json={"location_confirmed": False, "expected_ym": "2029-01"},
        headers=WRITE,
    )
    assert r.status_code == 200 and r.json()["catalyst"]["expected_ym"]["v"] == "2029-01"
    r = client.patch(
        f"/api/catalysts/{yes_id}", json={"location_confirmed": False, "expected_ym": None}, headers=WRITE
    )
    assert r.status_code == 200, r.text
    assert r.json()["catalyst"]["expected_ym"]["v"] is None, "null 로 지운다"


# ====================================================================== M-7 · D12-4 (리비전 3개, 옛 리비전 바이트 불변)


def test_d12_4_old_revision_responses_do_not_change_after_later_edits(client: TestClient) -> None:
    """발행 리비전 2(얼린 값) → 리비전 3 발행으로 옛 리비전이 된 뒤, 분류·생활권 이름·호재 단계·연결을 바꾸고 리비전을 더
    만들어도 리비전 2 의 상세·목록·시장·대시보드 응답 바이트와 보고서 데이터(생활권·호재·분류)가 그대로다(M-7)."""
    from app.models import Catalyst
    from app.reports.data import load_report
    from app.scheduler.snapshots import republish

    with get_session() as s:
        cat = Catalyst(region_id=1, name="리비전 테스트 역", kind="교통", stage="계획", location_confirmed=False)  # fmt: skip
        s.add(cat)
        s.flush()
        cat_id = cat.id
    r = client.patch(
        f"/api/catalysts/{cat_id}", json={"location_confirmed": True, "complex_ids": [CX]}, headers=WRITE
    )
    assert r.status_code == 200, r.text  # → 리비전 2(발행·얼림)
    with get_session() as s:
        rev2 = s.scalars(select(Snapshot).where(Snapshot.region_id == 1).order_by(Snapshot.id.desc())).first()
        assert rev2 is not None and rev2.status == "published" and rev2.revision == 2
        rev2_id = rev2.id
        rev3 = republish(s, 1, reason="테스트 리비전 3", created_at="2026-10-09T12:00:00+09:00")
        assert rev3 is not None and rev3.revision == 3
    urls = [
        f"/api/complexes/{CX}?snapshot={rev2_id}",
        f"/api/snapshots/{rev2_id}/complexes?size=200",
        f"/api/snapshots/{rev2_id}/market",
        f"/api/snapshots/{rev2_id}/dashboard",
    ]
    before = {u: client.get(u, headers=READ) for u in urls}
    assert all(r.status_code == 200 for r in before.values()), {u: r.text[:200] for u, r in before.items()}
    detail = before[urls[0]].json()
    assert any(c["id"] == cat_id for c in detail["catalysts"]), "리비전 2 에 그 시점 연결"

    def report_view() -> tuple[Any, ...]:
        with get_session() as s:
            data = load_report(s, rev2_id, scenario_id=None, compare_snapshot_id=None)
            cx = next(c for c in data.complexes if c.id == CX)
            return (
                [(a.get("id"), a.get("name")) for a in data.living_areas],
                sorted((c.name, c.stage) for c in data.catalysts),
                (cx.living_area, cx.living_area_name, cx.inclusion_class),
            )

    rep_before = report_view()
    # 나중 편집: 분류(classify 재판정 결과)·생활권 이름·호재 단계(호재 아님)·연결 해제 + 리비전 더
    with get_session() as s:
        cx = s.get(Complex, CX)
        assert cx is not None
        cx.inclusion_class = "범위 경계"
        c2 = s.get(Catalyst, cat_id)
        assert c2 is not None
        c2.stage = "호재 아님"
    region = client.get("/api/regions/1", headers=READ).json()
    areas = [
        {"id": a["id"], "name": a["name"] + " (개명)", "legal_dong_codes": a["legal_dong_codes"]}
        for a in region["living_areas"]
    ]
    r = client.put("/api/regions/1/living-areas", json={"living_areas": areas}, headers=WRITE)
    assert r.status_code == 200, r.text
    r = client.patch(f"/api/catalysts/{cat_id}", json={"location_confirmed": False}, headers=WRITE)
    assert r.status_code == 200, r.text
    after = {u: client.get(u, headers=READ) for u in urls}
    for u in urls:
        assert after[u].content == before[u].content, f"옛 리비전 응답이 바뀌었다(D12-4): {u}"
    assert report_view() == rep_before, "옛 리비전 보고서 데이터(생활권·호재·분류) 불변"
    # 지금 값(판정 중인 새 리비전 — 아직 얼리지 않음)은 바뀐 값을 본다
    with get_session() as s:
        newest = s.scalars(
            select(Snapshot).where(Snapshot.region_id == 1).order_by(Snapshot.id.desc())
        ).first()
        assert newest is not None and newest.status == "building" and newest.id != rev2_id
    live = client.get(f"/api/snapshots/{newest.id}/market", headers=READ).json()
    assert all(c["id"] != cat_id for c in live["catalysts"]), "새 리비전에는 '호재 아님'이 빠진다"


# ====================================================================== 보안·사람 확인 minor


def test_minor_complex_detail_rejects_snapshot_of_other_region(client: TestClient) -> None:
    from app.models import Region

    with get_session() as s:
        other = Region(name="다른 지역", query_text="x", selections=[], sido_codes=[], sigungu_codes=[],
                       legal_dong_codes=[], living_areas=[], age_premium_coef={}, applyhome_query={}, status="ready",
                       created_at="2026-10-09")  # fmt: skip
        s.add(other)
        s.flush()
        snap = Snapshot(region_id=other.id, asof_date="2026-10-08", status="published", degraded=False,
                        created_at="2026-10-08", revision=1)  # fmt: skip
        s.add(snap)
        s.flush()
        sid = snap.id
    r = client.get(f"/api/complexes/{CX}", params={"snapshot": sid}, headers=READ)
    assert r.status_code == 404, r.text


@pytest.mark.parametrize(
    ("field", "text", "ok"),
    [
        ("resale_months", "3년", 36),  # 개월 필드의 'N년' = N×12 (예전: 3개월)
        ("resale_months", "1E1", None),  # 지수 표기 거부(예전: 10)
        ("resale_months", "12%", None),  # 다른 단위
        ("down_payment_pct", "10%", 10.0),
        ("down_payment_pct", "10년", None),
    ],
)
def test_minor_human_value_units_and_plain_numbers(
    client: TestClient, field: str, text: str, ok: Any
) -> None:
    from app.api.demotion import ValueParseError, human_target, parse_human_value

    from .test_r3b_g3 import _ensure_resale

    _ensure_resale(12)
    with get_session() as s:
        target = human_target(s, CX, field)
        assert target is not None
        if ok is None:
            with pytest.raises(ValueParseError):
                parse_human_value(target, text)
        else:
            assert parse_human_value(target, text) == ok

"""판정기 결과 반영(계약 2026-10-09.3): needs_extract 추출값·audit flagged·compare contradicts 채택 변경."""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ChangeEvent, Complex, ComplexType, FieldProvenance, RawDocument, Region
from app.normalize.extract_request import ExtractRequest
from app.normalize.judged import (
    AuditMark,
    ExtractedValue,
    apply_compare,
    apply_extracted,
    parse_extracted,
)
from app.normalize.provenance import fact_for
from app.normalize.store import store_raw_document

from ._support import NOTICE, AddRaw, notice_manifest

CENTREVILLE = "2025000435_centreville.txt"


def _store_centreville(db_session: Session, region: Region, add_raw: AddRaw) -> tuple[ExtractRequest, int]:
    raw = add_raw(
        (NOTICE / CENTREVILLE).read_text(encoding="utf-8"),
        source_kind="notice_pdf",
        url=str(notice_manifest()[CENTREVILLE]["url"]),
        region_id=region.id,
    )
    res = store_raw_document(db_session, raw)
    req = next(r for r in res.extract_requests if r.entity_key == "2025000435:120P")
    t120 = db_session.scalars(select(ComplexType).where(ComplexType.type_code == "120P")).one()
    assert t120.max_price_won is None and "max_price_won" in req.fields
    return req, t120.id


def _rows(db_session: Session, type_id: int) -> list[FieldProvenance]:
    return list(
        db_session.scalars(
            select(FieldProvenance)
            .where(
                FieldProvenance.entity == "complex_type",
                FieldProvenance.entity_id == type_id,
                FieldProvenance.field == "max_price_won",
            )
            .order_by(FieldProvenance.id)
        )
    )


def test_extract_auto_with_audit_pass_is_confirmed(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    req, tid = _store_centreville(db_session, region, add_raw)
    out = apply_extracted(
        db_session,
        req,
        [ExtractedValue("max_price_won", "699,400,000원", "auto")],
        judgment_seq=11,
        audit={"max_price_won": AuditMark(flagged=False, p_wrong=0.05)},
        audit_seq=12,
    )
    assert set(out.applied) == {"max_price_won"} and not out.flagged
    t = db_session.get(ComplexType, tid)
    assert t is not None and t.max_price_won == 699_400_000
    rows = _rows(db_session, tid)
    assert len(rows) == 2  # 원래 '확인 불가' 출처 행은 남고(채택 아님), 추출 출처 행이 채택
    origin, judged = rows
    assert origin.label == "확인 불가" and not origin.chosen
    assert judged.chosen and judged.label == "확인됨" and judged.value_norm == "699400000"
    assert judged.reason is not None and "jl_11" in judged.reason and "jl_12" in judged.reason
    assert judged.raw_document_id == origin.raw_document_id and judged.excerpt == origin.excerpt
    assert judged.source_rank == origin.source_rank and judged.url and judged.checked_at
    fact = fact_for(db_session, "complex_type", tid, "max_price_won")
    assert fact["label"] == "확인됨" and fact["prov"] == f"fp_{judged.id}" and fact["v"] == 699_400_000
    ev = db_session.scalars(
        select(ChangeEvent).where(ChangeEvent.entity == "complex_type", ChangeEvent.field == "max_price_won")
    ).all()
    assert ev and ev[-1].entity_id == tid


def test_extract_auto_without_audit_is_estimate(db_session: Session, region: Region, add_raw: AddRaw) -> None:
    req, tid = _store_centreville(db_session, region, add_raw)
    apply_extracted(
        db_session, req, [ExtractedValue("max_price_won", "6억 9,940만원", "auto")], judgment_seq=21
    )
    judged = next(r for r in _rows(db_session, tid) if r.chosen)
    assert judged.label == "추정" and judged.reason == "판정기 추출 jl_21(감사 전)"
    t = db_session.get(ComplexType, tid)
    assert t is not None and t.max_price_won == 699_400_000


def test_extract_review_is_not_applied(db_session: Session, region: Region, add_raw: AddRaw) -> None:
    req, tid = _store_centreville(db_session, region, add_raw)
    out = apply_extracted(
        db_session, req, [ExtractedValue("max_price_won", "699,400,000원", "review")], judgment_seq=31
    )
    assert out.skipped == {"max_price_won": "review(미반영)"} and not out.applied
    assert len(_rows(db_session, tid)) == 1
    t = db_session.get(ComplexType, tid)
    assert t is not None and t.max_price_won is None
    assert fact_for(db_session, "complex_type", tid, "max_price_won")["label"] == "확인 불가"


def test_audit_flagged_withdraws_value(db_session: Session, region: Region, add_raw: AddRaw) -> None:
    req, tid = _store_centreville(db_session, region, add_raw)
    value = [ExtractedValue("max_price_won", "699,400,000원", "auto")]
    apply_extracted(db_session, req, value, judgment_seq=41)  # 감사 전 반영(추정)
    out = apply_extracted(
        db_session,
        req,
        value,
        judgment_seq=41,
        audit={"max_price_won": AuditMark(flagged=True, p_wrong=0.9)},
        audit_seq=42,
    )
    assert set(out.flagged) == {"max_price_won"} and not out.applied
    rows = _rows(db_session, tid)
    assert len(rows) == 2  # 같은 추출 출처 행을 갱신(새 행 없음)
    judged = rows[1]
    assert judged.label == "확인 불가" and judged.value_norm is None
    assert judged.reason is not None and judged.reason.startswith("판정기 감사 flagged jl_42")
    assert judged.value_text == "699,400,000원"  # 원문 대조용으로 남긴다
    t = db_session.get(ComplexType, tid)
    assert t is not None and t.max_price_won is None  # 사실 테이블 값도 거둔다
    assert fact_for(db_session, "complex_type", tid, "max_price_won")["label"] == "확인 불가"


def test_unparseable_value_is_skipped(db_session: Session, region: Region, add_raw: AddRaw) -> None:
    req, tid = _store_centreville(db_session, region, add_raw)
    out = apply_extracted(
        db_session, req, [ExtractedValue("max_price_won", "별도 공지", "auto")], judgment_seq=51
    )
    assert out.skipped == {"max_price_won": "형식 해석 실패"}
    assert len(_rows(db_session, tid)) == 1


@pytest.mark.parametrize(
    ("field", "text", "want"),
    [
        ("max_price_won", "699,400,000원", 699_400_000),
        ("max_price_won", "69,940만원", 699_400_000),
        ("balcony_won", "6억 9,940만 원", 699_400_000),
        ("down_payment_pct", "계약금 10%", 10.0),
        ("resale_months", "1년", 12),
        ("resale_months", "6개월", 6),
        ("residency_months", "해당 없음", 0),
        ("rewin_restriction_years", "10년", 10),
        ("move_in_ym", "2028년 3월 예정", "2028-03"),
        ("effective_from", "2025.07.04", "2025-07-04"),
        ("units_total", "1,573세대", 1573),
        ("interim_schedule", "2026-01-02", None),  # 목록 필드는 반영하지 않는다
    ],
)
def test_parse_extracted(field: str, text: str, want: object) -> None:
    assert parse_extracted(field, text) == want


# ---------------------------------------------------------------- compare


def _raw(db_session: Session, kind: str, n: int) -> RawDocument:
    row = RawDocument(
        source_kind=kind,
        url=f"https://example.test/{kind}/{n}",
        fetched_at="2026-10-09T06:00:00+09:00",
        http_status=200,
        sha256=hashlib.sha256(f"{kind}{n}".encode()).hexdigest(),
    )
    db_session.add(row)
    db_session.flush()
    return row


def _conflict(
    db_session: Session, region: Region, kinds: tuple[str, str], *, chosen_first: bool = True
) -> tuple[Complex, FieldProvenance, FieldProvenance]:
    cx = Complex(
        region_id=region.id, applyhome_id="2099000001", name="테스트 단지", former_names=[], apply_dates=[],
        contract_dates=[], inclusion_class="미분류", builder="가건설",
    )  # fmt: skip
    db_session.add(cx)
    db_session.flush()
    group = f"complex:{cx.id}:builder"
    rows = []
    for i, (kind, value) in enumerate(zip(kinds, ("가건설", "나건설"), strict=True)):
        raw = _raw(db_session, kind, i)
        fp = FieldProvenance(
            entity="complex", entity_id=cx.id, entity_key=cx.applyhome_id, field="builder", value_text=value,
            value_norm=value, raw_document_id=raw.id, url=raw.url, checked_at="2026-10-09", label="확인됨",
            source_rank=2, chosen=(i == 0) == chosen_first, conflict_group=group, excerpt=f"시공: {value}",
        )  # fmt: skip
        db_session.add(fp)
        rows.append(fp)
    db_session.flush()
    return cx, rows[0], rows[1]


def test_compare_contradicts_adopts_primary_notice_and_keeps_other_side_by_side(
    db_session: Session, region: Region
) -> None:
    cx, site, notice = _conflict(db_session, region, ("official_site", "notice_pdf"))
    group = site.conflict_group
    assert group is not None
    res = apply_compare(db_session, group, relation="contradicts", judgment_seq=77)
    assert res.changed and res.chosen_id == notice.id and res.side_ids == [site.id]
    assert notice.chosen and not site.chosen
    assert notice.conflict_group == site.conflict_group == group  # 상충 이력은 그대로
    assert notice.label == site.label == "확인됨"  # 라벨은 바꾸지 않는다
    assert site.reason is not None and "병기" in site.reason and "jl_77" in site.reason
    assert notice.compare_judgment_seq == site.compare_judgment_seq == 77
    assert cx.builder == "나건설"
    assert any(e.field == "builder" for e in res.change_events)
    fact = fact_for(db_session, "complex", cx.id, "builder")
    assert fact["prov"] == f"fp_{notice.id}"


def test_compare_contradicts_keeps_primary_already_chosen(db_session: Session, region: Region) -> None:
    _, notice, site = _conflict(db_session, region, ("notice_pdf", "official_site"))
    assert notice.conflict_group is not None
    res = apply_compare(db_session, notice.conflict_group, relation="contradicts", judgment_seq=78)
    assert not res.changed and notice.chosen and not site.chosen
    assert site.reason is not None and "병기" in site.reason


def test_compare_same_fact_changes_nothing(db_session: Session, region: Region) -> None:
    cx, site, notice = _conflict(db_session, region, ("official_site", "notice_pdf"))
    assert site.conflict_group is not None
    res = apply_compare(db_session, site.conflict_group, relation="same_fact", judgment_seq=79)
    assert not res.changed and site.chosen and not notice.chosen and cx.builder == "가건설"
    assert site.compare_judgment_seq == 79


def test_compare_contradicts_between_secondary_only_is_side_by_side(
    db_session: Session, region: Region
) -> None:
    _, a, b = _conflict(db_session, region, ("official_site", "news"))
    assert a.conflict_group is not None
    res = apply_compare(db_session, a.conflict_group, relation="contradicts", judgment_seq=80)
    assert not res.changed and a.chosen and "판정 미사용" in res.note
    assert all(r.reason and "판정 미사용" in r.reason for r in (a, b))

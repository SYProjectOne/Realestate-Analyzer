"""store: 원문 1개 → 후보 → resolve → upsert + provenance + change_event (한 트랜잭션).

- T5: 해링턴 1,573(청약홈 상세) vs 1,769(공고문) → conflict_group 1건, chosen = 청약홈, 저장 순서 무관
- T9: 임의공급 계약금 10% → 5% → payment_terms 2행, 현재 조건 = 최신, change_event critical
- 모든 수치 필드 provenance 행 존재 전수 검사
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ChangeEvent, Complex, ComplexType, FieldProvenance, PaymentTerms, RawDocument, Region
from app.normalize.changes import current_terms
from app.normalize.provenance import fact_for, missing_provenance
from app.normalize.store import StoreError, store_raw_document

from ._support import APPLYHOME, DETAIL_URL, NOTICE, NOTICE_BASE, AddRaw, dto, notice_manifest


def _notice_url(fname: str) -> str:
    return str(notice_manifest()[fname]["url"])


def _t5_docs() -> tuple[str, str]:
    detail = (APPLYHOME / "detail_2025000271.html").read_text(encoding="utf-8")
    assert '<td class="txt_l">670세대</td>' in detail
    detail = detail.replace('<td class="txt_l">670세대</td>', '<td class="txt_l">1,573세대</td>')
    notice = (NOTICE / "2025000271_harrington1.txt").read_text(encoding="utf-8")
    old = "총 866세대 중 일반분양 670세대"
    assert old in notice
    notice = notice.replace(old, "총 1,769세대")
    return detail, notice


@pytest.mark.parametrize("order", ["applyhome_first", "notice_first"])
def test_t5_conflict_group_one_and_applyhome_chosen(
    order: str, db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    detail, notice = _t5_docs()
    docs = [
        ("applyhome_detail", detail, DETAIL_URL.format(n="2025000271"), "html"),
        ("notice_pdf", notice, _notice_url("2025000271_harrington1.txt"), "txt"),
    ]
    if order == "notice_first":
        docs.reverse()
    for kind, content, url, ext in docs:
        raw = add_raw(content, source_kind=kind, url=url, region_id=region.id, ext=ext)
        store_raw_document(db_session, raw)

    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2025000271")).one()
    assert cx.units_total == 1573
    rows = list(
        db_session.scalars(
            select(FieldProvenance).where(
                FieldProvenance.entity == "complex",
                FieldProvenance.entity_id == cx.id,
                FieldProvenance.field == "units_total",
            )
        )
    )
    assert len(rows) == 2
    groups = {r.conflict_group for r in rows}
    assert groups == {f"complex:{cx.id}:units_total"}
    chosen = [r for r in rows if r.chosen]
    assert len(chosen) == 1 and chosen[0].value_text == "1,573세대"
    assert chosen[0].source_rank == 1
    other = next(r for r in rows if not r.chosen)
    assert other.source_rank == 2 and "1,769" in (other.value_text or "")
    # 출처 패널에 둘 다(원문 발췌 포함) 남는다
    assert all(r.excerpt and r.url and r.checked_at and r.label == "확인됨" for r in rows)


def test_t5_resolved_fields_has_one_conflict_and_no_compare(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    detail, notice = _t5_docs()
    store_raw_document(
        db_session,
        add_raw(
            detail, source_kind="applyhome_detail", url=DETAIL_URL.format(n="2025000271"), region_id=region.id
        ),
    )
    res = store_raw_document(
        db_session,
        add_raw(
            notice,
            source_kind="notice_pdf",
            url=_notice_url("2025000271_harrington1.txt"),
            region_id=region.id,
        ),
    )
    units = [g for g in res.resolved.conflicts if g.field == "units_total"]
    assert len(units) == 1 and units[0].needs_compare is False
    assert units[0].candidates[units[0].chosen_index].source_kind == "applyhome_detail"
    # 가격은 공고문(1) > 청약홈(2): 84A 최고가는 같은 값이라 상충 없음
    assert not [g for g in res.resolved.conflicts if g.field == "max_price_won"]


def test_t9_down_payment_10_to_5_two_rows_current_latest_and_critical_event(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    main = add_raw(
        (NOTICE / "2025000302_elif.txt").read_text(encoding="utf-8"),
        source_kind="notice_pdf",
        url=_notice_url("2025000302_elif.txt"),
        region_id=region.id,
        fetched_at="2025-08-25T06:00:00+09:00",
    )
    store_raw_document(db_session, main)
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2025000302")).one()
    imui = add_raw(
        (NOTICE / "2026940173_elif_imui3.txt").read_text(encoding="utf-8"),
        source_kind="notice_pdf",
        url=_notice_url("2026940173_elif_imui3.txt"),
        region_id=region.id,
        complex_id=cx.id,
        fetched_at="2026-08-15T06:00:00+09:00",
    )
    res = store_raw_document(db_session, imui)

    terms = list(db_session.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == cx.id)))
    assert sorted((t.notice_no, float(t.down_payment_pct or 0)) for t in terms) == [
        ("2025000302", 10.0),
        ("2026940173", 5.0),
    ]
    cur = current_terms(db_session, cx.id)
    assert cur is not None and cur.notice_no == "2026940173" and cur.effective_from == "2026-08-14"
    assert cur.notice_kind == "임의" and cur.down_payment_first_won == 5_000_000
    ev = [e for e in res.change_events if e.entity == "payment_terms" and e.field == "down_payment_pct"]
    assert len(ev) == 1
    assert (ev[0].old_text, ev[0].new_text, ev[0].severity, ev[0].triggers_rejudge) == (
        "10",
        "5",
        "critical",
        True,
    )
    assert any(e.entity == "notice" and e.severity == "critical" for e in res.change_events)
    stored = db_session.scalars(select(ChangeEvent).where(ChangeEvent.complex_id == cx.id)).all()
    assert any(e.field == "down_payment_pct" and e.severity == "critical" for e in stored)
    # 같은 단지 행 1개(임의공급 공고의 단지 키 = 최초 주택관리번호)
    assert db_session.scalar(select(func.count()).select_from(Complex)) == 1


def test_all_numeric_fields_have_provenance_rows(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    """완료 기준: 모든 수치 필드의 provenance 행 존재 전수 검사 — 공고문 발췌 전부 + 청약홈 상세·경쟁률."""
    man = notice_manifest()
    for fname, m in man.items():
        add = add_raw(
            (NOTICE / fname).read_text(encoding="utf-8"),
            source_kind="notice_pdf",
            url=str(m["url"]),
            region_id=region.id,
        )
        store_raw_document(db_session, add)
    for n in ("2025000271", "2025000302", "2025000573"):
        html = (APPLYHOME / f"detail_{n}.html").read_text(encoding="utf-8")
        store_raw_document(
            db_session,
            add_raw(html, source_kind="applyhome_detail", url=DETAIL_URL.format(n=n), region_id=region.id),
        )
    comp = (APPLYHOME / "competition_2025000271.html").read_text(encoding="utf-8")
    store_raw_document(
        db_session,
        add_raw(
            comp,
            source_kind="applyhome_detail",
            url="https://www.applyhome.co.kr/ai/aia/selectAPTCompetitionPopup.do?houseManageNo=2025000271&pblancNo=2025000271",
            region_id=region.id,
        ),
    )
    assert db_session.scalar(select(func.count()).select_from(ComplexType)) > 60
    assert missing_provenance(db_session) == []
    # 출처 행 라벨은 빈칸이 없다
    assert (
        db_session.scalar(
            select(func.count()).select_from(FieldProvenance).where(FieldProvenance.label == "")
        )
        == 0
    )
    # 행이 있는 수치는 Fact로 나간다(prov = fp_<id>)
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2025000271")).one()
    t84 = db_session.scalars(
        select(ComplexType).where(ComplexType.complex_id == cx.id, ComplexType.type_code == "84A")
    ).one()
    fact = fact_for(db_session, "complex_type", t84.id, "max_price_won")
    assert fact["v"] == 770_000_000 and fact["label"] == "확인됨" and str(fact["prov"]).startswith("fp_")


def test_missing_provenance_detects_unsourced_value(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    raw = add_raw(
        (NOTICE / "2025000271_harrington1.txt").read_text(encoding="utf-8"),
        source_kind="notice_pdf",
        url=_notice_url("2025000271_harrington1.txt"),
        region_id=region.id,
    )
    store_raw_document(db_session, raw)
    assert missing_provenance(db_session) == []
    t = db_session.scalars(select(ComplexType)).first()
    assert t is not None
    for fp in db_session.scalars(
        select(FieldProvenance).where(
            FieldProvenance.entity == "complex_type",
            FieldProvenance.entity_id == t.id,
            FieldProvenance.field == "max_price_won",
        )
    ):
        db_session.delete(fp)
    db_session.flush()
    probs = missing_provenance(db_session)
    assert [(p.entity, p.entity_id, p.field, p.problem) for p in probs] == [
        ("complex_type", t.id, "max_price_won", "no_row")
    ]
    assert fact_for(db_session, "complex_type", t.id, "max_price_won")["reason"] == "출처 누락"


def test_restore_same_document_is_idempotent(db_session: Session, region: Region, add_raw: AddRaw) -> None:
    raw = add_raw(
        (NOTICE / "2025000076_lotte.txt").read_text(encoding="utf-8"),
        source_kind="notice_pdf",
        url=_notice_url("2025000076_lotte.txt"),
        region_id=region.id,
    )
    store_raw_document(db_session, raw)
    n_fp = db_session.scalar(select(func.count()).select_from(FieldProvenance))
    n_ev = db_session.scalar(select(func.count()).select_from(ChangeEvent))
    res = store_raw_document(db_session, raw)
    assert db_session.scalar(select(func.count()).select_from(FieldProvenance)) == n_fp
    assert db_session.scalar(select(func.count()).select_from(ChangeEvent)) == n_ev
    assert res.change_events == []


def test_price_change_in_new_version_is_critical(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    text = (NOTICE / "2025000271_harrington1.txt").read_text(encoding="utf-8")
    url = _notice_url("2025000271_harrington1.txt")
    store_raw_document(db_session, add_raw(text, source_kind="notice_pdf", url=url, region_id=region.id))
    changed = text.replace(
        "기준층 221 248,910,000 521,090,000 770,000,000", "기준층 221 248,910,000 526,090,000 775,000,000"
    )
    assert changed != text
    res = store_raw_document(
        db_session,
        add_raw(
            changed,
            source_kind="notice_pdf",
            url=url,
            region_id=region.id,
            fetched_at="2026-10-10T06:00:00+09:00",
        ),
    )
    ev = [e for e in res.change_events if e.field == "max_price_won"]
    assert len(ev) == 1 and ev[0].old_text == "770000000" and ev[0].new_text == "775000000"
    assert ev[0].severity == "critical" and ev[0].entity == "complex_type"


def test_store_is_one_transaction_rolls_back_on_error(db_session: Session, add_raw: AddRaw) -> None:
    """지역을 모르는 새 단지는 저장할 수 없다 → 이 원문의 쓰기 전부 되돌림(단지·출처 행 0)."""
    raw = dto(
        source_kind="notice_pdf",
        url=NOTICE_BASE + "houseManageNo=2025000271&pblancNo=2025000271",
        raw_id=None,
        region_id=None,
        path=None,
    )
    db_session.flush()
    with pytest.raises(StoreError):
        store_raw_document(db_session, raw, parser=_FixedParser())
    assert db_session.scalar(select(func.count()).select_from(Complex)) == 0
    assert db_session.scalar(select(func.count()).select_from(FieldProvenance)) == 0
    assert db_session.scalar(select(func.count()).select_from(RawDocument)) == 0


class _FixedParser:
    def parse(self, raw: object) -> list:  # type: ignore[type-arg]
        from app.normalize.notice_parser import parse_notice_text

        text = (NOTICE / "2025000271_harrington1.txt").read_text(encoding="utf-8")
        return parse_notice_text(text, raw)  # type: ignore[arg-type]


def test_address_assigns_legal_dong_and_living_area(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    raw = add_raw(
        (NOTICE / "2025000302_elif.txt").read_text(encoding="utf-8"),
        source_kind="notice_pdf",
        url=_notice_url("2025000302_elif.txt"),
        region_id=region.id,
    )
    store_raw_document(db_session, raw)
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2025000302")).one()
    assert cx.legal_dong_code == "2826011600"  # 서구 마전동(주소 괄호 안 법정동)
    la = next(a for a in region.living_areas if "2826011600" in a["legal_dong_codes"])
    assert cx.living_area == la["id"]


def test_outside_region_is_boundary_not_dropped(
    db_session: Session, reference_db: object, add_raw: AddRaw
) -> None:
    from ._support import make_region

    only_yeonsu = make_region(db_session, reference_db, ["28185"])  # type: ignore[arg-type]
    raw = add_raw(
        (NOTICE / "2025000271_harrington1.txt").read_text(encoding="utf-8"),
        source_kind="notice_pdf",
        url=_notice_url("2025000271_harrington1.txt"),
        region_id=only_yeonsu.id,
    )
    store_raw_document(db_session, raw)
    cx = db_session.scalars(select(Complex)).one()
    assert cx.inclusion_class == "범위 경계" and cx.living_area is None
    assert cx.legal_dong_code == "4157010700"  # 김포시 풍무동 — 지역 밖이지만 코드는 남긴다


def test_kantavil_long_type_codes_join_short_types(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    """청약홈 상세의 문자 없는 주택형(084.9582)은 전용면적이 같은 공고문 약식 타입(84A)과 같은 행이 된다."""
    html = (APPLYHOME / "detail_2025000573.html").read_text(encoding="utf-8")
    store_raw_document(
        db_session,
        add_raw(
            html, source_kind="applyhome_detail", url=DETAIL_URL.format(n="2025000573"), region_id=region.id
        ),
    )
    store_raw_document(
        db_session,
        add_raw(
            (NOTICE / "2025000573_kantavil.txt").read_text(encoding="utf-8"),
            source_kind="notice_pdf",
            url=_notice_url("2025000573_kantavil.txt"),
            region_id=region.id,
        ),
    )
    codes = sorted(t.type_code for t in db_session.scalars(select(ComplexType)))
    assert codes == sorted(["66A", "66B", "84A", "84B", "104A", "104B", "127A", "127B"])
    t84 = db_session.scalars(select(ComplexType).where(ComplexType.type_code == "84A")).one()
    assert t84.max_price_won == 678_000_000 and t84.units == 212
    rows = list(
        db_session.scalars(
            select(FieldProvenance).where(
                FieldProvenance.entity == "complex_type",
                FieldProvenance.entity_id == t84.id,
                FieldProvenance.field == "max_price_won",
            )
        )
    )
    assert {r.source_rank for r in rows} == {1, 2}
    assert next(r for r in rows if r.chosen).source_rank == 1  # 가격은 공고문(1) 채택
    assert missing_provenance(db_session) == []


def test_extract_requests_built_for_unparsed_fields(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    raw = add_raw(
        (NOTICE / "2025000435_centreville.txt").read_text(encoding="utf-8"),
        source_kind="notice_pdf",
        url=_notice_url("2025000435_centreville.txt"),
        region_id=region.id,
    )
    res = store_raw_document(db_session, raw)
    reqs = {(r.entity, r.entity_key): r for r in res.extract_requests}
    r120 = reqs[("complex_type", "2025000435:120P")]
    assert "max_price_won" in r120.fields and r120.text and len(r120.text) <= 2000
    assert r120.payload["fields"][0]["description"]
    # 못 읽은 값은 행에 쓰지 않고 '확인 불가' 출처 행만 남는다
    t120 = db_session.scalars(select(ComplexType).where(ComplexType.type_code == "120P")).one()
    assert t120.max_price_won is None
    f = fact_for(db_session, "complex_type", t120.id, "max_price_won")
    assert f["label"] == "확인 불가" and f["reason"]

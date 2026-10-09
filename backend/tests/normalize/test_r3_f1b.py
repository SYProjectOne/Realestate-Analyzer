"""R3 수정 F1b — 정규화: C3(OCR 라벨·needs_extract) · M1(같은 rank 1차 상충 채택 보류) ·
M16(provenance 전수 검사 = 모델 메타데이터) · minor 3(공고문 16개 가격 단언)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contracts_gen import FieldCandidate
from app.core.contracts_gen import RawDocument as RawDocumentDTO
from app.models import (
    Complex,
    ComplexType,
    FieldProvenance,
    PaymentTerms,
    RawDocument,
    Region,
    RtmsTrade,
    Unsold,
)
from app.normalize.fields import (
    COMPARE_ADOPTED,
    CONFLICT_HOLD,
    OCR_REASON,
    is_numeric_field,
)
from app.normalize.judged import AuditMark, ExtractedValue, apply_compare, apply_extracted
from app.normalize.notice_parser import NoticeParser, mark_ocr, ocr_spans, parse_notice_text
from app.normalize.provenance import fact_for, missing_provenance, numeric_columns
from app.normalize.resolver import resolve
from app.normalize.store import store_raw_document

from ._support import NOTICE, AddRaw, dto, notice_manifest

HARRINGTON = "2025000271_harrington1.txt"


def _harrington_text() -> str:
    return (NOTICE / HARRINGTON).read_text(encoding="utf-8")


def _harrington_raw(**kw: Any) -> RawDocumentDTO:
    return dto(source_kind="notice_pdf", url=str(notice_manifest()[HARRINGTON]["url"]), **kw)


# ====================================================================== C3 OCR


def test_c3_ocr_notice_values_are_estimated_ocr_and_numeric_fields_need_extract() -> None:
    text = _harrington_text()
    raw = _harrington_raw(error_text="ocr")
    plain = parse_notice_text(text, raw)
    cands = mark_ocr(plain, ocr_spans("ocr", text))
    assert len(cands) == len(plain) > 50
    valued = [c for c in cands if c.label != "확인 불가"]
    assert valued and all(c.label == "추정" and c.reason == OCR_REASON for c in valued)  # 표시 '추정(OCR)'
    assert not any(c.label == "확인됨" for c in cands)
    for c in valued:
        assert c.needs_extract == is_numeric_field(c.entity, c.field, c.value), (c.entity, c.field)
    prices = [c for c in valued if c.field in ("max_price_won", "floor_sample_price_won", "balcony_won")]
    assert prices and all(c.needs_extract for c in prices)
    name = next(c for c in valued if c.entity == "complex" and c.field == "name")
    assert not name.needs_extract  # 글자 필드는 라벨만
    # 파서가 못 읽은 필드는 원래대로 '확인 불가'(표시를 바꾸지 않는다)
    for before, after in zip(plain, cands, strict=True):
        if before.label == "확인 불가":
            assert after == before


def test_c3_parser_reads_error_text_from_raw_row(tmp_path: Any) -> None:
    """NoticeParser.parse 가 raw.error_text 'ocr' 를 보고 표시한다(파일 경유 경로)."""
    path = tmp_path / "notice.txt"
    path.write_text(_harrington_text(), encoding="utf-8")
    parser = NoticeParser(raw_dir=tmp_path)
    ocr = parser.parse(_harrington_raw(path="notice.txt", text_path="notice.txt", error_text="ocr"))
    normal = parser.parse(_harrington_raw(path="notice.txt", text_path="notice.txt"))
    assert {c.label for c in ocr} <= {"추정", "확인 불가"}
    assert "확인됨" in {c.label for c in normal}
    assert parser.parse(_harrington_raw(path="notice.txt", text_path="notice.txt", error_text="scan")) == []


def test_c3_ocr_partial_marks_only_ocr_pages() -> None:
    text = _harrington_text()
    cut = text.index("3 공급대상 및 공급금액")
    paged = text[:cut] + "\f" + text[cut:]
    raw = _harrington_raw(error_text="ocr_partial:2")
    cands = mark_ocr(parse_notice_text(paged, raw), ocr_spans("ocr_partial:2", paged))
    by = {(c.entity, c.field, c.entity_key): c for c in cands}
    head = by[("complex", "notice_date", "2025000271")]
    assert head.label == "확인됨" and not head.needs_extract  # 1쪽(텍스트 레이어)
    price = next(c for c in cands if c.entity == "complex_type" and c.field == "max_price_won")
    assert price.label == "추정" and price.reason == OCR_REASON and price.needs_extract  # 2쪽(OCR)
    assert ocr_spans("ocr_partial:x", paged) == [(0, len(paged))]  # 페이지를 못 읽으면 전체
    assert ocr_spans(None, paged) == [] and ocr_spans("scan_partial:2", paged) == []


def _store_ocr_harrington(db_session: Session, region: Region, add_raw: AddRaw) -> tuple[Any, int]:
    raw = add_raw(
        _harrington_text(),
        source_kind="notice_pdf",
        url=str(notice_manifest()[HARRINGTON]["url"]),
        region_id=region.id,
    )
    row = db_session.get(RawDocument, raw.id)
    assert row is not None
    row.error_text = "ocr"
    db_session.flush()
    res = store_raw_document(db_session, raw)
    t84a = db_session.scalars(select(ComplexType).where(ComplexType.type_code == "84A")).one()
    req = next(r for r in res.extract_requests if r.entity_key == "2025000271:84A")
    assert "max_price_won" in req.fields
    return req, t84a.id


def test_c3_ocr_stored_value_is_estimated_ocr_until_judge(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    _, tid = _store_ocr_harrington(db_session, region, add_raw)
    fact = fact_for(db_session, "complex_type", tid, "max_price_won")
    assert fact["v"] == 770_000_000 and fact["label"] == "추정" and fact["reason"] == OCR_REASON
    # 확인됨 라벨이 붙은 공고문 수치 출처 행이 하나도 없다
    rows = db_session.scalars(select(FieldProvenance).where(FieldProvenance.entity == "complex_type"))
    assert not [r for r in rows if r.label == "확인됨"]


def test_c3_ocr_extract_audit_pass_keeps_estimated_label_and_replaces_ocr_row(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    req, tid = _store_ocr_harrington(db_session, region, add_raw)
    out = apply_extracted(
        db_session,
        req,
        [ExtractedValue("max_price_won", "771,000,000", "auto")],
        judgment_seq=11,
        audit={"max_price_won": AuditMark(False, 0.01)},
        audit_seq=12,
    )
    assert "max_price_won" in out.applied
    fact = fact_for(db_session, "complex_type", tid, "max_price_won")
    assert fact["v"] == 771_000_000 and fact["label"] == "추정"  # OCR 원문 → 감사 통과여도 추정
    assert "jl_11" in fact["reason"] and "jl_12" in fact["reason"] and "OCR" in fact["reason"]
    ocr_row = db_session.scalars(
        select(FieldProvenance).where(
            FieldProvenance.entity == "complex_type",
            FieldProvenance.entity_id == tid,
            FieldProvenance.field == "max_price_won",
            FieldProvenance.reason == OCR_REASON,
        )
    ).one()
    assert not ocr_row.chosen  # 판정기 결과가 OCR 판독값을 대신한다


def test_c3_ocr_audit_flagged_or_review_means_ocr_value_is_not_used(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    req, tid = _store_ocr_harrington(db_session, region, add_raw)
    apply_extracted(
        db_session,
        req,
        [ExtractedValue("max_price_won", "770,000,000", "auto"), ExtractedValue("units", None, "review")],
        judgment_seq=21,
        audit={"max_price_won": AuditMark(True, 0.9)},
        audit_seq=22,
    )
    t = db_session.get(ComplexType, tid)
    assert t is not None and t.max_price_won is None  # flagged → OCR 값도 쓰지 않는다
    assert fact_for(db_session, "complex_type", tid, "max_price_won")["label"] == "확인 불가"


def test_c3_ocr_extract_review_drops_ocr_value(db_session: Session, region: Region, add_raw: AddRaw) -> None:
    req, tid = _store_ocr_harrington(db_session, region, add_raw)
    out = apply_extracted(db_session, req, [ExtractedValue("max_price_won", None, "review")], judgment_seq=31)
    assert out.skipped["max_price_won"] == "review(미반영)"
    t = db_session.get(ComplexType, tid)
    assert t is not None and t.max_price_won is None


# ====================================================================== M1 같은 rank 1차·1차 상충


def _cand(
    kind: str, value: float | str, *, raw_id: int, observed: str, key: str = "2099000001"
) -> FieldCandidate:
    return FieldCandidate(
        entity="complex",
        entity_id=None,
        entity_key=key,
        field="developer",
        value_text=str(value),
        value=value,
        source_rank=2,
        source_kind=kind,
        primary=True,
        label="확인됨",
        excerpt=f"시행: {value}",
        excerpt_start=0,
        excerpt_end=5,
        raw_document_id=raw_id,
        url=f"https://example.test/{kind}/{raw_id}",
        checked_at="2026-10-09",
        observed_on=observed,
    )


def test_m1_resolver_holds_same_rank_primary_conflict() -> None:
    res = resolve(
        [
            _cand("notice_pdf", "가건설", raw_id=1, observed="2026-09-01"),
            _cand("official_site", "나건설", raw_id=2, observed="2026-10-01"),
        ]
    )
    (chosen,) = res.chosen
    assert chosen.value is None and chosen.label == "확인 불가" and chosen.reason == CONFLICT_HOLD
    assert res.needs_compare and res.conflicts[0].needs_compare
    lead = [r for r in res.provenance if r.chosen]
    assert len(lead) == 1 and lead[0].value_text == "나건설"  # 대표(최신) — P5 가 compare 할 기준
    assert (lead[0].reason or "").startswith(CONFLICT_HOLD)


def test_m1_resolver_same_source_kind_still_latest_wins() -> None:
    res = resolve(
        [
            _cand("notice_pdf", "가건설", raw_id=1, observed="2026-09-01"),
            _cand("notice_pdf", "나건설", raw_id=2, observed="2026-10-01"),
        ]
    )
    assert res.chosen[0].value == "나건설" and not res.needs_compare


class _OneField:
    def __init__(self, cand: FieldCandidate) -> None:
        self.cand = cand

    def parse(self, raw: RawDocumentDTO) -> list[FieldCandidate]:
        return [self.cand.model_copy(update={"raw_document_id": raw.id, "url": raw.url})]


def _store_conflict(
    db_session: Session, region: Region, add_raw: AddRaw, kinds: tuple[str, ...], values: tuple[str, ...]
) -> Complex:
    for i, (kind, value) in enumerate(zip(kinds, values, strict=True)):
        raw = add_raw(f"시행: {value} {i}", source_kind=kind, url=f"https://example.test/{kind}/{i}",
                      region_id=region.id)  # fmt: skip
        cand = _cand(kind, value, raw_id=raw.id or 0, observed=f"2026-0{i + 1}-01")
        store_raw_document(db_session, raw, parser=_OneField(cand))
    return db_session.scalars(select(Complex).where(Complex.applyhome_id == "2099000001")).one()


def _group(db_session: Session, cx: Complex) -> str:
    fp = db_session.scalars(
        select(FieldProvenance).where(
            FieldProvenance.entity_id == cx.id, FieldProvenance.field == "developer"
        )
    ).first()
    assert fp is not None and fp.conflict_group
    return fp.conflict_group


def test_m1_store_holds_value_out_of_scoring_and_shows_conflict_reason(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    cx = _store_conflict(db_session, region, add_raw, ("notice_pdf", "official_site"), ("가건설", "나건설"))
    assert cx.developer is None  # 채택 보류 = 사실 테이블 값 없음(점수·화면 미사용)
    fact = fact_for(db_session, "complex", cx.id, "developer")
    assert fact["label"] == "확인 불가" and fact["reason"].startswith("출처 상충")


@pytest.mark.parametrize("relation", ["review", None])
def test_m1_compare_review_or_degraded_keeps_hold(
    db_session: Session, region: Region, add_raw: AddRaw, relation: str | None
) -> None:
    cx = _store_conflict(db_session, region, add_raw, ("notice_pdf", "official_site"), ("가건설", "나건설"))
    res = apply_compare(db_session, _group(db_session, cx), relation=relation, judgment_seq=5)
    assert not res.changed and cx.developer is None and "보류" in res.note


def test_m1_compare_contradicts_adopts_notice_even_if_other_primary_was_lead(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    # 공식 홈페이지가 더 최신(임시 대표)이어도 contradicts 면 공고문 채택(RA §3)
    cx = _store_conflict(db_session, region, add_raw, ("notice_pdf", "official_site"), ("가건설", "나건설"))
    res = apply_compare(db_session, _group(db_session, cx), relation="contradicts", judgment_seq=7)
    assert res.changed and cx.developer == "가건설"
    rows = list(db_session.scalars(select(FieldProvenance).where(FieldProvenance.field == "developer")))
    chosen = [r for r in rows if r.chosen]
    assert len(chosen) == 1 and chosen[0].value_text == "가건설"
    assert (chosen[0].reason or "").startswith(COMPARE_ADOPTED) and "jl_7" in (chosen[0].reason or "")
    side = [r for r in rows if not r.chosen]
    assert side and all("병기" in (r.reason or "") for r in side)
    # 채택은 새 원문이 와도 유지된다(같은 값의 공고문 재수집)
    _store_conflict_more(db_session, region, add_raw, "notice_pdf", "가건설", 5)
    assert cx.developer == "가건설"


def _store_conflict_more(
    db_session: Session, region: Region, add_raw: AddRaw, kind: str, value: str, i: int
) -> None:
    raw = add_raw(f"시행: {value} {i}", source_kind=kind, url=f"https://example.test/{kind}/{i}",
                  region_id=region.id)  # fmt: skip
    store_raw_document(db_session, raw, parser=_OneField(_cand(kind, value, raw_id=raw.id or 0,
                                                               observed=f"2026-0{i}-01")))  # fmt: skip


def test_m1_new_uncompared_primary_rival_holds_again(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    cx = _store_conflict(db_session, region, add_raw, ("notice_pdf", "official_site"), ("가건설", "나건설"))
    apply_compare(db_session, _group(db_session, cx), relation="contradicts", judgment_seq=7)
    assert cx.developer == "가건설"
    _store_conflict_more(db_session, region, add_raw, "official_site", "다건설", 6)
    assert cx.developer is None  # 새 상충 = compare 필요 → 다시 보류


def test_m1_compare_same_fact_adopts_priority_lead(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    cx = _store_conflict(db_session, region, add_raw, ("notice_pdf", "official_site"), ("가건설", "나건설"))
    res = apply_compare(db_session, _group(db_session, cx), relation="same_fact", judgment_seq=8)
    assert res.changed and cx.developer == "나건설"  # 상충 아님 → §3 우선순위(최신) 대표


# ====================================================================== M16 provenance 전수 검사


def test_m16_numeric_columns_come_from_model_metadata() -> None:
    cx = numeric_columns(Complex)
    assert {"units_total", "notice_date", "move_in_ym", "inclusion_prob", "resale_months"} <= set(cx)
    assert {"apply_dates", "contract_dates"} <= set(cx)
    assert not {"id", "region_id", "inclusion_judgment_seq", "name", "address"} & set(cx)
    assert {"price_won", "area_m2", "deal_date", "floor"} <= set(numeric_columns(RtmsTrade))
    assert {"total", "post_completion", "ym"} <= set(numeric_columns(Unsold))
    assert {"effective_from", "interim_schedule", "down_payment_pct"} <= set(numeric_columns(PaymentTerms))


def test_m16_missing_provenance_covers_market_tables_pointer_columns_and_price_by_type(
    db_session: Session, region: Region
) -> None:
    cx = Complex(region_id=region.id, applyhome_id="2099000009", name="검사 단지", former_names=[],
                 apply_dates=[], contract_dates=[], inclusion_class="미분류")  # fmt: skip
    db_session.add(cx)
    db_session.flush()
    assert missing_provenance(db_session) == []
    cx.inclusion_prob = 0.9  # type: ignore[assignment]
    db_session.add(RtmsTrade(region_id=region.id, apt_name="거래", area_m2=84.9, price_won=600_000_000,
                             deal_date="2026-09-01", source="openapi"))  # fmt: skip
    db_session.add(PaymentTerms(complex_id=cx.id, notice_no="N1", effective_from="2026-09-01",
                                interim_schedule=[],
                                price_by_type={"84A": {"max_price_won": 1}}))  # fmt: skip
    db_session.flush()
    probs = {(p.entity, p.field) for p in missing_provenance(db_session)}
    assert ("complex", "inclusion_prob") in probs
    assert {("rtms_trade", "price_won"), ("rtms_trade", "area_m2"), ("rtms_trade", "deal_date")} <= probs
    assert ("payment_terms", "effective_from") in probs
    assert ("payment_terms", "price_by_type.84A.max_price_won") in probs
    cx.inclusion_judgment_seq = 62  # 판정기 행(jl_62)이 출처
    db_session.flush()
    assert ("complex", "inclusion_prob") not in {(p.entity, p.field) for p in missing_provenance(db_session)}


# ====================================================================== minor 3 공고문 16개


# 원문 표에서 직접 읽은 대조값(원) — 잔여 세대 공고 3개(expected_complex_types.json 밖)
REMAIN_PRICES: dict[str, dict[str, tuple[int, int]]] = {
    "2026940185_gochon13.txt": {
        "84A": (758_400_000, 758_400_000),
        "84B": (745_200_000, 745_200_000),
        "105": (937_800_000, 937_800_000),
    },
    "2026910242_marinabay.txt": {"84C": (784_000_000, 784_000_000)},
    "2026940173_elif_imui3.txt": {
        "64A": (507_000_000, 482_000_000),
        "84A": (605_000_000, 575_000_000),
        "84B": (578_000_000, 566_000_000),
        "84F": (602_000_000, 569_000_000),
        "98A": (689_000_000, 689_000_000),
    },
}
UNREAD: dict[str, set[str]] = {
    "2025000435_centreville.txt": {"120P"},
    "2026940173_elif_imui3.txt": {"98B", "98B1", "98C"},
}


def _type_prices(fname: str) -> dict[str, dict[str, FieldCandidate]]:
    raw = dto(source_kind="notice_pdf", url=str(notice_manifest()[fname]["url"]))
    out: dict[str, dict[str, FieldCandidate]] = {}
    for c in parse_notice_text((NOTICE / fname).read_text(encoding="utf-8"), raw):
        if c.entity == "complex_type" and c.field in ("max_price_won", "floor_sample_price_won"):
            out.setdefault(str(c.entity_key).split(":", 1)[1], {})[c.field] = c
    return out


def test_minor3_all_sixteen_notices_have_price_or_needs_extract_for_every_type() -> None:
    files = sorted(notice_manifest())
    assert len(files) == 16
    for fname in files:
        got = _type_prices(fname)
        assert got, fname  # 가격 후보(값 또는 needs_extract)가 하나도 없는 공고문은 없다
        for t, fields in got.items():
            for f, c in fields.items():
                if t in UNREAD.get(fname, set()):
                    assert c.value is None and c.needs_extract and c.label == "확인 불가", (fname, t, f)
                else:
                    assert isinstance(c.value, int | float) and c.value > 0 and not c.needs_extract, (
                        fname,
                        t,
                        f,
                    )


@pytest.mark.parametrize("fname", sorted(REMAIN_PRICES))
def test_minor3_remainder_notice_prices_to_the_won(fname: str) -> None:
    got = _type_prices(fname)
    for t, (top, low) in REMAIN_PRICES[fname].items():
        assert got[t]["max_price_won"].value == top, (fname, t)
        assert got[t]["floor_sample_price_won"].value == low, (fname, t)


# ====================================================================== W4·W12c 단지 키(지역·같은 블록)


def _region2(db_session: Session, region: Region) -> Region:
    other = Region(
        name="다른 지역", query_text="다른", selections=[], sido_codes=region.sido_codes,
        sigungu_codes=region.sigungu_codes, legal_dong_codes=region.legal_dong_codes,
        living_areas=region.living_areas, age_premium_coef=region.age_premium_coef, applyhome_query={},
        status="ready", created_at="2026-10-09T06:00:00+09:00",
    )  # fmt: skip
    db_session.add(other)
    db_session.flush()
    return other


class _Fields:
    def __init__(self, key: str, values: dict[str, str]) -> None:
        self.key, self.values = key, values

    def parse(self, raw: RawDocumentDTO) -> list[FieldCandidate]:
        return [
            FieldCandidate(
                entity="complex",
                entity_id=None,
                entity_key=self.key,
                field=f,
                value_text=v,
                value=v,
                source_rank=1,
                source_kind="applyhome_detail",
                primary=True,
                label="확인됨",
                excerpt=v,
                excerpt_start=0,
                excerpt_end=1,
                raw_document_id=raw.id,
                url=raw.url,
                checked_at="2026-10-09",
                observed_on="2026-09-01",
            )
            for f, v in self.values.items()
        ]


def _store_fields(
    db_session: Session, add_raw: AddRaw, region: Region, key: str, n: int, **values: str
) -> Any:
    url = f"https://www.applyhome.co.kr/ai/aia/selectAPTRemndrLttotPblancDetailView.do?houseManageNo={key}&n={n}"
    raw = add_raw(f"{key} {n} {values}", source_kind="applyhome_detail", url=url, region_id=region.id)
    return store_raw_document(db_session, raw, parser=_Fields(key, values))


def test_w4_other_region_complex_is_never_overwritten(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    _store_fields(
        db_session, add_raw, region, "2026000164", 1, name="더샵 송도그란테르", builder="포스코이앤씨"
    )
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2026000164")).one()
    other = _region2(db_session, region)
    res = _store_fields(db_session, add_raw, other, "2026000164", 2, name="더샵 송도그란테르 G5-1블록",
                        builder="㈜포스코이앤씨")  # fmt: skip
    assert (cx.region_id, cx.name, cx.builder) == (region.id, "더샵 송도그란테르", "포스코이앤씨")
    assert res.foreign_keys == ["2026000164"] and len(res.skipped) == 2 and not res.change_events


def test_w12c_remainder_detail_binds_to_same_block_complex(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    addr = "인천광역시 연수구 송도동 32-15 (G5-11BL)"
    _store_fields(
        db_session, add_raw, region, "2026000169", 1, name="더샵 송도그란테르 G5-11블록", address=addr
    )
    # 잔여 세대 상세(최초 번호 없음) — 이름 뒤 회차 괄호·주소 표기 차이는 정규화로 같다
    res = _store_fields(db_session, add_raw, region, "2026910207", 2,
                        name="더샵 송도그란테르 G5-11블록(조합원 자격상실세대 3회차)",
                        address="인천광역시 연수구 송도동 32-15번지 (G5-11BL)")  # fmt: skip
    rows = list(db_session.scalars(select(Complex).where(Complex.name.contains("G5-11"))))
    assert len(rows) == 1 and rows[0].applyhome_id == "2026000169"
    assert res.complex_ids == [rows[0].id]


def test_w12c_ambiguous_or_missing_address_does_not_merge(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    addr = "인천광역시 연수구 송도동 32-15"
    _store_fields(db_session, add_raw, region, "2026000101", 1, name="같은 이름 단지", address=addr)
    _store_fields(db_session, add_raw, region, "2026000102", 2, name="다른 이름 단지", address=addr)
    _store_fields(db_session, add_raw, region, "2026000103", 3, name="같은 이름 단지", address=addr + " 외")
    _store_fields(
        db_session, add_raw, region, "2026910300", 4, name="같은 이름 단지", address=addr
    )  # 정확히 1개
    _store_fields(db_session, add_raw, region, "2026910301", 5, name="같은 이름 단지")  # 주소 없음 → 새 행
    keys = sorted(c.applyhome_id or "" for c in db_session.scalars(select(Complex)))
    assert keys == ["2026000101", "2026000102", "2026000103", "2026910301"]


def test_w12c_two_candidates_is_ambiguous(db_session: Session, region: Region, add_raw: AddRaw) -> None:
    addr = "인천광역시 연수구 송도동 1"
    _store_fields(db_session, add_raw, region, "2026000201", 1, name="쌍둥이 단지", address=addr)
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2026000201")).one()
    db_session.add(Complex(region_id=region.id, applyhome_id="2026000202", name="쌍둥이 단지", address=addr,
                           former_names=[], apply_dates=[], contract_dates=[]))  # fmt: skip
    db_session.flush()
    _store_fields(db_session, add_raw, region, "2026910203", 2, name="쌍둥이 단지", address=addr)
    assert db_session.scalars(select(Complex).where(Complex.applyhome_id == "2026910203")).one() is not cx


def test_w4_archived_notices_scoped_by_region(db_session: Session, region: Region, add_raw: AddRaw) -> None:
    from app.normalize.archive import archived_notices

    url = "https://static.applyhome.co.kr/ai/aia/getAtchmnfl.do?houseManageNo=2026000164"
    raw = add_raw("공고문", source_kind="notice_pdf", url=url, region_id=region.id)
    other = _region2(db_session, region)
    assert [r.id for r in archived_notices(db_session, "2026000164")] == [raw.id]
    assert [r.id for r in archived_notices(db_session, "2026000164", region_id=region.id)] == [raw.id]
    assert archived_notices(db_session, "2026000164", region_id=other.id) == []

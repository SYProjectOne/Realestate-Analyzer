"""R5-NORM 2 (minor): 스캔 공고문 '확인 불가(스캔)' 후보 · 선택품목 필수 공고의 ``options_required_won``.

(a) 스캔 공고문(raw.error_text == 'scan', 텍스트 레이어 없음 — collectors.notice_pdf)
    수정 전: 후보 0개 → 공고문이 1순위인 필드(가격·발코니·옵션·전매·거주의무·재당첨·상한제, RA §3)는 출처 패널에 공고문이
    없었던 것처럼 하위 출처(청약홈)만 남는다. 수정 후: 이미 있는 그 단지(같은 주택관리번호·지역)에 대해 그 필드마다
    label '확인 불가' + reason '스캔'(화면 '확인 불가(스캔)') 후보. 값이 있는 하위 출처가 있으면 여전히 그 값이 채택되고
    (resolver 규칙 1 — 값 있는 후보 우선), 공고문만 주는 필드는 '확인 불가(스캔)'가 채택 출처가 된다. 원문에 글자가 없어
    판정기 extract 요청(needs_extract)은 만들지 않는다. 모르는 단지는 스캔 원문으로 새 단지 행을 만들지 않는다.
(b) 선택품목이 **필수**인 공고: '추가 선택품목 비용 미포함'(보일러플레이트)만 보고 필수 옵션 0원으로 읽으면 안 된다.
    필수 선택품목 표의 타입별 금액(행에 금액 하나)을 읽고, 못 읽으면 '확인 불가' + needs_extract(판정기 extract).
"""

# ruff: noqa: E501  (한국어 docstring·공고문 문장)

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ChangeEvent, Complex, ComplexType, FieldProvenance, RawDocument, Region
from app.normalize.notice_parser import NoticeParser, parse_notice_text
from app.normalize.store import store_raw_document

from ._support import APPLYHOME, DETAIL_URL, FIX, NOTICE, AddRaw, dto, notice_manifest

KEY = "2025000271"
HARRINGTON = "2025000271_harrington1.txt"
SCAN_URL = "https://static.applyhome.co.kr/ai/aia/getAtchmnfl.do?houseManageNo={n}&pblancNo={n}&atchmnflSeqNo=1&atchmnflSn=1"
SCAN_COMPLEX_FIELDS = {
    "resale_months",
    "resale_release_on_registration",
    "residency_months",
    "rewin_restriction_years",
    "price_cap",
}
SCAN_TYPE_FIELDS = {"max_price_won", "floor_sample_price_won", "balcony_won", "options_required_won"}


# ====================================================================== (a) 스캔


def _detail(db: Session, add_raw: AddRaw, region: Region) -> Complex:
    html = (APPLYHOME / f"detail_{KEY}.html").read_text(encoding="utf-8")
    raw = add_raw(html, source_kind="applyhome_detail", url=DETAIL_URL.format(n=KEY), region_id=region.id)
    store_raw_document(db, raw)
    db.flush()
    return db.scalars(select(Complex).where(Complex.applyhome_id == KEY)).one()


def _scan(db: Session, add_raw: AddRaw, region: Region, key: str = KEY, tag: str = "") -> RawDocument:
    dto_ = add_raw(f"%PDF scan {key} {tag}", source_kind="notice_pdf", url=SCAN_URL.format(n=key),
                   region_id=region.id, ext="pdf")  # fmt: skip
    row = db.get(RawDocument, dto_.id)
    assert row is not None
    row.error_text, row.text_path, row.content_type = "scan", None, "application/pdf"
    db.flush()
    return row


def _rows(db: Session, raw_id: int) -> list[FieldProvenance]:
    return list(db.scalars(select(FieldProvenance).where(FieldProvenance.raw_document_id == raw_id)))


def test_scan_notice_emits_unknown_scan_candidates_for_notice_rank1_fields(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    cx = _detail(db_session, add_raw, region)
    types = sorted(db_session.scalars(select(ComplexType.type_code).where(ComplexType.complex_id == cx.id)))
    assert types
    t84 = db_session.scalars(
        select(ComplexType).where(ComplexType.complex_id == cx.id, ComplexType.type_code == "84A")
    ).one()
    price_before = t84.max_price_won
    assert price_before  # 청약홈 상세(rank 2) 가격
    n_cx = db_session.scalar(select(func.count()).select_from(Complex))

    scan = _scan(db_session, add_raw, region)
    res = store_raw_document(db_session, scan)
    db_session.flush()

    assert res.change_events == [], "스캔 공고문은 사실 값을 바꾸지 않는다"
    assert res.extract_requests == [], "글자 없는 원문 — 판정기 extract 요청 없음"
    assert all(not c.needs_extract for c in res.candidates)
    rows = _rows(db_session, scan.id)
    assert rows and {(r.label, r.reason) for r in rows} == {("확인 불가", "스캔")}
    assert {r.field for r in rows if r.entity == "complex"} == SCAN_COMPLEX_FIELDS
    by_type: dict[int, set[str]] = {}
    for r in rows:
        if r.entity == "complex_type" and r.entity_id is not None:
            by_type.setdefault(r.entity_id, set()).add(r.field)
    assert len(by_type) == len(types) and all(v == SCAN_TYPE_FIELDS for v in by_type.values())

    # 값 있는 하위 출처(청약홈 상세 가격)는 그대로 채택된다 — 스캔 행은 병기(chosen=false)
    db_session.refresh(t84)
    assert t84.max_price_won == price_before
    scan_price = next(r for r in rows if r.entity_id == t84.id and r.field == "max_price_won")
    assert scan_price.chosen is False
    # 공고문만 주는 필드(거주의무)는 '확인 불가(스캔)'가 채택 출처
    resid = next(r for r in rows if r.entity == "complex" and r.field == "residency_months")
    others = db_session.scalars(
        select(FieldProvenance).where(
            FieldProvenance.entity == "complex",
            FieldProvenance.entity_id == cx.id,
            FieldProvenance.field == "residency_months",
            FieldProvenance.raw_document_id != scan.id,
        )
    ).all()
    if not any(o.value_norm is not None for o in others):
        assert resid.chosen is True
    assert db_session.scalar(select(func.count()).select_from(Complex)) == n_cx


def test_scan_renormalize_is_idempotent(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    _detail(db_session, add_raw, region)
    scan = _scan(db_session, add_raw, region)
    store_raw_document(db_session, scan)
    db_session.flush()
    before = [
        (r.id, r.entity, r.entity_id, r.field, r.label, r.reason, r.chosen)
        for r in _rows(db_session, scan.id)
    ]
    n_ev = db_session.scalar(select(func.count()).select_from(ChangeEvent))
    res = store_raw_document(db_session, scan)
    db_session.flush()
    after = [
        (r.id, r.entity, r.entity_id, r.field, r.label, r.reason, r.chosen)
        for r in _rows(db_session, scan.id)
    ]
    assert after == before and res.change_events == []
    assert db_session.scalar(select(func.count()).select_from(ChangeEvent)) == n_ev


def test_scan_notice_of_unknown_complex_creates_nothing(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    """모르는 주택관리번호의 스캔 공고문 — 글자가 없어 잔여 공고인지도 알 수 없다. 새 단지 행·출처 행을 만들지 않는다."""
    scan = _scan(db_session, add_raw, region, key="2026999001")
    res = store_raw_document(db_session, scan)
    db_session.flush()
    assert res.candidates == [] and _rows(db_session, scan.id) == []
    assert db_session.scalar(select(func.count()).select_from(Complex)) == 0


def test_scan_without_complex_lookup_stays_empty() -> None:
    """단지 조회 없이 쓰는 파서(판정기 추출 단계·벤치마크 아카이브)는 예전처럼 후보가 없다."""
    raw = dto(source_kind="notice_pdf", url=SCAN_URL.format(n=KEY), error_text="scan")
    assert NoticeParser().parse(raw) == []


# ====================================================================== (b) 선택품목 필수


BOILERPLATE = "• 상기 공급금액은 추가 선택품목 비용이 포함되지 아니한 가격이며"


def _harrington(insert: str) -> str:
    text = (NOTICE / HARRINGTON).read_text(encoding="utf-8")
    i = text.index(BOILERPLATE)
    j = text.index("\n", i) + 1
    return text[:j] + insert + text[j:]


def _opts(text: str) -> dict[str, tuple[object, str | None, str | None, bool | None]]:
    raw = dto(source_kind="notice_pdf", url=str(notice_manifest()[HARRINGTON]["url"]))
    return {
        (c.entity_key or "").split(":")[1]: (c.value, c.label, c.reason, c.needs_extract)
        for c in parse_notice_text(text, raw)
        if c.entity == "complex_type" and c.field == "options_required_won"
    }


def test_boilerplate_only_notice_keeps_zero() -> None:
    """수정 전과 같다: 필수 언급 없는 '추가 선택품목 미포함' 문장 → 필수 옵션 0원(확인됨)."""
    opts = _opts((NOTICE / HARRINGTON).read_text(encoding="utf-8"))
    assert opts and {v[0] for v in opts.values()} == {0} and {v[1] for v in opts.values()} == {"확인됨"}


def test_mandatory_option_table_is_parsed_per_type() -> None:
    text = _harrington(
        "• 단, 아래 필수 선택품목(시스템에어컨 거실·침실1)은 기 시공되어 반드시 계약하여야 하며, 공급금액에 포함되지 아니함.\n"
        "■ 필수 선택품목 공급금액 (단위 : 원)\n"
        "주택형 금액\n"
        "74A·74B·74C 3,210,000\n"
        "84A 3,610,000\n"
        "84B, 84C 3,450,000\n"
    )
    opts = _opts(text)
    assert opts["74A"][:2] == (3_210_000, "확인됨") and opts["74C"][0] == 3_210_000
    assert opts["84A"][:2] == (3_610_000, "확인됨")
    assert opts["84B"][0] == 3_450_000 and opts["84C"][0] == 3_450_000
    assert not any(v[3] for v in opts.values())


def test_mandatory_option_table_in_man_won_is_scaled() -> None:
    text = _harrington("■ 필수 선택품목 공급금액 (단위 : 만원)\n74A·74B·74C 321\n84A·84B·84C 361\n")
    opts = _opts(text)
    assert opts["74B"][0] == 3_210_000 and opts["84C"][0] == 3_610_000


def test_mandatory_option_without_readable_amount_is_unknown_not_zero() -> None:
    """필수 선택품목이 있다고만 하고 타입별 금액을 못 읽으면 0원이 아니라 '확인 불가' + 판정기 extract."""
    text = _harrington(
        "※ 시스템에어컨(거실)은 필수 선택품목으로 별도 계약하여야 하며 금액은 견본주택에서 안내함.\n"
    )
    opts = _opts(text)
    assert opts and all(v[0] is None for v in opts.values()), opts
    assert {v[1] for v in opts.values()} == {"확인 불가"}
    assert all(v[3] for v in opts.values())
    assert all("필수 선택품목" in (v[2] or "") for v in opts.values())


@pytest.mark.parametrize(
    "line",
    [
        # 녹화 공고문(R4)에 실제로 있는 '반드시'·'(의무)' 보일러플레이트 — 필수 선택품목이 아니다
        "• 추가 선택품목(가구, 가전, 마감, 조명 등)은 계약 전 반드시 확인하여야 하며, 옵션 및 평면 선택 시 전기, 배선 기구 위치가 다소 상이할 수 있습니다.",
        "Ÿ LG프리미엄환기(전열교환기) 선택시 기본제공(의무)되는 제품은 시공되지 않으며, 기본제공(의무)되는 제품의 비용은 상기 추가선택품목 판매가 산정 시 감액되어 정산된 금액임.",
        "❈ 공급계약 체결 시 선시공품목인 발코니 확장(유상옵션)을 별도로 반드시 계약하여야 합니다.",
    ],
    ids=["must-check", "default-provided-duty", "balcony-must-contract"],
)
def test_recorded_must_check_boilerplate_is_not_mandatory(line: str) -> None:
    opts = _opts(_harrington(line + "\n"))
    assert {v[0] for v in opts.values()} == {0}


def _recorded_notice_texts() -> list[Path]:
    out = sorted(NOTICE.glob("*.txt"))
    out += sorted(p for p in FIX.rglob("notice_pdf/**/*.txt"))
    return out


def test_no_recorded_notice_reads_as_mandatory_options() -> None:
    """녹화 공고문 전체: 새 '필수 선택품목' 규칙에 걸리는 공고가 없다(회귀 데이터 영향 0)."""
    raw = dto(source_kind="notice_pdf", url=SCAN_URL.format(n=KEY))
    paths = _recorded_notice_texts()
    assert len(paths) > 20
    for p in paths:
        for c in parse_notice_text(p.read_text(encoding="utf-8"), raw):
            if c.field == "options_required_won":
                assert "필수 선택품목" not in (c.reason or ""), p.name
                assert c.value in (0, None), p.name

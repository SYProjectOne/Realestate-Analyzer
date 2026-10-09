"""계약 2026-10-09.2 적용(R1F): observed_on·value_norm, 재파싱 없는 store, notice_type_code·price_by_type,
공식 홈페이지 intake_status 후보.

- 후보마다 observed_on(원문 시점 = 공고일 등), 출처 행마다 value_norm·observed_on.
- store는 같은 필드의 옛 출처를 원문을 다시 읽어 파싱하지 않고 field_provenance 행(value_norm)으로 합친다.
  value_norm이 없는 옛 행(0001 시절)만 예전처럼 다시 파싱한다(호환).
- 공고별 타입 가격(payment_terms.price_by_type) — 임의공급 가격 변경의 최초 대비 증감률 계산 재료.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.analysis.price import price_change_vs_first
from app.core.contracts_gen import FieldCandidate
from app.core.snapshot import store_raw
from app.models import ChangeEvent, Complex, ComplexType, FieldProvenance, PaymentTerms, Region
from app.normalize import applyhome_parser, notice_parser
from app.normalize.applyhome_parser import parse_applyhome_html
from app.normalize.changes import current_terms, first_terms
from app.normalize.fields import norm_value, value_from_norm
from app.normalize.notice_parser import parse_notice_text
from app.normalize.official_site_parser import OfficialSiteParser
from app.normalize.rtms_parser import parse_rtms_xml
from app.normalize.stats_parser import parse_unsold_csv
from app.normalize.store import store_raw_document

from ._support import APPLYHOME, DETAIL_URL, FIX, NOTICE, AddRaw, dto, notice_manifest

RTMS_URL = (
    "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade?LAWD_CD=41570&DEAL_YMD=202609"
)


def _notice(fname: str) -> list[FieldCandidate]:
    raw = dto(source_kind="notice_pdf", url=str(notice_manifest()[fname]["url"]))
    return parse_notice_text((NOTICE / fname).read_text(encoding="utf-8"), raw)


def _url(fname: str) -> str:
    return str(notice_manifest()[fname]["url"])


# ---------------------------------------------------------------- observed_on · value_norm


def test_notice_candidates_observed_on_is_this_notice_date() -> None:
    main = _notice("2025000302_elif.txt")
    assert main and {c.observed_on for c in main} == {"2025-08-22"}
    imui = _notice("2026940173_elif_imui3.txt")
    # 임의공급 공고의 원문 시점 = 이 공고의 공고일(단지 notice_date 값은 최초 공고일이어도)
    assert imui and {c.observed_on for c in imui} == {"2026-08-14"}
    nd = next(c for c in imui if c.field == "notice_date")
    assert nd.value == "2025-08-22" and nd.observed_on == "2026-08-14"


def test_other_parsers_observed_on() -> None:
    html = (APPLYHOME / "detail_2025000271.html").read_text(encoding="utf-8")
    det = parse_applyhome_html(
        html, dto(source_kind="applyhome_detail", url=DETAIL_URL.format(n="2025000271"))
    )
    notice_date = next(c.value for c in det if c.field == "notice_date")
    assert {c.observed_on for c in det} == {notice_date}
    xml = (FIX / "rtms" / "apt_trade_41570_202609.xml").read_text(encoding="utf-8")
    trades = parse_rtms_xml(xml, dto(source_kind="rtms", url=RTMS_URL))
    for c in trades:
        deal = next(x.value for x in trades if x.entity_key == c.entity_key and x.field == "deal_date")
        assert c.observed_on == deal
    csv_text = (FIX / "stats" / "unsold_202606_202608.csv").read_text(encoding="utf-8")
    unsold = parse_unsold_csv(csv_text, dto(source_kind="stats", url="https://stat.molit.go.kr/u.csv"))
    aug = [c for c in unsold if str(c.entity_key).endswith(":2026-08")]
    assert aug and {c.observed_on for c in aug} == {"2026-08-31"}


@pytest.mark.parametrize(
    ("field", "value", "norm"),
    [
        ("units_total", 1573, "1573"),
        ("area_m2", 84.98, "84.98"),
        ("down_payment_pct", 10.0, "10"),
        ("notice_date", "2025-07-04", "2025-07-04"),
        ("resale_release_on_registration", True, "true"),
        ("cancelled", False, "false"),
        ("interim_schedule", "[]", "[]"),
        ("name", "엘리프 검단 포레듀(AA32블록)", "엘리프 검단 포레듀(AA32블록)"),
        ("price_by_type.84A.max_price_won", 605_000_000, "605000000"),
        ("max_price_won", None, None),
    ],
)
def test_value_norm_round_trip(field: str, value: object, norm: str | None) -> None:
    assert norm_value(value) == norm  # type: ignore[arg-type]
    back = value_from_norm(field, norm)
    assert back == value and type(back) is type(value)


def test_provenance_rows_store_value_norm_and_observed_on(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    fname = "2025000302_elif.txt"
    raw = add_raw(
        (NOTICE / fname).read_text(encoding="utf-8"),
        source_kind="notice_pdf",
        url=_url(fname),
        region_id=region.id,
    )
    store_raw_document(db_session, raw)
    rows = {
        r.field: r
        for r in db_session.scalars(select(FieldProvenance).where(FieldProvenance.entity == "complex"))
    }
    assert (rows["units_total"].value_norm, rows["units_total"].observed_on) == ("669", "2025-08-22")
    assert rows["resale_release_on_registration"].value_norm == "true"
    assert rows["resale_months"].value_norm == "36"
    dp = db_session.scalars(select(FieldProvenance).where(FieldProvenance.field == "down_payment_pct")).one()
    assert dp.value_norm == "10" and dp.observed_on == "2025-08-22"


# ---------------------------------------------------------------- 재파싱 없음


def _t5_docs() -> tuple[str, str]:
    detail = (APPLYHOME / "detail_2025000271.html").read_text(encoding="utf-8")
    detail = detail.replace('<td class="txt_l">670세대</td>', '<td class="txt_l">1,573세대</td>')
    notice = (NOTICE / "2025000271_harrington1.txt").read_text(encoding="utf-8")
    notice = notice.replace("총 866세대 중 일반분양 670세대", "총 1,769세대")
    return detail, notice


@pytest.mark.parametrize("order", ["applyhome_first", "notice_first"])
def test_store_does_not_reparse_old_sources(
    order: str,
    db_session: Session,
    region: Region,
    add_raw: AddRaw,
    raw_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """옛 출처는 원문 파일이 없어도(지워도) 출처 행(value_norm)으로 합쳐진다 — 파서를 다시 부르지 않는다."""
    detail, notice = _t5_docs()
    docs = [
        ("applyhome_detail", detail, DETAIL_URL.format(n="2025000271"), "html"),
        ("notice_pdf", notice, _url("2025000271_harrington1.txt"), "txt"),
    ]
    if order == "notice_first":
        docs.reverse()
    (k1, c1, u1, e1), (k2, c2, u2, e2) = docs
    first = add_raw(c1, source_kind=k1, url=u1, region_id=region.id, ext=e1)
    store_raw_document(db_session, first)
    (raw_dir / str(first.path)).unlink()  # 옛 원문 파일을 치운다

    parsed: list[int | None] = []
    for mod, cls in ((applyhome_parser, "ApplyhomeParser"), (notice_parser, "NoticeParser")):
        orig = getattr(mod, cls).parse

        def spy(self: object, raw: object, _orig: object = orig) -> list[FieldCandidate]:
            parsed.append(getattr(raw, "id", None))
            return _orig(self, raw)  # type: ignore[operator, no-any-return]

        monkeypatch.setattr(getattr(mod, cls), "parse", spy)

    second = add_raw(c2, source_kind=k2, url=u2, region_id=region.id, ext=e2)
    res = store_raw_document(db_session, second)
    assert parsed == [second.id]  # 이번 원문만 파싱

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
    assert len(rows) == 2 and {r.conflict_group for r in rows} == {f"complex:{cx.id}:units_total"}
    chosen = [r for r in rows if r.chosen]
    assert len(chosen) == 1 and chosen[0].value_text == "1,573세대" and chosen[0].source_rank == 1
    units = [g for g in res.resolved.conflicts if g.field == "units_total"]
    assert len(units) == 1 and units[0].needs_compare is False
    assert units[0].candidates[units[0].chosen_index].source_kind == "applyhome_detail"
    # 가격은 공고문(1) > 청약홈(2): 출처 행으로 합쳐도 84A 최고가 상충 없음, 값 유지
    t84 = db_session.scalars(
        select(ComplexType).where(ComplexType.complex_id == cx.id, ComplexType.type_code == "84A")
    ).one()
    assert t84.max_price_won == 770_000_000


def test_legacy_rows_without_value_norm_are_reparsed(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    """0001 시절 출처 행(value_norm 없음)은 예전처럼 원문을 다시 파싱해 합친다(호환 읽기)."""
    detail, notice = _t5_docs()
    first = add_raw(
        detail, source_kind="applyhome_detail", url=DETAIL_URL.format(n="2025000271"), region_id=region.id
    )
    store_raw_document(db_session, first)
    db_session.execute(
        update(FieldProvenance)
        .where(FieldProvenance.raw_document_id == first.id)
        .values(value_norm=None, observed_on=None)
    )
    db_session.flush()
    store_raw_document(
        db_session,
        add_raw(
            notice,
            source_kind="notice_pdf",
            url=_url("2025000271_harrington1.txt"),
            region_id=region.id,
        ),
    )
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2025000271")).one()
    assert cx.units_total == 1573
    rows = list(
        db_session.scalars(
            select(FieldProvenance).where(
                FieldProvenance.entity_id == cx.id, FieldProvenance.field == "units_total"
            )
        )
    )
    assert len(rows) == 2 and all(r.value_norm for r in rows)  # 다시 쓰면서 value_norm이 채워진다


# ---------------------------------------------------------------- notice_type_code · price_by_type


def test_notice_type_code_and_price_by_type_candidates() -> None:
    main = {(c.entity, str(c.entity_key), c.field): c for c in _notice("2025000302_elif.txt")}
    assert main[("complex_type", "2025000302:84A", "notice_type_code")].value == "084.7800A"
    p = "2025000302:2025000302"
    assert main[("payment_terms", p, "price_by_type.84A.max_price_won")].value == 609_000_000
    assert main[("payment_terms", p, "price_by_type.84A.notice_type_code")].value == "084.7800A"
    assert main[("payment_terms", p, "price_by_type.84A.units")].value == 43

    imui = {(c.entity, str(c.entity_key), c.field): c for c in _notice("2026940173_elif_imui3.txt")}
    q = "2025000302:2026940173"
    assert imui[("payment_terms", q, "price_by_type.84A.max_price_won")].value == 605_000_000
    assert imui[("payment_terms", q, "price_by_type.84A.floor_sample_price_won")].value == 575_000_000
    assert imui[("payment_terms", q, "price_by_type.84A.floor_sample_text")].value == "3층"
    assert imui[("payment_terms", q, "price_by_type.84A.units")].value == 2
    assert imui[("payment_terms", q, "price_by_type.84F.max_price_won")].value == 602_000_000
    # 행 세대수 합이 공급대상 표와 맞지 않는 타입(98B: 동 번호가 세대수 칸에 붙음)은 추측하지 않는다
    assert ("payment_terms", q, "price_by_type.98B.max_price_won") not in imui
    # 임의공급 공고: 잔여 세대 가격만 — 면적·세대수(complex_type)는 내지 않는다
    ct = {f for (e, _, f) in imui if e == "complex_type"}
    assert ct == {"max_price_won", "floor_sample_price_won", "floor_sample_text", "notice_type_code"}
    for (e, _, f), c in imui.items():
        if e == "complex_type" or f.startswith("price_by_type."):
            assert c.excerpt and c.label == "확인됨" and not c.needs_extract, f


def test_store_price_by_type_current_price_and_change_vs_first(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    main = add_raw(
        (NOTICE / "2025000302_elif.txt").read_text(encoding="utf-8"),
        source_kind="notice_pdf",
        url=_url("2025000302_elif.txt"),
        region_id=region.id,
        fetched_at="2025-08-25T06:00:00+09:00",
    )
    store_raw_document(db_session, main)
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2025000302")).one()
    imui = add_raw(
        (NOTICE / "2026940173_elif_imui3.txt").read_text(encoding="utf-8"),
        source_kind="notice_pdf",
        url=_url("2026940173_elif_imui3.txt"),
        region_id=region.id,
        complex_id=cx.id,
        fetched_at="2026-08-15T06:00:00+09:00",
    )
    res = store_raw_document(db_session, imui)

    first, cur = first_terms(db_session, cx.id), current_terms(db_session, cx.id)
    assert first is not None and cur is not None
    assert (first.notice_no, cur.notice_no) == ("2025000302", "2026940173")
    assert cur.price_by_type is not None and cur.price_by_type["84A"] == {
        "max_price_won": 605_000_000,
        "floor_sample_price_won": 575_000_000,
        "floor_sample_text": "3층",
        "units": 2,
        "notice_type_code": "084.7800A",
    }
    assert first.price_by_type is not None and first.price_by_type["84A"]["max_price_won"] == 609_000_000
    # 출처 행: field = price_by_type.<type>.<항목>
    fp = db_session.scalars(
        select(FieldProvenance).where(
            FieldProvenance.entity == "payment_terms",
            FieldProvenance.entity_id == cur.id,
            FieldProvenance.field == "price_by_type.84A.max_price_won",
        )
    ).one()
    assert fp.chosen and fp.value_norm == "605000000" and fp.observed_on == "2026-08-14" and fp.excerpt

    # 현재 구매가(complex_type) = 현재 조건(최신 공고)의 값 — 가격 변경은 critical
    t84 = db_session.scalars(
        select(ComplexType).where(ComplexType.complex_id == cx.id, ComplexType.type_code == "84A")
    ).one()
    assert (t84.max_price_won, t84.floor_sample_price_won, t84.notice_type_code) == (
        605_000_000,
        575_000_000,
        "084.7800A",
    )
    ev = [e for e in res.change_events if e.entity == "complex_type" and e.field == "max_price_won"]
    assert any(e.entity_id == t84.id and e.severity == "critical" for e in ev)
    assert db_session.scalars(select(ChangeEvent).where(ChangeEvent.entity_id == t84.id)).first()
    # 최신 공고에 없는(배정 실패) 타입은 이전 값 그대로
    t98b = db_session.scalars(
        select(ComplexType).where(ComplexType.complex_id == cx.id, ComplexType.type_code == "98B")
    ).one()
    assert t98b.max_price_won == 675_000_000

    # §6-1 '임의공급 가격 변경': 판정 기준 타입(84A) 최초 대비 증감률
    assert price_change_vs_first(first.price_by_type, cur.price_by_type, "84A") == Decimal("-0.66")
    assert price_change_vs_first(first.price_by_type, cur.price_by_type, "98B") is None
    assert price_change_vs_first(None, cur.price_by_type, "84A") is None

    # 공고 순서를 바꿔 저장해도 현재 구매가는 최신 공고(observed_on) 값
    terms_rows = db_session.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == cx.id)).all()
    assert len(terms_rows) == 2


def test_price_order_independent_of_store_order(db_session: Session, region: Region, add_raw: AddRaw) -> None:
    """임의공급 공고를 먼저 저장해도(수집 시각이 늦어도) 원문 시점이 최신인 공고 가격이 채택된다."""
    imui = add_raw(
        (NOTICE / "2026940173_elif_imui3.txt").read_text(encoding="utf-8"),
        source_kind="notice_pdf",
        url=_url("2026940173_elif_imui3.txt"),
        region_id=region.id,
        fetched_at="2026-08-15T06:00:00+09:00",
    )
    store_raw_document(db_session, imui)
    main = add_raw(
        (NOTICE / "2025000302_elif.txt").read_text(encoding="utf-8"),
        source_kind="notice_pdf",
        url=_url("2025000302_elif.txt"),
        region_id=region.id,
        fetched_at="2026-10-09T06:00:00+09:00",  # 나중에 수집했지만 공고는 더 오래됨
    )
    store_raw_document(db_session, main)
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2025000302")).one()
    t84 = db_session.scalars(
        select(ComplexType).where(ComplexType.complex_id == cx.id, ComplexType.type_code == "84A")
    ).one()
    assert t84.max_price_won == 605_000_000


# ---------------------------------------------------------------- 공식 홈페이지 → intake_status 후보


def _site_raw(add_raw: AddRaw, region: Region, complex_id: int | None) -> object:
    text = (FIX / "official_site" / "popup_dom_text.txt").read_text(encoding="utf-8")
    return add_raw(
        text,
        source_kind="official_site",
        url="https://site.example.test/",
        region_id=region.id,
        complex_id=complex_id,
    )


def test_official_site_parser_emits_intake_status_text_candidates(raw_dir: Path) -> None:
    text = (FIX / "official_site" / "popup_dom_text.txt").read_text(encoding="utf-8")
    stored = store_raw(
        text.encode("utf-8"), source="official_site", day=date(2026, 10, 9), ext="txt", raw_dir=raw_dir
    )
    raw = dto(
        source_kind="official_site",
        url="https://site.example.test/",
        complex_id=4,
        path=stored.relpath,
        text_path=stored.relpath,
    )
    cands = OfficialSiteParser(raw_dir=raw_dir, complex_key=lambda cid: "2025000573").parse(raw)
    assert cands and {c.entity for c in cands} == {"intake_status"}
    assert {c.field for c in cands} == {"status_text"}
    first = cands[0]
    assert first.value == first.value_text == "선착순 동·호지정 계약 중"
    assert first.entity_key == "2025000573:official_popup" and first.entity_id is None
    assert first.source_kind == "official_site" and first.label == "확인됨" and first.source_rank == 1
    assert first.observed_on is None and first.checked_at == "2026-10-09"
    assert text[first.excerpt_start or 0 : first.excerpt_end] == first.excerpt
    assert any(c.value == "견본주택 개관 중 — 방문예약 후 상담" for c in cands)
    # 키워드 없는 줄은 후보가 아니다
    assert not any("세대창고" in str(c.value) for c in cands)
    # 렌더 스크린샷 행(image/png, text_path = 렌더 후 DOM 텍스트)은 path=headless_shot
    shot = raw.model_copy(update={"content_type": "image/png", "path": "official_site/x.png"})
    keys = {c.entity_key for c in OfficialSiteParser(raw_dir=raw_dir).parse(shot)}
    assert keys == {"complex_id=4:headless_shot"}
    # 옛 메타 JSON 행은 후보를 내지 않는다
    legacy = raw.model_copy(update={"content_type": "application/json; profile=official_site.meta"})
    assert OfficialSiteParser(raw_dir=raw_dir).parse(legacy) == []


def test_store_official_site_keys_by_applyhome_id_and_skips_table_write(
    db_session: Session, region: Region, add_raw: AddRaw
) -> None:
    cx = Complex(
        region_id=region.id,
        applyhome_id="2025000573",
        name="테스트 단지",
        former_names=[],
        apply_dates=[],
        contract_dates=[],
        inclusion_class="미분류",
    )
    db_session.add(cx)
    db_session.flush()
    raw = _site_raw(add_raw, region, cx.id)
    res = store_raw_document(db_session, raw)  # type: ignore[arg-type]
    intake = [c for c in res.candidates if c.entity == "intake_status"]
    assert intake and {c.entity_key for c in intake} == {"2025000573:official_popup"}
    # 상태 분류는 판정기·사람 몫 — store는 intake_status 행·출처 행을 만들지 않고 넘긴다
    assert {c.entity for c in res.skipped} == {"intake_status"}
    assert res.provenance_ids == []

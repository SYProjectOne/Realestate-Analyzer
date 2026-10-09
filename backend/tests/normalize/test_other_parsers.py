"""rtms·stats·official_site 파서, extract 요청, 실패 원문."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.protocols import Parser
from app.models import FieldProvenance, Region, RtmsTrade, Unsold
from app.normalize.notice_parser import NoticeParser
from app.normalize.official_site_parser import OfficialSiteParser, read_site, scan_text
from app.normalize.provenance import missing_provenance
from app.normalize.rtms_parser import RtmsParser, parse_rtms_xml
from app.normalize.stats_parser import StatsParser, parse_unsold_csv
from app.normalize.store import store_raw_document

from ._support import FIX, AddRaw, dto

RTMS_URL = (
    "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade?LAWD_CD=41570&DEAL_YMD=202609"
)


def test_parsers_satisfy_protocol() -> None:
    for p in (NoticeParser(), RtmsParser(), StatsParser(), OfficialSiteParser()):
        assert isinstance(p, Parser)


def test_rtms_openapi_xml() -> None:
    xml = (FIX / "rtms" / "apt_trade_41570_202609.xml").read_text(encoding="utf-8")
    c = parse_rtms_xml(xml, dto(source_kind="rtms", url=RTMS_URL))
    keys = sorted({x.entity_key for x in c})
    assert len(keys) == 3
    first = {x.field: x for x in c if x.entity_key == keys[0]}
    by_apt = {}
    for k in keys:
        f = {x.field: x.value for x in c if x.entity_key == k}
        by_apt[(f["apt_name"], f["deal_date"])] = f
    f = by_apt[("풍무센트럴푸르지오", "2026-09-12")]
    assert f["price_won"] == 725_000_000 and f["area_m2"] == 84.99 and f["floor"] == 15
    assert f["legal_dong_code"] == "4157010700" and f["completed_year"] == 2020
    assert f["cancelled"] is False and f["source"] == "openapi"
    assert by_apt[("풍무센트럴푸르지오", "2026-09-03")]["cancelled"] is True
    assert all(x.label == "확인됨" and x.source_rank == 1 for x in c)
    assert first["apt_name"].excerpt


def test_rtms_reprocessed_label() -> None:
    xml = (FIX / "rtms" / "apt_trade_41570_202609.xml").read_text(encoding="utf-8")
    c = parse_rtms_xml(xml, dto(source_kind="rtms", url="https://example-reprocessed.kr/apt"))
    assert {x.label for x in c} == {"재가공"} and {x.source_rank for x in c} == {2}
    assert {x.value for x in c if x.field == "source"} == {"reprocessed"}
    assert parse_rtms_xml("<not xml", dto(source_kind="rtms", url=RTMS_URL)) == []


def test_unsold_csv() -> None:
    text = (FIX / "stats" / "unsold_202606_202608.csv").read_text(encoding="utf-8")
    c = parse_unsold_csv(text, dto(source_kind="stats", url="https://stat.molit.go.kr/unsold.csv"))
    rows: dict[str, dict[str, object]] = {}
    for x in c:
        rows.setdefault(str(x.entity_key), {})[x.field] = x.value
    assert rows["41570:2026-08"] == {
        "ym": "2026-08",
        "scope_name": "김포시",
        "scope_code": "41570",
        "total": 1402,
        "post_completion": 97,
    }
    assert len(rows) == 4
    span = next(x for x in c if x.entity_key == "28260:2026-08" and x.field == "total")
    assert text[span.excerpt_start : span.excerpt_end].startswith("인천,서구,28260")


def test_store_rtms_and_unsold_idempotent(db_session: Session, region: Region, add_raw: AddRaw) -> None:
    xml = (FIX / "rtms" / "apt_trade_41570_202609.xml").read_text(encoding="utf-8")
    raw = add_raw(xml, source_kind="rtms", url=RTMS_URL, region_id=region.id, ext="xml")
    store_raw_document(db_session, raw)
    store_raw_document(db_session, raw)
    assert db_session.scalar(select(func.count()).select_from(RtmsTrade)) == 3
    t = db_session.scalars(select(RtmsTrade).where(RtmsTrade.price_won == 725_000_000)).one()
    assert t.legal_dong_code == "4157010700" and t.cancelled is False and t.raw_document_id == raw.id
    csv_text = (FIX / "stats" / "unsold_202606_202608.csv").read_text(encoding="utf-8")
    store_raw_document(
        db_session,
        add_raw(
            csv_text,
            source_kind="stats",
            url="https://stat.molit.go.kr/x.csv",
            region_id=region.id,
            ext="csv",
        ),
    )
    u = db_session.scalars(select(Unsold).where(Unsold.ym == "2026-08", Unsold.scope_code == "41570")).one()
    assert (u.total, u.post_completion, u.source_label) == (1402, 97, "확인됨")
    fp = db_session.scalars(
        select(FieldProvenance).where(FieldProvenance.entity == "unsold", FieldProvenance.entity_id == u.id)
    ).all()
    assert {r.field for r in fp} >= {"total", "post_completion"} and all(r.chosen for r in fp)
    assert missing_provenance(db_session) == []


def test_official_site_text_hits_without_status_judgement(raw_dir: Path) -> None:
    text = (FIX / "official_site" / "popup_dom_text.txt").read_text(encoding="utf-8")
    hits = scan_text(text)
    kw = {h.keyword for h in hits}
    assert {"선착순", "동·호지정", "계약 중", "방문예약"} <= kw
    h = next(h for h in hits if h.keyword == "선착순")
    assert h.excerpt == "선착순 동·호지정 계약 중" and text[h.start : h.end] == "선착순"


def test_official_site_403_is_data(raw_dir: Path) -> None:
    raw = dto(source_kind="official_site", url="https://opus-switzen.com/", http_status=403)
    res = read_site(raw)
    assert res.reason == "403" and res.hits == [] and res.checked_at == "2026-10-09"
    dns = read_site(
        dto(source_kind="official_site", url="https://x.invalid/", http_status=None, error_text="DNS")
    )
    assert dns.reason == "DNS"
    assert OfficialSiteParser().parse(raw) == []


def test_failed_or_scanned_notice_has_no_candidates() -> None:
    p = NoticeParser()
    assert p.parse(dto(source_kind="notice_pdf", url="https://x/?houseManageNo=1", http_status=404)) == []
    assert p.parse(dto(source_kind="notice_pdf", url="https://x/?houseManageNo=1", error_text="scan")) == []

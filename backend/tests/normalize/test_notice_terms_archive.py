"""공고문 납부 조건·전매·거주·입주월 파싱, extract 요청, 월별 아카이브."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Region
from app.normalize.archive import archive_kind, archived_notices, build_month_manifest, write_month_archive
from app.normalize.extract_request import build_extract_requests
from app.normalize.notice_parser import parse_notice_text
from app.normalize.store import store_raw_document

from ._support import NOTICE, AddRaw, dto, notice_manifest


def _fields(fname: str) -> dict[tuple[str, str], object]:
    raw = dto(source_kind="notice_pdf", url=notice_manifest()[fname]["url"])
    out: dict[tuple[str, str], object] = {}
    for c in parse_notice_text((NOTICE / fname).read_text(encoding="utf-8"), raw):
        if not c.needs_extract:
            out[(str(c.entity_key), c.field)] = c.value
    return out


def test_main_notice_terms_and_header() -> None:
    f = _fields("2025000302_elif.txt")
    k, p = "2025000302", "2025000302:2025000302"
    assert (k, "name") not in f  # R4-FIX D18-4: 제목 줄은 단지 이름 후보가 아니다(이름은 청약홈만)
    assert f[(k, "rewin_restriction_years")] == 10
    assert f[(k, "resale_months")] == 36 and f[(k, "resale_release_on_registration")] is True
    assert f[(k, "residency_months")] == 0 and f[(k, "price_cap")] == "적용"
    assert f[(k, "land_type")] == "공공택지" and f[(k, "regulated")] == "비규제"
    assert f[(k, "housing_type")] == "민영" and f[(k, "move_in_ym")] == "2028-03"
    assert f[(k, "units_total")] == 669 and f[(k, "units_special")] == 306
    assert f[(p, "notice_kind")] == "본청약" and f[(p, "effective_from")] == "2025-08-22"
    assert (f[(p, "down_payment_pct")], f[(p, "interim_pct")], f[(p, "balance_pct")]) == (10, 60, 30)
    sched = json.loads(str(f[(p, "interim_schedule")]))
    assert [s["due_date"] for s in sched] == [
        "2026-02-23",
        "2026-06-22",
        "2026-11-23",
        "2027-03-22",
        "2027-07-22",
        "2027-11-22",
    ]
    assert all(s["pct"] == 10 for s in sched)


def test_imui_notice_keys_to_original_complex() -> None:
    f = _fields("2026940173_elif_imui3.txt")
    p = "2025000302:2026940173"
    assert f[(p, "notice_kind")] == "임의" and f[(p, "effective_from")] == "2026-08-14"
    assert f[(p, "down_payment_pct")] == 5 and f[(p, "down_payment_first_won")] == 5_000_000
    assert f[("2025000302", "notice_date")] == "2025-08-22"  # 단지의 공고일은 최초 공고일
    # 임의공급 공고는 잔여 세대만 실으므로 complex_type의 면적·세대수는 내지 않는다. 가격은 현재 구매가
    # (계약 2026-10-09.2: complex_type 가격 = 현재 조건 공고의 값)로 낸다.
    fname = "2026940173_elif_imui3.txt"
    raw = dto(source_kind="notice_pdf", url=notice_manifest()[fname]["url"])
    cands = parse_notice_text((NOTICE / fname).read_text(encoding="utf-8"), raw)
    assert not [c for c in cands if c.entity == "complex_type" and c.field in ("area_m2", "units")]


def test_no_interim_notice() -> None:
    f = _fields("2026940185_gochon13.txt")
    p = "2023000579:2026940185"
    assert f[(p, "interim_pct")] == 0 and f[(p, "interim_schedule")] == "[]"
    assert f[(p, "down_payment_pct")] == 5 and f[(p, "balance_pct")] == 95


def test_extract_requests_group_by_entity() -> None:
    fname = "2026000329_hoban3.txt"
    raw = dto(source_kind="notice_pdf", url=notice_manifest()[fname]["url"])
    cands = parse_notice_text((NOTICE / fname).read_text(encoding="utf-8"), raw)
    reqs = build_extract_requests(cands)
    assert reqs and all(r.fields and r.text and len(r.text) <= 2000 for r in reqs)
    # 발췌 합본이 2,000자를 넘으면 같은 엔티티도 요청 여러 건으로 나뉜다(R3 3차 minor 23)
    mine = [r for r in reqs if (r.entity, r.entity_key) == ("complex", "2026000329")]
    assert "resale_months" in {f for r in mine for f in r.fields}
    assert all(r.payload["source_url"] == raw.url for r in mine)
    # 머리 표 발췌의 분양문의 전화번호는 판정기 요청 데이터에 넣지 않는다(guard 전 단계 마스킹)
    head_text = " ".join(r.text for r in mine)
    assert "1670-7830" not in head_text and "[REDACTED:phone]" in head_text


def test_archive_month_manifest_and_zip(
    db_session: Session, region: Region, add_raw: AddRaw, raw_dir: Path
) -> None:
    fname = "2025000271_harrington1.txt"
    raw = add_raw(
        (NOTICE / fname).read_text(encoding="utf-8"),
        source_kind="notice_pdf",
        url=notice_manifest()[fname]["url"],
        region_id=region.id,
        fetched_at="2026-09-03T06:00:00+09:00",
    )
    store_raw_document(db_session, raw)
    add_raw(
        "<table></table>",
        source_kind="applyhome_list",
        url="https://www.applyhome.co.kr/list",
        ext="html",
        fetched_at="2026-09-04T06:00:00+09:00",
    )
    add_raw(
        "other month",
        source_kind="notice_pdf",
        url="https://x/?houseManageNo=1",
        fetched_at="2026-10-01T06:00:00+09:00",
    )
    man = build_month_manifest(db_session, "2026-09")
    assert man.counts() == {"공고": 1, "목록": 1}
    out = write_month_archive(db_session, "2026-09", raw_dir=raw_dir, compress=True)
    assert out.manifest_path is not None and out.manifest_path.exists()
    assert out.zip_path is not None
    first = out.zip_path.read_bytes()
    again = write_month_archive(db_session, "2026-09", raw_dir=raw_dir, compress=True)
    assert again.zip_path is not None and again.zip_path.read_bytes() == first  # 결정적
    with zipfile.ZipFile(out.zip_path) as zf:
        assert "manifest.json" in zf.namelist() and raw.path in zf.namelist()
    assert (raw_dir / str(raw.path)).exists()  # 원문은 지우지 않는다
    assert [r.id for r in archived_notices(db_session, "2025000271")] == [raw.id]
    assert archive_kind("applyhome_detail", "https://x/selectAPTCompetitionPopup.do") == "경쟁률"
    assert archive_kind("rtms", "https://x") is None

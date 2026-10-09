"""reference: 법정동·행정동·매핑·세대수 참조 데이터 (DECISIONS D2-1, D3, T17).

완료 기준
- 사본 파일(contracts/fixtures/reference)로 legal_dong 적재, '연수구'·'김포시' 시군구 코드 조회
- 녹화 응답(respx)으로 refresh 2회 → raw_document 증가 0, 적재 변화 0
- 다운로드 실패(오류 페이지·503·DNS)도 raw_document 행 + 사본으로 동작
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.collectors.reference import ReferenceCollector, find_sigungu
from app.collectors.reference.jscode import (
    parse_attachments,
    parse_board,
    parse_jscode_zip,
    pick_article,
    pick_jscode,
    read_fixed_width,
)
from app.collectors.reference.legal_dong import (
    LEGAL_DONG_URL,
    ReferenceParseError,
    parse_legal_dong_text,
    parse_legal_dong_zip,
)
from app.collectors.reference.load import upsert_legal_dongs
from app.core.http import HttpClient
from app.models import AdminDong, AdminLegalMap, HouseholdStat, LegalDong, RawDocument

TODAY = date(2026, 10, 9)
MOIS = "https://www.mois.go.kr"


def _mock_all(router: respx.MockRouter, fx: Path, ref: Path, **override: Any) -> None:
    router.get("https://www.code.go.kr/robots.txt").respond(
        200, content=(fx / "codego_robots.txt").read_bytes()
    )
    router.get(LEGAL_DONG_URL).mock(
        return_value=override.get("legal")
        or httpx.Response(
            200,
            content=(ref / "legal_dong_full.zip").read_bytes(),
            headers={"content-type": "application/octet-stream;;charset=utf-8"},
        )
    )
    router.get(f"{MOIS}/robots.txt").respond(200, content=(fx / "mois_robots.txt").read_bytes())
    router.get(f"{MOIS}/frt/bbs/type001/commonSelectBoardList.do").mock(
        return_value=override.get("board")
        or httpx.Response(
            200,
            content=(fx / "mois_board.html").read_bytes(),
            headers={"content-type": "text/html;charset=UTF-8"},
        )
    )
    router.get(f"{MOIS}/frt/bbs/type001/commonSelectBoardArticle.do", params={"nttId": "129824"}).respond(
        200, content=(fx / "mois_article_129824.html").read_bytes(), headers={"content-type": "text/html"}
    )
    router.get(f"{MOIS}/cmm/fms/FileDown.do", params={"fileSn": "1"}).respond(
        200, content=(ref / "jscode20260930.zip").read_bytes(), headers={"content-type": "application/zip"}
    )
    router.get("https://jumin.mois.go.kr/robots.txt").respond(404)
    router.post("https://jumin.mois.go.kr/downloadCsv.do").mock(
        return_value=override.get("jumin")
        or httpx.Response(200, content=(ref / "jumin_households_202609.csv").read_bytes())
    )


# --- 파서 (녹화·사본 파일)


def test_legal_dong_copy_parses_existing_and_abolished(reference_copy: Path) -> None:
    records = parse_legal_dong_zip((reference_copy / "legal_dong_full.zip").read_bytes())
    by_code = {r.code: r for r in records}
    assert len(records) > 50_000
    assert sum(r.active for r in records) > 20_000
    yeonsu = by_code["2818500000"]
    assert (yeonsu.sido_name, yeonsu.sigungu_name, yeonsu.sigungu_code, yeonsu.active) == (
        "인천광역시",
        "연수구",
        "28185",
        True,
    )
    songdo = by_code["2818510600"]
    assert (songdo.sigungu_name, songdo.eupmyeondong_name, songdo.ri_name) == ("연수구", "송도동", None)
    ri = by_code["4157025021"]
    assert (ri.sigungu_name, ri.eupmyeondong_name, ri.ri_name) == ("김포시", "통진읍", "도사리")
    gu_in_city = by_code["4111112900"]
    assert gu_in_city.sigungu_name == "수원시 장안구"
    assert by_code["3611025021"].sigungu_name is None  # 세종: 시군구 없음


def test_geomdan_split_is_in_code_table(reference_copy: Path) -> None:
    """2026-07 검단구 분구: 옛 서구(28260)는 폐지로 남고 검단구(28290)가 현존.

    둘 다 후보가 될 수 있다(D3).
    """
    by_code = {r.code: r for r in parse_legal_dong_zip((reference_copy / "legal_dong_full.zip").read_bytes())}
    assert by_code["2826000000"].active is False
    assert by_code["2826011400"].full_name == "인천광역시 서구 당하동"
    assert by_code["2829000000"].active is True
    assert by_code["2829010400"].full_name == "인천광역시 검단구 당하동"


def test_error_page_is_not_a_legal_dong_file(fixtures_dir: Path) -> None:
    with pytest.raises(ReferenceParseError):
        parse_legal_dong_zip((fixtures_dir / "codego_file_missing.html").read_bytes())
    with pytest.raises(ReferenceParseError):
        parse_legal_dong_text("법정동코드\t법정동명\t폐지여부\n")


def test_mois_board_picks_effective_article_and_zip(fixtures_dir: Path) -> None:
    articles = parse_board((fixtures_dir / "mois_board.html").read_text(encoding="utf-8"))
    assert len(articles) >= 4
    chosen = pick_article(articles, TODAY)
    assert chosen is not None and chosen.ntt_id == "129824"  # 2026.10.12 시행 글은 아직 아님
    assert chosen.effective == date(2026, 9, 30)
    atts = parse_attachments((fixtures_dir / "mois_article_129824.html").read_text(encoding="utf-8"))
    zip_att = pick_jscode(atts)
    assert zip_att is not None
    assert zip_att.url.endswith("fileSn=1")
    assert "말소" not in zip_att.name


def test_jscode_copy_parses_admin_dongs_and_mapping(reference_copy: Path) -> None:
    data = parse_jscode_zip((reference_copy / "jscode20260930.zip").read_bytes())
    assert data.source_date == "2026-09-30"
    admins = {a.code: a for a in data.admin_dongs}
    assert admins["2818582000"].full_name == "인천광역시 연수구 송도1동"
    assert admins["2818582000"].sigungu_code == "28185"
    assert ("2829054000", "2829010400") in set(data.mappings)  # 검단구 당하동(행정) ↔ 당하동(법정)
    assert len(set(data.mappings)) == len(data.mappings)


def test_fixed_width_uses_byte_offsets() -> None:
    # 한글은 cp949 로 2바이트 — 열 위치는 글자 수가 아니라 바이트로 맞춰져 있다
    header = "코드".encode("cp949") + b" " + "이름".encode("cp949") + b" " * 9 + "비고".encode("cp949")
    line = b"11   " + "서울특별시".encode("cp949") + b"   " + b"X"
    assert header.index("이름".encode("cp949")) == 5
    assert header.index("비고".encode("cp949")) == line.index(b"X")
    rows = read_fixed_width(header + b"\r\n" + line + b"\r\n")
    assert rows == [{"코드": "11", "이름": "서울특별시", "비고": "X"}]


# --- 적재


def test_copy_loads_legal_dong_and_finds_sigungu(db_engine: Engine, reference_copy: Path) -> None:
    records = parse_legal_dong_zip((reference_copy / "legal_dong_full.zip").read_bytes())
    with Session(db_engine) as s:
        stats = upsert_legal_dongs(s, records, source_date="2026-10-09")
        s.commit()
        assert stats.inserted == len(records)
        assert [r.sigungu_code for r in find_sigungu(s, "연수구")] == ["28185"]
        assert [r.sigungu_code for r in find_sigungu(s, "김포시")] == ["41570"]
        seo = find_sigungu(s, "서구")
        assert ("28260", False) in [(r.sigungu_code, r.active) for r in seo]  # 인천 서구(폐지)
        assert [r.sigungu_code for r in find_sigungu(s, "검단구")] == ["28290"]
        again = upsert_legal_dongs(s, records, source_date="2026-10-09")
        assert (again.inserted, again.updated, again.deactivated) == (0, 0, 0)


def test_refresh_from_recordings_is_idempotent(
    db_engine: Engine,
    raw_dir: Path,
    fixtures_dir: Path,
    reference_copy: Path,
    http: HttpClient,
    count: Callable[[type[Any]], int],
) -> None:
    with respx.mock(assert_all_called=False) as router:
        _mock_all(router, fixtures_dir, reference_copy)
        collector = ReferenceCollector(http=http, fallback_dir=None, today=TODAY)
        first = collector.refresh()
        assert first.errors == []
        assert first.used_fallback == []
        assert first.jscode_source_date == "2026-09-30"
        assert first.household_ym == "2026-09"
        assert first.legal_dong is not None and first.legal_dong.inserted > 50_000
        n_raw = count(RawDocument)
        n_legal, n_admin, n_map, n_hh = (
            count(LegalDong),
            count(AdminDong),
            count(AdminLegalMap),
            count(HouseholdStat),
        )
        assert n_raw == 5  # 법정동 zip, 게시판, 글, jscode zip, 세대 CSV
        assert n_admin > 3_000 and n_map > 20_000 and n_hh > 3_000

        second = ReferenceCollector(http=http, fallback_dir=None, today=TODAY).refresh()
        assert count(RawDocument) == n_raw  # T17: 같은 원문 → 행 증가 0
        assert (count(LegalDong), count(AdminDong), count(AdminLegalMap), count(HouseholdStat)) == (
            n_legal,
            n_admin,
            n_map,
            n_hh,
        )
        assert second.legal_dong is not None and second.legal_dong.total_changes == 0
        assert second.admin_legal_map is not None and second.admin_legal_map.total_changes == 0

    with Session(db_engine) as s:
        docs = s.scalars(select(RawDocument)).all()
        assert {d.source_kind for d in docs} == {"reference", "stats"}
        assert all(d.path and (raw_dir / d.path).exists() for d in docs)
        assert all(d.url.startswith("https://") for d in docs)
        hh = s.scalars(select(HouseholdStat).where(HouseholdStat.scope_code == "2818582000")).one()
        assert (hh.ym, hh.households, hh.label, hh.reason) == ("2026-09", 14632, "추정", "주민등록 세대")


def test_refresh_falls_back_to_copy_and_keeps_failure_rows(
    db_engine: Engine,
    fixtures_dir: Path,
    reference_copy: Path,
    http: HttpClient,
    count: Callable[[type[Any]], int],
) -> None:
    """code.go.kr 가 '파일 없음' 페이지(실제 녹화)를, 행안부가 503 을, 주민등록이 DNS 실패를 주는 날."""
    missing = httpx.Response(
        200,
        content=(fixtures_dir / "codego_file_missing.html").read_bytes(),
        headers={"content-type": "text/html;charset=utf-8"},
    )
    with respx.mock(assert_all_called=False) as router:
        _mock_all(router, fixtures_dir, reference_copy, legal=missing, board=httpx.Response(503))
        router.get("https://jumin.mois.go.kr/robots.txt").mock(
            side_effect=httpx.ConnectError("[Errno 11001] getaddrinfo failed")
        )
        report = ReferenceCollector(http=http, fallback_dir=reference_copy, today=TODAY).refresh()

    assert set(report.used_fallback) == {
        "legal_dong_full.zip",
        "jscode20260930.zip",
        "jumin_households_202609.csv",
    }
    assert report.legal_dong_source_date == "2026-10-09"  # manifest 의 내려받은 날
    assert count(LegalDong) > 50_000 and count(AdminDong) > 3_000 and count(HouseholdStat) > 3_000
    with Session(db_engine) as s:
        docs = s.scalars(select(RawDocument)).all()
        by_url = {d.url: d for d in docs}
        board_fail = next(d for d in docs if "commonSelectBoardList" in d.url)
        assert (board_fail.http_status, board_fail.path) == (503, None)
        jumin_fail = next(d for d in docs if "jumin.mois.go.kr" in d.url)
        assert (jumin_fail.http_status, jumin_fail.error_text, jumin_fail.path) == (None, "DNS", None)
        assert "fixture://reference/legal_dong_full.zip" in by_url
        error_page = next(d for d in docs if "codeFullDown" in d.url)
        assert error_page.http_status == 200 and error_page.path is not None  # 오류 페이지도 원문으로 남김


@pytest.mark.live
def test_live_refresh_downloads_current_files(db_engine: Engine) -> None:
    """실제 code.go.kr·행안부·주민등록 접속(`pytest -m live`)."""
    report = ReferenceCollector(fallback_dir=None).refresh()
    assert report.errors == [], report.errors
    assert report.legal_dong is not None and report.admin_dong is not None and report.household is not None
    with Session(db_engine) as s:
        assert [r.sigungu_code for r in find_sigungu(s, "연수구")] == ["28185"]

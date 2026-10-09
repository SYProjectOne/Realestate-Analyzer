"""청약홈 파서·지역 필터·조회 창·원문 저장 단위 테스트 (녹화 HTML 사용)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.collectors.applyhome import month_windows, site
from app.collectors.applyhome.area import AreaFilter, build_region_areas, sido_short_name
from app.collectors.applyhome.parse import detail_supply_address, notice_pdf_links, parse_list
from app.collectors.applyhome.raw import RawStore, error_text_of
from app.core.http import FetchResult
from app.models import LegalDong

from .conftest import make_region
from .replay import Recording, request_key


def _list_html(recording: Recording, kind: site.ListKind, area: str, page: int) -> str:
    key = request_key("POST", site.list_url(kind), site.list_form(area, "202512", "202611", page))
    return recording.body(recording.entries[key]).decode("utf-8")


def test_parse_list_pages(recording: Recording) -> None:
    apt = parse_list(_list_html(recording, "apt", "인천", 1), "apt")
    assert apt.total is not None and apt.total >= 10
    assert len(apt.rows) == 10
    row = apt.rows[0]
    assert row.house_manage_no.isdigit() and row.pblanc_no.isdigit() and row.name
    assert row.area == "인천" and row.house_secd is None
    assert row.notice_date is not None and row.last_date is not None and row.last_date >= row.notice_date

    rem = parse_list(_list_html(recording, "remndr", "경기", 1), "remndr")
    assert rem.total is not None and rem.total > 100
    assert all(r.house_secd in {"04", "06", "11"} for r in rem.rows)
    assert all(r.area == "경기" for r in rem.rows)


def test_detail_address_and_notice_links(recording: Recording) -> None:
    details = [
        e
        for e in recording.entries.values()
        if e.method == "GET" and "Detail" in e.url and "Competition" not in e.url
    ]
    assert len(details) > 100
    with_pdf = 0
    for e in details:
        html = recording.body(e).decode("utf-8")
        address = detail_supply_address(html)
        assert address, e.url
        links = notice_pdf_links(html)
        assert all(link.startswith("https://static.applyhome.co.kr/ai/aia/getAtchmnfl.do?") for link in links)
        with_pdf += bool(links)
    assert with_pdf > len(details) // 2


@pytest.mark.parametrize(
    ("full", "short"),
    [
        ("인천광역시", "인천"),
        ("서울특별시", "서울"),
        ("경기도", "경기"),
        ("충청북도", "충북"),
        ("경상남도", "경남"),
        ("전라북도", "전북"),
        ("전북특별자치도", "전북"),
        ("강원특별자치도", "강원"),
        ("제주특별자치도", "제주"),
        ("세종특별자치시", "세종"),
    ],
)
def test_sido_short_name(full: str, short: str) -> None:
    assert sido_short_name(full) == short


def test_area_filter_token_boundaries() -> None:
    f = AreaFilter(sido_code="26", area="부산", sigungu={("서구",)})
    assert f.matches("부산광역시 서구 암남동 1")
    assert not f.matches("부산광역시 강서구 명지동 1")  # '서구'가 '강서구' 안에 있어도 토큰이 다르다
    g = AreaFilter(sido_code="41", area="경기", sigungu={("수원시", "장안구")}, dongs={"고촌읍"})
    assert g.matches("경기도 수원시 장안구 파장동 1")
    assert g.matches("경기도 김포시 고촌읍 향산리 1")
    assert not g.matches("경기도 수원시 권선구 1")
    assert not g.matches(None)
    # 행정구역이 없는 공급위치는 통과(범위 경계 판단은 WP2)
    assert g.matches("용현ㆍ학익 1블록 도시개발구역 내 공동1-1BL")
    assert not g.matches("경기도 화성시 검단신도시 1")
    assert AreaFilter(sido_code="28", area="인천", whole=True).matches(None)


def test_build_region_areas_from_selections_and_legal_dong(db_session: Session) -> None:
    region = make_region()
    areas = build_region_areas(region, db_session)  # legal_dong 표가 비어 있어도 selections 로 동작
    icn, ggi = areas.filters["28"], areas.filters["41"]
    assert (icn.area, ggi.area) == ("인천", "경기")
    assert {("연수구",), ("서구",), ("검단구",), ("계양구",)} == icn.sigungu
    assert icn.dongs == {"송도동"} and ggi.sigungu == {("김포시",)}

    # legal_dong 표가 있으면 region.legal_dong_codes 의 읍면동 이름도 쓴다
    # (분구 후 새 구 이름이 주소에 나와도 동 이름으로 통과)
    db_session.add_all(
        [
            LegalDong(
                code="2826011400",
                sido_name="인천광역시",
                sigungu_name="서구",
                eupmyeondong_name="원당동",
                full_name="인천광역시 서구 원당동",
                sigungu_code="28260",
                source_date="2026-07-01",
            ),
            LegalDong(
                code="4100000000",
                sido_name="경기도",
                sigungu_name=None,
                eupmyeondong_name=None,
                full_name="경기도",
                sigungu_code="41000",
                source_date="2026-07-01",
            ),
        ]
    )
    db_session.flush()
    region2 = make_region(
        selections=[{"kind": "sigungu", "code": "28260", "full_name": "인천광역시 서구"}],
        sido_codes=["28"],
        sigungu_codes=["28260"],
        legal_dong_codes=["2826011400"],
    )
    f = build_region_areas(region2, db_session).filters["28"]
    assert f.matches("인천광역시 검단구 원당동 1000")
    assert not f.matches("인천광역시 부평구 산곡동 10")


def test_region_area_override_and_whole_sido() -> None:
    region = make_region(
        selections=[{"kind": "sido", "code": "28", "full_name": "인천광역시"}],
        sido_codes=["28"],
        applyhome_query={"areas": {"28": "인천"}},
    )
    f = build_region_areas(region, None).filters["28"]
    assert f.whole and f.area == "인천" and f.matches("인천광역시 부평구 산곡동")


def test_month_windows_split_at_12_months() -> None:
    assert month_windows((2025, 12), (2026, 11)) == [("202512", "202611")]
    assert month_windows((2024, 10), (2026, 11)) == [
        ("202410", "202509"),
        ("202510", "202609"),
        ("202610", "202611"),
    ]


def _result(url: str, status: int | None, content: bytes = b"", **kw: object) -> FetchResult:
    return FetchResult(
        url=url,
        status=status,
        headers={"content-type": "text/html;charset=UTF-8"} if status else {},
        content=content,
        error=None if status and status < 400 else (kw.pop("error", None) or f"HTTP {status}"),  # type: ignore[arg-type]
        elapsed_ms=1,
        attempts=1,
        fetched_at=datetime(2026, 10, 8, 21, 30, tzinfo=UTC),  # KST 2026-10-09 06:30
        **kw,  # type: ignore[arg-type]
    )


def test_raw_store_idempotent_success_and_failure(db_session: Session, raw_dir: object) -> None:
    store = RawStore(db_session)
    ok = _result("https://www.applyhome.co.kr/x", 200, b"<html>same</html>")
    a = store.save(ok, source_kind="applyhome_detail", ext="html", region_id=None)
    b = store.save(ok, source_kind="applyhome_detail", ext="html", region_id=None)
    assert a.created and not b.created and a.row.id == b.row.id
    assert a.row.path == f"applyhome_detail/2026-10-09/{a.row.sha256}.html"
    assert a.row.fetched_at == "2026-10-09T06:30:00+09:00"

    denied = _result("https://www.applyhome.co.kr/y", 403, b"Forbidden")
    f1 = store.save(denied, source_kind="applyhome_list", ext="html", region_id=None)
    f2 = store.save(denied, source_kind="applyhome_list", ext="html", region_id=None)
    assert f1.created and not f2.created
    assert (f1.row.http_status, f1.row.path, f1.row.error_text) == (403, None, None)
    import hashlib

    assert f1.row.sha256 == hashlib.sha256(b"fail:https://www.applyhome.co.kr/y:403:2026-10-09").hexdigest()


def test_error_text_kinds() -> None:
    base = {
        "url": "https://x.example/",
        "status": None,
        "headers": {},
        "content": b"",
        "elapsed_ms": 0,
        "attempts": 1,
    }
    assert error_text_of(FetchResult(**base, error="timeout: ReadTimeout", error_kind="timeout")) == "timeout"  # type: ignore[arg-type]
    dns = FetchResult(**base, error="connect: [Errno 11001] getaddrinfo failed", error_kind="connect")  # type: ignore[arg-type]
    assert error_text_of(dns) == "DNS"
    refused = FetchResult(**base, error="connect: [Errno 111] Connection refused", error_kind="connect")  # type: ignore[arg-type]
    assert error_text_of(refused) == "connect"
    robots = FetchResult(**base, error="blocked_by_robots", error_kind="robots", blocked_by_robots=True)  # type: ignore[arg-type]
    assert error_text_of(robots) == "robots"

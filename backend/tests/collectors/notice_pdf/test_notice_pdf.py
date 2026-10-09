"""모집공고문 PDF 수집기 — 녹화 재생(respx) 오프라인 테스트 (WP1a 완료 기준).

- 공고문 PDF → txt(+표 JSON), 스캔 PDF 픽스처 → '확인 불가(스캔)'(error_text='scan')
- 같은 입력 2회 → raw_document 증가 0, 403 → http_status=403 행
픽스처: 실제 청약홈 공고문 3개(무순위·임의공급, 2026-10-09 녹화)
      + 스캔 PDF(실제 공고문 2쪽을 이미지로만 다시 만든 PDF).
청약홈 상세 원문은 applyhome 녹화 zip 에서 가져온다.
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import respx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collectors.applyhome import site
from app.collectors.applyhome.parse import notice_pdf_links
from app.collectors.applyhome.raw import RawStore
from app.collectors.notice_pdf import NoticePdfCollector, extract_pdf
from app.collectors.notice_pdf.collector import error_text_for
from app.core.contracts_gen import Region, Snapshot
from app.core.http import FetchResult, HttpClient
from app.core.paths import resolve_raw_path
from app.models import RawDocument as RawRow
from app.models import Region as RegionRow

HERE = Path(__file__).parent
FIX = HERE / "fixtures"
AH_ZIP = HERE.parent / "applyhome" / "fixtures" / "applyhome_2026-10-09.zip"
TEXT_PDFS = {
    "2026910242": "notice_2026910242.pdf",
    "2026940062": "notice_2026940062.pdf",
    "2026940173": "notice_2026940173.pdf",
}
SCAN_HM = "2026940035"  # 이 단지의 공고문 링크에는 스캔 PDF 를 돌려준다
FORBIDDEN_HM = "2026940078"  # 이 단지의 공고문 링크는 403
OUT_OF_REGION_HM = "2026940212"  # 인천 제물포구 — 지역 밖(링크를 모으지 않아야 한다)

REGION: dict[str, Any] = {
    "id": 1,
    "name": "인천 송도·검단 + 김포",
    "query_text": "송도, 검단, 김포시",
    "selections": [
        {"kind": "legal_dong", "code": "2818510600", "full_name": "인천광역시 연수구 송도동"},
        {"kind": "sigungu", "code": "28260", "full_name": "인천광역시 서구"},
        {"kind": "sigungu", "code": "28265", "full_name": "인천광역시 검단구"},
        {"kind": "sigungu", "code": "41570", "full_name": "경기도 김포시"},
    ],
    "sido_codes": ["28", "41"],
    "sigungu_codes": ["28185", "28260", "28265", "41570"],
    "legal_dong_codes": ["2818510600"],
    "living_areas": [],
    "age_premium_coef": {"c_per_year": 0.015, "cap_years": 8, "label": "추정"},
    "supply_ref_pct": 0.08,
    "applyhome_query": {},
    "status": "ready",
    "created_at": "2026-10-09T06:00:00+09:00",
}


def _detail_html(hm: str) -> bytes:
    with zipfile.ZipFile(AH_ZIP) as z:
        return z.read(f"detail_remndr_{hm}_{hm}.html")


def _ok(url: str, content: bytes) -> FetchResult:
    return FetchResult(
        url=url,
        status=200,
        headers={"content-type": "text/html;charset=UTF-8"},
        content=content,
        error=None,
        elapsed_ms=1,
        attempts=1,
        fetched_at=datetime(2026, 10, 8, 21, 0, tzinfo=UTC),
    )


@pytest.fixture
def region(db_session: Session) -> Region:
    r = Region.model_validate(REGION)
    db_session.add(
        RegionRow(
            id=r.id,
            name=r.name,
            query_text=r.query_text,
            selections=[s.model_dump() for s in r.selections],
            sido_codes=r.sido_codes,
            sigungu_codes=r.sigungu_codes,
            legal_dong_codes=r.legal_dong_codes,
            living_areas=[],
            age_premium_coef=r.age_premium_coef.model_dump(),
            supply_ref_pct=r.supply_ref_pct,
            applyhome_query={},
            status=r.status,
            created_at=r.created_at,
        )
    )
    db_session.flush()
    return r


@pytest.fixture
def snapshot() -> Snapshot:
    return Snapshot(
        id=1, region_id=1, asof_date="2026-10-09", status="building", degraded=False, created_at="x"
    )


@pytest.fixture
def links(db_session: Session, raw_dir: Path, region: Region) -> dict[str, str]:
    """청약홈 상세 원문(지역 안 5 + 지역 밖 1)을 raw_document 에 넣고 단지별 공고문 링크를 돌려준다."""
    store = RawStore(db_session)
    out: dict[str, str] = {}
    for hm in [*TEXT_PDFS, SCAN_HM, FORBIDDEN_HM, OUT_OF_REGION_HM]:
        html = _detail_html(hm)
        store.save(
            _ok(site.detail_url("remndr", hm, hm), html),
            source_kind="applyhome_detail",
            ext="html",
            region_id=1,
        )
        out[hm] = notice_pdf_links(html.decode("utf-8"))[0]
    db_session.flush()
    return out


@pytest.fixture
def http() -> Iterator[HttpClient]:
    c = HttpClient(rate_per_host=1.0, max_retries=0, jitter=0.0, sleep=lambda s: None)
    yield c
    c.close()


def _router(links: dict[str, str], *, html_for: str | None = None) -> respx.MockRouter:
    router = respx.mock(assert_all_called=False)
    router.get(url__regex=r"https://static\.applyhome\.co\.kr/robots\.txt").respond(404)
    pdf = {"content-type": "application/octet-stream;charset=UTF-8"}
    for hm, name in TEXT_PDFS.items():
        if hm == html_for:
            router.get(links[hm]).respond(200, html="<html>잘못된 접근입니다</html>")
            continue
        router.get(links[hm]).respond(200, content=(FIX / name).read_bytes(), headers=pdf)
    router.get(links[SCAN_HM]).respond(
        200, content=(FIX / "scan_2026940062_p1p3.pdf").read_bytes(), headers=pdf
    )
    router.get(links[FORBIDDEN_HM]).respond(403, text="Forbidden")
    return router


def _count(session: Session) -> int:
    return int(
        session.scalar(select(func.count()).select_from(RawRow).where(RawRow.source_kind == "notice_pdf"))
        or 0
    )


def test_collect_pdfs_text_scan_403_idempotent(
    db_session: Session,
    raw_dir: Path,
    region: Region,
    snapshot: Snapshot,
    links: dict[str, str],
    http: HttpClient,
) -> None:
    with _router(links):
        docs = NoticePdfCollector(http=http, session=db_session, ocr=None).fetch(region, snapshot, None)
    by_url = {d.url: d for d in docs}
    assert links[OUT_OF_REGION_HM] not in by_url  # 지역 밖 단지의 공고문은 받지 않는다
    assert len(docs) == 5 and _count(db_session) == 5

    for hm in TEXT_PDFS:
        d = by_url[links[hm]]
        assert d.http_status == 200 and d.error_text is None and d.region_id == 1
        assert d.path and d.path.endswith(".pdf") and d.text_path and d.text_path.endswith(".txt")
        text = resolve_raw_path(d.text_path).read_text(encoding="utf-8")
        assert "입주자모집공고" in text.replace(" ", "") and "\f" in text
        tables = json.loads(resolve_raw_path(d.text_path[:-4] + ".json").read_text(encoding="utf-8"))
        assert tables and all({"page", "tables"} <= set(t) for t in tables)

    scan = by_url[links[SCAN_HM]]
    assert scan.http_status == 200 and scan.path and scan.error_text == "scan" and scan.text_path is None
    denied = by_url[links[FORBIDDEN_HM]]
    assert denied.http_status == 403 and denied.path is None

    # 같은 입력 2회 → 증가 0, 같은 행
    with _router(links):
        again = NoticePdfCollector(http=http, session=db_session, ocr=None).fetch(region, snapshot, None)
    assert _count(db_session) == 5
    assert {d.id for d in again} == {d.id for d in docs}
    # 이미 받은 PDF 는 다시 받지 않는다(refetch=True 면 받되 같은 sha256 이라 행은 그대로)
    with _router(links) as router:
        NoticePdfCollector(http=http, session=db_session, ocr=None, refetch=True).fetch(
            region, snapshot, None
        )
        assert router.calls.call_count >= 5
    assert _count(db_session) == 5


def test_extract_text_pdf_has_price_table() -> None:
    ex = extract_pdf((FIX / "notice_2026940062.pdf").read_bytes())
    assert ex.method == "pdfplumber" and not ex.scan_pages and ex.page_count >= 5
    assert "공급금액" in ex.text.replace(" ", "") or "분양가" in ex.text
    assert ex.tables and error_text_for(ex) is None


def test_extract_scan_pdf_is_unverifiable() -> None:
    ex = extract_pdf((FIX / "scan_2026940062_p1p3.pdf").read_bytes())
    assert ex.scanned and ex.scan_pages == [0, 1] and not ex.tables
    assert error_text_for(ex) == "scan"  # 화면: 확인 불가(스캔)


def test_extract_scan_with_ocr_function() -> None:
    def fake_ocr(content: bytes, pages: list[int]) -> dict[int, str]:
        return {p: f"OCR 텍스트 페이지 {p} 공급금액 41,500" for p in pages}

    ex = extract_pdf((FIX / "scan_2026940062_p1p3.pdf").read_bytes(), ocr=fake_ocr)
    assert ex.ocr_pages == [0, 1] and "41,500" in ex.text
    assert error_text_for(ex) == "ocr"  # 라벨 추정(OCR)


def test_pypdf_fallback_and_broken_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    import pdfplumber

    def broken(*a: object, **k: object) -> object:
        raise ValueError("pdfplumber 실패 흉내")

    monkeypatch.setattr(pdfplumber, "open", broken)
    ex = extract_pdf((FIX / "notice_2026910242.pdf").read_bytes())
    assert ex.method == "pypdf" and not ex.scan_pages and "입주자" in ex.text
    bad = extract_pdf(b"%PDF-1.4 not really a pdf")
    assert bad.method == "none" and bad.error and error_text_for(bad).startswith("pdf_parse:")  # type: ignore[union-attr]


def test_not_pdf_response_is_flagged(
    db_session: Session,
    raw_dir: Path,
    region: Region,
    snapshot: Snapshot,
    links: dict[str, str],
    http: HttpClient,
) -> None:
    with _router(links, html_for="2026910242"):
        docs = NoticePdfCollector(http=http, session=db_session, ocr=None).fetch(region, snapshot, None)
    bad = next(d for d in docs if d.url == links["2026910242"])
    assert bad.http_status == 200 and bad.error_text == "not_pdf" and bad.text_path is None
    assert bad.path and bad.path.endswith(".html")


@pytest.mark.live
def test_live_download_notice_pdf(test_settings: object) -> None:
    url = "https://static.applyhome.co.kr/ai/aia/getAtchmnfl.do?houseManageNo=2026940062&pblancNo=2026940062&atchmnflSeqNo=1766146&atchmnflSn=1"
    with HttpClient() as c:
        r = c.get(url)
    assert r.ok and r.content[:4] == b"%PDF"
    assert extract_pdf(r.content).page_count > 0

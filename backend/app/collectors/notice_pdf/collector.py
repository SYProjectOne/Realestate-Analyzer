"""모집공고문 PDF 수집기 (RA §5 WP1, Collector 프로토콜, DECISIONS D5).

지역 1개에 대해
1. 저장된 청약홈 상세 원문(``applyhome_detail``, 성공 행, URL 별 최신) 중 공급위치가 region 사전 필터를
   통과하는 것에서 모집공고문 링크(``getAtchmnfl.do``)를 모은다 — 청약홈 수집기가 먼저 돌아야 한다.
2. 링크마다 PDF 를 받는다. 이미 성공한 URL 은 다시 받지 않고 기존 행을 돌려준다(첨부 번호가 바뀌면 새 URL).
3. 새 PDF 는 ``extract_pdf`` 로 텍스트(+표 JSON)를 뽑아 원문 옆에 ``{sha256}.txt``·``{sha256}.json`` 으로
   저장하고 ``text_path`` 에 txt 상대 경로를 둔다.

raw_document.error_text (성공 행에서의 의미)
- ``scan``: 텍스트 레이어가 전혀 없음 → 화면 '확인 불가(스캔)', 사람 입력(OCR 미설치·미채택 시 기본값)
- ``ocr``: 전 페이지 스캔을 OCR 로 읽음 → 값 라벨 '추정(OCR)'
- ``scan_partial:3,4`` / ``ocr_partial:3,4``: 일부 페이지(1부터 센 번호)만 스캔 / 그 페이지를 OCR 로 읽음
- ``pdf_parse: …``: pdfplumber·pypdf 모두 실패(text_path 없음)
- ``not_pdf``: 200 이지만 PDF 가 아님(오류 HTML 등)
실패 응답(403·5xx·DNS·timeout)은 다른 수집기와 같은 실패 행이다.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collectors.applyhome import parse as ah_parse
from app.collectors.applyhome import site as ah_site
from app.collectors.applyhome.area import RegionAreas, address_tokens, build_region_areas, sido_short_name
from app.collectors.applyhome.raw import RawStore, Stored, to_contract
from app.collectors.notice_pdf.extract import OcrFn, PdfExtraction, extract_pdf, is_pdf
from app.core.contracts_gen import RawDocument, Region, Snapshot
from app.core.db import get_sessionmaker
from app.core.http import HttpClient
from app.core.paths import raw_path, raw_relpath, resolve_raw_path
from app.models import Complex
from app.models import RawDocument as RawRow

__all__ = ["NoticePdfCollector", "error_text_for", "write_text_atomic"]

SOURCE = "notice_pdf"
_DETAIL_PATHS = tuple(ep.detail_path for ep in ah_site.ENDPOINTS.values())


def write_text_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def error_text_for(ex: PdfExtraction) -> str | None:
    if ex.method == "none":
        return f"pdf_parse: {ex.error}"[:500]
    if not ex.scan_pages:
        return None
    if ex.scanned:
        return "ocr" if len(ex.ocr_pages) == ex.page_count else "scan"
    if ex.ocr_pages and set(ex.ocr_pages) == set(ex.scan_pages):
        return "ocr_partial:" + ",".join(str(p + 1) for p in ex.ocr_pages)
    return "scan_partial:" + ",".join(str(p + 1) for p in ex.scan_pages)


class NoticePdfCollector:
    """``fetch(region, snapshot, since) -> list[RawDocument]`` (app.core.protocols.Collector)."""

    source_kinds = (SOURCE,)

    def __init__(
        self,
        *,
        http: HttpClient | None = None,
        session: Session | None = None,
        ocr: OcrFn | Literal["auto"] | None = "auto",
        refetch: bool = False,
    ) -> None:
        """``ocr='auto'``: 선택 의존성 OCR 엔진이 설치돼 있으면 쓴다(``ocr.load_ocr``). None 이면 OCR 없음."""
        self._http = http
        self._session = session
        self._ocr_setting = ocr
        self._ocr: OcrFn | None = None
        self._ocr_loaded = False
        self._refetch = refetch

    def _get_ocr(self) -> OcrFn | None:
        if not self._ocr_loaded:
            if self._ocr_setting == "auto":
                from app.collectors.notice_pdf import ocr

                self._ocr = ocr.load_ocr()
            else:
                self._ocr = self._ocr_setting
            self._ocr_loaded = True
        return self._ocr

    @contextmanager
    def _resources(self) -> Iterator[tuple[HttpClient, Session, bool]]:
        http = self._http or HttpClient()
        own = self._session is None
        session = self._session or get_sessionmaker()()
        try:
            yield http, session, own
            if own:
                session.commit()
            else:
                session.flush()
        except BaseException:
            if own:
                session.rollback()
            raise
        finally:
            if own:
                session.close()
            if self._http is None:
                http.close()

    # --- 프로토콜
    def fetch(self, region: Region, snapshot: Snapshot, since: str | None) -> list[RawDocument]:
        with self._resources() as (http, session, own):
            store = RawStore(session)
            out: list[RawDocument] = []
            seen: set[int] = set()
            for url, complex_id in self.links_for_region(session, region):
                stored = self.download(http, store, url, region_id=region.id, complex_id=complex_id)
                if stored.row.id not in seen:
                    seen.add(stored.row.id)
                    out.append(to_contract(stored.row))
                if own:
                    session.commit()
                else:
                    session.flush()
            return out

    # --- 링크 모으기
    def links_for_region(self, session: Session, region: Region) -> list[tuple[str, int | None]]:
        areas = build_region_areas(region, session)
        latest = (
            select(func.max(RawRow.id))
            .where(
                RawRow.source_kind == "applyhome_detail",
                RawRow.path.is_not(None),
                RawRow.http_status >= 200,
                RawRow.http_status < 400,
            )
            .group_by(RawRow.url)
        )
        rows = session.scalars(select(RawRow).where(RawRow.id.in_(latest)).order_by(RawRow.id)).all()
        links: list[tuple[str, int | None]] = []
        for row in rows:
            if not any(p in row.url for p in _DETAIL_PATHS) or row.path is None:
                continue
            html = _read(row.path)
            if not html or not _in_region(areas, ah_parse.detail_supply_address(html)):
                continue
            complex_id = row.complex_id or _complex_id(session, region.id, _house_manage_no(row.url))
            for link in ah_parse.notice_pdf_links(html):
                if all(link != u for u, _ in links):
                    links.append((link, complex_id))
        return links

    # --- 받기
    def download(
        self,
        http: HttpClient,
        store: RawStore,
        url: str,
        *,
        region_id: int | None,
        complex_id: int | None,
    ) -> Stored:
        if not self._refetch:
            known = store.latest_ok(SOURCE, url)
            if known is not None:
                return Stored(known, created=False)
        result = http.get(url)
        if result.ok and not is_pdf(result.content):
            stored = store.save(
                result, source_kind=SOURCE, ext="html", region_id=region_id, complex_id=complex_id
            )
            if stored.created:
                stored.row.error_text = "not_pdf"
            return stored

        def extract(row: RawRow, day: date) -> None:
            ex = extract_pdf(result.content, ocr=self._get_ocr())
            row.error_text = error_text_for(ex)
            if ex.method == "none":
                return
            if any(p.strip() for p in ex.pages):
                write_text_atomic(raw_path(SOURCE, day, row.sha256, "txt"), ex.text.encode("utf-8"))
                row.text_path = raw_relpath(SOURCE, day, row.sha256, "txt").as_posix()
            if ex.tables:
                payload = json.dumps(ex.tables, ensure_ascii=False).encode("utf-8")
                write_text_atomic(raw_path(SOURCE, day, row.sha256, "json"), payload)

        return store.save(
            result,
            source_kind=SOURCE,
            ext="pdf",
            region_id=region_id,
            complex_id=complex_id,
            on_new_file=extract,
        )


def _read(relpath: str) -> str:
    try:
        return resolve_raw_path(relpath).read_bytes().decode("utf-8", errors="replace")
    except (OSError, ValueError):
        return ""


def _in_region(areas: RegionAreas, address: str | None) -> bool:
    """공급위치가 region 의 어느 시도 필터든 통과하면 True (시도 이름으로 시작하지 않는 주소도 있다)."""
    if not address:
        return False
    return any(f.matches(address) for f in areas.filters.values() if not f.whole) or any(
        f.whole and sido_short_name(t) == f.area
        for f in areas.filters.values()
        for t in address_tokens(address)
    )


def _house_manage_no(url: str) -> str:
    values = parse_qs(urlsplit(url).query).get("houseManageNo") or [""]
    return values[0]


def _complex_id(session: Session, region_id: int, house_manage_no: str) -> int | None:
    if not house_manage_no:
        return None
    stmt = select(Complex.id).where(Complex.applyhome_id == house_manage_no, Complex.region_id == region_id)
    return session.scalars(stmt).first()

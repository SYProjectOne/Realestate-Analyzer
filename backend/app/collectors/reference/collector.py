"""참조 데이터 수집기 — ``reference.refresh`` 잡의 본체 (DECISIONS D2-1·D2-4).

순서
1. 법정동코드 전체자료(code.go.kr) zip → ``legal_dong`` (폐지 코드 active=false 유지)
2. 행안부 게시판 → 시행일이 기준일 이하인 최신 "변경내역" 글 → ``jscodeYYYYMMDD.zip`` →
  ``admin_dong``·``admin_legal_map``
3. (선택) 주민등록 세대현황 → ``household_stat`` (``app.collectors.stats.households``)

받은 파일은 전부 ``raw_document``(source_kind='reference' / 세대는 'stats')로 남기고, 다운로드·파싱이 실패하면
실패 행을 남긴 뒤 ``contracts/fixtures/reference/`` 의 최신 사본으로 적재한다(공공누리 제1유형). 사본으로
적재한 행의 원문 URL 은 ``fixture://reference/<파일>`` 이다.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.collectors.reference.jscode import (
    MOIS_BOARD_PARAMS,
    MOIS_BOARD_URL,
    JscodeData,
    parse_attachments,
    parse_board,
    parse_jscode_zip,
    pick_article,
    pick_jscode,
)
from app.collectors.reference.legal_dong import (
    LEGAL_DONG_PARAMS,
    LEGAL_DONG_URL,
    LegalDongRecord,
    ReferenceParseError,
    parse_legal_dong_zip,
)
from app.collectors.reference.load import (
    LoadStats,
    replace_admin_legal_map,
    upsert_admin_dongs,
    upsert_legal_dongs,
)
from app.collectors.reference.rawstore import RawStore, fetch_failure
from app.core.contracts_gen import RawDocument, Region, Snapshot
from app.core.db import get_session
from app.core.http import HttpClient
from app.core.time import today_kst

__all__ = ["DEFAULT_FALLBACK_DIR", "ReferenceCollector", "RefreshReport"]

# backend/app/collectors/reference/collector.py → 저장소 루트/contracts/fixtures/reference
DEFAULT_FALLBACK_DIR = Path(__file__).resolve().parents[4] / "contracts" / "fixtures" / "reference"
LEGAL_DONG_FALLBACK = "legal_dong_full.zip"
LEGAL_DONG_SHOWN_URL = f"{LEGAL_DONG_URL}?codeseId=법정동코드"

SessionFactory = Callable[[], AbstractContextManager[Session]]


@dataclass(slots=True)
class RefreshReport:
    legal_dong: LoadStats | None = None
    admin_dong: LoadStats | None = None
    admin_legal_map: LoadStats | None = None
    household: LoadStats | None = None
    legal_dong_source_date: str | None = None
    jscode_source_date: str | None = None
    household_ym: str | None = None
    used_fallback: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    documents: list[RawDocument] = field(default_factory=list)


class ReferenceCollector:
    """법정동·행정동·매핑 참조 파일 수집기 (source_kind='reference')."""

    source_kind = "reference"

    def __init__(
        self,
        *,
        http: HttpClient | None = None,
        session_factory: SessionFactory = get_session,
        raw_dir: Path | None = None,
        fallback_dir: Path | None = DEFAULT_FALLBACK_DIR,
        today: date | None = None,
    ) -> None:
        self._http = http
        self._session_factory = session_factory
        self._raw_dir = raw_dir
        self._fallback_dir = fallback_dir
        self._today = today
        self.last: RefreshReport | None = None

    # --- Collector 프로토콜: 원문만 받는다(적재는 refresh)
    def fetch(self, region: Region, snapshot: Snapshot, since: str | None) -> list[RawDocument]:
        report = self.refresh(load=False, households=False, today=date.fromisoformat(snapshot.asof_date))
        return report.documents

    def refresh(
        self, *, load: bool = True, households: bool = True, today: date | None = None
    ) -> RefreshReport:
        """``reference.refresh`` 잡: 받기 → 파싱(실패 시 사본) → 적재. 한 트랜잭션."""
        day = today or self._today or today_kst()
        report = RefreshReport()
        http = self._http or HttpClient()
        try:
            with self._session_factory() as session:
                store = RawStore(session, raw_dir=self._raw_dir)
                legal = self._legal_dong(http, store, report, day)
                jscode = self._jscode(http, store, report, day)
                if load and legal is not None:
                    records, source_date = legal
                    report.legal_dong = upsert_legal_dongs(session, records, source_date=source_date)
                if load and jscode is not None:
                    src = jscode.source_date or day.isoformat()
                    report.admin_dong = upsert_admin_dongs(session, jscode.admin_dongs, source_date=src)
                    report.admin_legal_map = replace_admin_legal_map(session, jscode.mappings)
                if households:
                    from app.collectors.stats.households import HouseholdCollector

                    hc = HouseholdCollector(
                        http=http, raw_dir=self._raw_dir, fallback_dir=self._fallback_dir, load=load
                    )
                    hres = hc.collect(session, asof=day)
                    report.documents.extend(hres.documents)
                    report.household = hres.load
                    report.household_ym = hres.ym
                    if hres.used_fallback:
                        report.used_fallback.append(hres.used_fallback)
        finally:
            if self._http is None:
                http.close()
        self.last = report
        return report

    # --- 1. 법정동
    def _legal_dong(
        self, http: HttpClient, store: RawStore, report: RefreshReport, day: date
    ) -> tuple[list[LegalDongRecord], str] | None:
        r = http.get(LEGAL_DONG_URL, params=LEGAL_DONG_PARAMS)
        if r.ok:
            doc = store.save_result(r, source_kind="reference", ext="zip", url=LEGAL_DONG_SHOWN_URL)
            report.documents.append(doc)
            try:
                records = parse_legal_dong_zip(r.content)
                report.legal_dong_source_date = day.isoformat()
                return records, day.isoformat()
            except ReferenceParseError as exc:
                report.errors.append(f"legal_dong: {exc} (raw_document {doc.id})")
        else:
            doc = store.save_result(
                r, source_kind="reference", ext="zip", url=LEGAL_DONG_SHOWN_URL, failure=fetch_failure(r)
            )
            report.documents.append(doc)
            report.errors.append(f"legal_dong: 다운로드 실패 {doc.http_status or doc.error_text}")
        fb = self._fallback(store, report, LEGAL_DONG_FALLBACK, ext="zip", content_type="application/zip")
        if fb is None:
            return None
        content, source_date = fb
        try:
            records = parse_legal_dong_zip(content)
        except ReferenceParseError as exc:
            report.errors.append(f"legal_dong 사본: {exc}")
            return None
        report.legal_dong_source_date = source_date
        return records, source_date

    # --- 2. 행정동·매핑
    def _jscode(
        self, http: HttpClient, store: RawStore, report: RefreshReport, day: date
    ) -> JscodeData | None:
        data = self._jscode_download(http, store, report, day)
        if data is not None:
            report.jscode_source_date = data.source_date
            return data
        name = self._latest_fallback("jscode*.zip")
        if name is None:
            return None
        fb = self._fallback(store, report, name, ext="zip", content_type="application/zip")
        if fb is None:
            return None
        try:
            data = parse_jscode_zip(fb[0])
        except ReferenceParseError as exc:
            report.errors.append(f"jscode 사본: {exc}")
            return None
        report.jscode_source_date = data.source_date
        return data

    def _jscode_download(
        self, http: HttpClient, store: RawStore, report: RefreshReport, day: date
    ) -> JscodeData | None:
        board_url = f"{MOIS_BOARD_URL}?bbsId={MOIS_BOARD_PARAMS['bbsId']}"
        r = http.get(MOIS_BOARD_URL, params=MOIS_BOARD_PARAMS)
        if not r.ok:
            doc = store.save_result(
                r, source_kind="reference", ext="html", url=board_url, failure=fetch_failure(r)
            )
            report.documents.append(doc)
            report.errors.append(f"jscode 게시판: 실패 {doc.http_status or doc.error_text}")
            return None
        html = r.text()
        report.documents.append(store.save_result(r, source_kind="reference", ext="html", url=board_url))
        article = pick_article(parse_board(html), day)
        if article is None:
            report.errors.append("jscode 게시판: 변경내역 글을 찾지 못했다")
            return None
        r = http.get(article.url)
        if not r.ok:
            doc = store.save_result(r, source_kind="reference", ext="html", failure=fetch_failure(r))
            report.documents.append(doc)
            report.errors.append(f"jscode 글 {article.ntt_id}: 실패 {doc.http_status or doc.error_text}")
            return None
        report.documents.append(store.save_result(r, source_kind="reference", ext="html"))
        att = pick_jscode(parse_attachments(r.text()))
        if att is None:
            report.errors.append(f"jscode 글 {article.ntt_id}: jscode zip 첨부가 없다")
            return None
        r = http.get(att.url)
        if not r.ok:
            doc = store.save_result(r, source_kind="reference", ext="zip", failure=fetch_failure(r))
            report.documents.append(doc)
            report.errors.append(f"jscode zip: 실패 {doc.http_status or doc.error_text}")
            return None
        doc = store.save_result(r, source_kind="reference", ext="zip", content_type="application/zip")
        report.documents.append(doc)
        try:
            return parse_jscode_zip(r.content)
        except ReferenceParseError as exc:
            report.errors.append(f"jscode zip: {exc} (raw_document {doc.id})")
            return None

    # --- 사본
    def _manifest(self) -> dict[str, Any]:
        if self._fallback_dir is None:
            return {}
        path = self._fallback_dir / "manifest.json"
        if not path.exists():
            return {}
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data

    def _latest_fallback(self, pattern: str) -> str | None:
        if self._fallback_dir is None:
            return None
        files = sorted(p.name for p in self._fallback_dir.glob(pattern) if "말소" not in p.name)
        return files[-1] if files else None

    def _fallback(
        self, store: RawStore, report: RefreshReport, name: str, *, ext: str, content_type: str
    ) -> tuple[bytes, str] | None:
        if self._fallback_dir is None:
            report.errors.append(f"사본 없음: {name}")
            return None
        path = self._fallback_dir / name
        if not path.exists():
            report.errors.append(f"사본 없음: {path}")
            return None
        content = path.read_bytes()
        doc = store.save_content(
            source_kind="reference",
            url=f"fixture://reference/{name}",
            content=content,
            http_status=None,  # 사본 파일(HTTP 응답 아님) — url 이 fixture:// 이다
            ext=ext,
            content_type=content_type,
        )
        report.documents.append(doc)
        report.used_fallback.append(name)
        meta = self._manifest().get(name, {})
        downloaded = str(meta.get("downloaded_at", ""))[:10]
        return content, downloaded or doc.fetched_at[:10]

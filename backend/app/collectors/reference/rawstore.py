"""WP1b 수집기 공용: ``FetchResult`` → ``raw_document`` 행 (멱등·실패도 행).

``collectors/common/`` 을 만들지 않는 규칙(WP1b 카드) 때문에 WP1b 패키지(official_site·rtms·stats·news·
reference)가 이 모듈을 같이 쓴다.

규칙 (contracts/schemas/raw_document.json, RA §4-3 Collector)
- 성공 행: sha256 = 본문 sha256. 이미 있으면 저장하지 않고 기존 행을 돌려준다(멱등, T17).
- 실패 행: path=None. 403·5xx 는 http_status, 응답이 없으면 http_status=None + error_text('DNS'·'timeout'·
  'TLS'·'robots' …). sha256 = sha256('fail:' + url + ':' + (http_status 또는 error_text) + ':' + 날짜(KST)) —
  같은 날 재시도는 행이 늘지 않고 날마다 한 행.
- DB·로그에 남는 URL 에서는 키 파라미터(serviceKey 등)를 뺀다(AGENTS 규칙 6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contracts_gen import RawDocument
from app.core.http import FetchResult, HttpClient
from app.core.snapshot import sha256_bytes, sha256_text, store_raw
from app.core.time import now_kst, to_kst
from app.models import RawDocument as RawDocumentRow

__all__ = [
    "Failure",
    "RawStore",
    "SourceKind",
    "classify_failure",
    "diagnose_blocked",
    "failure_sha256",
    "fetch_failure",
    "iso_kst",
    "safe_url",
]

SourceKind = Literal[
    "applyhome_list",
    "applyhome_detail",
    "notice_pdf",
    "official_site",
    "rtms",
    "stats",
    "news",
    "reference",
]

_SECRET_PARAM = re.compile(
    r"(?i)^(service_?key|api_?key|access_?token|token|secret|password|key|client_?secret|client_?id)$"
)
_DNS_MARKERS = (
    "getaddrinfo",
    "name or service not known",
    "nodename nor servname",
    "no address associated",
    "temporary failure in name resolution",
    "11001",
    "name resolution",
)
_TLS_MARKERS = ("ssl", "certificate", "tls")


def iso_kst(dt: datetime) -> str:
    """aware datetime → KST ISO 문자열(초 단위)."""
    return to_kst(dt).isoformat(timespec="seconds")


def safe_url(url: str) -> str:
    """키·토큰 쿼리 파라미터를 뺀 URL(저장·표시용)."""
    parts = urlsplit(url)
    if not parts.query:
        return url
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _SECRET_PARAM.match(k)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept, doseq=True), parts.fragment))


def failure_sha256(url: str, key: str, day: date) -> str:
    """실패 행 sha256 (contracts/schemas/raw_document.json)."""
    return sha256_text(f"fail:{url}:{key}:{day.isoformat()}")


@dataclass(frozen=True, slots=True)
class Failure:
    """실패 행의 상태: http_status(응답이 있으면) 또는 error_text(응답이 없으면)."""

    http_status: int | None
    error_text: str | None

    @property
    def key(self) -> str:
        return str(self.http_status) if self.http_status is not None else (self.error_text or "error")

    @property
    def reason(self) -> str:
        """화면 표시용 사유('403', 'DNS', 'timeout' …) — SourceStatus.failing_targets.reason."""
        return self.key


def _network_reason(kind: str | None, message: str) -> str:
    low = message.lower()
    if kind == "timeout":
        return "timeout"
    if any(m in low for m in _DNS_MARKERS):
        return "DNS"
    if any(m in low for m in _TLS_MARKERS):
        return "TLS"
    if kind == "robots":
        return "robots"
    return kind or "network"


def classify_failure(result: FetchResult) -> Failure:
    """FetchResult(실패) → Failure. 응답이 있으면 상태 코드, 없으면 원인 한 단어."""
    if result.status is not None:
        return Failure(result.status, None)
    return Failure(None, _network_reason(result.error_kind, result.error or ""))


def diagnose_blocked(url: str) -> Failure:
    """core.http 가 robots 로 막았을 때 원인을 가린다.

    core.http 는 robots.txt 가 5xx·네트워크 실패여도 '전부 불허'로 막는다(RFC 9309). 그러면 DNS 실패·TLS
    오류도
    'robots' 로만 보이므로, 같은 호스트의 robots.txt 를 한 번 더(robots.txt 자체는 항상 받아도 된다) 받아
    원인을 적는다. robots.txt 가 정상이면 진짜 robots 차단이다.
    """
    parts = urlsplit(url)
    robots_url = urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
    with HttpClient(respect_robots=False, max_retries=0, jitter=0) as diag:
        r = diag.get(robots_url)
    if r.status is not None and r.status < 500:
        return Failure(None, "robots")
    if r.status is not None:
        return Failure(r.status, f"robots.txt {r.status}")
    return Failure(None, _network_reason(r.error_kind, r.error or ""))


def _to_dto(row: RawDocumentRow) -> RawDocument:
    return RawDocument(
        id=row.id,
        source_kind=row.source_kind,
        url=row.url,
        fetched_at=row.fetched_at,
        http_status=row.http_status,
        sha256=row.sha256,
        path=row.path,
        content_type=row.content_type,
        text_path=row.text_path,
        table_path=row.table_path,
        complex_id=row.complex_id,
        region_id=row.region_id,
        error_text=row.error_text,
        image_hash=row.image_hash,
        meta=row.meta,
    )


class RawStore:
    """한 세션 안에서 raw_document 행을 만든다. commit 은 호출자(세션 컨텍스트)가 한다."""

    def __init__(self, session: Session, *, raw_dir: Path | None = None) -> None:
        self.session = session
        self.raw_dir = raw_dir
        self.created = 0  # 이번에 새로 만든 행 수

    def _existing(self, sha256: str) -> RawDocumentRow | None:
        return self.session.scalar(select(RawDocumentRow).where(RawDocumentRow.sha256 == sha256))

    def save_content(
        self,
        *,
        source_kind: SourceKind,
        url: str,
        content: bytes,
        ext: str,
        content_type: str | None,
        fetched_at: datetime | None = None,
        http_status: int | None = 200,
        text: str | None = None,
        region_id: int | None = None,
        complex_id: int | None = None,
        image_hash: str | None = None,
        error_text: str | None = None,
    ) -> RawDocument:
        """본문을 RAW_DIR 에 저장하고 행을 만든다. 같은 sha256 행이 있으면 그 행을 돌려준다."""
        digest = sha256_bytes(content)
        existing = self._existing(digest)
        if existing is not None:
            return _to_dto(existing)
        when = fetched_at or now_kst()
        day = to_kst(when).date()
        stored = store_raw(content, source=source_kind, day=day, ext=ext, raw_dir=self.raw_dir)
        text_path = None
        if text is not None:
            text_path = store_raw(
                text.encode("utf-8"), source=source_kind, day=day, ext="txt", raw_dir=self.raw_dir
            ).relpath
        row = RawDocumentRow(
            source_kind=source_kind,
            url=safe_url(url),
            fetched_at=iso_kst(when),
            http_status=http_status,
            sha256=digest,
            path=stored.relpath,
            content_type=content_type,
            text_path=text_path,
            complex_id=complex_id,
            region_id=region_id,
            error_text=error_text,
            image_hash=image_hash,
        )
        self.session.add(row)
        self.session.flush()
        self.created += 1
        return _to_dto(row)

    def save_failure(
        self,
        *,
        source_kind: SourceKind,
        url: str,
        failure: Failure,
        fetched_at: datetime | None = None,
        region_id: int | None = None,
        complex_id: int | None = None,
        detail: str | None = None,
    ) -> RawDocument:
        """실패 행(path=None). 같은 날 같은 URL·같은 원인이면 기존 행을 돌려준다."""
        when = fetched_at or now_kst()
        url = safe_url(url)
        digest = failure_sha256(url, failure.key, to_kst(when).date())
        existing = self._existing(digest)
        if existing is not None:
            return _to_dto(existing)
        error_text = failure.error_text
        if detail:
            error_text = f"{error_text}: {detail}" if error_text else detail
        row = RawDocumentRow(
            source_kind=source_kind,
            url=url,
            fetched_at=iso_kst(when),
            http_status=failure.http_status,
            sha256=digest,
            path=None,
            content_type=None,
            text_path=None,
            complex_id=complex_id,
            region_id=region_id,
            error_text=error_text,
            image_hash=None,
        )
        self.session.add(row)
        self.session.flush()
        self.created += 1
        return _to_dto(row)

    def save_result(
        self,
        result: FetchResult,
        *,
        source_kind: SourceKind,
        ext: str,
        url: str | None = None,
        content_type: str | None = None,
        text: str | None = None,
        region_id: int | None = None,
        complex_id: int | None = None,
        image_hash: str | None = None,
        failure: Failure | None = None,
        detail: str | None = None,
    ) -> RawDocument:
        """성공이면 본문 행, 실패면 실패 행. ``url`` 은 저장용(키 없는) URL — 없으면 result.url."""
        shown = url or result.url
        if result.ok:
            return self.save_content(
                source_kind=source_kind,
                url=shown,
                content=result.content,
                ext=ext,
                content_type=content_type or result.headers.get("content-type"),
                fetched_at=result.fetched_at,
                http_status=result.status,
                text=text,
                region_id=region_id,
                complex_id=complex_id,
                image_hash=image_hash,
            )
        return self.save_failure(
            source_kind=source_kind,
            url=shown,
            failure=failure or classify_failure(result),
            fetched_at=result.fetched_at,
            region_id=region_id,
            complex_id=complex_id,
            detail=detail,
        )


def fetch_failure(result: FetchResult) -> Failure:
    """실패한 FetchResult 의 원인. robots 차단이면 core.http 가 보존한 robots.txt 결과로 진짜 원인을 가린다
    (계약 2026-10-09.2: FetchResult.robots_status·robots_error_kind — 다시 요청하지 않는다)."""
    if result.blocked_by_robots:
        if result.robots_status is not None and result.robots_status < 500:
            return Failure(None, "robots")
        if result.robots_status is not None:
            return Failure(result.robots_status, f"robots.txt {result.robots_status}")
        return Failure(None, _network_reason(result.robots_error_kind, result.robots_error or ""))
    return classify_failure(result)

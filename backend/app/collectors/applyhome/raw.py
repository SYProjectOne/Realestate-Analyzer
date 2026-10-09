"""FetchResult → raw_document 행 (멱등·실패도 행). applyhome·notice_pdf 공용(WP1a 패키지 안에 둔다).

규칙(contracts/schemas/raw_document.json, protocols.Collector)
- 성공: 원문을 ``store_raw`` 로 ``RAW_DIR/{source_kind}/{yyyy-mm-dd}/{sha256}.{ext}`` 에 쓰고 행을 만든다.
  같은 sha256 행이 있으면 새로 쓰지 않고 그 행을 돌려준다(raw_document 증가 0).
- 실패: ``http_status``(403·5xx 등) 또는 ``http_status=None`` + ``error_text``('DNS'·'timeout'·'connect'·
  'network'·'robots'·'invalid_url'). sha256 = sha256('fail:' + url + ':' + (상태 또는 오류 종류) + ':'
  + 날짜), path=None — 같은 날 재시도는 행이 늘지 않고 날마다 한 행.
- 날짜·fetched_at 은 Asia/Seoul.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import contracts_gen as cg
from app.core.http import FetchResult
from app.core.snapshot import sha256_text, store_raw
from app.core.time import to_kst
from app.models import RawDocument as RawRow

__all__ = ["RawStore", "SourceKind", "Stored", "failure_kind", "to_contract"]

SourceKind = str

_DNS_MARKERS = (
    "getaddrinfo",
    "name or service not known",
    "nodename nor servname",
    "temporary failure in name resolution",
    "no address associated",
    "name resolution",
    "11001",
)


def failure_kind(result: FetchResult) -> str:
    """실패 종류 문자열 — http_status 가 있으면 그 숫자, 없으면 error_text 값."""
    if result.status is not None:
        return str(result.status)
    return error_text_of(result) or "error"


def error_text_of(result: FetchResult) -> str | None:
    if result.status is not None:
        return None
    kind = result.error_kind
    message = (result.error or "").lower()
    if kind == "timeout":
        return "timeout"
    if kind == "connect" and any(m in message for m in _DNS_MARKERS):
        return "DNS"
    if kind == "robots" or result.blocked_by_robots:
        return "robots"
    return kind or "error"


def to_contract(row: RawRow) -> cg.RawDocument:
    return cg.RawDocument(
        id=row.id,
        source_kind=row.source_kind,  # DB CHECK 가 SourceKind 로 제한
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


@dataclass(frozen=True, slots=True)
class Stored:
    row: RawRow
    created: bool  # False = 같은 sha256 행이 이미 있었다

    @property
    def ok(self) -> bool:
        return (
            self.row.http_status is not None
            and 200 <= self.row.http_status < 400
            and self.row.path is not None
        )


class RawStore:
    """세션 하나 위에서 raw_document 행을 멱등하게 만든다. commit 은 호출자가 한다."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def by_sha(self, sha256: str) -> RawRow | None:
        return self.session.scalars(select(RawRow).where(RawRow.sha256 == sha256)).first()

    def latest_ok(self, source_kind: SourceKind, url: str) -> RawRow | None:
        """같은 URL 의 가장 최근 성공 행."""
        stmt = (
            select(RawRow)
            .where(
                RawRow.source_kind == source_kind,
                RawRow.url == url,
                RawRow.path.is_not(None),
                RawRow.http_status >= 200,
                RawRow.http_status < 400,
            )
            .order_by(RawRow.id.desc())
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def save(
        self,
        result: FetchResult,
        *,
        source_kind: SourceKind,
        ext: str,
        region_id: int | None,
        complex_id: int | None = None,
        on_new_file: Callable[[RawRow, date], None] | None = None,
    ) -> Stored:
        """성공이면 원문 저장, 실패면 실패 행. ``on_new_file`` 은 새 원문 행일 때만 불린다(텍스트 추출 등)."""
        fetched = to_kst(result.fetched_at)
        day = fetched.date()
        fetched_at = fetched.isoformat(timespec="seconds")
        if not result.ok:
            return self._save_failure(result, source_kind, day, fetched_at, region_id, complex_id)

        digest = result.sha256
        existing = self.by_sha(digest)
        if existing is not None:
            return Stored(existing, created=False)
        stored = store_raw(result.content, source=source_kind, day=day, ext=ext)
        row = RawRow(
            source_kind=source_kind,
            url=result.url,
            fetched_at=fetched_at,
            http_status=result.status,
            sha256=stored.sha256,
            path=stored.relpath,
            content_type=result.headers.get("content-type"),
            text_path=None,
            complex_id=complex_id,
            region_id=region_id,
        )
        if on_new_file is not None:
            on_new_file(row, day)
        return self._insert(row)

    def _save_failure(
        self,
        result: FetchResult,
        source_kind: SourceKind,
        day: date,
        fetched_at: str,
        region_id: int | None,
        complex_id: int | None,
    ) -> Stored:
        digest = sha256_text(f"fail:{result.url}:{failure_kind(result)}:{day.isoformat()}")
        existing = self.by_sha(digest)
        if existing is not None:
            return Stored(existing, created=False)
        row = RawRow(
            source_kind=source_kind,
            url=result.url,
            fetched_at=fetched_at,
            http_status=result.status,
            sha256=digest,
            path=None,
            content_type=result.headers.get("content-type") if result.status is not None else None,
            text_path=None,
            complex_id=complex_id,
            region_id=region_id,
            error_text=error_text_of(result),
        )
        return self._insert(row)

    def _insert(self, row: RawRow) -> Stored:
        try:
            with self.session.begin_nested():
                self.session.add(row)
        except IntegrityError:  # 다른 수집기가 같은 sha256 을 먼저 넣었다
            existing = self.by_sha(row.sha256)
            if existing is None:
                raise
            return Stored(existing, created=False)
        return Stored(row, created=True)

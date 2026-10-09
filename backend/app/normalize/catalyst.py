"""호재 후보 (R3 M6) — 뉴스 수집 결과·사람이 입력한 URL → ``catalyst`` 후보 행.

후보 행 = ``kind='기타'``, ``stage='미확정'``, ``decision``·``stage_prob``·``judgment_seq`` 없음,
``location_confirmed=false``(위치 미확정 → ``catalyst_link`` 를 만들지 않는다). 이름 = 제목, note = 발췌,
source_url = 원문 링크. 종류·단계는 판정기 P4 classify(``scheduler/pipeline.py``)가 정한다 — 여기서는 키워드로
거르거나 단계를 정하지 않는다(AGENTS 규칙 3). 그래서 뉴스 항목은 전부 후보가 된다.

멱등: 같은 지역·같은 source_url 이면 기존 행을 돌려준다(제목이 바뀌어도 새 행을 만들지 않는다).

- ``catalyst_candidate(session, region_id, url=, title=, excerpt=)`` — 공개 함수. 사람 URL 입력 엔드포인트
  (``POST /catalysts``, F3)가 부른다. URL 은 http(s) 만, 제목은 비어 있으면 안 된다(``CatalystInputError`` → 422).
- ``catalysts_from_news(session, region_id, docs)`` — 뉴스 원문(source_kind='news', 성공 행) → 후보들.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.news.collector import parse_news_json
from app.core.contracts_gen import RawDocument as RawDTO
from app.core.paths import resolve_raw_path
from app.models import Catalyst

__all__ = [
    "CANDIDATE_KIND",
    "CANDIDATE_STAGE",
    "CatalystCandidate",
    "CatalystInputError",
    "NewsCatalysts",
    "catalyst_candidate",
    "catalysts_from_news",
]

CANDIDATE_KIND: Final = "기타"
CANDIDATE_STAGE: Final = "미확정"
_NOTE_MAX: Final = 1_000


class CatalystInputError(ValueError):
    """URL·제목이 후보 조건에 맞지 않는다(API 는 422)."""


@dataclass(frozen=True)
class CatalystCandidate:
    catalyst: Catalyst
    created: bool


@dataclass(frozen=True)
class NewsCatalysts:
    inserted: int
    existing: int

    def stats(self) -> dict[str, int]:
        return {"inserted": self.inserted, "existing": self.existing}


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())


def _check_url(url: str) -> str:
    u = url.strip()
    parts = urlsplit(u)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise CatalystInputError(f"http(s) URL 이 아니다: {u[:80]!r}")
    return u


def catalyst_candidate(
    session: Session,
    region_id: int,
    *,
    url: str,
    title: str,
    excerpt: str | None = None,
    raw_document_id: int | None = None,
) -> CatalystCandidate:
    """URL + 제목 + 발췌 → 호재 후보 행(분류 전). 같은 URL 이 이미 있으면 그 행. flush 만 한다."""
    link = _check_url(url)
    name = _clean(title)
    if not name:
        raise CatalystInputError("제목이 비어 있다")
    found = session.scalars(
        select(Catalyst).where(Catalyst.region_id == region_id, Catalyst.source_url == link).order_by(Catalyst.id)
    ).first()
    if found is not None:
        return CatalystCandidate(found, created=False)
    note = _clean(excerpt)
    row = Catalyst(
        region_id=region_id,
        name=name[:200],
        kind=CANDIDATE_KIND,
        stage=CANDIDATE_STAGE,
        stage_prob=None,
        decision=None,
        expected_ym=None,
        location_confirmed=False,
        lat=None,
        lon=None,
        raw_document_id=raw_document_id,
        judgment_seq=None,
        source_url=link,
        note=note[:_NOTE_MAX] or None,
    )
    session.add(row)
    session.flush()
    return CatalystCandidate(row, created=True)


def _read(doc: RawDTO) -> bytes | None:
    for rel in (doc.text_path, doc.path):
        if not rel:
            continue
        try:
            p: Path = resolve_raw_path(rel)
            return p.read_bytes()
        except (OSError, ValueError):
            continue
    return None


def catalysts_from_news(session: Session, region_id: int, docs: Iterable[RawDTO]) -> NewsCatalysts:
    """뉴스 원문(성공 행)의 항목마다 후보 행. 실패 행·다른 원문은 건너뛴다. flush 만 한다."""
    inserted = existing = 0
    for doc in docs:
        if doc.source_kind != "news" or doc.http_status != 200 or doc.error_text:
            continue
        content = _read(doc)
        if content is None:
            continue
        for item in parse_news_json(content, raw_document_id=doc.id):
            try:
                out = catalyst_candidate(
                    session,
                    region_id,
                    url=item.url,
                    title=item.title,
                    excerpt=item.excerpt,
                    raw_document_id=doc.id,
                )
            except CatalystInputError:
                continue
            if out.created:
                inserted += 1
            else:
                existing += 1
    return NewsCatalysts(inserted, existing)

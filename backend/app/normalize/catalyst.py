"""호재 후보 (R3 M6) — 뉴스 수집 결과·사람이 입력한 URL → ``catalyst`` 후보 행.

후보 행 = ``kind='기타'``, ``stage='미확정'``, ``decision``·``stage_prob``·``judgment_seq`` 없음,
``location_confirmed=false``(위치 미확정 → ``catalyst_link`` 를 만들지 않는다). 이름 = 제목, note = 발췌,
source_url = 원문 링크. 종류·단계는 판정기 P4 classify(``scheduler/pipeline.py``)가 정한다 — 여기서는 키워드로
거르거나 단계를 정하지 않는다(AGENTS 규칙 3). 뉴스 항목은 호출자가 넘기는 ``accept``(판정기 P1 screen 호재 관련성,
D10-6)를 통과한 것만 후보가 된다(``accept`` 가 없으면 전부).

멱등: 같은 지역·같은 source_url 이면 기존 행을 돌려준다(제목이 바뀌어도 새 행을 만들지 않는다).

출처(R3b M6): 후보 행을 만들 때 ``field_provenance``(entity='catalyst') 출처 행을 남긴다 — 필드 ``name``(제목·발췌)과
``source_url``. 라벨 '비공식'(언론 기사·사람이 넣은 링크 — 공식 근거는 판정기 단계 분류가 따로 본다), URL = 원문
링크, 확인일 = 뉴스 원문 수집일(사람 입력이면 입력일), raw_document_id = 뉴스 원문 행(사람 입력이면 없음).
판정 확률(stage_prob)의 출처는 judgment_seq 포인터다(``provenance.POINTER_PROVENANCE``).

- ``catalyst_candidate(session, region_id, url=, title=, excerpt=)`` — 공개 함수. 사람 URL 입력 엔드포인트
  (``POST /catalysts``, F3)가 부른다. URL 은 http(s) 만, 제목은 비어 있으면 안 된다(``CatalystInputError`` → 422).
- ``catalysts_from_news(session, region_id, docs)`` — 뉴스 원문(source_kind='news', 성공 행) → 후보들.
"""

# ruff: noqa: E501  (한국어 docstring·발췌 문구)

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.news.collector import NewsItem, parse_news_json
from app.core.contracts_gen import ProvenanceRow
from app.core.contracts_gen import RawDocument as RawDTO
from app.core.paths import resolve_raw_path
from app.core.time import now_kst
from app.models import Catalyst, RawDocument
from app.normalize.provenance import upsert_provenance

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
SOURCE_LABEL: Final = "비공식"
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
    rejected: int = 0  # accept(호재 관련성 screen)를 통과하지 못해 후보로 만들지 않은 항목
    invalid: list[dict[str, str]] = dataclass_field(default_factory=list)
    """후보 조건(CatalystInputError)에 맞지 않아 행을 만들지 못한 항목 — 실패도 기록(규칙 7, R3 3차 minor 24)."""

    def stats(self) -> dict[str, Any]:
        out: dict[str, Any] = {"inserted": self.inserted, "existing": self.existing}
        if self.rejected:  # screen 을 쓴 실행에서 걸러진 항목이 있을 때만(기존 stats 모양 유지)
            out["rejected"] = self.rejected
        if self.invalid:
            out["invalid"] = len(self.invalid)
            out["invalid_items"] = self.invalid[:20]
        return out


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
        select(Catalyst)
        .where(Catalyst.region_id == region_id, Catalyst.source_url == link)
        .order_by(Catalyst.id)
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
    _write_provenance(session, row, raw_document_id)
    return CatalystCandidate(row, created=True)


def _write_provenance(session: Session, row: Catalyst, raw_document_id: int | None) -> None:
    """후보 행의 출처 행(name·source_url) — 라벨 '비공식', URL = 원문 링크(M6)."""
    doc = session.get(RawDocument, raw_document_id) if raw_document_id is not None else None
    checked = (
        doc.fetched_at[:10] if doc is not None and doc.fetched_at else None
    ) or now_kst().date().isoformat()
    reason = "뉴스 검색 결과(언론 기사)" if doc is not None else "사람 입력 URL"
    excerpt = (f"{row.name} — {row.note}" if row.note else row.name)[:_NOTE_MAX]
    key = f"catalyst:{row.id}"
    url = row.source_url or ""
    upsert_provenance(
        session,
        [
            ProvenanceRow(
                entity="catalyst",
                entity_id=row.id,
                entity_key=key,
                field=field_name,
                value_text=text,
                value_norm=text,
                raw_document_id=doc.id if doc is not None else None,
                url=url,
                checked_at=checked,
                observed_on=None,
                label=SOURCE_LABEL,
                reason=reason,
                source_rank=2,
                chosen=True,
                conflict_group=None,
                excerpt=excerpt,
                excerpt_start=None,
                excerpt_end=None,
            )
            for field_name, text in (("name", row.name), ("source_url", url))
        ],
    )


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


def catalysts_from_news(
    session: Session,
    region_id: int,
    docs: Iterable[RawDTO],
    *,
    accept: Callable[[NewsItem], bool] | None = None,
) -> NewsCatalysts:
    """뉴스 원문(성공 행)의 항목마다 후보 행. 실패 행·다른 원문은 건너뛴다. flush 만 한다.

    ``accept``(D10-6): 새 URL 항목을 후보로 만들기 전에 부르는 검사 — 파이프라인은 판정기 P1 screen(호재 관련성,
    ``judge.pipeline.p1_screen_catalyst``)의 usable 을 넘긴다. False 면 후보를 만들지 않고 ``rejected`` 로 센다.
    이미 후보인 URL 은 다시 검사하지 않는다. 여기서는 판단하지 않는다(키워드 필터 없음).
    """
    inserted = existing = rejected = 0
    invalid: list[dict[str, str]] = []
    for doc in docs:
        if doc.source_kind != "news" or doc.http_status != 200 or doc.error_text:
            continue
        content = _read(doc)
        if content is None:
            continue
        for item in parse_news_json(content, raw_document_id=doc.id):
            if accept is not None and not _known(session, region_id, item.url) and not accept(item):
                rejected += 1
                continue
            try:
                out = catalyst_candidate(
                    session,
                    region_id,
                    url=item.url,
                    title=item.title,
                    excerpt=item.excerpt,
                    raw_document_id=doc.id,
                )
            except CatalystInputError as exc:
                invalid.append({"url": item.url[:300], "title": (item.title or "")[:80], "reason": str(exc)[:120]})
                continue
            if out.created:
                inserted += 1
            else:
                existing += 1
    return NewsCatalysts(inserted, existing, rejected, invalid)


def _known(session: Session, region_id: int, url: str) -> bool:
    """같은 지역에 이 URL 의 후보 행이 이미 있는가(catalyst_candidate 의 멱등 키와 같다)."""
    link = url.strip()
    return (
        session.scalars(
            select(Catalyst.id).where(Catalyst.region_id == region_id, Catalyst.source_url == link)
        ).first()
        is not None
    )

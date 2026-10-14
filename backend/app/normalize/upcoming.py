"""트랙 (A) '12개월 안 공고 예정' 단지 후보 (meta §1-3 #1, DECISIONS D20-2).

뉴스 원문(``source_kind='news'``, 성공 행) 항목마다:

1. 판정기 P1 screen — 공고 예정 신호(``judge.payloads.UPCOMING_SCREEN_TASK``). 통과(pass·ok)만 다음.
2. 판정기 P2 extract — 기사가 알린 단지 이름 1~3개(auto 값만).
3. 판정기 P4 classify — 이름마다 지역 안·민간분양·12개월 안 공고 예정인가(``UPCOMING_CLASSES``). auto +
   ``private_sale_apt`` 만 후보.
4. 같은 지역 단지와 대조: 정규화 이름 키(``store.block_name_key`` — 이름·옛 이름)가 **같으면** 같은 단지(새 행 없음). 키가
   서로를 **포함**하면 판정기 compare(같은 단지인가)에 묻고 same_fact·auto 면 같은 단지 — 그 후보 행의 옛 이름(former_names)에
   새 이름을 더한다(뒤에 청약홈 공고가 그 이름으로 와도 합쳐지게). 문자열 대조는 묻는 쌍을 고를 뿐이다(판단은 판정기, 규칙 3).
5. 새 단지 = ``complex``(applyhome_id NULL, track 'A', inclusion = 3의 classify 결과, 공고일·가격 없음 → 판정 범위
   '보류 — 공고 후 재판정' 사유 '분양가 미공개(공고 전)') + 이름 출처 행(라벨 '비공식' — 언론, meta §1-3 #5) + change_event
   (complex·track, notice). 청약홈 공고가 나오면 정규화(``store._Binder``)가 같은 이름 키의 이 행에 주택관리번호를 붙인다.

판정기 호출은 호출자(``scheduler.assemble``)가 넘긴 ``UpcomingJudge`` 로만 한다(AGENTS 규칙 4 — 판정기를 직접 부르는 코드는
``judge/`` 밖에 없다). 이 모듈은 이름 정리(따옴표·'(843가구)' 꼬리 떼기 — 파싱)와 행 쓰기만 한다. 멱등: 같은 기사·같은 이름이면
같은 판정 입력(캐시)·같은 행.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.news.collector import NewsItem, parse_news_json
from app.core.contracts_gen import ProvenanceRow
from app.core.contracts_gen import RawDocument as RawDTO
from app.models import ChangeEvent, Complex, RawDocument
from app.normalize.provenance import upsert_provenance

__all__ = [
    "UPCOMING_LABEL",
    "UPCOMING_REASON",
    "ClassifiedName",
    "UpcomingJudge",
    "UpcomingResult",
    "clean_name",
    "upcoming_from_news",
]

UPCOMING_LABEL: Final = "비공식"
"""언론 기사에서 온 공고 예정 단지 사실(meta §1-3 #5 — 보도자료·블로그는 비공식)."""
UPCOMING_REASON: Final = "언론(공고 예정, 청약홈 미등록)"
_QUOTES: Final = "‘’'\"“”`"
_TAIL_RE: Final = re.compile(r"\s*\(\s*(?:총\s*)?[0-9][0-9,]*\s*(?:가구|세대|실)\s*\)\s*$")
_MIN_KEY: Final = 4


def clean_name(text: str) -> str:
    """판정기가 고른 이름 원문 → 단지 이름: 따옴표·앞뒤 공백·끝 '(843가구)' 같은 규모 괄호를 뗀다(파싱)."""
    name = " ".join(text.strip().strip(_QUOTES).split())
    return _TAIL_RE.sub("", name).strip(_QUOTES).strip()


@dataclass(frozen=True, slots=True)
class ClassifiedName:
    label: str | None
    prob: float | None
    judgment_seq: int | None
    resolved: bool


class UpcomingJudge(Protocol):
    """판정기 호출(호출자 제공). 판단은 여기서만."""

    def screen(self, item: NewsItem, key: str) -> bool: ...

    def names(self, item: NewsItem, key: str) -> list[str]: ...

    def classify(self, item: NewsItem, key: str, names: list[str]) -> Mapping[str, ClassifiedName]: ...

    def same(self, a: str, a_text: str, b: str, b_text: str) -> bool: ...


@dataclass
class UpcomingResult:
    screened: int = 0
    rejected: int = 0
    names: int = 0
    not_upcoming: int = 0
    created: int = 0
    existing: int = 0
    aliases: int = 0
    events: list[ChangeEvent] = field(default_factory=list)
    complex_ids: list[int] = field(default_factory=list)

    def stats(self) -> dict[str, Any]:
        return {
            "screened": self.screened,
            "rejected": self.rejected,
            "names": self.names,
            "not_upcoming": self.not_upcoming,
            "created": self.created,
            "existing": self.existing,
            "aliases": self.aliases,
        }


def _read(doc: RawDTO) -> bytes | None:
    from app.core.paths import resolve_raw_path

    for rel in (doc.text_path, doc.path):
        if not rel:
            continue
        try:
            return resolve_raw_path(rel).read_bytes()
        except (OSError, ValueError):
            continue
    return None


def _keys(cx: Complex) -> set[str]:
    from app.normalize.store import block_name_key

    return {k for k in (block_name_key(n) for n in (cx.name, *(cx.former_names or []))) if k}


def _text_of(item: NewsItem) -> str:
    return f"{item.title} — {item.excerpt}" if item.excerpt else item.title


def upcoming_from_news(
    session: Session,
    region_id: int,
    docs: Iterable[RawDTO],
    *,
    judge: UpcomingJudge,
    key_of: Any,
    snapshot_id: int | None,
    detected_at: str,
) -> UpcomingResult:
    """뉴스 원문 → 트랙 (A) 공고 예정 단지 후보 행. ``key_of(item)`` = 판정 purpose 키(뉴스 URL·제목 해시). flush 만 한다."""
    from app.normalize.store import block_name_key

    res = UpcomingResult()
    for doc in docs:
        if doc.source_kind != "news" or doc.http_status != 200 or doc.error_text:
            continue
        content = _read(doc)
        if content is None:
            continue
        for item in parse_news_json(content, raw_document_id=doc.id):
            key = str(key_of(item))
            session.commit()  # 판정기 어댑터는 자기 세션으로 judgment_log 를 쓴다 — 쓰기 잠금을 먼저 푼다(SQLite)
            if not judge.screen(item, key):
                res.rejected += 1
                continue
            res.screened += 1
            raw_names = [n for n in (clean_name(x) for x in judge.names(item, key)) if n]
            names = list(dict.fromkeys(raw_names))
            if not names:
                continue
            res.names += len(names)
            classified = judge.classify(item, key, names)
            for name in names:
                out = classified.get(name)
                if out is None or not out.resolved or out.label != "private_sale_apt":
                    res.not_upcoming += 1
                    continue
                nkey = block_name_key(name)
                if len(nkey) < _MIN_KEY:
                    res.not_upcoming += 1
                    continue
                region_rows = list(
                    session.scalars(
                        select(Complex)
                        .where(Complex.region_id == region_id, Complex.merged_into_id.is_(None))  # D29-2
                        .order_by(Complex.id)
                    )
                )
                hit = next((cx for cx in region_rows if nkey in _keys(cx)), None)
                if hit is None:
                    for cx in region_rows:
                        if not any(nkey in k or k in nkey for k in _keys(cx) if len(k) >= _MIN_KEY):
                            continue
                        session.commit()
                        if judge.same(name, _text_of(item), cx.name, cx.name):
                            hit = cx
                            if (
                                cx.applyhome_id is None
                                and name not in (cx.former_names or [])
                                and name != cx.name
                            ):
                                cx.former_names = [*(cx.former_names or []), name]
                                res.aliases += 1
                            break
                if hit is not None:
                    res.existing += 1
                    continue
                cx = _create(session, region_id, name, item, doc, out)
                res.created += 1
                res.complex_ids.append(cx.id)
                ev = ChangeEvent(
                    snapshot_id=snapshot_id, entity="complex", entity_id=cx.id, field="track", old_text=None,
                    new_text=f"A 공고 예정 후보 {name}(언론, 청약홈 미등록)", detected_at=detected_at,
                    severity="notice", triggers_rejudge=False, complex_id=cx.id,
                )  # fmt: skip
                session.add(ev)
                session.flush()
                res.events.append(ev)
    return res


def _create(
    session: Session, region_id: int, name: str, item: NewsItem, doc: RawDTO, out: ClassifiedName
) -> Complex:
    from decimal import Decimal

    cx = Complex(
        region_id=region_id,
        applyhome_id=None,
        name=name[:200],
        former_names=[],
        apply_dates=[],
        contract_dates=[],
        inclusion_class="private_sale_apt",
        inclusion_decision="auto",
        inclusion_prob=Decimal(str(round(out.prob, 4))) if out.prob is not None else None,
        inclusion_judgment_seq=out.judgment_seq,
        track="A",
    )
    session.add(cx)
    session.flush()
    raw = session.get(RawDocument, doc.id) if doc.id is not None else None
    checked = (raw.fetched_at if raw is not None else doc.fetched_at)[:10]
    upsert_provenance(
        session,
        [
            ProvenanceRow(
                entity="complex", entity_id=cx.id, entity_key=f"upcoming:{cx.id}", field="name", value_text=name,
                value_norm=name, raw_document_id=doc.id, url=item.url, checked_at=checked, observed_on=None,
                label=UPCOMING_LABEL, reason=UPCOMING_REASON, source_rank=3, chosen=True, conflict_group=None,
                excerpt=_text_of(item)[:300], excerpt_start=None, excerpt_end=None,
            )
        ],
    )  # fmt: skip
    return cx

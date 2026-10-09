"""공식 홈페이지 원문(DOM 텍스트) → 접수 상태 '텍스트 후보' (WP2).

접수 가능 여부를 정하지 않는다 — '선착순 동·호지정 계약 중', '전 타입 마감임박', '분양완료' 같은 문구를
원문 위치와 함께 모아 넘길 뿐이다. 상태 분류(가능/미정/불가)는 판정기(classify) 또는 사람 확인(G7)이 한다
(AGENTS 규칙 3). 403·DNS·타임아웃 원문은 문구 없이 실패 사유만 담는다(실패도 데이터, T3).

FieldCandidate.entity에 intake_status가 없어(계약 2026-10-09.1) ``Parser.parse``는 빈 목록을 돌려주고,
``read_site``가 전용 결과(``SiteTextResult``)를 돌려준다 — 보고서의 '계약 변경 요청' 참고.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.core.contracts_gen import FieldCandidate, RawDocument
from app.normalize._text import checked_on, line_span, read_raw_text

__all__ = ["KEYWORDS", "OfficialSiteParser", "SiteTextHit", "SiteTextResult", "read_site", "scan_text"]

# 접수 상태와 관련된 공고·팝업 문구(표기 변형 포함). 문구 → 그대로 보여 줄 키워드 이름.
KEYWORDS: dict[str, str] = {
    r"선\s*착\s*순": "선착순",
    r"동\s*[·ㆍ.\-]?\s*호\s*(?:수\s*)?지\s*정": "동·호지정",
    r"계약\s*(?:진행\s*)?중": "계약 중",
    r"분양\s*중": "분양 중",
    r"잔여\s*(?:세대|물량|호실)": "잔여 세대",
    r"마감\s*임박": "마감임박",
    r"(?<!임박)마\s*감(?!\s*임박)": "마감",
    r"분양\s*완료|완\s*판": "분양완료",
    r"방문\s*예약": "방문예약",
    r"무순위": "무순위",
    r"임의\s*공급": "임의공급",
    r"계약\s*축하금|할인\s*분양": "혜택 문구",
}
_COMPILED = [(re.compile(p), name) for p, name in KEYWORDS.items()]


@dataclass(frozen=True)
class SiteTextHit:
    keyword: str
    phrase: str
    excerpt: str
    start: int
    end: int


@dataclass
class SiteTextResult:
    raw_document_id: int | None
    url: str
    checked_at: str
    http_status: int | None
    reason: str | None  # 실패 사유('403', 'DNS', 'timeout', '원문 없음'); 성공이면 None
    image_hash: str | None
    hits: list[SiteTextHit] = field(default_factory=list)

    @property
    def keywords(self) -> list[str]:
        return sorted({h.keyword for h in self.hits})


def scan_text(text: str) -> list[SiteTextHit]:
    """문구 위치를 줄 단위 발췌와 함께 모은다(겹치는 같은 키워드는 한 번)."""
    hits: list[SiteTextHit] = []
    seen: set[tuple[str, int]] = set()
    for rx, name in _COMPILED:
        for m in rx.finditer(text):
            ls, le = line_span(text, m.start())
            if (name, ls) in seen:
                continue
            seen.add((name, ls))
            hits.append(SiteTextHit(name, m.group(0), text[ls:le].strip(), m.start(), m.end()))
    hits.sort(key=lambda h: (h.start, h.keyword))
    return hits


def read_site(raw: RawDocument, *, raw_dir: Path | None = None) -> SiteTextResult:
    res = SiteTextResult(
        raw_document_id=raw.id,
        url=raw.url,
        checked_at=checked_on(raw),
        http_status=raw.http_status,
        reason=None,
        image_hash=raw.image_hash,
    )
    if raw.http_status is not None and raw.http_status != 200:
        res.reason = str(raw.http_status)
        return res
    if raw.http_status is None and raw.error_text:
        res.reason = raw.error_text
        return res
    text = read_raw_text(raw, raw_dir=raw_dir)
    if text is None:
        res.reason = "원문 없음"
        return res
    res.hits = scan_text(text)
    return res


class OfficialSiteParser:
    """``Parser`` 모양을 맞춘 구현. 접수 상태는 FieldCandidate로 낼 수 없어(계약) 빈 목록 — ``read_site``
    사용."""

    def __init__(self, *, raw_dir: Path | None = None) -> None:
        self._raw_dir = raw_dir

    def parse(self, raw: RawDocument) -> list[FieldCandidate]:
        del raw
        return []

    def read(self, raw: RawDocument) -> SiteTextResult:
        return read_site(raw, raw_dir=self._raw_dir)

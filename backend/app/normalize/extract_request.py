"""파서가 못 읽은 필드 → 판정기 extract 요청 데이터 (WP2 → WP3).

정규식·표 파서가 실패한 후보(needs_extract=True, label='확인 불가')를 원문·엔티티별로 묶어
``{text, fields[], source_url, raw_document_id, entity, entity_key}`` 데이터로 만든다.
판정기를 부르지 않는다 — 실제 호출·guard·캐시는 WP3(judge/)가 한다(AGENTS 규칙 4·6).
텍스트는 공개 공고문 발췌뿐이고, 전화번호·이메일 같은 민감 패턴은 ``app.core.redact``로 가린 뒤
2,000자로 자른다(RA WP3 카드 '증거 카드 ≤2,000자').
한 묶음의 필드가 JEV extract 상한(32개, ``EXTRACT_FIELDS_MAX``)을 넘으면 32개씩 나눈 요청 여러 건을 만든다 —
OCR 공고문처럼 필드가 많아도 잘려 나가는 필드가 없다(R3b C3). 요청마다 텍스트는 그 필드들의 발췌만 담는다.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from app.core.contracts_gen import FieldCandidate
from app.core.redact import redact_text
from app.core.settings import get_settings

__all__ = ["EXTRACT_FIELDS_MAX", "FIELD_DESCRIPTIONS", "MAX_TEXT", "ExtractRequest", "build_extract_requests"]

MAX_TEXT = 2000
EXTRACT_FIELDS_MAX = 32
"""JEV extract fields 상한(``judge.payloads.extract_payload`` 와 같은 수)."""

FIELD_DESCRIPTIONS: dict[str, str] = {
    "max_price_won": "주택형별 공급금액 최고가(원, 정수)",
    "floor_sample_price_won": "주택형별 최저층(대표층) 공급금액(원, 정수)",
    "balcony_won": "주택형별 발코니 확장 금액(원, 정수; 무상이면 0)",
    "options_required_won": "필수 옵션 합계(원, 정수; 없으면 0)",
    "down_payment_pct": "계약금 비율(%)",
    "interim_pct": "중도금 비율(%)",
    "balance_pct": "잔금 비율(%)",
    "interim_schedule": "중도금 회차별 납부일(YYYY-MM-DD)과 비율(%) 목록",
    "effective_from": "이 공고의 입주자모집공고일(YYYY-MM-DD)",
    "resale_months": "전매제한 기간(개월)",
    "residency_months": "거주의무기간(개월, 없으면 0)",
    "rewin_restriction_years": "재당첨제한 기간(년, 없으면 0)",
    "move_in_ym": "입주 예정 연월(YYYY-MM)",
    "units_total": "공급 세대수(일반분양 기준)",
}


@dataclass(frozen=True)
class ExtractRequest:
    raw_document_id: int | None
    source_url: str | None
    entity: str
    entity_key: str | None
    fields: list[str]
    text: str
    reasons: dict[str, str] = field(default_factory=dict)

    @property
    def payload(self) -> dict[str, Any]:
        """판정기 extract에 넘길 데이터(공개 공고문 발췌 + 뽑을 필드 정의). guard는 WP3가 적용한다."""
        return {
            "text": self.text,
            "fields": [{"name": f, "description": FIELD_DESCRIPTIONS.get(f, f)} for f in self.fields],
            "source_url": self.source_url,
            "entity": self.entity,
            "entity_key": self.entity_key,
        }


def build_extract_requests(
    candidates: list[FieldCandidate], *, max_text: int = MAX_TEXT, max_fields: int = EXTRACT_FIELDS_MAX
) -> list[ExtractRequest]:
    groups: OrderedDict[tuple[int | None, str, str | None], list[FieldCandidate]] = OrderedDict()
    for c in candidates:
        if c.needs_extract:
            groups.setdefault((c.raw_document_id, c.entity, c.entity_key), []).append(c)
    secrets = get_settings().secret_values()
    out: list[ExtractRequest] = []
    for (rid, entity, key), cs in groups.items():
        fields = list(OrderedDict.fromkeys(c.field for c in cs))
        for start in range(0, len(fields), max_fields):
            chunk = fields[start : start + max_fields]
            members = [c for c in cs if c.field in set(chunk)]
            excerpts: list[str] = []
            for c in members:
                if c.excerpt not in excerpts:
                    excerpts.append(c.excerpt)
            out.append(
                ExtractRequest(
                    raw_document_id=rid,
                    source_url=cs[0].url,
                    entity=entity,
                    entity_key=key,
                    fields=chunk,
                    text=redact_text("\n…\n".join(excerpts), secrets)[:max_text],
                    reasons={c.field: (c.reason or "파싱 실패") for c in members},
                )
            )
    return out

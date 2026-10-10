"""R3f CORE4 — m12·D14-6: resolver 의 '사람 확인 이후 관측' 비교는 KST 날짜(``core.time.kst_date``) — 문자열 앞 10자가 아니다."""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from app.core.contracts_gen import FieldCandidate
from app.normalize.resolver import resolve


def _cand(**kw: Any) -> FieldCandidate:
    base: dict[str, Any] = {
        "entity": "complex", "entity_id": 7, "entity_key": None, "field": "resale_months", "value_text": "12개월",
        "value": 12, "source_rank": 1, "source_kind": "notice_pdf", "primary": True, "label": "확인됨",
        "excerpt": "전매제한 12개월", "raw_document_id": 11, "url": "https://www.applyhome.co.kr/a",
        "checked_at": "2026-09-01", "observed_on": "2026-09-01",
    }  # fmt: skip
    base.update(kw)
    return FieldCandidate(**base)


def _human(value: int, *, checked_at: str, observed_on: str | None) -> FieldCandidate:
    return _cand(value=value, value_text=str(value), source_rank=0, source_kind=None, label="확인됨",
                 reason="사람 확인(phone)", excerpt="전화 확인", raw_document_id=None, url=None,
                 checked_at=checked_at, observed_on=observed_on)  # fmt: skip


def test_utc_evening_human_check_is_next_kst_day_same_day_notice_loses() -> None:
    """2026-10-09T20:00:00Z = KST 10-10 05시. 10-10 관측 공고는 같은 날(이후가 아님) → 사람 확인이 이긴다."""
    human = _human(24, checked_at="2026-10-09T20:00:00Z", observed_on=None)
    notice = _cand(value=36, raw_document_id=13, observed_on="2026-10-10", checked_at="2026-10-10")
    r = resolve([human, notice])
    assert [c.value for c in r.chosen] == [24]


def test_utc_observed_on_on_human_row_is_compared_in_kst() -> None:
    """observed_on 에 시각이 붙어 있어도(옛 행) KST 날짜로 본다 — '2026-10-09T20:00:00Z'[:10] 은 10-09 지만 KST 는 10-10."""
    human = _human(24, checked_at="2026-10-09T20:00:00Z", observed_on="2026-10-09T20:00:00Z")
    notice = _cand(value=36, raw_document_id=13, observed_on="2026-10-10", checked_at="2026-10-10")
    assert [c.value for c in resolve([human, notice]).chosen] == [24]
    later = _cand(value=36, raw_document_id=14, observed_on="2026-10-11", checked_at="2026-10-11")
    assert [c.value for c in resolve([human, later]).chosen] == [36], (
        "KST 다음 날 관측 공고의 다른 값은 이긴다(D12-1)"
    )


def test_date_only_legacy_human_unchanged() -> None:
    human = _human(24, checked_at="2026-10-09", observed_on="2026-10-09")
    same_day = _cand(value=36, raw_document_id=13, observed_on="2026-10-09")
    after = _cand(value=36, raw_document_id=14, observed_on="2026-10-10")
    assert [c.value for c in resolve([human, same_day]).chosen] == [24]
    assert [c.value for c in resolve([human, after]).chosen] == [36]

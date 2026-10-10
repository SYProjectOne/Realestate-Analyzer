"""R3d CORE2 — 정규화 쪽 4차 리뷰 재현 (`docs/design/wp/R3_REVIEW4.md`, DECISIONS D12-1, 계약 2026-10-09.9).

| 리뷰 | 테스트 |
| --- | --- |
| C-2 | compare 채택(adopted)이 사람 확인(source_rank 0)을 이기지 못한다 — resolver·정규화 저장 둘 다 |
| M-10 · D12-1 | 사람 확인 **이후에** 관측된 공식 1차 출처의 다른 값 → 그 값 채택 + critical change_event + '사람 확인 재검토' |
"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contracts_gen import FieldCandidate
from app.core.contracts_gen import RawDocument as RawDocumentDTO
from app.models import ChangeEvent, ChecklistItem, Complex, FieldProvenance, Region
from app.normalize.fields import COMPARE_ADOPTED, COMPARE_SIDE, with_tag
from app.normalize.resolver import resolve
from app.normalize.store import store_raw_document

from ._support import AddRaw


def _cand(**kw: Any) -> FieldCandidate:
    base: dict[str, Any] = {
        "entity": "complex", "entity_id": 7, "entity_key": None, "field": "resale_months", "value_text": "12개월",
        "value": 12, "source_rank": 1, "source_kind": "notice_pdf", "primary": True, "label": "확인됨",
        "excerpt": "전매제한 12개월", "raw_document_id": 11, "url": "https://www.applyhome.co.kr/a",
        "checked_at": "2026-09-01", "observed_on": "2026-09-01",
    }  # fmt: skip
    base.update(kw)
    return FieldCandidate(**base)


def _human(value: int, day: str = "2026-10-09") -> FieldCandidate:
    return _cand(value=value, value_text=str(value), source_rank=0, source_kind=None, label="확인됨",
                 reason="사람 확인(phone)", excerpt="전화 확인", raw_document_id=None, url=None,
                 checked_at=f"{day}T10:00:00+09:00", observed_on=day)  # fmt: skip


def test_c2_compare_adopted_does_not_beat_human_check() -> None:
    adopted = _cand(value=12, reason=with_tag(None, COMPARE_ADOPTED, "jl_3"))
    side = _cand(
        value=36,
        source_kind="applyhome_detail",
        raw_document_id=12,
        reason=with_tag(None, COMPARE_SIDE, "jl_3"),
    )
    r = resolve([adopted, side, _human(24)])
    assert [c.value for c in r.chosen] == [24], "compare 채택은 사람 확인(0순위)을 이기지 못한다(C-2·D12-1)"
    assert not r.needs_compare
    chosen_rows = [p for p in r.provenance if p.chosen]
    assert len(chosen_rows) == 1 and (chosen_rows[0].reason or "").startswith("사람 확인")


def test_d12_1_older_official_source_loses_to_human() -> None:
    r = resolve([_cand(value=12, observed_on="2026-10-08"), _human(24, "2026-10-09")])
    assert [c.value for c in r.chosen] == [24]


def test_d12_1_newer_official_source_with_other_value_wins() -> None:
    newer = _cand(value=36, raw_document_id=13, observed_on="2026-10-12", checked_at="2026-10-12")
    r = resolve([_cand(value=12), _human(24, "2026-10-09"), newer])
    assert [c.value for c in r.chosen] == [36], "사람 확인 이후 공식 1차 출처의 다른 값이 채택된다(D12-1)"
    assert "사람 확인 이후" in r.conflicts[0].rule
    # 같은 값이면 사람 확인 그대로(재검토 불필요), 공식이 아닌 출처(언론)는 이기지 못한다
    same = _cand(value=24, raw_document_id=13, observed_on="2026-10-12")
    assert [c.value for c in resolve([_human(24), same]).chosen] == [24]
    news = _cand(
        value=36,
        raw_document_id=14,
        source_rank=3,
        source_kind="news",
        primary=False,
        label="비공식",
        observed_on="2026-10-12",
    )
    assert [c.value for c in resolve([_human(24), news]).chosen] == [24]


class _One:
    def __init__(self, key: str, field: str, value: Any, observed_on: str) -> None:
        self.key, self.field, self.value, self.observed_on = key, field, value, observed_on

    def parse(self, raw: RawDocumentDTO) -> list[FieldCandidate]:
        return [
            _cand(entity_id=None, entity_key=self.key, field=self.field, value=self.value, value_text=str(self.value),
                  raw_document_id=raw.id, url=raw.url, observed_on=self.observed_on, checked_at=self.observed_on,
                  excerpt=f"{self.field} {self.value}"),
        ]  # fmt: skip


def test_d12_1_store_new_official_notice_after_human_check(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    key = "2026000777"
    raw = add_raw("n1", source_kind="notice_pdf", url="https://www.applyhome.co.kr/n1", region_id=region.id)
    cx = Complex(region_id=region.id, applyhome_id=key, name="테스트 단지", former_names=[], apply_dates=[],
                 contract_dates=[], inclusion_class="미분류")  # fmt: skip
    db_session.add(cx)
    db_session.flush()
    store_raw_document(db_session, raw, parser=_One(key, "resale_months", 12, "2026-09-01"))
    # 사람 확인(0순위 후보) — API 와 같은 경로
    from app.normalize.store import resolve_field_group

    resolve_field_group(
        db_session, "complex", cx.id, "resale_months", [_human(24).model_copy(update={"entity_id": cx.id})]
    )
    db_session.refresh(cx)
    assert cx.resale_months == 24
    # 사람 확인보다 오래된 공고 재수집(같은 원문 재정규화) → 사람 확인 유지
    raw_old = add_raw(
        "n1-again", source_kind="notice_pdf", url="https://www.applyhome.co.kr/n1b", region_id=region.id
    )
    store_raw_document(db_session, raw_old, parser=_One(key, "resale_months", 12, "2026-10-01"))
    db_session.refresh(cx)
    assert cx.resale_months == 24, "사람 확인 이전에 관측된 공고는 사람 확인을 이기지 못한다"
    # 사람 확인 이후의 새 공식 공고(다른 값) → 채택 + critical 이벤트 + 재검토 체크리스트
    raw_new = add_raw(
        "n2", source_kind="notice_pdf", url="https://www.applyhome.co.kr/n2", region_id=region.id
    )
    res = store_raw_document(db_session, raw_new, parser=_One(key, "resale_months", 36, "2026-10-12"))
    db_session.refresh(cx)
    assert cx.resale_months == 36, "사람 확인 이후 새 공식 공고의 다른 값 채택(D12-1)"
    ev = [e for e in res.change_events if e.field == "resale_months"]
    assert ev and ev[0].severity == "critical" and ev[0].triggers_rejudge, "critical change_event"
    items = list(db_session.scalars(select(ChecklistItem).where(ChecklistItem.complex_id == cx.id)))
    review = [i for i in items if i.title.startswith("사람 확인 재검토")]
    assert len(review) == 1 and review[0].status == "open" and review[0].kind == "사실 재확인", [
        i.title for i in items
    ]
    # 같은 원문 다시 정규화 → 이벤트·항목 중복 없음
    raw_new2 = add_raw(
        "n2-again", source_kind="notice_pdf", url="https://www.applyhome.co.kr/n2b", region_id=region.id
    )
    store_raw_document(db_session, raw_new2, parser=_One(key, "resale_months", 36, "2026-10-12"))
    assert len([i for i in db_session.scalars(select(ChecklistItem).where(ChecklistItem.complex_id == cx.id))
                if i.title.startswith("사람 확인 재검토")]) == 1  # fmt: skip
    crit = list(db_session.scalars(select(ChangeEvent).where(ChangeEvent.complex_id == cx.id, ChangeEvent.field == "resale_months",
                                                            ChangeEvent.severity == "critical")))  # fmt: skip
    assert len(crit) == 1
    human_row = db_session.scalars(select(FieldProvenance).where(FieldProvenance.entity_id == cx.id,
                                                                 FieldProvenance.reason.like("사람 확인%"))).one()  # fmt: skip
    assert human_row.chosen is False, "사람 확인 행은 남되(병기) 채택되지 않는다"

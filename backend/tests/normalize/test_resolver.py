"""Resolver (RA §3 표 · T5): 우선순위, conflict_group, needs_compare(1차·1차 같은 rank만)."""

from __future__ import annotations

from typing import Any

from app.core.contracts_gen import FieldCandidate
from app.core.protocols import Resolver
from app.normalize.resolver import PriorityResolver, resolve


def cand(**kw: Any) -> FieldCandidate:
    base: dict[str, Any] = {
        "entity": "complex",
        "entity_id": 13,
        "entity_key": "2025000271",
        "field": "units_total",
        "value_text": "1,573",
        "value": 1573,
        "source_rank": 1,
        "source_kind": "applyhome_detail",
        "primary": True,
        "label": "확인됨",
        "excerpt": "공급세대수 1,573세대",
        "raw_document_id": 9101,
        "url": "https://www.applyhome.co.kr/",
        "checked_at": "2026-10-07",
    }
    base.update(kw)
    return FieldCandidate(**base)


def test_implements_protocol() -> None:
    assert isinstance(PriorityResolver(), Resolver)


def test_t5_harrington_1573_vs_1769_rank1_chosen_one_conflict_no_compare() -> None:
    a = cand()
    b = cand(
        value=1769,
        value_text="1,769",
        source_rank=2,
        source_kind="notice_pdf",
        excerpt="총 1,769세대",
        raw_document_id=9102,
    )
    r = resolve([b, a])  # 입력 순서와 무관
    assert [c.value for c in r.chosen] == [1573]
    assert len(r.conflicts) == 1
    g = r.conflicts[0]
    assert g.conflict_group == "complex:13:units_total"
    assert g.needs_compare is False and r.needs_compare is False
    assert g.candidates[g.chosen_index].source_kind == "applyhome_detail"
    rows = {p.value_text: p for p in r.provenance}
    assert rows["1,573"].chosen is True and rows["1,769"].chosen is False
    assert rows["1,573"].conflict_group == rows["1,769"].conflict_group == "complex:13:units_total"
    assert "청약홈 상세(1) > 공고문(2)" in g.rule


def test_same_value_no_conflict_but_all_rows_kept() -> None:
    r = resolve(
        [cand(), cand(source_rank=2, source_kind="notice_pdf", raw_document_id=9102, value_text="1573")]
    )
    assert r.conflicts == [] and len(r.provenance) == 2
    assert sum(p.chosen for p in r.provenance) == 1
    assert all(p.conflict_group is None for p in r.provenance)


def test_primary_vs_primary_same_rank_different_sources_needs_compare() -> None:
    a = cand(field="notice_date", value="2025-07-04", value_text="2025-07-04")
    b = cand(
        field="notice_date",
        value="2025-07-05",
        value_text="2025-07-05",
        source_kind="applyhome_list",
        raw_document_id=9200,
    )
    r = resolve([a, b])
    assert r.needs_compare is True and r.conflicts[0].needs_compare is True


def test_same_source_kind_latest_wins_without_compare() -> None:
    """가격은 '공고문 최신' — 같은 출처 종류(공고문 2건)는 최신이 이기고 compare는 없다."""
    old = cand(
        entity="complex_type",
        entity_key="2025000302:84A",
        entity_id=None,
        field="max_price_won",
        value=609_000_000,
        value_text="609,000,000",
        source_kind="notice_pdf",
        checked_at="2025-08-22",
        raw_document_id=1,
    )
    new = old.model_copy(
        update={
            "value": 605_000_000,
            "value_text": "605,000,000",
            "checked_at": "2026-08-14",
            "raw_document_id": 2,
        }
    )
    r = resolve([old, new])
    assert r.chosen[0].value == 605_000_000
    assert r.needs_compare is False
    assert r.conflicts[0].conflict_group == "complex_type:2025000302:84A:max_price_won"


def test_primary_beats_secondary_and_secondary_pair_is_listed_without_compare() -> None:
    news = cand(
        source_rank=3, source_kind="news", primary=False, label="비공식", value=1700, value_text="1,700"
    )
    r = resolve([news, cand()])
    assert r.chosen[0].value == 1573 and r.needs_compare is False
    n1 = cand(source_rank=3, source_kind="news", primary=False, label="비공식", value=1700, raw_document_id=1)
    n2 = cand(source_rank=3, source_kind="news", primary=False, label="비공식", value=1800, raw_document_id=2)
    r2 = resolve([n1, n2])
    assert r2.needs_compare is False and "둘 다 2차" in r2.conflicts[0].rule


def test_value_beats_unreadable_candidate() -> None:
    missing = cand(
        value=None, value_text=None, label="확인 불가", reason="파싱 실패", needs_extract=True, source_rank=1
    )
    got = cand(source_rank=2, source_kind="notice_pdf", raw_document_id=5)
    r = resolve([missing, got])
    assert r.chosen[0].value == 1573 and r.conflicts == []
    only_missing = resolve([missing])
    assert only_missing.chosen[0].label == "확인 불가" and only_missing.provenance[0].chosen is True


def test_groups_by_entity_id_then_key() -> None:
    r = resolve([cand(field="units_total"), cand(field="units_general", value=303, value_text="303")])
    assert len(r.chosen) == 2 and r.conflicts == []

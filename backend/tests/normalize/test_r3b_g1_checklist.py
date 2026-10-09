"""R3b G1 — 체크리스트 (N-M5 · F1a '계약' kind · F2 미해결 단지 유지).

N-M5: 항목 식별은 제목(값 포함)이 아니라 (단지, 항목 키 = kind·필드) — 값이 바뀌면 같은 열린 항목의 제목·날짜를 고친다.
리뷰 재현: resale_months 12→24 → '전매제한 종료' 열린 항목 2개가 남던 것.
"""

# ruff: noqa: E501

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ChecklistItem, Complex, FieldProvenance, Region
from app.normalize.checklist import sync_checklist

from ._assemble_support import ASOF, add_complex


def _items(db_session: Session, complex_id: int) -> list[ChecklistItem]:
    return list(
        db_session.scalars(
            select(ChecklistItem).where(ChecklistItem.complex_id == complex_id).order_by(ChecklistItem.id)
        )
    )


def _cx(db_session: Session, region: Region, **kw: object) -> Complex:
    base: dict[str, object] = dict(
        notice_date="2026-09-01", winner_date="2026-09-20", resale_months=12, residency_months=24,
        move_in_ym="2028-03", contract_dates=[{"from": "2026-10-20", "to": "2026-10-22"}],
    )  # fmt: skip
    base.update(kw)
    return add_complex(db_session, region.id, "2026000111", "테스트 단지", **base)


def test_nm5_review_repro_resale_change_updates_same_item(db_session: Session, region: Region) -> None:
    cx = _cx(db_session, region)
    sync_checklist(db_session, region.id, asof_date=ASOF)
    cx.resale_months = 24
    db_session.flush()
    res = sync_checklist(db_session, region.id, asof_date=ASOF)
    resale = [i for i in _items(db_session, cx.id) if i.title.startswith("전매제한 종료")]
    assert [(i.title, i.due_date, i.status) for i in resale] == [
        ("전매제한 종료(당첨자 발표일 + 24개월, 산술)", "2028-09-20", "open")
    ]
    assert res.inserted == 0 and res.updated == 1


def test_nm5_residency_and_legal_estimate_value_change_updates_same_item(
    db_session: Session, region: Region
) -> None:
    cx = _cx(db_session, region)
    fp = FieldProvenance(entity="complex", entity_id=cx.id, field="resale_months", value_text="12",
                         url="https://example.com/n.pdf", checked_at="2026-10-08", label="추정", source_rank=2,
                         chosen=True)  # fmt: skip
    db_session.add(fp)
    db_session.flush()
    sync_checklist(db_session, region.id, asof_date=ASOF)
    n = len(_items(db_session, cx.id))
    cx.residency_months = 36
    fp.value_text = "24"
    db_session.flush()
    sync_checklist(db_session, region.id, asof_date=ASOF)
    items = _items(db_session, cx.id)
    assert len(items) == n
    titles = {i.title for i in items}
    assert (
        "거주의무 만료(입주예정월 + 36개월, 추정)" in titles
        and "거주의무 만료(입주예정월 + 24개월, 추정)" not in titles
    )
    assert "전매제한 기간 확인(추정 값 24)" in titles and "전매제한 기간 확인(추정 값 12)" not in titles


def test_nm5_done_item_is_not_rewritten(db_session: Session, region: Region) -> None:
    cx = _cx(db_session, region)
    sync_checklist(db_session, region.id, asof_date=ASOF)
    item = next(i for i in _items(db_session, cx.id) if i.title.startswith("전매제한 종료"))
    item.status = "done"
    cx.resale_months = 24
    db_session.flush()
    sync_checklist(db_session, region.id, asof_date=ASOF)
    resale = [i for i in _items(db_session, cx.id) if i.title.startswith("전매제한 종료")]
    assert [(i.title, i.status) for i in resale] == [("전매제한 종료(당첨자 발표일 + 12개월, 산술)", "done")]


def test_nm5_old_duplicate_open_items_collapse(db_session: Session, region: Region) -> None:
    """옛 버전이 남긴 같은 키의 열린 항목 둘 → 하나만 갱신하고 나머지는 na."""
    cx = _cx(db_session, region, resale_months=24)
    db_session.add_all([
        ChecklistItem(complex_id=cx.id, kind="만료", title="전매제한 종료(당첨자 발표일 + 12개월, 산술)", due_date="2027-09-20", status="open"),
        ChecklistItem(complex_id=cx.id, kind="만료", title="전매제한 종료(당첨자 발표일 + 24개월, 산술)", due_date="2028-09-20", status="open"),
    ])  # fmt: skip
    db_session.flush()
    sync_checklist(db_session, region.id, asof_date=ASOF)
    resale = [(i.title, i.status) for i in _items(db_session, cx.id) if i.title.startswith("전매제한 종료")]
    assert sorted(resale) == [
        ("전매제한 종료(당첨자 발표일 + 12개월, 산술)", "na"),
        ("전매제한 종료(당첨자 발표일 + 24개월, 산술)", "open"),
    ]


def test_f1a_contract_deadline_uses_contract_kind(db_session: Session, region: Region) -> None:
    cx = _cx(db_session, region)
    old = ChecklistItem(
        complex_id=cx.id, kind="만료", title="계약 체결 마감", due_date="2026-10-21", status="open"
    )
    db_session.add(old)
    db_session.flush()
    sync_checklist(db_session, region.id, asof_date=ASOF)
    contract = [
        (i.kind, i.title, i.due_date) for i in _items(db_session, cx.id) if i.title == "계약 체결 마감"
    ]
    assert contract == [("계약", "계약 체결 마감", "2026-10-22")]  # 옛 '만료' 행을 같은 항목으로 옮김


def test_f2_unresolved_exclusion_keeps_items_open(db_session: Session, region: Region) -> None:
    """제외 클래스라도 분류가 미해결(decision ≠ auto)이면 열린 항목을 닫지 않는다(판정 범위 '미해결')."""
    cx = _cx(db_session, region)
    sync_checklist(db_session, region.id, asof_date=ASOF)
    cx.inclusion_class, cx.inclusion_decision = "public_rental", "review"
    db_session.flush()
    res = sync_checklist(db_session, region.id, asof_date=ASOF)
    assert res.closed == 0 and {i.status for i in _items(db_session, cx.id)} == {"open"}
    cx.inclusion_decision = "auto"
    db_session.flush()
    res = sync_checklist(db_session, region.id, asof_date=ASOF)
    assert {i.status for i in _items(db_session, cx.id)} == {"na"} and res.closed > 0


def test_fact_recheck_items_are_never_touched(db_session: Session, region: Region) -> None:
    """계약 .6 D10-3: '사실 재확인' 항목(강등 — API 가 만들고 닫는다)은 체크리스트 동기화가 고치거나 닫지 않는다."""
    cx = _cx(db_session, region)
    item = ChecklistItem(
        complex_id=cx.id, kind="사실 재확인", title="사실 재확인: 전매제한 기간(검증 모순)", status="open"
    )
    db_session.add(item)
    db_session.flush()
    sync_checklist(db_session, region.id, asof_date=ASOF)
    cx.inclusion_class, cx.inclusion_decision = "public_rental", "auto"
    db_session.flush()
    sync_checklist(db_session, region.id, asof_date=ASOF)
    assert (item.kind, item.title, item.status) == (
        "사실 재확인",
        "사실 재확인: 전매제한 기간(검증 모순)",
        "open",
    )

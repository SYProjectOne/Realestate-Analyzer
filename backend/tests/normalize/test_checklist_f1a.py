"""R3 M7: checklist_item — 사실 테이블에서 결정론적으로(멱등).

- 중도금: 현재 납부 조건(최신 effective_from)의 interim_schedule 회차별 납부일
- 만료: 전매제한 종료(당첨자 발표일 + 전매 개월), 거주의무 만료(입주예정월 + 거주 개월) · 계약: 계약 체결 마감
- 공고 예상: 모집공고일이 기준일 뒤인 단지, 공고 전 단지(applyhome_id 없음)
- 법적 확인: 토지거래허가·대지지분, 비과세 거주요건(항상 확인 권고), 라벨 '추정'인 법적 사실 필드
기준일 이전 날짜는 새로 만들지 않는다. 제외 클래스 단지의 열린 항목은 na.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ChecklistItem, FieldProvenance, PaymentTerms, Region
from app.normalize.checklist import sync_checklist

from ._assemble_support import ASOF, add_complex


def _items(db_session: Session, complex_id: int | None = None) -> list[ChecklistItem]:
    stmt = select(ChecklistItem).order_by(ChecklistItem.id)
    if complex_id is not None:
        stmt = stmt.where(ChecklistItem.complex_id == complex_id)
    return list(db_session.scalars(stmt))


def _seed(db_session: Session, region: Region) -> int:
    cx = add_complex(
        db_session,
        region.id,
        "2026000111",
        "테스트 단지",
        notice_date="2026-09-01",
        winner_date="2026-09-20",
        resale_months=12,
        residency_months=24,
        move_in_ym="2028-03",
        contract_dates=[{"from": "2026-10-20", "to": "2026-10-22"}],
    )
    db_session.add_all(
        [
            PaymentTerms(
                complex_id=cx.id,
                notice_no="2026000111",
                notice_kind="본청약",
                effective_from="2026-09-01",
                interim_schedule=[
                    {"seq": 1, "due_date": "2026-09-30", "pct": 10},  # 지난 날짜 → 만들지 않음
                    {"seq": 2, "due_date": "2027-01-15", "pct": 10},
                ],
                price_by_type={},
            ),
            PaymentTerms(
                complex_id=cx.id,
                notice_no="2026940999",
                notice_kind="임의",
                effective_from="2026-10-01",  # 최신 = 현재 조건
                interim_schedule=[{"seq": 1, "due_date": "2026-11-30", "pct": 10}],
                price_by_type={},
            ),
        ]
    )
    db_session.flush()
    return cx.id


def test_items_from_fact_tables(db_session: Session, region: Region) -> None:
    cid = _seed(db_session, region)
    res = sync_checklist(db_session, region.id, asof_date=ASOF)
    got = {(i.kind, i.title, i.due_date) for i in _items(db_session, cid)}
    assert ("중도금", "중도금 1회차 납부일", "2026-11-30") in got  # 현재(최신) 납부 조건
    assert not any(k == "중도금" and d == "2027-01-15" for k, _, d in got)  # 옛 조건 회차는 안 씀
    assert ("만료", "전매제한 종료(당첨자 발표일 + 12개월, 산술)", "2027-09-20") in got
    assert ("만료", "거주의무 만료(입주예정월 + 24개월, 추정)", "2030-03-01") in got
    assert ("계약", "계약 체결 마감", "2026-10-22") in got  # kind 계약(0004)
    legal = {t for k, t, _ in got if k == "법적 확인"}
    assert "토지거래허가구역 여부·대지지분 기준 확인(확인 권고)" in legal
    assert "비과세 거주요건 적용 여부 확인(확인 권고)" in legal
    assert all(i.status == "open" for i in _items(db_session, cid))
    assert res.inserted == len(got)


def test_announcement_expected(db_session: Session, region: Region) -> None:
    future = add_complex(db_session, region.id, "2026000222", "공고 예정 단지", notice_date="2026-11-05")
    pre = add_complex(db_session, region.id, None, "공고 전 단지")
    sync_checklist(db_session, region.id, asof_date=ASOF)
    assert [
        (i.kind, i.title, i.due_date) for i in _items(db_session, future.id) if i.kind == "공고 예상"
    ] == [("공고 예상", "모집공고 예정", "2026-11-05")]
    assert [(i.kind, i.due_date) for i in _items(db_session, pre.id) if i.kind == "공고 예상"] == [
        ("공고 예상", None)
    ]


def test_estimated_legal_fact_becomes_legal_check(db_session: Session, region: Region) -> None:
    cid = _seed(db_session, region)
    db_session.add(
        FieldProvenance(
            entity="complex",
            entity_id=cid,
            field="residency_months",
            value_text="24",
            url="https://example.com/notice.pdf",
            checked_at="2026-10-08",
            label="추정",
            source_rank=2,
            chosen=True,
        )
    )
    db_session.flush()
    sync_checklist(db_session, region.id, asof_date=ASOF)
    titles = {i.title for i in _items(db_session, cid) if i.kind == "법적 확인"}
    assert "거주의무 기간 확인(추정 값 24)" in titles


def test_sync_is_idempotent_and_updates_open_due_date(db_session: Session, region: Region) -> None:
    cid = _seed(db_session, region)
    sync_checklist(db_session, region.id, asof_date=ASOF)
    n = len(_items(db_session))
    again = sync_checklist(db_session, region.id, asof_date=ASOF)
    assert (again.inserted, again.updated) == (0, 0) and len(_items(db_session)) == n

    pt = db_session.scalars(select(PaymentTerms).where(PaymentTerms.notice_no == "2026940999")).one()
    pt.interim_schedule = [{"seq": 1, "due_date": "2026-12-10", "pct": 10}]
    done = next(i for i in _items(db_session, cid) if i.kind == "계약" and i.title.startswith("계약"))
    done.status = "done"
    db_session.flush()
    res = sync_checklist(db_session, region.id, asof_date=ASOF)
    assert res.updated == 1 and len(_items(db_session)) == n
    item = next(i for i in _items(db_session, cid) if i.title == "중도금 1회차 납부일")
    assert item.due_date == "2026-12-10"
    assert db_session.get(ChecklistItem, done.id).status == "done"  # type: ignore[union-attr]


def test_excluded_complex_gets_no_items_and_open_items_become_na(db_session: Session, region: Region) -> None:
    cid = _seed(db_session, region)
    rental = add_complex(
        db_session,
        region.id,
        "2026000333",
        "임대 단지",
        inclusion_class="public_rental",
        inclusion_decision="auto",  # 제외 확정(미해결이면 항목 유지 — test_r3b_g1_checklist)
        notice_date="2026-11-01",
    )
    sync_checklist(db_session, region.id, asof_date=ASOF)
    assert _items(db_session, rental.id) == []
    from app.models import Complex

    cx = db_session.get(Complex, cid)
    assert cx is not None
    cx.inclusion_class = "범위 경계"
    db_session.flush()
    res = sync_checklist(db_session, region.id, asof_date=ASOF)
    assert {i.status for i in _items(db_session, cid)} == {"na"}
    assert res.closed == len(_items(db_session, cid))


def test_fact_dict_values_are_read(db_session: Session, region: Region) -> None:
    """interim_schedule 항목이 Fact dict({v: …}) 로 저장된 경우도 읽는다(픽스처 형태)."""
    cx = add_complex(db_session, region.id, "2026000444", "Fact 단지")
    db_session.add(
        PaymentTerms(
            complex_id=cx.id,
            notice_no="2026000444",
            effective_from="2026-09-01",
            interim_schedule=[
                {"seq": 3, "due_date": {"v": "2026-12-01", "label": "확인됨"}, "pct": {"v": 10}}
            ],
            price_by_type={},
        )
    )
    db_session.flush()
    sync_checklist(db_session, region.id, asof_date=ASOF)
    assert [(i.title, i.due_date) for i in _items(db_session, cx.id) if i.kind == "중도금"] == [
        ("중도금 3회차 납부일", "2026-12-01")
    ]

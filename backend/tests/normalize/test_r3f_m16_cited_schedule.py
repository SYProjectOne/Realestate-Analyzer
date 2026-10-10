"""R3f CORE4 — 6차 리뷰 minor 16: 원 단지에 묶인 잔여 공고의 원 단지 후보(``CITED_COMPLEX_FIELDS``)가 '원 번호 인용'
경로의 입주월뿐이었다 — 같은 블록으로 묶인(W12c, 자기 번호) 잔여 공고의 입주 일정 변경은 버려졌다.

범위(D11-4와의 경계): 원 단지 후보로 받는 것은 **그 단지 전체의 일정**인 입주 예정월뿐이다. 잔여 공고의 공고일·청약
일정·당첨일·계약일은 그 잔여 공급 자신의 일정이라(``remaining_event``·``payment_terms`` 에 기록) 원 단지 값을 덮지
않는다 — D11-4 "이름·당첨일·세대수·일정 등은 원 단지 값을 덮어쓰지 않는다".

| 리뷰 | 테스트 |
| --- | --- |
| m16 같은 블록 병합 잔여 공고의 입주 지연 | ``test_m16_same_block_remainder_move_in_delay_is_kept`` |
| m16 경계: 인용·병합 잔여 공고의 자기 일정은 원 단지를 덮지 않음 | ``test_m16_remainder_own_schedule_never_overwrites`` |
"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contracts_gen import FieldCandidate
from app.core.contracts_gen import RawDocument as RawDocumentDTO
from app.models import ChangeEvent, Complex, Region
from app.normalize.store import store_raw_document

from ._support import AddRaw

ADDR = "인천광역시 연수구 송도동 32-15 (G5-11BL)"
REMNDR = "https://www.applyhome.co.kr/ai/aia/selectAPTRemndrLttotPblancDetailView.do?houseManageNo={key}&pblancNo={key}"
OWN_SCHEDULE = {"notice_date": "2026-09-01", "winner_date": "2026-09-20"}


class _Batch:
    """후보 묶음 그대로(단지 키·납부 조건 키는 호출자가 정한다)."""

    def __init__(self, rows: list[tuple[str, str, str, Any]], observed_on: str) -> None:
        self.rows, self.observed_on = rows, observed_on

    def parse(self, raw: RawDocumentDTO) -> list[FieldCandidate]:
        return [
            FieldCandidate(entity=e, entity_id=None, entity_key=k, field=f, value=v, value_text=str(v), source_rank=1,
                           source_kind="notice_pdf", primary=True, label="확인됨", excerpt=f"{f} {v}",
                           raw_document_id=raw.id, url=raw.url, observed_on=self.observed_on, checked_at=self.observed_on)
            for e, k, f, v in self.rows
        ]  # fmt: skip


def _orig(db_session: Session, add_raw: AddRaw, region: Region, key: str) -> Complex:
    rows = [
        ("complex", key, "name", "더샵 원 단지 G5-11블록"), ("complex", key, "address", ADDR),
        ("complex", key, "units_total", 3100), ("complex", key, "move_in_ym", "2028-03"),
        ("complex", key, "notice_date", "2024-04-20"), ("complex", key, "winner_date", "2024-05-10"),
        ("payment_terms", f"{key}:{key}", "effective_from", "2024-05-01"),
        ("payment_terms", f"{key}:{key}", "notice_kind", "본청약"),
    ]  # fmt: skip
    raw = add_raw(
        "orig", source_kind="notice_pdf", url="https://www.applyhome.co.kr/o.pdf", region_id=region.id
    )
    store_raw_document(db_session, raw, parser=_Batch(rows, "2024-05-01"))
    return db_session.scalars(select(Complex).where(Complex.applyhome_id == key)).one()


def test_m16_same_block_remainder_move_in_delay_is_kept(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    """자기 번호로 온 잔여 공고(같은 블록 병합 W12c): 이름·세대수·자기 일정은 버리고 입주 지연(2028-03 → 2028-09)은 받는다."""
    key, rem = "2024000111", "2026910777"
    cx = _orig(db_session, add_raw, region, key)
    rows = [
        ("complex", rem, "name", "더샵 원 단지 G5-11블록(임의공급 4차)"), ("complex", rem, "address", ADDR),
        ("complex", rem, "units_total", 3), ("complex", rem, "move_in_ym", "2028-09"),
        *(("complex", rem, f, v) for f, v in OWN_SCHEDULE.items()),
        ("payment_terms", f"{rem}:{rem}", "effective_from", "2026-09-10"),
        ("payment_terms", f"{rem}:{rem}", "notice_kind", "임의"),
    ]  # fmt: skip
    raw = add_raw("rem", source_kind="applyhome_detail", url=REMNDR.format(key=rem), region_id=region.id)
    res = store_raw_document(db_session, raw, parser=_Batch(rows, "2026-09-10"))
    assert [c.applyhome_id for c in db_session.scalars(select(Complex))] == [key], (
        "같은 블록 원 단지에 묶인다"
    )
    db_session.refresh(cx)
    assert (cx.name, cx.units_total, cx.move_in_ym) == ("더샵 원 단지 G5-11블록", 3100, "2028-09")
    assert (cx.notice_date, cx.winner_date) == ("2024-04-20", "2024-05-10")
    skipped = sorted({c.field for c in res.skipped if c.entity == "complex"})
    assert skipped == sorted(["name", "address", "units_total", *OWN_SCHEDULE]), skipped
    evs = [e.field for e in db_session.scalars(select(ChangeEvent).where(ChangeEvent.complex_id == cx.id))]
    assert "move_in_ym" in evs, evs


def test_m16_remainder_own_schedule_never_overwrites(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    """원 번호를 인용한 잔여 공고(PDF): 입주월만 원 단지 후보 — 공고일·당첨일(그 잔여 공급의 일정)은 원 단지를 덮지 않는다(D11-4)."""
    key, rem = "2024000222", "2026910888"
    cx = _orig(db_session, add_raw, region, key)
    rows = [
        ("complex", key, "name", "더샵 원 단지 G5-11블록(잔여세대)"), ("complex", key, "move_in_ym", "2028-06"),
        *(("complex", key, f, v) for f, v in OWN_SCHEDULE.items()),
        ("payment_terms", f"{key}:{rem}", "effective_from", "2026-09-10"),
        ("payment_terms", f"{key}:{rem}", "notice_kind", "무순위"),
    ]  # fmt: skip
    raw = add_raw(
        "rem2", source_kind="notice_pdf", url="https://www.applyhome.co.kr/r2.pdf", region_id=region.id
    )
    res = store_raw_document(db_session, raw, parser=_Batch(rows, "2026-09-10"))
    db_session.refresh(cx)
    assert (cx.move_in_ym, cx.notice_date, cx.winner_date) == ("2028-06", "2024-04-20", "2024-05-10")
    assert sorted({c.field for c in res.skipped if c.entity == "complex"}) == sorted(["name", *OWN_SCHEDULE])

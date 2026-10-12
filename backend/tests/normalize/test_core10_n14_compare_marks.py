"""R4 4차 재시험 N14(major — (b) 뒤 재판정 tools/call 0 위반, D23-3) — 재정규화 때 판정기 compare 채택·병기 표식을 보존한다.

R4 4차 2회차 (b): 같은 날 재정규화(``store._reparse_existing`` — 같은 원문 출처 행은 이번 파싱 후보가 대신)가 출처 행 reason 을 파서
값으로 다시 써 ``COMPARE_ADOPTED``·``COMPARE_SIDE`` 표식을 지웠다 → 47 필드의 '판정기 compare 채택' 근거가 change_event 없이 사라지고,
다음 재판정이 표식 없는 상대를 새 상충으로 보고 compare 4회를 새로 불렀다. 위험(같은 결과의 다른 모양): **같은 rank 1차·1차 상충**을
compare 로 푼 필드는 표식이 지워진 순간 다시 '채택 보류'(출처 상충 — compare 대기)가 되어 값이 빈다('확인됨' → '확인 불가') — R4
실데이터에는 그런 필드가 없어 관찰되지 않았다(이 테스트가 그 회귀를 고정한다).

D23-3: 같은 원문이 같은 자리(엔티티·필드·발췌 위치)에 **같은 값**을 다시 내면 그 출처 행의 compare 표식을 이번 후보에 다시 붙인다
(``store._carry_compare_marks``). 값이 바뀌면 옮기지 않는다 — 새 상충(compare 필요)이고 값 변경 이벤트가 남는다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.contracts_gen import FieldCandidate
from app.core.contracts_gen import RawDocument as RawDTO
from app.models import ChangeEvent, Complex, FieldProvenance, RawDocument, Region
from app.normalize.fields import COMPARE_ADOPTED, COMPARE_SIDE, CONFLICT_HOLD
from app.normalize.judged import apply_compare
from app.normalize.store import raw_dto, store_raw_document

KEY = "2099000077"
URLS = {
    "applyhome_detail": f"https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail?cond%5BHOUSE_MANAGE_NO%3A%3AEQ%5D={KEY}",
    "notice_pdf": f"https://static.applyhome.co.kr/ai/aia/getAtchmnfl.do?houseManageNo={KEY}&pblancNo={KEY}&atchmnflSeqNo=1",
}


class _Parser:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def parse(self, raw: RawDTO) -> list[FieldCandidate]:
        out = []
        for i, (field, value) in enumerate(sorted(self.values.items())):
            out.append(
                FieldCandidate(
                    entity="complex",
                    entity_id=None,
                    entity_key=KEY,
                    field=field,
                    value_text=value,
                    value=value,
                    source_rank=1,
                    source_kind=raw.source_kind,
                    primary=True,
                    label="확인됨",
                    reason=None,
                    excerpt=f"{field}: {value}",
                    excerpt_start=100 * i,
                    excerpt_end=100 * i + 20,
                    raw_document_id=raw.id,
                    url=raw.url,
                    checked_at="2026-10-13",
                    observed_on=None,
                    needs_extract=False,
                )
            )
        return out


def _raw(db: Session, region: Region, kind: str) -> RawDTO:
    row = RawDocument(
        source_kind=kind, url=URLS[kind], fetched_at="2026-10-13T01:05:00+09:00", http_status=200,
        sha256=hashlib.sha256(kind.encode()).hexdigest(), region_id=region.id,
    )  # fmt: skip
    db.add(row)
    db.flush()
    return raw_dto(row)


def _state(db: Session) -> tuple[Any, ...]:
    cx = db.scalars(select(Complex).where(Complex.applyhome_id == KEY)).one()
    rows = [
        (f.id, f.raw_document_id, f.value_norm, f.label, f.reason, f.chosen, f.conflict_group)
        for f in db.scalars(
            select(FieldProvenance).where(FieldProvenance.entity == "complex", FieldProvenance.field == "move_in_ym")
            .order_by(FieldProvenance.id)
        )
    ]  # fmt: skip
    return cx.move_in_ym, rows


def _adopted(db: Session, region: Region) -> tuple[RawDTO, RawDTO, str]:
    """같은 rank 1차·1차 상충(청약홈 2028-03 vs 공고문 2028-09) → 채택 보류 → compare same_fact → 채택·병기."""
    api, pdf = _raw(db, region, "applyhome_detail"), _raw(db, region, "notice_pdf")
    store_raw_document(db, api, parser=_Parser({"name": "테스트 단지", "move_in_ym": "2028-03"}))
    store_raw_document(db, pdf, parser=_Parser({"move_in_ym": "2028-09"}))
    value, rows = _state(db)
    held = next(r for r in rows if r[5])
    assert value is None and (held[4] or "").startswith(CONFLICT_HOLD), ("채택 보류여야 한다", value, rows)
    group = held[6]
    assert group is not None
    res = apply_compare(db, group, relation="same_fact", judgment_seq=None)
    assert res.chosen_id is not None
    value, rows = _state(db)
    assert value == "2028-09", rows
    assert any((r[4] or "").startswith(COMPARE_ADOPTED) for r in rows)
    assert any((r[4] or "").startswith(COMPARE_SIDE) for r in rows)
    return api, pdf, group


@pytest.mark.parametrize("which", ["side", "adopted"])  # 다시 정규화하는 원문: 병기(청약홈)·채택(공고문)
def test_renormalize_keeps_compare_marks_and_value(db_session: Session, region: Region, which: str) -> None:
    """compare 로 푼 같은 rank 상충 → 같은 원문 재정규화: 값 '2028-09' 그대로, 표식·출처 행 그대로, change_event 0."""
    api, pdf, _group = _adopted(db_session, region)
    before = _state(db_session)
    ev0 = db_session.scalar(select(func.count()).select_from(ChangeEvent))
    if which.startswith("side"):
        store_raw_document(db_session, api, parser=_Parser({"name": "테스트 단지", "move_in_ym": "2028-03"}))
    else:
        store_raw_document(db_session, pdf, parser=_Parser({"move_in_ym": "2028-09"}))
    after = _state(db_session)
    lost = [a for a, b in zip(before[1], after[1], strict=False) if a != b]
    assert after == before, (
        f"재정규화가 compare 표식을 지웠다(N14): 값 {before[0]} → {after[0]}, 바뀐 출처 행 {lost}"
    )
    events = list(db_session.scalars(select(ChangeEvent).offset(ev0)))
    assert events == [], [(e.entity, e.field, e.old_text, e.new_text, e.severity) for e in events]


def test_changed_value_on_renormalize_is_a_new_conflict_not_silent(
    db_session: Session, region: Region
) -> None:
    """같은 원문 자리의 값이 바뀌면 표식을 옮기지 않는다 — 다시 채택 보류(compare 필요) + 값 변경 이벤트(조용한 변경 아님)."""
    api, _pdf, _group = _adopted(db_session, region)
    ev0 = db_session.scalar(select(func.count()).select_from(ChangeEvent))
    store_raw_document(db_session, api, parser=_Parser({"name": "테스트 단지", "move_in_ym": "2028-06"}))
    value, rows = _state(db_session)
    api_rows = [r for r in rows if r[1] == api.id and r[2] == "2028-06"]
    assert api_rows and not any((r[4] or "").startswith((COMPARE_ADOPTED, COMPARE_SIDE)) for r in api_rows)
    assert value is None and any((r[4] or "").startswith(CONFLICT_HOLD) for r in rows if r[5]), rows
    events = list(db_session.scalars(select(ChangeEvent).offset(ev0)))
    assert any(e.field == "move_in_ym" for e in events), "값이 바뀌면 이벤트"

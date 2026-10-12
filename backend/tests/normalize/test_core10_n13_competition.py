"""R4 4차 재시험 N13(critical, D23-2) — 경쟁률 행은 원문·회차·원 면적 코드로 식별한다(그 시점의 타입 매칭 결과로 찾지 않음).

R4 4차 2회차 (b): 같은 날 ``collect.daily`` 가 이미 받은 경쟁률 원문을 다시 정규화하면서 **경쟁률 행 70개를 중복으로 새로 만들었다**
(단지 11개, 바뀐 원문 없음) → 발행 리비전 5 에 '확인됨' Fact 140개가 change_event 없이 생김. 원인: ``store._Binder.competition_type``
이 경쟁률 면적 코드를 **그 시점에 있는** 단지 주택형과 대조해 행 키(type_code)를 바꿨다 — bootstrap 에서는 주택형(Mdl)이 '84.9939'
로 있어 원 코드 그대로, 공고문이 주택형을 '84' 로 바꾼 뒤의 재정규화는 '84'(또는 '확인 불가(타입 모호)')로 키가 달라 새 행.

D23-2: 행 식별 = (단지, 구분, 회차, 원 면적 코드) — 저장 순서와 무관. 주택형 대조는 읽기 시점 표시 속성
(``normalize.competition.display_type_codes`` — API·보고서).

녹화: ``r4d_core10.zip``(R4 4차 원문) — R4 4차 (b) 가 중복을 만든 단지 중 자기 번호 공고문이 있는 5곳: 28 풍무역세권 수자인
그라센트 2차(2026000073, '84.9939' → '84' 8행) · 25 한강 푸르지오 리버프론트(2026000367, '122.7490' → '122' 4행 — R4 3차 녹화 재생에서도
같은 중복) · 31 김포북변 칸타빌 디 에디션(2025000573, 32행) · 32 풍무역세권 수자인 그라센트 1차(2025000555, 4행) · 70 연수 서해그랑블 5단지
(잔여 공고 자기 번호 2025940263, '53.5854' → '확인 불가(타입 모호)' 1행).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ChangeEvent, Competition, Complex, ComplexType, FieldProvenance, Region
from app.normalize.store import store_raw_document

from . import _r4d

# R4 4차 (b) 가 중복을 만든 단지(주택관리번호 → 중복 행 수)
N13 = {"2026000073": 8, "2026000367": 4, "2025000573": 32, "2025000555": 4, "2025940263": 1}


@pytest.fixture(autouse=True)
def _raw(raw_dir: Path) -> None:
    _r4d.install(raw_dir)


def _docs(house: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """그 단지의 (청약홈 경쟁률 아닌 원문, 경쟁률 원문, 공고문) — 수집 순서."""
    rows = [r for r in _r4d.all_rows() if _r4d.house_no(str(r["url"])) == house]
    comp = [r for r in rows if "Cmpet" in r["url"] or "Competition" in r["url"]]
    pdf = [r for r in rows if r["source_kind"] == "notice_pdf"]
    other = [r for r in rows if r not in comp and r not in pdf]
    assert comp and pdf and other, house
    return other, comp, pdf


def _store(db: Session, region: Region, rows: list[dict[str, Any]]) -> None:
    for d in _r4d.insert(db, rows, region_id=region.id):
        store_raw_document(db, d)


def _competition(db: Session, house: str) -> list[tuple[Any, ...]]:
    cx = db.scalars(select(Complex).where(Complex.applyhome_id == house)).one()
    return [
        (c.id, c.kind, c.round, c.type_code, c.supply, c.applied, c.ratio_or_shortfall_text)
        for c in db.scalars(
            select(Competition).where(Competition.complex_id == cx.id).order_by(Competition.id)
        )
    ]


def _prov(db: Session) -> list[tuple[Any, ...]]:
    return [
        (f.id, f.entity, f.entity_id, f.field, f.value_text, f.raw_document_id, f.label, f.reason, f.chosen)
        for f in db.scalars(select(FieldProvenance).order_by(FieldProvenance.id))
    ]


@pytest.mark.parametrize("house", sorted(N13))
def test_same_competition_raw_renormalized_after_types_changed_makes_no_new_rows(
    db_session: Session, region: Region, house: str
) -> None:
    """R4 4차 순서(청약홈 상세·주택형·경쟁률 → 공고문 — 주택형 코드가 바뀜) → 같은 경쟁률 원문 재정규화: 행·출처·이벤트 그대로."""
    other, comp, pdf = _docs(house)
    _store(db_session, region, [*other, *comp])
    _store(db_session, region, pdf)
    before, prov0 = _competition(db_session, house), _prov(db_session)
    ev0 = db_session.scalar(select(func.count()).select_from(ChangeEvent))
    _store(db_session, region, comp)  # 같은 날 collect.daily (b) — 바뀐 원문 없음
    after = _competition(db_session, house)
    new = [r for r in after if r not in before]
    assert not new, (
        f"재정규화가 경쟁률 행 {len(new)}개를 새로 만들었다(N13, R4 4차 {N13[house]}행): {new[:4]} — 기존 {before[:2]}"
    )
    assert after == before
    assert _prov(db_session) == prov0
    assert db_session.scalar(select(func.count()).select_from(ChangeEvent)) == ev0


@pytest.mark.parametrize("house", sorted(N13))
def test_competition_rows_do_not_depend_on_store_order(
    db_session: Session, region: Region, house: str
) -> None:
    """경쟁률 원문을 주택형 변경 전에 저장하든 뒤에 저장하든 같은 행(원 면적 코드) — D21-3·D22-3 '순서 무관'."""
    other, comp, pdf = _docs(house)
    with db_session.begin_nested() as sp:
        _store(db_session, region, [*other, *comp, *pdf])
        first = sorted(r[1:] for r in _competition(db_session, house))
        sp.rollback()
    with db_session.begin_nested() as sp:
        _store(db_session, region, [*other, *pdf, *comp])
        second = sorted(r[1:] for r in _competition(db_session, house))
        sp.rollback()
    assert first == second, f"저장 순서에 따라 경쟁률 행 키가 다르다: {sorted(set(first) ^ set(second))[:4]}"


def test_display_type_matches_types_at_read_time(db_session: Session, region: Region) -> None:
    """표시 주택형(API·보고서)은 지금 단지 주택형과 대조한 값 — 단지 28 은 '84'·'105'(원 코드 '84.9939'·'105.2083' 저장)."""
    from app.normalize.competition import (
        display_type_codes,  # D23-2 새 모듈(수정 전에는 없다 — 이 테스트만 실패)
    )

    other, comp, pdf = _docs("2026000073")
    _store(db_session, region, [*other, *comp, *pdf])
    cx = db_session.scalars(select(Complex).where(Complex.applyhome_id == "2026000073")).one()
    types = list(db_session.scalars(select(ComplexType).where(ComplexType.complex_id == cx.id)))
    rows = list(db_session.scalars(select(Competition).where(Competition.complex_id == cx.id)))
    assert {r.type_code for r in rows} == {"84.9939", "105.2083"}, "저장 = 원 면적 코드"
    shown = display_type_codes(types, rows)
    assert {shown[r.id] for r in rows} == {"84", "105"}
    assert {(r.type_code, shown[r.id]) for r in rows} == {("84.9939", "84"), ("105.2083", "105")}


class _T:
    def __init__(self, code: str, area: float | None, notice: str | None = None) -> None:
        self.type_code, self.area_m2, self.notice_type_code = code, area, notice


class _C:
    def __init__(self, i: int, code: str, rnd: str = "1순위 해당지역") -> None:
        self.id, self.kind, self.round, self.type_code = i, "본청약", rnd, code


def test_display_rules_ambiguous_and_collisions_are_deterministic() -> None:
    """옛 저장 규칙과 같다: 하나면 그 타입, 없으면 원 코드, 여럿이면 '타입 모호'. 같은 회차에서 겹치면 원 코드 순 첫 행만."""
    from app.normalize.competition import TYPE_AMBIGUOUS, display_type_codes, match_type_code

    types = [_T("84A", 84.75, "084.7529A"), _T("84B", 84.75, "084.7529B"), _T("84C", 84.96, "084.9582C")]
    assert match_type_code("84.9582", types) == "84C"
    assert match_type_code("84.7529", types) == TYPE_AMBIGUOUS
    assert match_type_code("59.9999", types) == "59.9999"
    assert match_type_code("84A", types) == "84A"
    rows = [_C(1, "84.9582"), _C(2, "84.7529"), _C(3, "84.7530"), _C(4, "84C", "2순위 해당지역")]
    want = {1: "84C", 2: TYPE_AMBIGUOUS, 3: "84.7530", 4: "84C"}
    assert display_type_codes(types, rows) == want
    assert display_type_codes(types, list(reversed(rows))) == want, "입력 순서와 무관"
    # 같은 회차에 원 코드 '84C'(웹) 행이 이미 있으면 면적 코드 행은 원 코드로(합쳐 보이지 않게)
    both = [_C(1, "84.9582"), _C(5, "84C")]
    assert display_type_codes(types, both) == {1: "84.9582", 5: "84C"}

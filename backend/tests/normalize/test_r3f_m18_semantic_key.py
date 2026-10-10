"""R3f CORE4 — 6차 리뷰 minor 18: ``facts_view.semantic_rows``(강등, D12-2)와 ``semantic_group``(사람 확인, D13-2)이
의미 키 규칙(같은 (단지, 의미 필드) 행 묶음)을 따로 갖고 있었다 — 한 함수(``facts_view._semantic_rows_of``)로 합친다.
``normalize.store.semantic_humans`` 는 ``semantic_group`` 을 부르므로 같은 함수를 지난다.

| 리뷰 | 테스트 |
| --- | --- |
| m18 두 호출부가 같은 함수를 지난다 | ``test_m18_both_call_sites_use_one_rule`` |
| m18 두 호출부의 묶음이 같다(가격·납부 조건·타입·단지 필드) | ``test_m18_groups_identical`` |
"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.models import Complex, ComplexType, FactDemotion, PaymentTerms


def _seed(db_session: Session, region: Any) -> tuple[Complex, list[ComplexType], list[PaymentTerms]]:
    cx = Complex(region_id=region.id, applyhome_id="2026888001", name="의미 키 단지", former_names=[], apply_dates=[],
                 contract_dates=[], inclusion_class="미분류")  # fmt: skip
    db_session.add(cx)
    db_session.flush()
    types = [ComplexType(complex_id=cx.id, type_code=c) for c in ("84A", "84B", "59")]
    terms = [PaymentTerms(complex_id=cx.id, notice_no=n, effective_from=d, interim_schedule=[])
             for n, d in (("2026888001", "2026-01-01"), ("2026910001", "2026-06-01"))]  # fmt: skip
    db_session.add_all([*types, *terms])
    db_session.flush()
    return cx, types, terms


def _cases(cx: Complex, types: list[ComplexType], terms: list[PaymentTerms]) -> list[tuple[str, int, str]]:
    return [
        ("complex", cx.id, "move_in_ym"),
        ("complex_type", types[0].id, "max_price_won"),
        ("complex_type", types[1].id, "max_price_won"),
        ("complex_type", types[0].id, "units"),
        ("payment_terms", terms[0].id, "price_by_type.84A.max_price_won"),
        ("payment_terms", terms[1].id, "price_by_type.84B.floor_sample_price_won"),
        ("payment_terms", terms[1].id, "down_payment_pct"),
    ]


def test_m18_groups_identical(db_session: Session, region: Any) -> None:
    from app.facts_view import _load_rows, semantic_group, semantic_rows

    cx, types, terms = _seed(db_session, region)
    rows = _load_rows(db_session, {cx.id})
    for entity, eid, fname in _cases(cx, types, terms):
        d = FactDemotion(entity=entity, entity_id=eid, field=fname, complex_id=cx.id)
        cid, group = semantic_group(db_session, entity, eid, fname)
        assert cid == cx.id
        assert semantic_rows(d, rows) == group, (entity, fname)
    # 가격 묶음 = 그 타입 코드의 타입 행 + 모든 공고의 price_by_type.<타입>.max_price_won
    _cid, price = semantic_group(db_session, "complex_type", types[0].id, "max_price_won")
    assert price == [
        ("complex_type", types[0].id, "max_price_won"),
        ("payment_terms", terms[0].id, "price_by_type.84A.max_price_won"),
        ("payment_terms", terms[1].id, "price_by_type.84A.max_price_won"),
    ]  # fmt: skip


def test_m18_both_call_sites_use_one_rule(
    db_session: Session, region: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.facts_view as fv

    cx, _types, terms = _seed(db_session, region)
    calls: list[tuple[str, int, str]] = []
    real = fv._semantic_rows_of

    def spy(entity: str, entity_id: int, field_name: str, *a: Any, **kw: Any) -> Any:
        calls.append((entity, entity_id, field_name))
        return real(entity, entity_id, field_name, *a, **kw)

    monkeypatch.setattr(fv, "_semantic_rows_of", spy)
    me = ("payment_terms", terms[0].id, "down_payment_pct")
    fv.semantic_group(db_session, *me)
    fv.semantic_rows(FactDemotion(entity=me[0], entity_id=me[1], field=me[2], complex_id=cx.id),
                     fv._load_rows(db_session, {cx.id}))  # fmt: skip
    assert calls == [me, me]

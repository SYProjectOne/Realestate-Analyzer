"""계약 .8 D11-6: 단지 상세 납부 조건 ``PaymentTerms.discount_by_type``(타입별 할인 Fact, 없으면 {}).

- 할인이 없으면 모든 납부 조건 행에 ``discount_by_type == {}``.
- 할인이 있으면 타입별 Fact(값·라벨·출처 = 출처 행 'discount_by_type.<type_code>').
  기준 타입 칸은 ``price.discount`` 와 같은 Fact 다(같은 출처 행).
- 라벨 확인됨일 때만 구매가에서 뺀다(``price.composition`` 에 '할인', low 가 할인만큼 작다).
  확인됨이 아니면 표시만(composition 에 '할인' 없음, low 는 할인 없을 때와 같다) —
  ``discount_by_type`` 는 그 라벨을 그대로 싣는다.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.db import get_session
from app.models import ComplexType, FieldProvenance, PaymentTerms

from ._support import WRITE, validate

CX = 1
WON = 10_000_000


def _detail(client: TestClient) -> dict[str, Any]:
    r = client.get(f"/api/complexes/{CX}", headers=WRITE)
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    validate("getComplex", 200, body)
    return body


def _set_discount(label: str | None) -> list[str]:
    """단지 CX 의 모든 납부 조건 × 모든 주택형에 할인 WON 원 + 출처 행(라벨 ``label``). None 이면 지운다."""
    with get_session() as s:
        codes = [t.type_code for t in s.scalars(select(ComplexType).where(ComplexType.complex_id == CX))]
        for pt in s.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == CX)):
            s.execute(
                delete(FieldProvenance).where(
                    FieldProvenance.entity == "payment_terms",
                    FieldProvenance.entity_id == pt.id,
                    FieldProvenance.field.like("discount_by_type.%"),
                )
            )
            pt.discount_by_type = {c: WON for c in codes} if label else {}
            for c in codes if label else []:
                s.add(
                    FieldProvenance(
                        entity="payment_terms", entity_id=pt.id, field=f"discount_by_type.{c}",
                        value_text=str(WON), value_norm=str(WON), url="https://www.applyhome.co.kr/notice",
                        checked_at="2026-10-08", label=label, source_rank=1, chosen=True,
                        reason=None if label == "확인됨" else "공고문 할인 문구 해석",
                    )
                )  # fmt: skip
    return codes


def test_no_discount_is_empty_object(client: TestClient) -> None:
    body = _detail(client)
    assert body["payment"], "devseed 단지 1 에 납부 조건이 있다"
    for p in body["payment"]:
        assert p["discount_by_type"] == {}
    assert body["price"]["discount"] is None


def test_confirmed_discount_by_type_matches_price_discount_and_is_subtracted(client: TestClient) -> None:
    base_low = _detail(client)["price"]["price_low"]["v"]
    codes = _set_discount("확인됨")
    body = _detail(client)
    cur = next(p for p in body["payment"] if p["is_current"])
    assert sorted(cur["discount_by_type"]) == sorted(codes)
    for f in cur["discount_by_type"].values():
        assert f["v"] == WON and f["label"] == "확인됨" and f["unit"] == "won"
        assert str(f["prov"]).startswith("fp_")
    price = body["price"]
    basis = price["basis_type_code"]
    assert cur["discount_by_type"][basis] == price["discount"]  # 같은 출처 행 · 같은 라벨
    assert "할인" in (price["composition"] or "")
    assert price["price_low"]["v"] == base_low - WON


def test_unconfirmed_discount_is_shown_with_label_but_not_subtracted(client: TestClient) -> None:
    base_low = _detail(client)["price"]["price_low"]["v"]
    _set_discount("추정")
    body = _detail(client)
    cur = next(p for p in body["payment"] if p["is_current"])
    assert cur["discount_by_type"], "확인됨이 아니어도 표시한다"
    for f in cur["discount_by_type"].values():
        assert f["v"] == WON and f["label"] == "추정"
    price = body["price"]
    assert price["discount"]["label"] == "추정"
    assert cur["discount_by_type"][price["basis_type_code"]] == price["discount"]
    assert "할인" not in (price["composition"] or "")
    assert price["price_low"]["v"] == base_low

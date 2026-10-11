"""R3i CORE7 — 9차 리뷰 major 4 · m2 · m4 / **D17-4**(사람 확인 의미 단위 유지 — 값 없는 새 공고) (재현: scratchpad ``r9/a``).

| 리뷰 | 테스트 |
| --- | --- |
| major 4 사람 확인 할인 뒤 할인 줄 없는 새 공고(무순위·정정)가 현재 공고가 되면 차감이 조용히 사라짐 | ``test_major4_new_notice_without_discount_keeps_human_discount`` |
| D17-4 같은 규칙 — 계약금(값 없는 새 공고) | ``test_d17_4_new_notice_without_down_payment_keeps_human_value`` |
| D17-4 새 공고가 같은 값(추정) → 사람 확인 그대로 / 다른 값 → D12-1 채택 + critical + 재검토(가드) | ``test_d17_4_new_notice_same_value_keeps``·``test_d17_4_new_notice_other_value_supersedes`` |
| m4 옛 공고 entity_id 사람 확인 201 무효 → 현재 공고에도 적용 | ``test_m4_human_discount_on_old_notice_applies_to_current`` |
| m4 기준 타입이 바뀌면 옛 기준 타입 할인은 차감하지 않는다(표시만 — 가드) | ``test_m4_basis_type_change_does_not_carry_discount`` |
| D17-4 사람 확인 응답 기준 타입 표시 필드 | ``test_d17_4_human_check_response_has_basis_type`` |
| m2 할인 값 형식 엄격(쉼표 자리·공백·전각·아랍 숫자·'-0') → 422 ``discount_format`` | ``test_m2_discount_format_rejected``·``test_m2_discount_format_accepted`` |
| m2 할인 ≥ 가격(차감 바탕) → 422 ``discount_not_below_price`` | ``test_m2_discount_not_below_price`` |
| m2 다른 칸도 틀리면 validation_error + 모든 칸 | ``test_m2_discount_and_other_field_errors`` |
"""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.contracts_gen import FieldCandidate
from app.core.db import get_session
from app.models import ChecklistItem, Complex, ComplexType, PaymentTerms, RawDocument

from ._support import READ, WRITE, as_live

CX = 1


def _detail(client: TestClient) -> dict[str, Any]:
    r = client.get(f"/api/complexes/{CX}", headers=READ)
    assert r.status_code == 200, r.text
    return dict(r.json())


def _human(client: TestClient, field: str, value: str, *, day: str = "2026-10-09", entity_id: int | None = None, **extra: Any) -> Any:
    body: dict[str, Any] = {"complex_id": CX, "field": field, "value_text": value, "kind": "phone",
                            "checked_at": f"{day}T10:00:00+09:00", "entered_by": "운영자", "note": "R3i", **extra}  # fmt: skip
    if entity_id is not None:
        body["entity_id"] = entity_id
    return client.post("/api/ops/human-checks", headers=WRITE, json=body)


class _Notice:
    def __init__(self, key: str, notice_no: str, values: dict[str, Any], labels: dict[str, str], observed_on: str) -> None:
        self.key, self.notice_no, self.values, self.labels, self.observed_on = key, notice_no, values, labels, observed_on

    def parse(self, raw: Any) -> list[FieldCandidate]:
        tk = f"{self.key}:{self.notice_no}"
        return [
            FieldCandidate(
                entity="payment_terms", entity_id=None, entity_key=tk, field=f, value_text=str(v), value=v,
                source_rank=1, source_kind="notice_pdf", primary=True, label=self.labels.get(f, "확인됨"),
                reason="공고문 자동 추출 — 조건 확인 필요" if f.startswith("discount_by_type") else None,
                excerpt=f"{f} {v}", excerpt_start=0, excerpt_end=1, raw_document_id=raw.id, url=raw.url,
                checked_at=self.observed_on, observed_on=self.observed_on,
            )
            for f, v in self.values.items()
        ]  # fmt: skip


def _store_notice(notice_no: str, values: dict[str, Any], labels: dict[str, str] | None = None, observed_on: str = "2026-10-10") -> None:
    """리뷰 재현 r9/a store_notice: 같은 단지의 새 공고(무순위·정정) 원문 1건을 정규화 저장."""
    from app.normalize.store import store_raw_document

    with get_session() as s:
        cx = s.get(Complex, CX)
        assert cx is not None
        raw = RawDocument(
            source_kind="notice_pdf", url=f"https://www.applyhome.co.kr/notice/{notice_no}",
            fetched_at=f"{observed_on}T09:00:00+09:00", http_status=200,
            sha256=hashlib.sha256(f"{notice_no}{values}".encode()).hexdigest(), region_id=cx.region_id, complex_id=cx.id,
        )  # fmt: skip
        s.add(raw)
        s.flush()
        store_raw_document(s, raw, parser=_Notice(str(cx.applyhome_id), notice_no, values, labels or {}, observed_on))


def _basis() -> tuple[str, int, int]:
    """(기준 타입 코드, 최고가, 차감 바탕 = min(대표층가, 최고가))."""
    from app.analysis.price_view import current_price

    with get_session() as s:
        types = list(s.scalars(select(ComplexType).where(ComplexType.complex_id == CX)))
        terms = list(s.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == CX)))
        v = current_price(types, terms, discount_label=None)
        assert v.basis_type_code is not None and v.max_ref is not None
        top = int(v.max_ref.value)
        floor = int(v.floor_ref.value) if v.floor_ref is not None and v.floor_ref.value is not None else top
        return v.basis_type_code, top, min(top, floor)


def _current(d: dict[str, Any]) -> dict[str, Any]:
    cur = next((x for x in d["payment"] if x["is_current"]), None)
    assert cur is not None
    return dict(cur)


# ====================================================================== major 4 / D17-4


def test_major4_new_notice_without_discount_keeps_human_discount(client: TestClient) -> None:
    as_live()
    code, top, _ = _basis()
    r = _human(client, "discount", "10,000,000")
    assert r.status_code == 201, r.text
    before = _detail(client)["price"]
    assert before["discount_applied"] is True and before["discount"]["v"] == 10_000_000
    _store_notice("2026990101", {"effective_from": "2026-10-10", "notice_kind": "무순위", f"price_by_type.{code}.max_price_won": top, "down_payment_pct": 10.0})
    d = _detail(client)
    cur = _current(d)
    assert cur["notice_no"] == "2026990101"
    p = d["price"]
    assert p["discount"] is not None and p["discount"]["v"] == 10_000_000 and p["discount"]["label"] == "확인됨", p["discount"]
    assert p["discount_applied"] is True and p["price_high"]["v"] == top - 10_000_000, p
    assert cur["discount_by_type"][code]["v"] == 10_000_000 and cur["discount_by_type"][code]["label"] == "확인됨"


def test_d17_4_new_notice_without_down_payment_keeps_human_value(client: TestClient) -> None:
    as_live()
    code, top, _ = _basis()
    r = _human(client, "down_payment_pct", "15")
    assert r.status_code == 201, r.text
    _store_notice("2026990105", {"effective_from": "2026-10-10", "notice_kind": "무순위", f"price_by_type.{code}.max_price_won": top})
    cur = _current(_detail(client))
    assert cur["notice_no"] == "2026990105"
    assert cur["down_payment_pct"]["v"] == 15 and cur["down_payment_pct"]["label"] == "확인됨", cur["down_payment_pct"]


def test_d17_4_new_notice_same_value_keeps(client: TestClient) -> None:
    as_live()
    code, top, _ = _basis()
    assert _human(client, "discount", "10,000,000").status_code == 201
    _store_notice("2026990102", {"effective_from": "2026-10-10", "notice_kind": "무순위", f"price_by_type.{code}.max_price_won": top, f"discount_by_type.{code}": 10_000_000}, labels={f"discount_by_type.{code}": "추정"})
    p = _detail(client)["price"]
    assert p["discount"]["label"] == "확인됨" and p["discount_applied"] is True, p["discount"]


def test_d17_4_new_notice_other_value_supersedes(client: TestClient) -> None:
    """새 공고가 **다른 값**을 내면 D12-1(채택 + critical + '사람 확인 재검토') — 값 없음과 다르다."""
    as_live()
    code, top, _ = _basis()
    assert _human(client, "discount", "10,000,000").status_code == 201
    _store_notice("2026990103", {"effective_from": "2026-10-10", "notice_kind": "무순위", f"price_by_type.{code}.max_price_won": top, f"discount_by_type.{code}": 20_000_000}, labels={f"discount_by_type.{code}": "추정"})
    p = _detail(client)["price"]
    assert p["discount"]["v"] == 20_000_000 and p["discount_applied"] is False, p["discount"]
    with get_session() as s:
        items = [i.title for i in s.scalars(select(ChecklistItem).where(ChecklistItem.complex_id == CX, ChecklistItem.status == "open"))]
    assert any("사람 확인 재검토" in t and "할인" in t for t in items), items


def test_m4_human_discount_on_old_notice_applies_to_current(client: TestClient) -> None:
    """옛 공고 행을 entity_id 로 지정한 사람 확인 할인 — 예전엔 201 이지만 현재 공고(값 없음)에 퍼지지 않아 차감 없음."""
    as_live()
    code, top, _ = _basis()
    with get_session() as s:
        old = int(min(s.scalars(select(PaymentTerms.id).where(PaymentTerms.complex_id == CX))))
    _store_notice("2026990106", {"effective_from": "2026-10-10", "notice_kind": "무순위", f"price_by_type.{code}.max_price_won": top})
    r = _human(client, "discount", "10,000,000", day="2026-10-11", entity_id=old)
    assert r.status_code == 201, r.text
    p = _detail(client)["price"]
    assert p["discount_applied"] is True and p["discount"]["v"] == 10_000_000, p["discount"]


def test_m4_basis_type_change_does_not_carry_discount(client: TestClient) -> None:
    """사람 확인 할인은 그 기준 타입 칸이다(D17-4). 84㎡에 더 가까운 타입이 생겨 기준 타입이 바뀌면 옛 칸 할인은 차감하지 않는다
    (그 타입 칸에 '확인됨'으로 표시만)."""
    as_live()
    code, _top, _ = _basis()
    assert _human(client, "discount", "10,000,000").status_code == 201
    with get_session() as s:
        other = next(t for t in s.scalars(select(ComplexType).where(ComplexType.complex_id == CX)) if t.type_code != code)
        other.area_m2 = 84  # 84㎡에 더 가까운 타입 → 기준 타입이 바뀐다
        new_code = other.type_code
    d = _detail(client)
    assert d["price"]["basis_type_code"] == new_code
    assert d["price"]["discount_applied"] is False
    assert _current(d)["discount_by_type"][code]["label"] == "확인됨"


def test_d17_4_human_check_response_has_basis_type(client: TestClient) -> None:
    as_live()
    code, _top, _ = _basis()
    r = _human(client, "discount", "1,000,000")
    assert r.status_code == 201 and r.json()["basis_type_code"] == code, r.text
    r2 = _human(client, "move_in_ym", "2029-01")
    assert r2.status_code == 201 and r2.json()["basis_type_code"] is None, r2.text


# ====================================================================== m2


@pytest.mark.parametrize(
    "value",
    ["１０,０００,０００", "-0", " 1 0 0 0 ", "1,0", ",,5,,", "٣٣٣", "10,000,000원원", "+5", "1억", "5,000만원", "1e9", "1,0000", "10,00,000", "10,000,000 원", "100000000001"],
)
def test_m2_discount_format_rejected(client: TestClient, value: str) -> None:
    as_live()
    r = _human(client, "discount", value)
    assert r.status_code == 422, (value, r.text)
    body = r.json()
    assert body["code"] == "discount_format", body
    assert body["field_errors"] == [{"loc": ["body", "value_text"], "msg": body["detail"]}], body


@pytest.mark.parametrize(("value", "won"), [("10,000,000", 10_000_000), ("10000000", 10_000_000), ("10,000,000원", 10_000_000), ("0", 0), (" 1,000 ", 1000)])
def test_m2_discount_format_accepted(client: TestClient, value: str, won: int) -> None:
    as_live()
    code, _top, _ = _basis()
    r = _human(client, "discount", value)
    assert r.status_code == 201, (value, r.text)
    with get_session() as s:
        pt = s.get(PaymentTerms, r.json()["entity_id"])
        assert pt is not None and (pt.discount_by_type or {}).get(code) == won


def test_m2_discount_not_below_price(client: TestClient) -> None:
    as_live()
    _code, top, base_low = _basis()
    for v in (base_low, top, top + 1):
        r = _human(client, "discount", str(v))
        assert r.status_code == 422 and r.json()["code"] == "discount_not_below_price", (v, r.text)
        assert r.json()["field_errors"][0]["loc"] == ["body", "value_text"]
    ok = _human(client, "discount", str(base_low - 1))
    assert ok.status_code == 201, ok.text
    assert _detail(client)["price"]["discount_applied"] is True


def test_m2_discount_and_other_field_errors(client: TestClient) -> None:
    as_live()
    r = _human(client, "discount", "1,0", kind="zzz")
    assert r.status_code == 422 and r.json()["code"] == "validation_error", r.text
    locs = [e["loc"] for e in r.json()["field_errors"]]
    assert ["body", "kind"] in locs and ["body", "value_text"] in locs, locs

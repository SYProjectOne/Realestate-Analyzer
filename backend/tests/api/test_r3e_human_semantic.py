"""R3e CORE3 — D13-2 사람 확인 = (단지, 의미 필드) 단위 (계약 2026-10-09.10, R3 5차 리뷰 K1).

사람 확인은 강등과 같은 의미 키(D12-2)에 걸린다: 가격 = 그 타입의 공고문 타입 행 + 그 단지 모든 공고의
``price_by_type.<타입>.max_price_won``, 납부 조건 필드 = 그 단지 모든 공고의 같은 필드, 단지 필드 = 단지 행.

| 리뷰 재현 | 테스트 |
| --- | --- |
| K1 무순위 새 공고 X(사람 확인 이전 관측) | ``test_k1_new_notice_row_*[before]`` — 사람 확인 값 유지(화면·목록·점수) |
| K1 무순위 새 공고 X(사람 확인 이후 관측) | ``test_k1_new_notice_row_*[after]`` — 새 값 채택 + critical + '사람 확인 재검토' |
| K1 기준 타입 칸 없는 새 공고 | ``test_k1_new_notice_without_basis_type_keeps_human_value`` |
| K1 이른 관측·늦은 시행 | ``test_k1_early_observed_late_effective_notice_loses`` |
| K1 계약금(10% → 20%) | ``test_k1_down_payment_*`` (이전·이후 관측) |
| 사람 확인이 의미 묶음 전부에 | ``test_d13_2_human_value_lands_on_every_valued_row`` |
| minor 이른 사람 확인 | ``test_d13_2_backdated_human_check_is_422_without_writes`` |
"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.db import get_session
from app.models import (
    ChangeEvent,
    ChecklistItem,
    ComplexType,
    FieldProvenance,
    HumanCheck,
    PaymentTerms,
    RawDocument,
)

from ._support import READ, WRITE, as_live
from .test_r3b_g3 import CX, SNAP
from .test_r3d_core2 import _demote_price, _score_price, human_check, store_cx_field, store_notice

X = 700_000_000  # 모순 값(공급가)
Y = 690_000_000  # 사람 확인 값


def _basis() -> ComplexType:
    from app.analysis.price_view import basis_type

    with get_session() as s:
        t = basis_type(list(s.scalars(select(ComplexType).where(ComplexType.complex_id == CX))))
        assert t is not None
        s.expunge(t)
        return t


def _set_type_row_price(won: int) -> str:
    """공고문 타입 행(기준 타입)에 값 + chosen 원문 출처 행(실제 공고문 정규화와 같은 모양)."""
    t = _basis()
    with get_session() as s:
        raw = s.scalars(select(RawDocument).order_by(RawDocument.id)).first()
        assert raw is not None
        for fp in s.scalars(select(FieldProvenance).where(FieldProvenance.entity == "complex_type",
                                                          FieldProvenance.entity_id == t.id,
                                                          FieldProvenance.field == "max_price_won")):  # fmt: skip
            fp.chosen = False
        row = s.get(ComplexType, t.id)
        assert row is not None
        row.max_price_won = won
        s.add(FieldProvenance(entity="complex_type", entity_id=t.id, field="max_price_won", value_text=f"{won:,}",
                              value_norm=str(won), raw_document_id=raw.id, url=raw.url, checked_at="2026-08-01",
                              observed_on="2026-08-01", label="확인됨", source_rank=1, chosen=True,
                              excerpt=f"공급금액 {won:,}"))  # fmt: skip
    return t.type_code


def _high(client: TestClient) -> tuple[Any, str]:
    """상세 구매가 상한(발코니·옵션 뺀 공급가)·라벨."""
    d = client.get(f"/api/complexes/{CX}", params={"snapshot": SNAP}, headers=READ).json()
    hi = d["price"]["price_high"]
    t = _basis()
    extras = (t.balcony_won or 0) + (t.options_required_won or 0)
    return (hi["v"] - extras if hi["v"] is not None else None), hi["label"]


def _review_items() -> list[str]:
    with get_session() as s:
        return [
            i.title
            for i in s.scalars(select(ChecklistItem).where(ChecklistItem.complex_id == CX))
            if i.title.startswith("사람 확인 재검토") and i.status == "open"
        ]


@pytest.mark.parametrize("when", ["before", "after"])
def test_k1_new_notice_row_with_contradicted_price(client: TestClient, when: str) -> None:
    as_live()
    code = _set_type_row_price(X)
    _demote_price(client, X)
    human_check(client, "max_price_won", str(Y), day="2026-10-09")
    assert _high(client)[0] == Y
    observed = "2026-10-05" if when == "before" else "2026-10-12"
    store_notice(CX, "2026990009", {"effective_from": "2026-10-10", "notice_kind": "무순위",
                                    f"price_by_type.{code}.max_price_won": X}, observed_on=observed)  # fmt: skip
    value, label = _high(client)
    items = client.get(f"/api/snapshots/{SNAP}/complexes", params={"size": 200}, headers=READ).json()["items"]
    row = next(i for i in items if i["complex_id"] == CX)
    if when == "before":
        # 사람 확인 이전에 관측된 출처는 행과 무관하게 사람 확인 값에 진다(D13-2)
        assert value == Y, (value, label)
        assert row["price_high"]["v"] is not None and row["price_high"]["label"] != "확인 불가"
        assert _score_price(CX)[0] is not None and _score_price(CX)[1] != "확인 불가"
        assert not _review_items()
    else:
        # 이후 관측된 공식 1차 출처의 다른 값 → 채택 + critical + '사람 확인 재검토'(행과 무관 — D12-1·D13-2)
        assert value == X, (value, label)
        assert _review_items() == ["사람 확인 재검토: 기준 타입 최고 공급금액"]
        with get_session() as s:
            crit = [e for e in s.scalars(select(ChangeEvent).where(ChangeEvent.complex_id == CX))
                    if e.severity == "critical" and e.triggers_rejudge and str(X) in (e.new_text or "").replace(",", "")]  # fmt: skip
            assert crit, "critical change_event"


def test_k1_new_notice_without_basis_type_keeps_human_value(client: TestClient) -> None:
    as_live()
    code = _set_type_row_price(X)
    _demote_price(client, X)
    human_check(client, "max_price_won", str(Y), day="2026-10-09")
    assert code != "59Z"
    # 무순위 공고가 다른 타입만 — 기준 타입 칸이 없어 현재 구매가가 원 공고문 타입 행으로 돌아간다(그 행도 사람 확인 값)
    store_notice(CX, "2026990010", {"effective_from": "2026-10-10", "notice_kind": "무순위",
                                    "price_by_type.59Z.max_price_won": 420_000_000}, observed_on="2026-10-05")  # fmt: skip
    assert _high(client)[0] == Y


def test_k1_early_observed_late_effective_notice_loses(client: TestClient) -> None:
    """사람 확인(10-09)보다 먼저 관측(10-08)됐는데 시행일만 늦은(10-10) 공고 — 사람 확인이 이긴다(668,280,000 재현)."""
    as_live()
    from .test_r3c_core import _price_by_type

    won = 658_140_000
    _pt, code = _price_by_type(CX, won)
    human_check(client, "max_price_won", f"{won - 5_000_000}")
    store_notice(CX, "2026990031", {"effective_from": "2026-10-10", "notice_kind": "무순위",
                                    f"price_by_type.{code}.max_price_won": won + 7_000_000}, observed_on="2026-10-08")  # fmt: skip
    assert _high(client)[0] == won - 5_000_000
    assert not _review_items()


@pytest.mark.parametrize("when", ["before", "after"])
def test_k1_down_payment_cross_row(client: TestClient, when: str) -> None:
    as_live()
    human_check(client, "down_payment_pct", "10%")
    observed = "2026-10-08" if when == "before" else "2026-10-12"
    store_notice(CX, "2026990051", {"effective_from": "2026-10-12", "notice_kind": "무순위", "down_payment_pct": 20.0},
                 observed_on=observed)  # fmt: skip
    d = client.get(f"/api/complexes/{CX}", params={"snapshot": SNAP}, headers=READ).json()
    cur = next(p for p in d["payment"] if p["is_current"])
    assert cur["notice_no"] == "2026990051"
    if when == "before":
        assert cur["down_payment_pct"]["v"] == 10 and cur["down_payment_pct"]["label"] == "확인됨"
        assert not _review_items()
    else:
        assert cur["down_payment_pct"]["v"] == 20
        assert _review_items() == ["사람 확인 재검토: 계약금 비율"]


def test_d13_2_human_value_lands_on_every_valued_row(client: TestClient) -> None:
    """사람 확인은 의미 묶음의 값 있는 행 전부에 0순위 후보로 들어간다(옛 공고 행·공고문 타입 행 — 어느 행을 읽어도 같은 값)."""
    as_live()
    code = _set_type_row_price(X)
    store_notice(CX, "2026990061", {"effective_from": "2026-09-01", "notice_kind": "본청약",
                                    f"price_by_type.{code}.max_price_won": X}, observed_on="2026-09-01")  # fmt: skip
    human_check(client, "max_price_won", str(Y), day="2026-10-09")
    t = _basis()
    with get_session() as s:
        assert s.get(ComplexType, t.id).max_price_won == Y  # type: ignore[union-attr]
        for pt in s.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == CX)):
            cell = (pt.price_by_type or {}).get(code)
            if isinstance(cell, dict) and cell.get("max_price_won") is not None:
                assert cell["max_price_won"] == Y, (pt.id, pt.notice_no, cell)


def test_d13_2_backdated_human_check_is_422_without_writes(client: TestClient) -> None:
    """이미 수집된 공식 공고(관측 10-05)보다 이른 확인일(10-03)의 사람 확인 — 조용히 지지 않고 422(D13-2)."""
    as_live()
    store_cx_field(CX, "move_in_ym", "2028-01", "notice_pdf", "2026-10-05", "bd")
    with get_session() as s:
        n_hc = s.scalar(select(func.count()).select_from(HumanCheck))
        n_ev = s.scalar(select(func.count()).select_from(ChangeEvent))
    r = client.post(
        "/api/ops/human-checks", headers=WRITE,
        json={"complex_id": CX, "field": "move_in_ym", "value_text": "2028-06", "kind": "phone",
              "checked_at": "2026-10-03T10:00:00+09:00", "entered_by": "운영자"},
    )  # fmt: skip
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["field_errors"][0]["loc"] == ["body", "checked_at"] and "2026-10-05" in body["detail"]
    with get_session() as s:
        assert s.scalar(select(func.count()).select_from(HumanCheck)) == n_hc
        assert s.scalar(select(func.count()).select_from(ChangeEvent)) == n_ev
    ok = human_check(client, "move_in_ym", "2028-06", day="2026-10-05")  # 같은 날은 이후가 아니다(받는다)
    assert ok["change_event_id"] is not None

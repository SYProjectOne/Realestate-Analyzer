"""R4 FE10 보고(DECISIONS D22-5, 계약 2026-10-09.17).

- 발행 리비전 저장본의 출처 서랍 수집이 ``name_prov`` 도 모은다 — FE10 e2e(writes12-r4fe10 F1): 발행 리비전에서 이름 출처 서랍
  ``GET /provenance/{name_prov}?snapshot_id=`` 이 404('발행 리비전 … 저장본에 출처 fp_… 없음') — ``snapshot_view._PROV_RE`` 가
  ``"prov":`` 키만 보았다.
- 기준 타입 가격 채택 보류(출처 상충 — compare 대기)일 때 현재 구매가 사유는 '출처 상충 — compare 대기'('분양가 미공개'가 아님).
- 계약 .17: 판정 범위 사유 문자열 ``judge_scope_reason`` 을 단지 목록 행·상세 머리에 낸다(FE 가 서버 ``analysis.scope`` 규칙을
  옮겨 쓰지 않게 — FE10 계약 변경 요청).
"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_session
from app.models import Complex, ComplexType, FieldProvenance, PaymentTerms

from ._support import READ, as_live, publish_revision, validate
from .test_r3b_g3 import SNAP

CANDIDATE = 15  # devseed 트랙 (A) 공고 예정 후보(applyhome_id null)
HELD_COMPLEX = 3
CONFLICT_HOLD = "출처 상충 — compare 대기"


def test_contract_version_is_17() -> None:
    from app.core.protocols import CONTRACT_VERSION

    assert CONTRACT_VERSION == "2026-10-09.17"


def _rows(client: TestClient, snap: int = SNAP) -> list[dict[str, Any]]:
    r = client.get(f"/api/snapshots/{snap}/complexes", params={"size": 200}, headers=READ)
    assert r.status_code == 200, r.text
    validate("listComplexes", 200, r.json())
    items: list[dict[str, Any]] = r.json()["items"]
    return items


def test_published_revision_name_provenance_drawer_is_200(client: TestClient) -> None:
    with get_session() as s:
        cx = s.get(Complex, CANDIDATE)
        assert cx is not None and cx.applyhome_id is None
        fp = FieldProvenance(
            entity="complex", entity_id=CANDIDATE, entity_key=f"upcoming:{CANDIDATE}", field="name",
            value_text=cx.name, value_norm=cx.name, label="비공식", reason="언론(공고 예정, 청약홈 미등록)",
            url="https://news.example.com/core9/upcoming", checked_at="2026-10-12", source_rank=9, chosen=True,
        )  # fmt: skip
        s.add(fp)
        s.flush()
        pid = f"fp_{fp.id}"
    rev = publish_revision(1, "CORE9 이름 출처 서랍")
    row = next(r for r in _rows(client, rev) if r["complex_id"] == CANDIDATE)
    assert (row.get("name_prov"), row.get("name_label")) == (pid, "비공식")
    r = client.get(f"/api/provenance/{pid}", params={"snapshot_id": rev}, headers=READ)
    assert r.status_code == 200, r.text
    assert r.json()["url"] == "https://news.example.com/core9/upcoming"


def test_judge_scope_reason_in_list_row_and_detail_header(client: TestClient) -> None:
    rows = _rows(client)
    assert rows and all(
        isinstance(r.get("judge_scope_reason"), str) and r["judge_scope_reason"] for r in rows
    ), [(r["complex_id"], r.get("judge_scope_reason")) for r in rows if not r.get("judge_scope_reason")]
    for row in rows[:5]:
        d = client.get(f"/api/complexes/{row['complex_id']}", headers=READ)
        assert d.status_code == 200, d.text
        validate("getComplex", 200, d.json())
        assert d.json()["header"].get("judge_scope_reason") == row["judge_scope_reason"], row["complex_id"]


def test_judge_scope_reason_names_boundary_without_dong(client: TestClient) -> None:
    """범위 경계 + 법정동 없음 + 주소에 동 없음 → '범위 경계(주소에 동 없음)'(서버 analysis.scope 와 같은 문자열)."""
    as_live()
    with get_session() as s:
        cx = s.get(Complex, 16)
        assert cx is not None
        cx.inclusion_class, cx.legal_dong_code, cx.address = (
            "범위 경계",
            None,
            "인천광역시 서구 검단신도시 RC3BL",
        )
    row = next(r for r in _rows(client) if r["complex_id"] == 16)
    assert row["judge_scope_reason"] == "범위 경계(주소에 동 없음)"
    # 화면 범위는 점수 실행 저장값(D10-1) — 현재 사실 범위(제외)와 다르면 재판정 필요 표시, 사유는 현재 사실 범위의 것
    assert row["judge_scope"] == "제외" or row.get("rejudge_needed") is True, row
    head = client.get("/api/complexes/16", headers=READ).json()["header"]
    assert head["judge_scope_reason"] == "범위 경계(주소에 동 없음)"


def _hold_basis_price(complex_id: int, basis: str) -> None:
    """기준 타입 가격 채택 보류(resolver 와 같은 모양): chosen 출처 행 reason 앞 '출처 상충 — compare 대기' + 사실 값 비움."""
    with get_session() as s:
        t = s.scalars(
            select(ComplexType).where(ComplexType.complex_id == complex_id, ComplexType.type_code == basis)
        ).one()
        terms = list(s.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == complex_id)))
        for p in terms:  # 현재 공고의 그 타입 칸이 있으면 그 칸도(현재 구매가가 그 칸을 쓴다)
            pbt = dict(p.price_by_type or {})
            if isinstance(pbt.get(basis), dict) and "max_price_won" in pbt[basis]:
                pbt[basis] = {**pbt[basis], "max_price_won": None}
                p.price_by_type = pbt
                for fp in s.scalars(
                    select(FieldProvenance).where(
                        FieldProvenance.entity == "payment_terms", FieldProvenance.entity_id == p.id,
                        FieldProvenance.field == f"price_by_type.{basis}.max_price_won", FieldProvenance.chosen.is_(True),
                    )
                ):  # fmt: skip
                    fp.reason = f"{CONFLICT_HOLD} · {fp.reason or ''}".strip(" ·")
        for fp in s.scalars(
            select(FieldProvenance).where(
                FieldProvenance.entity == "complex_type", FieldProvenance.entity_id == t.id,
                FieldProvenance.field == "max_price_won", FieldProvenance.chosen.is_(True),
            )
        ):  # fmt: skip
            fp.reason = f"{CONFLICT_HOLD} · {fp.reason or ''}".strip(" ·")
        t.max_price_won = None


def test_held_basis_price_reason_is_conflict_hold(client: TestClient) -> None:
    as_live()
    d = client.get(f"/api/complexes/{HELD_COMPLEX}", headers=READ).json()
    basis = d["price"]["basis_type_code"]
    assert basis and d["price"]["price_low"]["v"] is not None
    _hold_basis_price(HELD_COMPLEX, basis)
    held = client.get(f"/api/complexes/{HELD_COMPLEX}", headers=READ)
    assert held.status_code == 200, held.text
    validate("getComplex", 200, held.json())
    price = held.json()["price"]
    for key in ("price_low", "price_high", "price_mid"):
        assert (price[key]["label"], price[key].get("reason")) == ("확인 불가", CONFLICT_HOLD), (
            key,
            price[key],
        )
    row = next(r for r in _rows(client) if r["complex_id"] == HELD_COMPLEX)
    for key in ("price_low", "price_high", "price_mid"):
        assert row[key].get("reason") == CONFLICT_HOLD, (key, row[key])
    # 판정 범위 사유도 같은 까닭(보류 — '분양가 미공개(공고 전)'이 아니다)
    assert row.get("judge_scope_reason") == CONFLICT_HOLD, row.get("judge_scope_reason")
    assert held.json()["header"].get("judge_scope_reason") == CONFLICT_HOLD

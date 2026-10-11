"""R3h CORE6 — **D16-1** 사람 확인 할인(`discount`, D13-2 의미 단위): '확인됨'이 된 할인만 구매가에서 뺀다.

파서 할인은 언제나 '추정'(``tests/normalize/test_r3h_discount.py``). 사람이 분양사무소·공고문을 보고 기준 타입 할인을 확인하면
(``POST /ops/human-checks`` field ``discount``) 그 값이 resolver 0순위 후보(라벨 확인됨, reason '사람 확인(kind)')로 현재 공고
``payment_terms.discount_by_type.<기준 타입>`` 에 들어가고, 가격을 쓰는 **모든 경로**(상세·목록 값·필터·정렬·비교·보고서·점수
입력·발행 저장본)가 같은 값으로 뺀다(D12-3 ``price_view.current_price``).

| 리뷰·결정 | 테스트 |
| --- | --- |
| D16-1 사람 확인 할인 → 전 경로 차감 | ``test_d16_1_human_discount_is_subtracted_on_every_path`` |
| D16-1 파서 '추정' 할인 위에 사람 확인 → 확인됨으로 바뀌어 차감 | ``test_d16_1_human_check_turns_estimate_into_confirmed`` |
| D16-1 사람 확인 할인 = 의미 단위(그 단지 모든 공고의 같은 타입 할인) | ``test_d16_1_human_discount_spreads_to_semantic_rows`` |
| D16-1 발행 저장본도 차감 | ``test_d16_1_human_discount_in_published_revision`` |
| 값 검사(형·범위) | ``test_d16_1_human_discount_value_validation`` |
"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_session
from app.models import FieldProvenance, PaymentTerms, Region, Snapshot

from ._support import READ, WRITE, as_live, run_job, validate

CX = 1
SNAP = 12
WON = 10_000_000


def _detail(client: TestClient, snap: int | None = SNAP) -> dict[str, Any]:
    params = {"snapshot": snap} if snap is not None else {}
    r = client.get(f"/api/complexes/{CX}", params=params, headers=READ)
    assert r.status_code == 200, r.text
    out: dict[str, Any] = r.json()
    return out


def _human_discount(client: TestClient, value: str, *, day: str = "2026-10-09", cx: int = CX) -> Any:
    return client.post(
        "/api/ops/human-checks", headers=WRITE,
        json={"complex_id": cx, "field": "discount", "value_text": value, "kind": "phone",
              "checked_at": f"{day}T10:00:00+09:00", "entered_by": "운영자", "note": "분양사무소 통화: 기준 타입 할인 확인"},
    )  # fmt: skip


def _parser_estimate(won: int) -> None:
    """현재 공고(그 단지 모든 납부 조건)에 파서가 낸 것과 같은 '추정' 할인 출처 행 + 사실(D16-1 — 파서 할인은 언제나 추정)."""
    from app.analysis.price_view import basis_type
    from app.models import ComplexType, RawDocument

    with get_session() as s:
        t = basis_type(list(s.scalars(select(ComplexType).where(ComplexType.complex_id == CX))))
        assert t is not None
        raw = s.scalars(
            select(RawDocument).where(RawDocument.source_kind == "notice_pdf").order_by(RawDocument.id)
        ).first()
        assert raw is not None
        for pt in s.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == CX)):
            pt.discount_by_type = {**(pt.discount_by_type or {}), t.type_code: won}
            s.add(
                FieldProvenance(
                    entity="payment_terms", entity_id=pt.id, field=f"discount_by_type.{t.type_code}",
                    value_text=f"{won:,}", value_norm=str(won), raw_document_id=raw.id, url=raw.url,
                    checked_at="2026-10-08", observed_on="2026-10-01", label="추정",
                    reason="공고문 자동 추출 — 조건 확인 필요", source_rank=1, chosen=True,
                )
            )  # fmt: skip


def test_d16_1_human_discount_is_subtracted_on_every_path(client: TestClient) -> None:
    """사람 확인 할인 → 상세·목록(값·필터·정렬)·비교(계약금)·보고서·점수 입력에서 같은 값으로 뺀다(D16-1·D12-3)."""
    as_live()
    from app.reports.data import load_report
    from app.scheduler.inputs import load_facts

    before = _detail(client)["price"]
    base_low = before["price_low"]["v"]
    assert isinstance(base_low, int) and before["discount"] is None
    r = _human_discount(client, "10,000,000원")
    assert r.status_code == 201, r.text
    out = r.json()
    validate("createHumanCheck", 201, out)
    assert out["field"] == "discount" and out["entity"] == "payment_terms" and out["job_id"] is not None
    price = _detail(client)["price"]
    assert price["discount"]["v"] == WON and price["discount"]["label"] == "확인됨", price["discount"]
    assert price["discount_applied"] is True and "할인" in (price["composition"] or "")
    want_low = base_low - WON
    assert price["price_low"]["v"] == want_low, "상세"
    mid = price["price_mid"]["v"]
    items = client.get(f"/api/snapshots/{SNAP}/complexes", params={"size": 200}, headers=READ).json()["items"]
    row = next(i for i in items if i["complex_id"] == CX)
    assert row["price_low"]["v"] == want_low and row["price_mid"]["v"] == mid, "목록 값"
    got = client.get(
        f"/api/snapshots/{SNAP}/complexes", params={"size": 200, "filter[price_max]": mid}, headers=READ
    ).json()
    assert CX in [i["complex_id"] for i in got["items"]], "목록 필터(상한 = 상세 mid)"
    got = client.get(
        f"/api/snapshots/{SNAP}/complexes", params={"size": 200, "filter[price_min]": mid + 1}, headers=READ
    ).json()
    assert CX not in [i["complex_id"] for i in got["items"]], "목록 필터(하한 = 상세 mid + 1)"
    lows = [
        r["price_low"]["v"]
        for r in client.get(
            f"/api/snapshots/{SNAP}/complexes", params={"size": 200, "sort": "price_low"}, headers=READ
        ).json()["items"]
        if r["price_low"]["v"] is not None
    ]
    assert lows == sorted(lows) and want_low in lows, "목록 정렬"
    other = next(i["complex_id"] for i in items if i["complex_id"] != CX)
    cmp = client.get(f"/api/snapshots/{SNAP}/compare", params={"ids": f"{CX},{other}"}, headers=READ).json()
    term = next(t for t in cmp["terms"] if t["complex_id"] == CX)
    if term["down_payment_pct"]["v"] is not None:
        assert term["down_payment_won"]["v"] == round(mid * term["down_payment_pct"]["v"] / 100), (
            "비교 계약금"
        )
    with get_session() as s:
        data = load_report(s, SNAP, scenario_id=None, compare_snapshot_id=None)
        view = next(c for c in data.complexes if c.id == CX)
        assert view.price_low.v == want_low and "할인" in (view.price_low.reason or ""), "보고서"
        snap = s.get(Snapshot, SNAP)
        assert snap is not None
        region = s.get(Region, snap.region_id)
        assert region is not None
        f = next(x for x in load_facts(s, snap, region) if x.row.id == CX)
        assert f.price_low == want_low, "점수 입력"


def test_d16_1_human_check_turns_estimate_into_confirmed(client: TestClient) -> None:
    """파서 '추정' 할인(표시만, 차감 없음) → 사람이 같은 금액을 확인하면 '확인됨' + 차감. 다른 금액이면 사람 값."""
    as_live()
    base_low = _detail(client)["price"]["price_low"]["v"]
    _parser_estimate(WON)
    price = _detail(client)["price"]
    assert price["discount"]["label"] == "추정" and price["discount_applied"] is False
    assert price["price_low"]["v"] == base_low, "추정 할인은 빼지 않는다"
    r = _human_discount(client, "8,000,000")
    assert r.status_code == 201, r.text
    price = _detail(client)["price"]
    assert price["discount"]["v"] == 8_000_000 and price["discount"]["label"] == "확인됨"
    assert price["discount_applied"] is True and price["price_low"]["v"] == base_low - 8_000_000


def test_d16_1_human_discount_spreads_to_semantic_rows(client: TestClient) -> None:
    """D13-2: 할인 사람 확인도 (단지, 의미 필드) 단위 — 그 단지의 할인 값이 있는 모든 공고 행이 사람 확인 값(확인됨)이다."""
    as_live()
    _parser_estimate(WON)
    r = _human_discount(client, "9,000,000")
    assert r.status_code == 201, r.text
    field = None
    with get_session() as s:
        terms = list(s.scalars(select(PaymentTerms).where(PaymentTerms.complex_id == CX)))
        assert len(terms) >= 1
        for pt in terms:
            for code, won in (pt.discount_by_type or {}).items():
                field = f"discount_by_type.{code}"
                assert won == 9_000_000, (pt.id, pt.discount_by_type)
                chosen = s.scalars(
                    select(FieldProvenance).where(
                        FieldProvenance.entity == "payment_terms", FieldProvenance.entity_id == pt.id,
                        FieldProvenance.field == field, FieldProvenance.chosen.is_(True),
                    )
                ).one()  # fmt: skip
                assert chosen.label == "확인됨" and (chosen.reason or "").startswith("사람 확인"), (
                    chosen.reason
                )
    assert field is not None


def test_d16_1_human_discount_in_published_revision(client: TestClient) -> None:
    """사람 확인 뒤 새 리비전을 발행하면 저장본(상세·목록)도 차감한 값이다 — 발행 GET 은 저장본만 읽는다(D13-1)."""
    base_low = _detail(client, None)["price"]["price_low"]["v"]
    r = _human_discount(client, "10,000,000")
    assert r.status_code == 201, r.text
    rev = int(
        r.json()["suggested_job"]["payload"]["snapshot_id"]
    )  # 사람 확인이 만든 쓰기 가능 리비전(판정 전)
    # 재판정(판정기) 대신 바탕 발행 리비전 파생 행을 복사해 발행 — 저장본 계산은 지금 사실(사람 확인 할인)을 읽는다
    from app.scheduler.jobs import enqueue

    with get_session() as s:
        job = enqueue(s, "snapshot.publish", {"snapshot_id": rev, "carry_from_snapshot_id": SNAP})
        s.flush()
        jid = job.id
    st, stats = run_job(jid)
    assert st == "done" and stats["published"], stats
    detail = _detail(client, rev)
    assert detail["snapshot_id"] == rev
    assert detail["price"]["discount_applied"] is True and detail["price"]["discount"]["label"] == "확인됨"
    assert detail["price"]["price_low"]["v"] == base_low - WON
    items = client.get(f"/api/snapshots/{rev}/complexes", params={"size": 200}, headers=READ).json()["items"]
    assert next(i for i in items if i["complex_id"] == CX)["price_low"]["v"] == base_low - WON
    # 옛 발행 리비전(12)은 그대로(발행 순간 값)
    assert _detail(client, SNAP)["price"]["price_low"]["v"] == base_low


@pytest.mark.parametrize("value", ["abc", "-1", "1.5", "1E7", "10,000,000만원", "200,000,000,000"])
def test_d16_1_human_discount_value_validation(client: TestClient, value: str) -> None:
    """할인 값 = 원 단위 정수(0 ~ 1천억, 단위 '원'만). 형·범위가 틀리면 422(value_text) — 쓰기 없음."""
    from sqlalchemy import func

    from app.models import HumanCheck

    with get_session() as s:
        n0 = s.scalar(select(func.count()).select_from(HumanCheck))
    r = _human_discount(client, value)
    assert r.status_code == 422, (value, r.text)
    assert r.json()["field_errors"][0]["loc"] == ["body", "value_text"]
    with get_session() as s:
        assert s.scalar(select(func.count()).select_from(HumanCheck)) == n0

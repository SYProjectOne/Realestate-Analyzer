"""R3f CORE4 — 사람 확인 `checked_at`·KST 날짜·같은 값 공고·재확인·옛 행 이전 (DECISIONS D14-6, R3 6차 리뷰).

| 리뷰 | 테스트 |
| --- | --- |
| N-M4 형식(RFC3339 + 시간대) | ``test_n_m4_checked_at_must_be_rfc3339_with_offset`` |
| N-M4 미래(10분 넘게) | ``test_n_m4_future_checked_at_is_422`` · ``test_n_m4_near_future_and_utc_z_accepted`` |
| m12 UTC/KST 경계 | ``test_m12_utc_evening_is_next_kst_day`` |
| m11 나중 공고 = 사람 확인 값 | ``test_m11_later_notice_with_same_value_accepted`` · ``test_m11_same_value_notice_after_human_no_review`` |
| D14-6 이른 확인일 422 = 값이 다를 때만 | ``test_m11_later_notice_with_same_value_accepted`` · ``test_d14_6_backdated_different_value_still_422`` |
| m13 재확인 → '사람 확인 재검토' 닫힘 | ``test_m13_reconfirm_closes_human_review`` |
| m14 .9 행 단위 사람 확인 이전 | ``test_m14_migrate_row_human_checks_idempotent`` |
| 옛 날짜만 checked_at 읽기 | ``test_legacy_date_only_checked_at_still_readable`` |
"""

# ruff: noqa: E501

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.db import get_session
from app.core.time import now_kst
from app.models import ChangeEvent, ChecklistItem, ComplexType, FieldProvenance, HumanCheck

from ._support import READ, WRITE, as_live
from .test_r3b_g3 import CX, SNAP
from .test_r3d_core2 import human_check, store_cx_field, store_notice
from .test_r3e_human_semantic import _basis, _high, _review_items, _set_type_row_price

X = 700_000_000  # 공고문 값
Y = 690_000_000  # 사람 확인 값


def _post(client: TestClient, field: str, value: str, checked_at: str, **kw: Any) -> Any:
    return client.post(
        "/api/ops/human-checks", headers=WRITE,
        json={"complex_id": kw.get("cx", CX), "field": field, "value_text": value, "kind": "phone",
              "checked_at": checked_at, "entered_by": "운영자"},
    )  # fmt: skip


def _counts() -> tuple[int, int]:
    with get_session() as s:
        return (
            int(s.scalar(select(func.count()).select_from(HumanCheck)) or 0),
            int(s.scalar(select(func.count()).select_from(ChangeEvent)) or 0),
        )


def _assert_checked_at_422(r: Any) -> dict[str, Any]:
    assert r.status_code == 422, r.text
    body: dict[str, Any] = r.json()
    assert body["code"] == "validation_error", body
    assert body["field_errors"][0]["loc"] == ["body", "checked_at"], body
    return body


# ====================================================================== N-M4


@pytest.mark.parametrize(
    "value",
    [
        "zzzzzzzzzz",
        "2026-10-09",
        "2026-10-09T10:00:00",
        "2026-10-09 10:00:00+09:00",
        "2026-10-09T25:00:00+09:00",
    ],
)
@pytest.mark.parametrize("field", ["move_in_ym", "other", "intake_status"])
def test_n_m4_checked_at_must_be_rfc3339_with_offset(client: TestClient, value: str, field: str) -> None:
    before = _counts()
    text = {"move_in_ym": "2028-06", "other": "메모", "intake_status": "가능"}[field]
    _assert_checked_at_422(_post(client, field, text, value))
    assert _counts() == before, "거절된 입력은 아무것도 쓰지 않는다"


def test_n_m4_future_checked_at_is_422(client: TestClient) -> None:
    before = _counts()
    for ahead in (timedelta(minutes=11), timedelta(days=1), timedelta(days=365 * 70)):
        stamp = (now_kst() + ahead).isoformat(timespec="seconds")
        body = _assert_checked_at_422(_post(client, "move_in_ym", "2028-06", stamp))
        assert "미래" in body["detail"], body
    assert _counts() == before


def test_n_m4_near_future_and_utc_z_accepted(client: TestClient) -> None:
    """서버 시계보다 10분 이내 앞선 값(입력기 시계 차)·UTC 'Z'·밀리초(화면 toISOString())는 받는다."""
    near = (now_kst() + timedelta(minutes=5)).isoformat(timespec="seconds")
    assert _post(client, "other", "메모", near).status_code == 201
    r = _post(client, "other", "메모", "2026-10-09T01:20:00.000Z")
    assert r.status_code == 201, r.text
    assert r.json()["checked_at"] == "2026-10-09T01:20:00.000Z", "입력 문자열 그대로 저장·응답"


# ====================================================================== m12 (KST 날짜)


def test_m12_utc_evening_is_next_kst_day(client: TestClient) -> None:
    """공고 관측 10-05. '2026-10-04T20:00:00Z' = KST 10-05 05시(같은 날 → 받는다), '…T14:00:00Z' = KST 10-04 23시(이르다 → 422)."""
    as_live()
    store_cx_field(CX, "move_in_ym", "2028-01", "notice_pdf", "2026-10-05", "m12")
    body = _assert_checked_at_422(_post(client, "move_in_ym", "2028-06", "2026-10-04T14:00:00Z"))
    assert "2026-10-05" in body["detail"]
    r = _post(client, "move_in_ym", "2028-06", "2026-10-04T20:00:00Z")
    assert r.status_code == 201, r.text
    with get_session() as s:
        fp = s.scalars(
            select(FieldProvenance)
            .where(FieldProvenance.entity == "complex", FieldProvenance.entity_id == CX,
                   FieldProvenance.field == "move_in_ym", FieldProvenance.raw_document_id.is_(None))
            .order_by(FieldProvenance.id.desc())
        ).first()  # fmt: skip
        assert fp is not None and (fp.reason or "").startswith("사람 확인")
        assert fp.observed_on == "2026-10-05", "사람 확인 출처 행 observed_on = KST 날짜"
        assert fp.chosen


# ====================================================================== m11 · D14-6


@pytest.mark.parametrize(
    ("field", "notice", "value"),
    [("move_in_ym", "2028-06", "2028-06"), ("down_payment_pct", 10.0, "10%")],
)
def test_m11_later_notice_with_same_value_accepted(
    client: TestClient, field: str, notice: Any, value: str
) -> None:
    """이미 수집된 나중 공고(관측 10-05)의 값이 사람 확인 값과 같으면 이른 확인일(10-04)도 받는다 — 재검토·critical 재검토 이벤트 없음."""
    as_live()
    if field == "move_in_ym":
        store_cx_field(CX, field, notice, "notice_pdf", "2026-10-05", "m11")
    else:
        store_notice(CX, "2026990105", {"effective_from": "2026-10-05", "notice_kind": "본청약", field: notice},
                     observed_on="2026-10-05")  # fmt: skip
    r = _post(client, field, value, "2026-10-04T10:00:00+09:00")
    assert r.status_code == 201, r.text
    assert not _review_items()


def test_d14_6_backdated_different_value_still_422(client: TestClient) -> None:
    as_live()
    store_notice(CX, "2026990106", {"effective_from": "2026-10-05", "notice_kind": "본청약", "down_payment_pct": 20.0},
                 observed_on="2026-10-05")  # fmt: skip
    before = _counts()
    body = _assert_checked_at_422(_post(client, "down_payment_pct", "10%", "2026-10-04T10:00:00+09:00"))
    assert "2026-10-05" in body["detail"]
    assert _counts() == before


def test_m11_same_value_notice_after_human_no_review(client: TestClient) -> None:
    """사람 확인(10-01) 뒤 관측(10-05)된 새 공고가 같은 값 → 정상 수용(값 그대로, '사람 확인 재검토'·critical 재검토 이벤트 없음)."""
    as_live()
    code = _set_type_row_price(X)
    human_check(client, "max_price_won", str(Y), day="2026-10-01")
    with get_session() as s:
        last_ev = int(s.scalar(select(func.max(ChangeEvent.id))) or 0)
    store_notice(CX, "2026990107", {"effective_from": "2026-10-05", "notice_kind": "무순위",
                                    f"price_by_type.{code}.max_price_won": Y}, observed_on="2026-10-05")  # fmt: skip
    assert _high(client)[0] == Y
    assert not _review_items()
    with get_session() as s:
        crit = [e for e in s.scalars(select(ChangeEvent).where(ChangeEvent.id > last_ev, ChangeEvent.complex_id == CX))
                if e.severity == "critical" and "사람 확인" in (e.old_text or "")]  # fmt: skip
        assert not crit, [(e.old_text, e.new_text) for e in crit]


# ====================================================================== m13


@pytest.mark.parametrize("again", [695_000_000, 711_000_000])
def test_m13_reconfirm_closes_human_review(client: TestClient, again: int) -> None:
    """사람 확인 → 새 공고에 짐('사람 확인 재검토' open) → 같은 (단지, 의미 필드) 재확인 → 그 항목 done(closed_by auto)."""
    as_live()
    code = _set_type_row_price(X)
    human_check(client, "max_price_won", str(Y), day="2026-10-01")
    notice = {
        "effective_from": "2026-10-05",
        "notice_kind": "무순위",
        f"price_by_type.{code}.max_price_won": 711_000_000,
    }
    store_notice(CX, "2026990108", notice, observed_on="2026-10-05")
    assert _high(client)[0] == 711_000_000
    assert _review_items() == ["사람 확인 재검토: 기준 타입 최고 공급금액"]
    r = _post(client, "max_price_won", str(again), "2026-10-06T10:00:00+09:00")
    assert r.status_code == 201, r.text
    assert _high(client)[0] == again
    assert not _review_items(), "재확인하면 열린 '사람 확인 재검토'가 닫힌다(D14-6)"
    with get_session() as s:
        item = s.scalars(select(ChecklistItem).where(ChecklistItem.complex_id == CX,
                                                     ChecklistItem.title == "사람 확인 재검토: 기준 타입 최고 공급금액")).one()  # fmt: skip
        assert (item.status, item.closed_by) == ("done", "auto")
    # 같은 공고 재정규화 — 사람 확인(10-06)이 이후라 다시 열리지 않는다
    store_notice(CX, "2026990108", {**notice, "interim_pct": 60.0}, observed_on="2026-10-05")
    assert _high(client)[0] == again
    assert not _review_items()


def test_m13_reconfirm_other_field_keeps_review_open(client: TestClient) -> None:
    """다른 의미 필드의 사람 확인은 그 항목을 닫지 않는다."""
    as_live()
    code = _set_type_row_price(X)
    human_check(client, "max_price_won", str(Y), day="2026-10-01")
    store_notice(CX, "2026990109", {"effective_from": "2026-10-05", "notice_kind": "무순위",
                                    f"price_by_type.{code}.max_price_won": 711_000_000}, observed_on="2026-10-05")  # fmt: skip
    assert _review_items() == ["사람 확인 재검토: 기준 타입 최고 공급금액"]
    assert _post(client, "move_in_ym", "2028-06", "2026-10-06T10:00:00+09:00").status_code == 201
    assert _review_items() == ["사람 확인 재검토: 기준 타입 최고 공급금액"]


# ====================================================================== m14


def test_m14_migrate_row_human_checks_idempotent(client: TestClient) -> None:
    """.9 행 단위 사람 확인(그 행 하나에만 사람 확인 출처) → 의미 묶음의 값 있는 다른 행에도 0순위 후보로. 두 번째 호출 0."""
    from app.api.demotion import migrate_row_human_checks

    as_live()
    code = _set_type_row_price(X)
    store_notice(CX, "2026990110", {"effective_from": "2026-09-01", "notice_kind": "본청약",
                                    f"price_by_type.{code}.max_price_won": X}, observed_on="2026-09-01")  # fmt: skip
    human_check(client, "max_price_won", str(Y), day="2026-10-09")
    t = _basis()
    with get_session() as s:
        hc = s.scalars(select(HumanCheck).order_by(HumanCheck.id.desc())).first()
        assert hc is not None and (hc.entity, hc.entity_id) != ("complex_type", t.id)
        # .9 흉내: 타입 행의 사람 확인 출처를 지우고 원문 출처를 다시 chosen, 값도 공고문 값으로
        for fp in s.scalars(select(FieldProvenance).where(FieldProvenance.entity == "complex_type",
                                                         FieldProvenance.entity_id == t.id,
                                                         FieldProvenance.field == "max_price_won")):  # fmt: skip
            if fp.raw_document_id is None:
                s.delete(fp)
            else:
                fp.chosen = fp.value_norm == str(X)
        row = s.get(ComplexType, t.id)
        assert row is not None
        row.max_price_won = X
    with get_session() as s:
        n = migrate_row_human_checks(s)
        s.commit()
    assert n >= 1
    with get_session() as s:
        assert s.get(ComplexType, t.id).max_price_won == Y  # type: ignore[union-attr]
        chosen = s.scalars(select(FieldProvenance).where(FieldProvenance.entity == "complex_type",
                                                        FieldProvenance.entity_id == t.id,
                                                        FieldProvenance.field == "max_price_won",
                                                        FieldProvenance.chosen.is_(True))).one()  # fmt: skip
        assert (chosen.reason or "").startswith("사람 확인") and chosen.value_norm == str(Y)
        n_fp = s.scalar(select(func.count()).select_from(FieldProvenance))
        n_ev = s.scalar(select(func.count()).select_from(ChangeEvent))
    with get_session() as s:
        assert migrate_row_human_checks(s) == 0, "멱등 — 두 번째 호출은 바꿀 것이 없다"
        s.commit()
    with get_session() as s:
        assert s.scalar(select(func.count()).select_from(FieldProvenance)) == n_fp
        assert s.scalar(select(func.count()).select_from(ChangeEvent)) == n_ev


# ====================================================================== 옛 행 호환


def test_legacy_date_only_checked_at_still_readable(client: TestClient) -> None:
    """D14-6 이전에 저장된 날짜만 checked_at(옛 행)도 출처 서랍·상세에서 그대로 읽힌다."""
    as_live()
    human_check(client, "move_in_ym", "2028-06", day="2026-10-09")
    with get_session() as s:
        hc = s.scalars(select(HumanCheck).order_by(HumanCheck.id.desc())).first()
        assert hc is not None
        hc.checked_at = "2026-10-09"
        hc_id = hc.id
    prov = client.get(f"/api/provenance/hc_{hc_id}", headers=READ)
    assert prov.status_code == 200, prov.text
    assert prov.json()["checked_at"] == "2026-10-09"
    d = client.get(f"/api/complexes/{CX}", params={"snapshot": SNAP}, headers=READ)
    assert d.status_code == 200, d.text
    # 옛 행이 있는 상태에서 새 공고가 와도(사람 확인 이후 관측 비교) 깨지지 않는다
    store_cx_field(CX, "move_in_ym", "2028-09", "notice_pdf", "2026-10-12", "legacy")
    assert client.get(f"/api/complexes/{CX}", params={"snapshot": SNAP}, headers=READ).status_code == 200


@pytest.mark.parametrize(
    ("value", "ok"),
    [
        ("2026-10-10T12:00:00+09:00", True),
        ("2026-10-10T03:00:00Z", True),
        ("2026-10-10T03:00:00.123456789z", True),
        ("2026-10-10t12:00:00+09:00", True),
        ("2026-10-10T12:10:00+09:00", True),  # 정확히 10분 = 허용
        ("2026-10-10T12:10:01+09:00", False),  # 10분 넘게 미래
        ("2026-10-10T03:10:01Z", False),
        ("2026-10-10", False),
        ("2026-10-10T12:00:00", False),
        ("2026-10-10T12:00+09:00", False),
        ("2026-10-10T12:00:00+0900", False),
        ("2026-10-10T12:00:00+09:00\n", False),
        ("2026-02-30T12:00:00+09:00", False),
        ("zzzzzzzzzz", False),
        (20261010, False),
        (None, False),
    ],
)
def test_checked_at_error_rules_independent_of_schema_format_checker(value: Any, ok: bool) -> None:
    """엔드포인트 자체 검사(스키마 FormatChecker 가 date-time 을 모르는 환경에서도 같은 규칙) — 서버 now 주입."""
    from datetime import datetime

    from app.api.demotion import checked_at_error
    from app.core.time import KST

    now = datetime(2026, 10, 10, 12, 0, 0, tzinfo=KST)
    assert (checked_at_error(value, now=now) is None) is ok, checked_at_error(value, now=now)

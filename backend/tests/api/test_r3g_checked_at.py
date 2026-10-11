"""R3g CORE5 — D15-7·M6·minor 2: 사람 확인 ``checked_at`` 범위·overflow 422, 소문자 ``t``/``z`` = 대문자와 같은 KST 날짜.

예전: '0001-01-01T00:00:00+14:00' 이 201 로 들어가 지역 목록·CSV·단지 읽기가 OverflowError(404/500). 소문자
'2026-10-09t20:00:00z' 는 형식 통과 후 ``kst_date`` None → 앞 10자(UTC 날짜 10-09)로 저장·비교됐다.
"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.db import get_session
from app.models import FieldProvenance, HumanCheck, IntakeStatus

from ._support import READ, WRITE, as_live
from .test_r3b_g3 import CX, SNAP
from .test_r3d_core2 import store_cx_field

BAD = [
    "0001-01-01T00:00:00+14:00",  # UTC 로 바꾸면 overflow
    "0001-01-01T00:00:00Z",  # 2000년 이전
    "1999-12-31T23:59:59+09:00",  # KST 1999년
    "9999-12-31T23:59:59-12:00",  # overflow + 미래
]


def _post(client: TestClient, field: str, value: str, checked_at: str) -> Any:
    return client.post(
        "/api/ops/human-checks", headers=WRITE,
        json={"complex_id": CX, "field": field, "value_text": value, "kind": "phone",
              "checked_at": checked_at, "entered_by": "운영자"},
    )  # fmt: skip


def _human_checks() -> int:
    with get_session() as s:
        return int(s.scalar(select(func.count()).select_from(HumanCheck)) or 0)


def _reads_ok(client: TestClient) -> None:
    for url in (
        "/api/regions",
        f"/api/snapshots/{SNAP}/complexes",
        f"/api/snapshots/{SNAP}/complexes.csv",
        f"/api/complexes/{CX}",
    ):
        r = client.get(url, headers=READ)
        assert r.status_code == 200, (url, r.status_code, r.text[:300])


@pytest.mark.parametrize("value", BAD)
@pytest.mark.parametrize(("field", "text"), [("move_in_ym", "2028-06"), ("intake_status", "가능")])
def test_out_of_range_or_overflow_is_422_and_reads_stay_200(
    client: TestClient, value: str, field: str, text: str
) -> None:
    before = _human_checks()
    r = _post(client, field, text, value)
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["code"] == "validation_error", body
    assert body["field_errors"][0]["loc"] == ["body", "checked_at"], body
    assert _human_checks() == before, "422 면 아무것도 저장하지 않는다"
    _reads_ok(client)


def test_old_year_detail_mentions_2000(client: TestClient) -> None:
    r = _post(client, "move_in_ym", "2028-06", "1999-12-31T23:59:59+09:00")
    assert r.status_code == 422 and "2000" in r.json()["detail"], r.text


@pytest.mark.parametrize("value", ["2026-10-09t20:00:00z", "2026-10-09T20:00:00Z"])
def test_lowercase_t_z_is_kst_next_day_like_uppercase(client: TestClient, value: str) -> None:
    """공고 관측 10-10. UTC 10-09 20시 = KST 10-10 05시 → 같은 날(이후 아님) → 받는다. 사람 확인 출처 행 observed_on = 10-10."""
    as_live()
    store_cx_field(CX, "move_in_ym", "2028-01", "notice_pdf", "2026-10-10", "r3g")
    r = _post(client, "move_in_ym", "2028-06", value)
    assert r.status_code == 201, r.text
    with get_session() as s:
        fp = s.scalars(
            select(FieldProvenance)
            .where(FieldProvenance.entity == "complex", FieldProvenance.entity_id == CX,
                   FieldProvenance.field == "move_in_ym", FieldProvenance.raw_document_id.is_(None))
            .order_by(FieldProvenance.id.desc())
        ).first()  # fmt: skip
        assert fp is not None and (fp.reason or "").startswith("사람 확인")
        assert fp.observed_on == "2026-10-10", "KST 날짜(UTC 앞 10자 2026-10-09 가 아니다)"
        assert fp.chosen
    _reads_ok(client)


@pytest.mark.parametrize("value", ["2026-10-09t14:00:00z", "2026-10-09T14:00:00Z"])
def test_lowercase_early_kst_day_is_422_like_uppercase(client: TestClient, value: str) -> None:
    """UTC 10-09 14시 = KST 10-09 23시 → 10-10 공고보다 이르다(값 다름) → 422(D13-2). 대소문자 무관."""
    as_live()
    store_cx_field(CX, "move_in_ym", "2028-01", "notice_pdf", "2026-10-10", "r3g-early")
    r = _post(client, "move_in_ym", "2028-06", value)
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["field_errors"][0]["loc"] == ["body", "checked_at"], body
    assert "2026-10-09" in body["detail"], body["detail"]


def test_legacy_overflow_rows_do_not_break_reads(client: TestClient) -> None:
    """형식 검사 이전에 들어간 옛 행(overflow 시각)이 있어도 목록·CSV·단지 읽기는 200(``kst_date`` 는 예외를 던지지 않는다)."""
    as_live()
    with get_session() as s:
        s.add(IntakeStatus(complex_id=CX, snapshot_id=SNAP, status="가능", path="human_check",
                           checked_at="0001-01-01T00:00:00+14:00", note="옛 행", entered_by="운영자"))  # fmt: skip
    _reads_ok(client)

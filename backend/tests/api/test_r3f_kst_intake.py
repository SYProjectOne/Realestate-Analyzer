"""R3f CORE4 — D14-6 후속(CEO 2026-10-10): 접수 ``checked_at`` 의 날짜도 공용 KST 함수(``core.time.kst_day``)로.

예전 4곳은 앞 10자를 잘라 '2026-10-09T20:00:00Z'(KST 10-10 05:00)를 10-09 로 보였다 — 표시 접수 행 고르기(``scope.pick_intake``)·
상황 요건 근거(``scenarios._checked_note``)·목록 CSV 확인일·보고서 Fact 확인일(``reports.fmt.make_fact``).
"""

# ruff: noqa: E501

from __future__ import annotations

import csv
import io
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from app.core.db import get_session
from app.models import IntakeStatus

from ._support import READ, as_live
from .test_r3b_g3 import CX, SNAP

UTC_EVENING = "2026-10-09T20:00:00Z"  # KST 2026-10-10 05:00


def test_kst_day_helper() -> None:
    from app.core.time import kst_day

    assert kst_day(UTC_EVENING) == "2026-10-10"
    assert kst_day("2026-10-09") == "2026-10-09"
    assert kst_day("2026-10-09T23:00:00+09:00") == "2026-10-09"
    assert kst_day(None) == "" and kst_day("") == ""


def test_pick_intake_compares_kst_days() -> None:
    """같은 경로 두 행: UTC 저녁(KST 다음 날, id 작음)이 KST 같은 날 밤(id 큼)보다 최근 — 예전엔 앞 10자가 같아 id 로 졌다."""
    from app.analysis.scope import pick_intake

    a = SimpleNamespace(id=1, path="human_check", checked_at=UTC_EVENING, status="가능")
    b = SimpleNamespace(id=2, path="human_check", checked_at="2026-10-09T23:00:00+09:00", status="불가")
    assert pick_intake([a, b]) is a


def test_scenario_requirement_note_uses_kst_day() -> None:
    from app.analysis.scenarios import _checked_note

    note = _checked_note(SimpleNamespace(intake_checked_at=UTC_EVENING), "2026-10-10")  # type: ignore[arg-type]
    assert "확인 2026-10-10" in note


def test_report_fact_checked_day_is_kst() -> None:
    from app.reports.fmt import make_fact

    assert make_fact(1, "확인됨", "fp_1", UTC_EVENING).checked_at == "2026-10-10"
    assert make_fact(None, "확인 불가", None, UTC_EVENING, reason="x").checked_at == "2026-10-10"


def test_csv_intake_checked_day_is_kst(client: TestClient) -> None:
    as_live()  # 발행 전 리비전 = 지금 값(CSV 실시간)
    with get_session() as s:
        s.add(IntakeStatus(complex_id=CX, snapshot_id=SNAP, status="가능", path="human_check", checked_at=UTC_EVENING,
                           note="KST 시험", entered_by="운영자"))  # fmt: skip
    r = client.get(f"/api/snapshots/{SNAP}/complexes.csv", headers=READ)
    assert r.status_code == 200, r.text
    rows: list[Any] = list(csv.reader(io.StringIO(r.text.lstrip("﻿"))))
    head = rows[0]
    row = next(x for x in rows[1:] if x and x[0] == str(CX))
    col = (
        next(i for i, h in enumerate(head) if "확인" in h and "접수" in h)
        if any("확인" in h and "접수" in h for h in head)
        else 7
    )
    assert row[col] == "2026-10-10", (head, row[:9])

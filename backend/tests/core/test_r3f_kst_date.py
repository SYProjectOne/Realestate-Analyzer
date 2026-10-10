"""R3f CORE4 — D14-6·m12: checked_at·observed_on 의 KST 날짜 = 공용 함수 하나(``core.time.kst_date``)."""

from __future__ import annotations

from datetime import date

import pytest

from app.core.time import kst_date


@pytest.mark.parametrize(
    ("value", "want"),
    [
        ("2026-10-09", date(2026, 10, 9)),  # 날짜만(옛 행·observed_on) = 그 날짜
        ("2026-10-09T10:00:00+09:00", date(2026, 10, 9)),
        ("2026-10-09T20:00:00Z", date(2026, 10, 10)),  # UTC 20시 = KST 다음 날 05시
        ("2026-10-09T15:00:00.000Z", date(2026, 10, 10)),  # 화면이 보내는 toISOString() 모양
        ("2026-10-09T14:59:59Z", date(2026, 10, 9)),
        ("2026-10-10T08:59:59+09:00", date(2026, 10, 10)),
        ("2026-10-09T23:30:00-05:00", date(2026, 10, 10)),
        ("2026-10-09T23:00:00", date(2026, 10, 9)),  # 시간대 없음 = KST 로 본다
        ("2026-10-09 23:00:00+00:00", date(2026, 10, 10)),
        ("  2026-10-09  ", date(2026, 10, 9)),
    ],
)
def test_kst_date(value: str, want: date) -> None:
    assert kst_date(value) == want


@pytest.mark.parametrize("value", [None, "", "zzzzzzzzzz", "2026-10", "2026-13-01", "2026-10-09Tzz"])
def test_kst_date_unparseable_is_none(value: str | None) -> None:
    assert kst_date(value) is None

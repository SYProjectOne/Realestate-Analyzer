"""R3g CORE5 — D15-7·M6·minor 2: 시각 파싱은 ``core.time`` 하나(``parse_datetime``·``kst_date``·``checked_at_range_error``).

- ``T``·``Z`` 대소문자 무관('2026-10-09t20:00:00z' = KST 10-10, 예전엔 형식 통과 후 ``kst_date`` None → UTC 앞 10자)
- 연도 2000년 ~ 지금 + 10분, 범위 밖·overflow 는 422(예전 '0001-01-01T00:00:00+14:00' 은 201 뒤 읽기 OverflowError)
- 파서·``kst_date``·``kst_day`` 는 어떤 문자열에도 예외를 던지지 않는다
"""

# ruff: noqa: E501

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.time import (
    CHECKED_AT_FUTURE_SLACK,
    CHECKED_AT_MIN,
    KST,
    checked_at_range_error,
    kst_date,
    kst_day,
    parse_datetime,
)

NOW = datetime(2026, 10, 10, 12, 0, 0, tzinfo=KST)

# (입력, parse_datetime 이 읽는가, checked_at_error 통과?, kst_date) — 리뷰어 스크립트 r7/b/fuzz_checked_at.py 의 사례 + 범위
CASES: list[tuple[str, bool, bool, date | None]] = [
    ("2026-10-09", False, False, date(2026, 10, 9)),  # 날짜만: 입력은 422, 옛 행 읽기는 그 날짜
    ("2026-10-09T10:20:00", False, False, date(2026, 10, 9)),  # 시간대 없음: 422, 옛 행은 KST 로 본다
    ("2026-10-09T10:20:00+09:00", True, True, date(2026, 10, 9)),
    ("2026-10-09t10:20:00z", True, True, date(2026, 10, 9)),
    ("2026-10-09T10:20:00Z", True, True, date(2026, 10, 9)),
    ("2026-10-09t20:00:00z", True, True, date(2026, 10, 10)),  # minor 2: 소문자도 KST 다음 날
    ("2026-10-09T20:00:00z", True, True, date(2026, 10, 10)),
    ("2026-10-09t20:00:00Z", True, True, date(2026, 10, 10)),
    ("2026-10-09 10:20:00+09:00", False, False, date(2026, 10, 9)),  # 공백 구분: 입력 422, 옛 행 읽기는 관대
    ("2026-10-09T23:59:60Z", False, False, None),  # 윤초는 표현 불가
    ("2016-12-31T23:59:60Z", False, False, None),
    ("0000-01-01T00:00:00Z", False, False, None),
    ("0001-01-01T00:00:00+14:00", False, False, None),  # M6: UTC 로 바꾸면 overflow
    ("0001-01-01T00:00:00Z", True, False, date(1, 1, 1)),  # 읽히지만 2000년 이전 → 422
    ("9999-12-31T23:59:59-12:00", False, False, None),  # overflow
    ("9999-12-31T23:59:59+09:00", True, False, date(9999, 12, 31)),  # 미래 → 422
    ("1999-12-31T23:59:59+09:00", True, False, date(1999, 12, 31)),  # KST 1999년 → 422
    ("1999-12-31T15:00:00Z", True, True, date(2000, 1, 1)),  # KST 2000-01-01 00:00 = 하한(포함)
    ("1999-12-31T14:59:59Z", True, False, date(1999, 12, 31)),
    ("2026-10-09T10:20:00+14:00", True, True, date(2026, 10, 9)),
    ("2026-10-09T10:20:00-12:00", True, True, date(2026, 10, 10)),
    ("2026-10-09T10:20:00+0900", False, False, date(2026, 10, 9)),
    ("2026-10-09T10:20:00.123456789+09:00", True, True, date(2026, 10, 9)),
    ("2026-10-09T10:20:00.1+09:00", True, True, date(2026, 10, 9)),
    ("2026-10-09T10:20+09:00", False, False, date(2026, 10, 9)),
    ("2026-10-09T10:20:00+23:59", True, True, date(2026, 10, 8)),
    ("2026-10-09T10:20:00+24:00", False, False, None),
    ("2026-10-09T10:20:00+99:99", False, False, None),
    ("2026-10-09T10:20:00-00:00", True, True, date(2026, 10, 9)),
    ("２０２６-10-09T10:20:00+09:00", False, False, None),  # 전각 숫자
    ("2026-10-09T10:20:00+09:00\n", False, False, date(2026, 10, 9)),  # 입력은 엄격, 읽기는 strip
    (" 2026-10-09T10:20:00+09:00", False, False, date(2026, 10, 9)),
    ("2026-10-10T12:10:00+09:00", True, True, date(2026, 10, 10)),  # 정확히 10분 = 허용
    ("2026-10-10T12:10:01+09:00", True, False, date(2026, 10, 10)),
    ("2026-10-10T12:10:00.000001+09:00", True, False, date(2026, 10, 10)),
    ("2026-10-10T03:10:00Z", True, True, date(2026, 10, 10)),
    ("2026-10-10T03:10:01Z", True, False, date(2026, 10, 10)),
    ("2026-10-10t03:10:01z", True, False, date(2026, 10, 10)),
    ("2026-02-30T10:00:00Z", False, False, None),
    ("2026-10-09T25:00:00Z", False, False, None),
    ("2026-W41-1", False, False, None),  # ISO 주 날짜(10자)는 날짜가 아니다
    ("20261009", False, False, None),
]


@pytest.mark.parametrize(("text", "parses", "ok", "day"), CASES)
def test_fuzz_cases(text: str, parses: bool, ok: bool, day: date | None) -> None:
    from app.api.demotion import checked_at_error

    dt = parse_datetime(text)
    assert (dt is not None) is parses, dt
    if dt is not None:
        assert dt.tzinfo is not None and dt.utcoffset() is not None
    err = checked_at_error(text, now=NOW)
    assert (err is None) is ok, err
    assert kst_date(text) == day
    assert kst_day(text) == (day.isoformat() if day is not None else text[:10])


def test_lowercase_equals_uppercase() -> None:
    assert parse_datetime("2026-10-09t20:00:00z") == parse_datetime("2026-10-09T20:00:00Z")
    assert parse_datetime("2026-10-09t20:00:00z") == datetime(2026, 10, 9, 20, tzinfo=UTC)


def test_range_error_codes() -> None:
    assert datetime(2000, 1, 1, tzinfo=KST) == CHECKED_AT_MIN
    assert timedelta(minutes=10) == CHECKED_AT_FUTURE_SLACK
    assert checked_at_range_error(NOW, now=NOW) is None
    assert checked_at_range_error(NOW + timedelta(minutes=10), now=NOW) is None
    assert checked_at_range_error(NOW + timedelta(minutes=10, microseconds=1), now=NOW) == "future"
    assert checked_at_range_error(CHECKED_AT_MIN, now=NOW) is None
    assert checked_at_range_error(CHECKED_AT_MIN - timedelta(microseconds=1), now=NOW) == "too_old"
    assert checked_at_range_error(datetime(1, 1, 1, tzinfo=UTC), now=NOW) == "too_old"
    assert checked_at_range_error(datetime.max.replace(tzinfo=UTC), now=NOW) == "future"
    assert checked_at_range_error(datetime.now(KST)) is None  # now 생략 = 서버 시계


@pytest.mark.parametrize("value", [None, 20261010, b"2026-10-09T10:20:00Z", ["x"]])
def test_non_strings_never_raise(value: Any) -> None:
    assert parse_datetime(value) is None
    assert kst_date(value) is None


def test_checked_at_error_messages() -> None:
    from app.api.demotion import checked_at_error

    old = checked_at_error("1999-12-31T23:59:59+09:00", now=NOW)
    assert old is not None and "2000" in old
    ovf = checked_at_error("0001-01-01T00:00:00+14:00", now=NOW)
    assert ovf is not None and "RFC3339" in ovf
    fut = checked_at_error("2026-10-10t03:10:01z", now=NOW)
    assert fut is not None and "미래" in fut


# ---------------------------------------------------------------- 성질 시험

_offsets = st.integers(min_value=-(23 * 60 + 59), max_value=23 * 60 + 59).map(
    lambda m: timezone(timedelta(minutes=m))
)


@settings(max_examples=400, deadline=None)
@given(st.text())
def test_never_raises_on_any_text(text: str) -> None:
    parse_datetime(text)
    kst_date(text)
    kst_day(text)


_ISOISH = st.text(alphabet="0123456789-:+TtZz. W", max_size=40)


@settings(max_examples=600, deadline=None)
@given(_ISOISH)
def test_never_raises_on_iso_like_text(text: str) -> None:
    dt = parse_datetime(text)
    if dt is not None:
        dt.astimezone(KST)  # 읽힌 값은 언제나 KST·UTC 로 바꿀 수 있다
        dt.astimezone(UTC)
        checked_at_range_error(dt, now=NOW)
    kst_date(text)
    kst_day(text)


@settings(max_examples=400, deadline=None)
@given(st.datetimes(min_value=datetime(1, 1, 2), max_value=datetime(9999, 12, 30), timezones=_offsets))
def test_extreme_aware_datetimes_never_raise(dt: datetime) -> None:
    text = dt.isoformat()
    got = parse_datetime(text)
    if got is not None:
        assert got == dt
    kst_date(text)


@settings(max_examples=500, deadline=None)
@given(
    st.datetimes(min_value=datetime(2000, 1, 2), max_value=datetime(2100, 1, 1), timezones=_offsets),
    st.booleans(),
    st.booleans(),
    st.booleans(),
)
def test_kst_date_matches_astimezone_any_case(
    dt: datetime, lower_t: bool, use_z: bool, lower_z: bool
) -> None:
    text = dt.isoformat()
    if lower_t:
        text = text[:10] + "t" + text[11:]
    if use_z and dt.utcoffset() == timedelta(0):
        text = text[:-6] + ("z" if lower_z else "Z")
    want = dt.astimezone(KST).date()
    assert parse_datetime(text) == dt
    assert kst_date(text) == want
    assert kst_day(text) == want.isoformat()

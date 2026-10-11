"""Asia/Seoul 기준 시간 유틸. 기준일(스냅샷 날짜)과 D±일 계산.

naive datetime 은 받지 않는다(어느 시간대인지 모르면 기준일이 하루 틀어질 수 있다).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from functools import lru_cache
from typing import Final, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SEOUL = "Asia/Seoul"


def _load_kst() -> tzinfo:
    try:
        return ZoneInfo(SEOUL)
    except ZoneInfoNotFoundError:  # tz 데이터가 없는 최소 이미지: 한국은 1988년 이후 DST 없음
        return timezone(timedelta(hours=9), "KST")


KST: tzinfo = _load_kst()


def now_kst() -> datetime:
    return datetime.now(KST)


def to_kst(dt: datetime) -> datetime:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("naive datetime 은 쓸 수 없다 — tzinfo 를 붙여라")
    return dt.astimezone(KST)


def today_kst(now: datetime | None = None) -> date:
    """기준일 = Asia/Seoul 달력 날짜."""
    return to_kst(now).date() if now is not None else now_kst().date()


CHECKED_AT_MIN: Final[datetime] = datetime(2000, 1, 1, tzinfo=KST)
"""D15-7: 사람 확인 시각 하한(포함) — KST 2000-01-01 00:00. 이보다 이르면 422."""
CHECKED_AT_FUTURE_SLACK: Final[timedelta] = timedelta(minutes=10)
"""D14-6·D15-7: 서버 시계보다 이만큼 넘게 앞선 시각은 422(입력기 시계 차는 허용)."""

# RFC3339 date-time(시간대 필수) — T·Z 대소문자 무관(D15-7), 소수 초 1~9자리, 오프셋 ±HH:MM. ASCII 숫자만(전각 거부)
_RFC3339_RE: Final = re.compile(
    r"(\d{4}-\d{2}-\d{2})[Tt](\d{2}:\d{2}:\d{2})(\.\d{1,9})?([Zz]|[+-]\d{2}:\d{2})", re.ASCII
)
_DATE_RE: Final = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)


def _convertible(dt: datetime) -> datetime | None:
    """aware ``dt`` 를 UTC·KST 로 바꿀 수 있으면 그대로, overflow(0001년 + 양수 오프셋 등)면 None."""
    try:
        dt.astimezone(UTC)
        dt.astimezone(KST)
    except (OverflowError, ValueError):
        return None
    return dt


def parse_datetime(text: object) -> datetime | None:
    """D15-7: 시각 파싱은 이 함수 하나 — 시간대가 붙은 RFC3339 date-time → aware datetime. 예외를 던지지 않는다.

    - 'YYYY-MM-DDTHH:MM:SS[.f]{Z|±HH:MM}', ``T``·``Z`` 대소문자 무관('2026-10-09t20:00:00z' = '…T20:00:00Z')
    - 날짜만·시간대 없음·공백 구분·'+0900'·앞뒤 공백·전각 숫자·윤초(:60)·없는 날짜 → None
    - UTC·KST 로 바꿀 수 없는 값(overflow — '0001-01-01T00:00:00+14:00', '9999-12-31T23:59:59-12:00') → None
    - 범위(2000년 ~ 지금 + 10분)는 ``checked_at_range_error`` 가 본다(여기서는 읽기만)"""
    if not isinstance(text, str):
        return None
    m = _RFC3339_RE.fullmatch(text)
    if m is None:
        return None
    day, clock, frac, off = m.groups()
    frac = (frac or "")[
        :7
    ]  # 마이크로초(6자리)까지 — 나머지는 버린다(fromisoformat 은 6자리 초과를 자르지 않을 수 있다)
    off = "+00:00" if off in ("Z", "z") else off
    try:
        dt = datetime.fromisoformat(f"{day}T{clock}{frac}{off}")
    except (ValueError, OverflowError):
        return None
    if dt.tzinfo is None or dt.utcoffset() is None:  # 정규식상 올 수 없지만 방어
        return None
    return _convertible(dt)


def checked_at_range_error(
    dt: datetime, *, now: datetime | None = None, slack: timedelta = CHECKED_AT_FUTURE_SLACK
) -> Literal["too_old", "future"] | None:
    """D15-7: 사람 확인 시각 범위 — ``CHECKED_AT_MIN``(KST 2000-01-01) 이상, 지금 + ``slack``(10분) 이하.
    범위 안이면 None, 아니면 'too_old'·'future'. ``dt`` 는 aware(``parse_datetime`` 결과)."""
    current = now or now_kst()
    if dt < CHECKED_AT_MIN:
        return "too_old"
    if dt - current > slack:
        return "future"
    return None


def kst_day(value: str | None) -> str:
    """``kst_date`` 의 'YYYY-MM-DD' 문자열(표시·정렬 키). 못 읽으면 앞 10자(옛 값 그대로), 없으면 ''. 예외 없음."""
    d = kst_date(value)
    if d is not None:
        return d.isoformat()
    return value[:10] if isinstance(value, str) else ""


def kst_date(value: str | None) -> date | None:
    """사람 확인 ``checked_at``·출처 ``observed_on`` 문자열 → KST 달력 날짜(D14-6 — 날짜 비교는 이 함수 하나). 예외 없음.

    - 날짜만('2026-10-09', 옛 행·observed_on) → 그 날짜
    - 시간대가 붙은 시각('…+09:00'·'…Z'·'…z', ``parse_datetime``) → Asia/Seoul 로 바꾼 날짜('2026-10-09t20:00:00z' → 2026-10-10)
    - 그 밖의 옛 행 모양(공백 구분·'+0900'·초 없음 — 형식 검사 이전 입력): 시간대가 있으면 KST 로 바꾸고,
      없으면 KST 로 본다(그 날짜 그대로). 앞뒤 공백은 무시한다
    - 못 읽거나 KST 로 바꿀 수 없으면(overflow) None(문자열 앞 10자를 날짜로 믿지 않는다)"""
    if not isinstance(value, str) or not value:
        return None
    return _kst_date_cached(value)


@lru_cache(maxsize=65536)  # 같은 시각 문자열을 수십만 번 읽는다(발행 계산·보고서) — 결과는 불변 date
def _kst_date_cached(value: str) -> date | None:
    s = value.strip()
    if len(s) == 10:
        if _DATE_RE.fullmatch(s) is None:
            return None
        try:
            return date.fromisoformat(s)
        except ValueError:
            return None
    dt = parse_datetime(s) or _parse_legacy(s)
    if dt is None:
        return None
    if dt.tzinfo is None or dt.utcoffset() is None:
        return dt.date()
    try:
        return dt.astimezone(KST).date()
    except (OverflowError, ValueError):
        return None


def _parse_legacy(s: str) -> datetime | None:
    """옛 행(형식 검사 이전)의 관대한 ISO 읽기 — ``kst_date`` 전용. 날짜 부분은 'YYYY-MM-DD'(ASCII), 구분자 T·t·공백,
    끝 Z·z 는 UTC. naive 도 돌려준다(호출자가 KST 로 본다). 예외 없음."""
    if len(s) < 11 or _DATE_RE.fullmatch(s[:10]) is None or s[10] not in "Tt " or not s.isascii():
        return None
    body = s[:10] + "T" + s[11:]
    if body[-1] in "Zz":
        body = body[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(body)
    except (ValueError, OverflowError):
        return None
    if dt.tzinfo is not None and dt.utcoffset() is not None:
        return _convertible(dt)
    return dt


def kst_day_after(later: str | None, earlier: str | None) -> bool:
    """``later`` 가 ``earlier`` 보다 **뒤의** KST 날짜인가(같은 날은 뒤가 아니다) — 사람 확인 '이후 관측' 비교(D13-2·D14-6)를
    resolver·API 가 같은 규칙으로 쓴다. ``later`` 가 비면 False.

    둘 다 읽히면 KST 날짜 비교. 어느 한쪽을 못 읽는 옛 행은 ``kst_day`` 문자열(읽히는 쪽은 KST 날짜, 못 읽는 쪽은 앞 10자)
    비교 — 결정적이고, 읽히는 시각을 UTC 앞 10자로 자르지 않는다."""
    if not later:
        return False
    a, b = kst_date(later), kst_date(earlier)
    if a is not None and b is not None:
        return a > b
    return kst_day(later) > kst_day(earlier)


def add_days(base: date, days: int) -> date:
    return base + timedelta(days=days)


def d_day(target: date, base: date | None = None) -> int:
    """target - base 일수. 미래면 양수(D-n), 지났으면 음수(D+n)."""
    return (target - (base or today_kst())).days


def format_d_day(target: date, base: date | None = None) -> str:
    n = d_day(target, base)
    if n == 0:
        return "D-day"
    return f"D-{n}" if n > 0 else f"D+{-n}"

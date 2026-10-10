"""Asia/Seoul 기준 시간 유틸. 기준일(스냅샷 날짜)과 D±일 계산.

naive datetime 은 받지 않는다(어느 시간대인지 모르면 기준일이 하루 틀어질 수 있다).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone, tzinfo
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


def kst_day(value: str | None) -> str:
    """``kst_date`` 의 'YYYY-MM-DD' 문자열(표시·정렬 키). 못 읽으면 앞 10자(옛 값 그대로), 없으면 ''."""
    d = kst_date(value)
    if d is not None:
        return d.isoformat()
    return (value or "")[:10]


def kst_date(value: str | None) -> date | None:
    """사람 확인 ``checked_at``·출처 ``observed_on`` 문자열 → KST 달력 날짜(D14-6 — 날짜 비교는 이 함수 하나).

    - 날짜만('2026-10-09', 옛 행·observed_on) → 그 날짜
    - 시간대가 붙은 시각('…+09:00'·'…Z') → Asia/Seoul 로 바꾼 날짜('2026-10-09T20:00:00Z' → 2026-10-10)
    - 시간대 없는 시각(옛 행) → KST 로 본다(그 날짜 그대로)
    - 못 읽으면 None(문자열 앞 10자를 날짜로 믿지 않는다)"""
    if not value:
        return None
    s = value.strip()
    if len(s) == 10:
        try:
            return date.fromisoformat(s)
        except ValueError:
            return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None or dt.utcoffset() is None:
        return dt.date()
    return dt.astimezone(KST).date()


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

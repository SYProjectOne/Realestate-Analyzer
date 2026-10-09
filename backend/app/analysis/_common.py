"""analysis 내부 공용: 10진 연산·날짜(연월)·금액 표기. 순수 함수만 둔다(DB·시계 접근 없음)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.core.time import d_day

Q4 = Decimal("0.0001")
Q2 = Decimal("0.01")
ZERO = Decimal(0)
TEN = Decimal(10)
EOK = 100_000_000
MAN = 10_000
MINUS = "−"


def dec(x: float | int | str | Decimal) -> Decimal:
    """float는 repr 문자열로 바꿔 10진 값으로(0.35 → Decimal('0.35'))."""
    if isinstance(x, Decimal):
        return x
    if isinstance(x, float):
        return Decimal(repr(x))
    return Decimal(x)


def q4(x: Decimal) -> Decimal:
    return x.quantize(Q4, rounding=ROUND_HALF_UP)


def clamp(x: Decimal, lo: Decimal = ZERO, hi: Decimal = TEN) -> Decimal:
    return max(lo, min(hi, x))


def norm(x: Decimal) -> Decimal:
    """표시·비교용 정규화: 4자리 반올림 후 뒤 0 제거(6.0000 → 6, 0E-4 → 0)."""
    v = q4(x).normalize()
    return v + 0 if v == 0 else v  # -0 → 0


def to_float(x: Decimal | None) -> float | None:
    return None if x is None else float(norm(x))


def num(x: Decimal, places: int = 2) -> str:
    """식 문자열용 숫자: 반올림, 뒤 0 제거, 음수는 수학 기호 '−'."""
    v = x.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    s = format(v.normalize(), "f")
    if s.startswith("-"):
        s = MINUS + s[1:]
    return "0" if s in ("−0", "0") else s


def paren(x: Decimal, places: int = 2) -> str:
    """음수면 괄호로 감싼다: '(−4.35)'."""
    s = num(x, places)
    return f"({s})" if s.startswith(MINUS) else s


def median(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise ValueError("빈 목록의 중앙값")
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def quantile(sorted_values: Sequence[Decimal], p: Decimal) -> Decimal:
    """선형 보간 분위수(포함형, numpy 기본과 같음)."""
    n = len(sorted_values)
    if n == 0:
        raise ValueError("빈 목록의 분위수")
    pos = (n - 1) * p
    lo = int(pos)
    frac = pos - lo
    if lo + 1 >= n:
        return sorted_values[-1]
    return sorted_values[lo] + (sorted_values[lo + 1] - sorted_values[lo]) * frac


def slope(points: Iterable[tuple[int, Decimal]]) -> Decimal | None:
    """최소제곱 기울기. 점이 2개 미만이거나 x가 모두 같으면 None."""
    pts = list(points)
    if len(pts) < 2:
        return None
    n = Decimal(len(pts))
    mx = sum((Decimal(x) for x, _ in pts), ZERO) / n
    my = sum((y for _, y in pts), ZERO) / n
    sxx = sum(((Decimal(x) - mx) ** 2 for x, _ in pts), ZERO)
    if sxx == 0:
        return None
    sxy = sum(((Decimal(x) - mx) * (y - my) for x, y in pts), ZERO)
    return sxy / sxx


# ------------------------------------------------------------------ 날짜·연월


def parse_date(s: str) -> date:
    return date.fromisoformat(s[:10])


def ym_index(ym: str) -> int:
    """'YYYY-MM' → 월 일련번호(연×12 + 월−1)."""
    y, m = ym[:7].split("-")
    return int(y) * 12 + int(m) - 1


def ym_from_index(idx: int) -> str:
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def ym_of(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def add_months_ym(ym: str, months: int) -> str:
    return ym_from_index(ym_index(ym) + months)


def add_months_date(d: date, months: int) -> date:
    """월 더하기. 말일 넘침은 그 달 말일로(2025-08-31 + 6개월 → 2026-02-28)."""
    idx = d.year * 12 + d.month - 1 + months
    y, m = idx // 12, idx % 12 + 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    raise ValueError(f"날짜 계산 실패: {d} + {months}개월")  # pragma: no cover


def ym_first_day(ym: str) -> date:
    y, m = ym[:7].split("-")
    return date(int(y), int(m), 1)


def years_until(target: date, asof: date) -> Decimal:
    """기준일부터 target까지 연수 = 일수/365 (지났으면 0), 4자리 반올림."""
    days = max(0, d_day(target, asof))
    return q4(Decimal(days) / Decimal(365))


# ------------------------------------------------------------------ 금액 표기


def fmt_won(won: int | Decimal) -> str:
    """금액 표기: 1억 이상은 'N억' 또는 'N.NNN억', 미만은 'N,NNN만'(만 단위 반올림)."""
    w = Decimal(won)
    sign = MINUS if w < 0 else ""
    w = abs(w)
    if w >= EOK:
        e = (w / EOK).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP).normalize()
        return f"{sign}{format(e, 'f')}억"
    m = int((w / MAN).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return f"{sign}{m:,}만"

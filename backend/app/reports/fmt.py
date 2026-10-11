"""숫자·Fact 표시 규칙 — 프론트 ``src/lib/format.ts``·FactCell 과 같은 모양(보고서용 Python 판).

Fact 표시 문자열 규칙은 ``contracts/schemas/fact.json`` 설명이 원본이다:
'확인 불가(<reason>, <checked_at>)' / '<label>(<reason>)' / '<label>' / human=true → '사람 확인됨'.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.core.contracts_gen import Fact
from app.core.time import kst_day

__all__ = [
    "MISSING_REASON",
    "count_missing",
    "fact_label_text",
    "fact_value_text",
    "fmt_eok",
    "fmt_number",
    "fmt_score",
    "fmt_won",
    "make_fact",
    "round_half_up",
    "unknown_fact",
]

UNKNOWN = "확인 불가"
MISSING_REASON = "출처 누락"


def count_missing() -> bool:
    """'확인 불가(출처 누락)'을 하나 냈다. 저장본 계산 중(``app.api.facts.MISSING_COUNT`` 켜짐, D14-8)이면
    건수를 하나 세고 True — R3 7차 minor 12: 보고서 저장본의 출처 누락도 잡 통계 ``missing_provenance`` 에."""
    from app.api.facts import MISSING_COUNT

    box = MISSING_COUNT.get()
    if box is None:
        return False
    box[0] += 1
    return True


def round_half_up(value: Any, digits: int = 2) -> Decimal:
    q = Decimal(1).scaleb(-digits)
    return Decimal(str(value)).quantize(q, rounding=ROUND_HALF_UP)


def fmt_number(n: float | int | Decimal, digits: int = 0) -> str:
    d = round_half_up(n, digits)
    return f"{d:,.{digits}f}"


def fmt_won(won: float | int | Decimal) -> str:
    """원 → '7억 4,900만원'. 만 단위 반올림, 1만 미만은 원 그대로."""
    w = Decimal(str(won))
    sign = "-" if w < 0 else ""
    a = abs(w)
    if a < 10_000:
        return f"{sign}{fmt_number(a)}원"
    total_man = int(round_half_up(a / 10_000, 0))
    eok, man = divmod(total_man, 10_000)
    parts = []
    if eok:
        parts.append(f"{eok:,}억")
    if man:
        parts.append(f"{man:,}만")
    return f"{sign}{' '.join(parts)}원"


def fmt_eok(won: float | int | Decimal, digits: int = 2) -> str:
    return f"{round_half_up(Decimal(str(won)) / 100_000_000, digits)}억"


def fmt_score(score: float | int | Decimal, digits: int = 2) -> str:
    return f"{round_half_up(score, digits)}"


def fact_value_text(f: Fact) -> str:
    """값 부분만(라벨 제외). 값이 없으면 빈 문자열."""
    v = f.v
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    try:
        num = Decimal(str(v))
    except InvalidOperation:  # pragma: no cover - 방어
        return str(v)
    unit = f.unit
    if unit == "won":
        return fmt_eok(num) if abs(num) >= 100_000_000 else fmt_won(num)
    if unit == "pct":
        return f"{round_half_up(num, 1).normalize():f}%"
    if unit == "prob" or unit == "ratio":
        return fmt_score(num, 2)
    if unit == "score":
        return fmt_score(num, 2)
    if unit == "m2":
        return f"{round_half_up(num, 2)}㎡"
    if unit == "units":
        return f"{fmt_number(num)}세대"
    if unit == "count":
        return f"{fmt_number(num)}건"
    if unit == "months":
        return f"{fmt_number(num)}개월"
    if unit == "years":
        return f"{fmt_number(num)}년"
    if unit == "year":
        return str(int(num))
    if unit == "m":
        return f"{fmt_number(num)}m"
    if num == num.to_integral_value():
        return fmt_number(num)
    return f"{num.normalize():f}"


def fact_label_text(f: Fact) -> str:
    if f.human:
        return "사람 확인됨"
    if f.label == UNKNOWN:
        reason = f.reason or "사유 미기재"
        return f"확인 불가({reason}, {f.checked_at})" if f.checked_at else f"확인 불가({reason})"
    return f"{f.label}({f.reason})" if f.reason else f.label


def unknown_fact(reason: str, *, checked_at: str | None = None, unit: str | None = None) -> Fact:
    return Fact.model_validate(
        {
            "v": None,
            "label": UNKNOWN,
            "reason": reason[:120],
            "prov": None,
            "checked_at": checked_at,
            "unit": unit,
        }
    )


def make_fact(
    v: Any,
    label: str,
    prov: str | None,
    checked_at: str | None,
    *,
    unit: str | None = None,
    reason: str | None = None,
) -> Fact:
    """값·라벨·출처로 Fact. 값이 없거나 출처가 없으면 '확인 불가'로 낮춘다(빈 라벨·출처 없는 수치 금지)."""
    day = kst_day(checked_at) or None if checked_at else None  # KST 날짜(D14-6)
    if label == UNKNOWN or v is None:
        why = reason if label == UNKNOWN and reason else ("값 없음" if v is None else "사유 미기재")
        return Fact.model_validate(
            {"v": None, "label": UNKNOWN, "reason": why[:120], "prov": prov, "checked_at": day, "unit": unit}
        )
    if prov is None:
        count_missing()
        return unknown_fact(MISSING_REASON, checked_at=day, unit=unit)
    if isinstance(v, Decimal):
        v = float(v)
    elif isinstance(v, bool):
        v = "예" if v else "아니오"
    return Fact.model_validate(
        {
            "v": v,
            "label": label,
            "reason": reason[:120] if reason else None,
            "prov": prov,
            "checked_at": day,
            "unit": unit,
        }
    )

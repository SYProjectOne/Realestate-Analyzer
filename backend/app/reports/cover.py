"""보고서 첫 장(결론 요약 + 메타 상자)·용어 첫 등장 괄호 풀이·증감 표식 (R9-REPORT, D28-4, 30-proposal §11-2).

판단 없음: 첫 장 요약은 ``ReportData`` 에 이미 있는 값(판정기 결과·점수·접수 상태·라벨)만 템플릿 문장에 끼운다.
여기서 하는 계산은 개수 세기와 두 저장값의 방향(▲▼) 표시뿐이다(D25-3 메타 값 — 순위 차이는 '파생' 메타 값).
"""

# ruff: noqa: E501  (한국어 문구)

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from markupsafe import Markup

from app.core.contracts_gen import Fact
from app.reports.data import ComplexView, DecisionView, ReportData, ScenarioBlock, ScoreView
from app.reports.diff import DiffRow, SnapshotDiff
from app.reports.glossary import GLOSSARY

__all__ = [
    "INTAKE_ORDER",
    "SCOPE_ORDER",
    "Cover",
    "ScenarioLine",
    "TermState",
    "build_cover",
    "delta_mark",
    "diff_mark",
    "intake_counts_text",
    "rank_move",
]

INTAKE_ORDER: Final = ("가능", "미정", "불가", "확인 불가")
SCOPE_ORDER: Final = ("판정 대상", "참고", "보류", "미해결", "제외")
TOP_N: Final = 3  # 첫 장 종합 점수 상위 n곳(30-proposal §11-2 (2)-1)


@dataclass(frozen=True, slots=True)
class ScenarioLine:
    block: ScenarioBlock
    chosen: list[DecisionView]
    tie: bool


@dataclass(frozen=True, slots=True)
class Cover:
    open_now: list[ComplexView]
    intake_counts: list[tuple[str, int]]  # (접수 상태, 단지 수) — 기록 없음 포함
    top: list[ScoreView]
    scenarios: list[ScenarioLine]
    scope_counts: list[tuple[str, str, int]]  # (범위 코드, 표시 문구, 단지 수)
    scope_groups: list[
        tuple[str, list[ComplexView]]
    ]  # 판정 대상이 아닌 범위별 단지(표시 문구, 단지들 — 사유는 scope_reason)
    unknown_values: int  # 라벨 '확인 불가' 채택 출처 행 수(§9-2)
    unresolved_calls: int
    critical_changes: int
    diff_counts: dict[str, int] = field(default_factory=dict)  # added·removed·changed·up·down
    ref_count: int = 0
    ref_days: tuple[str, str] | None = None
    failed_sources: int = 0
    revision: int | None = None
    compare_revision: int | None = None


def _scope_text(data: ReportData, code: str) -> str:
    for c in data.complexes:
        if c.judge_scope == code:
            return c.judge_scope_text
    return code


def build_cover(
    data: ReportData,
    diff: SnapshotDiff | None = None,
    *,
    revision: int | None = None,
    compare_revision: int | None = None,
) -> Cover:
    shown = [c for c in data.complexes if c.judge_scope != "제외"]
    open_now = [c for c in shown if c.intake_shown is not None and c.intake_shown.status == "가능"]
    ic: Counter[str] = Counter(
        c.intake_shown.status if c.intake_shown is not None else "기록 없음" for c in shown
    )
    intake_counts = [(k, ic[k]) for k in (*INTAKE_ORDER, "기록 없음") if ic.get(k)]
    intake_counts += [(k, n) for k, n in ic.items() if k not in INTAKE_ORDER and k != "기록 없음"]
    sc: Counter[str] = Counter(c.judge_scope for c in data.complexes)
    scope_counts = [(k, _scope_text(data, k), sc[k]) for k in SCOPE_ORDER if sc.get(k)]
    scope_counts += [(k, _scope_text(data, k), n) for k, n in sc.items() if k not in SCOPE_ORDER]
    scope_groups = [
        (text, [c for c in data.complexes if c.judge_scope == code])
        for code, text, _n in scope_counts
        if code != "판정 대상"
    ]
    scenarios = [
        ScenarioLine(block=b, chosen=[d for d in b.decisions if d.chosen], tie=b.tie) for b in data.scenarios
    ]
    diff_counts: dict[str, int] = {}
    if diff is not None and not diff.note:
        kinds = Counter(r.kind for r in diff.rows)
        moves = Counter(_direction(r) for r in diff.rows if r.kind == "changed")
        diff_counts = {
            "total": len(diff.rows),
            "added": kinds.get("added", 0),
            "removed": kinds.get("removed", 0),
            "changed": kinds.get("changed", 0),
            "up": moves.get("up", 0),
            "down": moves.get("down", 0),
        }
    days = sorted({r.checked_at[:10] for r in data.references if r.checked_at})
    return Cover(
        open_now=open_now,
        intake_counts=intake_counts,
        top=data.top5[:TOP_N],
        scenarios=scenarios,
        scope_counts=scope_counts,
        scope_groups=scope_groups,
        unknown_values=int(data.label_counts.get("확인 불가", 0)),
        unresolved_calls=len(data.unresolved_calls),
        critical_changes=sum(1 for c in data.changes if c.get("severity") == "critical"),
        diff_counts=diff_counts,
        ref_count=len(data.references),
        ref_days=(days[0], days[-1]) if days else None,
        failed_sources=len(data.failed_sources),
        revision=revision,
        compare_revision=compare_revision,
    )


# ------------------------------------------------------------------ 용어 첫 등장 괄호 풀이


class TermState:
    """보고서 한 부 안에서 용어의 첫 등장에만 괄호 풀이를 단다(30-proposal §7-1 '같은 화면에서 반복 금지')."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    def __call__(self, key: str, shown: str | None = None) -> Markup:
        item = GLOSSARY[key]  # 없는 key 는 KeyError — 템플릿 오타를 숨기지 않는다
        text = shown or item.term
        head = Markup('<span class="term" data-term="{}">{}</span>').format(key, text)
        if key in self.seen or not item.inline:
            return head
        self.seen.append(key)
        return head + Markup('<span class="gloss">({})</span>').format(item.inline)


# ------------------------------------------------------------------ 증감 표식(▲▼ + 글자, 색만으로 말하지 않음)

_NUM: Final = re.compile(r"^[+-]?\d+(?:\.\d+)?$")


def _dec(text: str | None) -> Decimal | None:
    if text is None:
        return None
    t = str(text).strip().replace(",", "")
    if not _NUM.match(t):
        return None
    try:
        return Decimal(t)
    except InvalidOperation:  # pragma: no cover - 정규식이 막는다
        return None


def _direction(row: DiffRow) -> str:
    a, b = _dec(row.old), _dec(row.new)
    if a is None or b is None:
        return "other"
    return "up" if b > a else "down" if b < a else "same"


def _mark(kind: str, text: str) -> Markup:
    sym = {"up": "▲", "down": "▼", "same": "―", "add": "＋", "remove": "－"}.get(kind, "·")
    return Markup('<span class="delta {}">{} {}</span>').format(kind, sym, text)


def diff_mark(row: DiffRow) -> Markup:
    """§12 diff 표 '구분': 추가 ＋ / 제외 － / 변경(숫자면 ▲ 증가·▼ 감소)."""
    if row.kind == "added":
        return _mark("add", "추가")
    if row.kind == "removed":
        return _mark("remove", "제외")
    d = _direction(row)
    if d == "up":
        return _mark("up", "증가(변경)")
    if d == "down":
        return _mark("down", "감소(변경)")
    return Markup('<span class="delta other">변경</span>')


def _rank_int(text: str) -> int | None:
    m = re.match(r"^(\d+)위$", text or "")
    return int(m.group(1)) if m else None


def rank_move(r0: str, r1: str, t0: Fact | None = None, t1: Fact | None = None) -> Markup:
    """§12 순위 변화: '▲ 2계단 오름' 등. 점수는 방향만(새 숫자를 만들지 않는다)."""
    a, b = _rank_int(r0), _rank_int(r1)
    if a is not None and b is not None:
        if b < a:
            out = _mark("up", f"{a - b}계단 오름")
        elif b > a:
            out = _mark("down", f"{b - a}계단 내림")
        else:
            out = _mark("same", "순위 같음")
    elif a is None and b is not None:
        out = _mark("add", "새로 순위에 듦")
    elif a is not None and b is None:
        out = _mark("remove", "순위에서 빠짐")
    else:
        out = Markup('<span class="delta other">순위 비교 없음</span>')
    v0 = t0.v if t0 is not None else None
    v1 = t1.v if t1 is not None else None
    if isinstance(v0, (int, float)) and isinstance(v1, (int, float)):
        if v1 > v0:
            out += Markup(" · ") + _mark("up", "점수 높아짐")
        elif v1 < v0:
            out += Markup(" · ") + _mark("down", "점수 낮아짐")
    return out


def delta_mark(f: Any) -> Markup:
    """변동률 같은 부호 있는 값 옆 표식: ▲ 오름 / ▼ 내림 / ― 변동 없음(값이 없으면 빈 문자열)."""
    v = f.v if isinstance(f, Fact) else None
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return Markup("")
    if v > 0:
        return _mark("up", "오름")
    if v < 0:
        return _mark("down", "내림")
    return _mark("same", "변동 없음")


def intake_counts_text(counts: list[tuple[str, int]]) -> str:
    return " · ".join(f"{k} {n}곳" for k, n in counts) or "기록 없음"

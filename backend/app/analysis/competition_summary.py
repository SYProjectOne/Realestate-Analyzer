"""경쟁률 요약 (계약 2026-10-09.20, DECISIONS D28-5 Q4 — ``competition.json`` ``CompetitionSummary``).

저장된 경쟁률 행(청약홈 원문 그대로 — 구분·회차·주택형·공급·접수)에서 **산술로만** 목록·비교용 요약을 만든다:
1순위 해당지역 최고 경쟁률(접수 ÷ 공급)과 미달 행 수(접수 < 공급). 회차 문자열 머리말 비교는 파싱 규칙이지 판단이 아니다
(AGENTS 규칙 3). 순수 함수 — DB 접근 없음. Fact(라벨·출처) 조립은 API(``app.api.views.competition_summary_view``)가 한다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

__all__ = ["BASIS", "CompRow", "CompSummary", "is_basis_row", "summarize"]

BASIS: Final = "본청약 1순위 해당지역"
"""기준 행 설명(계약 ``CompetitionSummary.basis``)."""


@dataclass(frozen=True, slots=True)
class CompRow:
    """경쟁률 행 1개의 요약 입력(저장값 그대로)."""

    id: int
    kind: str
    round: str
    supply: int | None
    applied: int | None


@dataclass(frozen=True, slots=True)
class CompSummary:
    """요약 결과. 위치는 입력 순서의 번호(행 객체를 다시 찾지 않는다)."""

    basis_idx: tuple[int, ...]
    """기준 행(1순위 해당지역)의 입력 번호."""
    max_idx: int | None
    """최고 경쟁률 행 번호(공급 > 0 이고 공급·접수가 다 있는 행 중, 같은 값이면 앞 행). 없으면 None."""
    max_ratio: Decimal | None
    """접수 ÷ 공급 — 소수 2자리 ROUND_HALF_UP."""
    shortfall: int
    """기준 행 중 접수 < 공급 행 수(공급·접수가 다 있는 행만)."""
    incomplete: int
    """기준 행 중 공급 또는 접수가 없는 행 수."""


def is_basis_row(kind: str, round_text: str) -> bool:
    """1순위 해당지역 행: 구분 '본청약' + 회차가 '1순위'로 시작하고 '해당'을 포함(예 '1순위 해당', '1순위 해당지역')."""
    text = (round_text or "").replace(" ", "")
    return kind == "본청약" and text.startswith("1순위") and "해당" in text


def ratio(applied: int, supply: int) -> Decimal:
    """접수 ÷ 공급(공급 > 0) — 소수 2자리 ROUND_HALF_UP."""
    return (Decimal(applied) / Decimal(supply)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def summarize(rows: Sequence[CompRow]) -> CompSummary:
    """기준 행만 본다. 입력 순서 = id 순(같은 최댓값이면 앞 행)."""
    basis = tuple(i for i, r in enumerate(rows) if is_basis_row(r.kind, r.round))
    best: tuple[Decimal, int] | None = None
    shortfall = incomplete = 0
    for i in basis:
        r = rows[i]
        if r.supply is None or r.applied is None:
            incomplete += 1
            continue
        if r.applied < r.supply:
            shortfall += 1
        if r.supply <= 0:
            continue
        q = ratio(r.applied, r.supply)
        if best is None or q > best[0]:
            best = (q, i)
    return CompSummary(
        basis_idx=basis,
        max_idx=best[1] if best is not None else None,
        max_ratio=best[0] if best is not None else None,
        shortfall=shortfall,
        incomplete=incomplete,
    )

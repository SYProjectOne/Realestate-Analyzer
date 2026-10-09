"""가중 합·동점 규칙 (RA §6-4, contracts/schemas/score_run.json) — score.py·sensitivity.py 공용."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Final

from app.analysis._common import ZERO
from app.analysis.types import ComponentKey, RankedEntry

TIE_EPSILON: Final = Decimal("0.05")
TOP_N: Final = 5


def weighted_total(
    scores: Mapping[ComponentKey, Decimal | None], weights: Mapping[ComponentKey, Decimal]
) -> Decimal | None:
    """S = Σ w_i s_i (10진). 가중치가 있는 성분 중 하나라도 None이면 None(미계산)."""
    total = ZERO
    for key, w in weights.items():
        s = scores.get(key)
        if s is None:
            return None
        total += w * s
    return total


def rank_totals(
    totals: Mapping[int, Decimal | None], epsilon: Decimal = TIE_EPSILON
) -> dict[int, RankedEntry]:
    """total 내림차순(동률이면 complex_id 오름차순). 그룹 리더와 |ΔS| < epsilon이면 같은 rank·tie_group.

    rank는 경쟁 순위(1,2,2,4), tie_group은 2개 이상인 그룹에만 1부터. None은 순위 없음(결과에서 빠짐).
    """
    order = sorted(((cid, t) for cid, t in totals.items() if t is not None), key=lambda x: (-x[1], x[0]))
    out: dict[int, RankedEntry] = {}
    i = 0
    group = 0
    while i < len(order):
        leader_total = order[i][1]
        j = i + 1
        while j < len(order) and leader_total - order[j][1] < epsilon:
            j += 1
        members = order[i:j]
        tie_group = None
        if len(members) > 1:
            group += 1
            tie_group = group
        for cid, t in members:
            out[cid] = RankedEntry(complex_id=cid, total=t, rank=i + 1, tie_group=tie_group)
        i = j
    return out


def top_set(ranked: Mapping[int, RankedEntry], n: int = TOP_N) -> frozenset[int]:
    """TOP n 집합 = rank ≤ n인 단지 전부(공동 n위 포함)."""
    return frozenset(cid for cid, r in ranked.items() if r.rank <= n)

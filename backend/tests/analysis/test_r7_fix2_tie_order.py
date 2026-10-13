"""R7-FIX2(CEO 결정): 공동 순위 묶음 안의 표시 순서 = 종합 점수 높은 순 → complex_id. 한 키(``_ranking.display_order_key``)를
대시보드 TOP 5·단지 목록 ``sort=rank``·민감도·보고서가 같이 쓴다.

운영 사례(인천 score_run 6, base): 엘리프 검단 포레듀 4.6714(단지 41)·힐스테이트 구월아트파크 4.6404(단지 16) — |ΔS| 0.031 < 0.05 라
같은 rank 2. 예전 API 는 id 순(16 → 41), 보고서는 점수 순(41 → 16)이었다.
"""

# ruff: noqa: E501

from __future__ import annotations

from decimal import Decimal

from app.analysis._ranking import display_order_key, rank_totals, tie_order_key
from app.analysis.sensitivity import compute_sensitivity
from app.core.contracts_gen import Weights


def test_display_order_key_ties_by_total_then_id() -> None:
    totals = {16: Decimal("4.6404"), 41: Decimal("4.6714"), 3: Decimal("5.3809"), 9: Decimal("3.4838"), 27: None}
    ranked = rank_totals(totals)
    assert (ranked[41].rank, ranked[16].rank, ranked[41].tie_group) == (2, 2, ranked[16].tie_group)
    order = sorted(totals, key=lambda c: display_order_key(ranked[c].rank if c in ranked else None, totals[c], c))
    assert order == [3, 41, 16, 9, 27]  # 공동 2위 안은 점수 높은 41 먼저, 순위 없음은 뒤
    # 저장 정밀도(소수 4자리)로 같으면 complex_id
    assert tie_order_key(Decimal("4.61000"), 5) < tie_order_key(Decimal("4.6100"), 7)
    assert sorted([7, 5], key=lambda c: tie_order_key(Decimal("4.61004") if c == 7 else Decimal("4.610049"), c)) == [5, 7]
    # 문자열(목록 저장 키)·float 도 같은 순서
    assert tie_order_key("4.6714", 41) < tie_order_key(4.6404, 16)
    assert tie_order_key(None, 1) > tie_order_key(Decimal("0"), 99)


def test_sensitivity_top5_and_ranks_follow_display_order() -> None:
    """민감도 base_top5·변형 top5·ranks 도 같은 키 — 공동 순위 안에서 점수 높은 단지가 먼저(예전: id 순)."""
    keys = ("p10", "rerank", "gap", "benchmark", "supply", "liquidity")
    w = Weights.model_validate({**dict.fromkeys(keys, 0.15), "p10": 0.25})

    def flat(v: str) -> dict[str, Decimal | None]:
        return dict.fromkeys(keys, Decimal(v))

    scores = {
        1: flat("6"),  # 6.00 — 1위
        2: flat("4.61"),  # 공동 2위(낮은 점수, 작은 id)
        3: flat("4.64"),  # 공동 2위(높은 점수, 큰 id)
    }
    sens = compute_sensitivity(scores, w, snapshot_id=1, scenario_id=1)
    assert sens.base_top5 == [1, 3, 2]
    for cell in sens.cells:
        ranks = [(r.complex_id, r.rank, r.total) for r in cell.ranks]
        keyed = sorted(ranks, key=lambda x: display_order_key(x[1], x[2], x[0]))
        assert ranks == keyed, (cell.variant, ranks)
        assert cell.top5 == [c for c, r, _t in ranks if r is not None and r <= 5], cell.variant

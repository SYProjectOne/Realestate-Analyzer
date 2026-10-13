"""§6-6 민감도 (RA §6-6, §9 T12, contracts/schemas/sensitivity.json).

가중치 6개 각각 ±0.10: w_i' = clamp(w_i ± 0.10, 0, 1), 나머지는 원래 비율대로 w_j' = w_j × (1 − w_i')/(1 − w_i)
(나머지 합이 0이면 균등 분배). 12개 변형마다 종합 점수·순위(동점 규칙 동일)를 다시 구해 TOP 5 집합(rank ≤ 5,
공동 5위 포함)이 기준과 다르면 changed. 한 번이라도 바뀌면 unstable, 들어오거나 나간 단지가 unstable_complex_ids.
"""

# ruff: noqa: E501  (한국어 docstring·식 문자열은 화면 폭 기준으로 길다)

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from app.analysis._common import ZERO, clamp, to_float
from app.analysis._ranking import display_order_key, rank_totals, top_set, weighted_total
from app.analysis.types import COMPONENT_ORDER, ComponentKey, RankedEntry
from app.core.contracts_gen import Sensitivity, SensitivityCell, SensitivityRank, Weights

DELTA: Final = Decimal("0.10")
_Q6: Final = Decimal("0.000001")


def weights_map(w: Weights | Mapping[str, Decimal]) -> dict[ComponentKey, Decimal]:
    """성분 순서대로 10진 가중치(None은 뺀다)."""
    raw: Mapping[str, object] = w.model_dump() if isinstance(w, Weights) else w
    out: dict[ComponentKey, Decimal] = {}
    for key in COMPONENT_ORDER:
        v = raw.get(key)
        if v is None:
            continue
        out[key] = v if isinstance(v, Decimal) else Decimal(repr(v))
    return out


def variant_weights(
    w: Weights | Mapping[str, Decimal], component: ComponentKey, delta: Decimal
) -> dict[ComponentKey, Decimal]:
    base = weights_map(w)
    if component not in base:
        raise KeyError(f"가중치에 없는 성분: {component}")
    wi = base[component]
    wi2 = clamp(wi + delta, ZERO, Decimal(1))
    rest = [k for k in base if k != component]
    out: dict[ComponentKey, Decimal] = {}
    for k in base:
        if k == component:
            out[k] = wi2
        elif 1 - wi != 0:
            out[k] = base[k] * (1 - wi2) / (1 - wi)
        else:
            out[k] = (1 - wi2) / len(rest)
    return out


def _weights_model(w: Mapping[ComponentKey, Decimal]) -> Weights:
    return Weights.model_validate({k: float(v.quantize(_Q6, rounding=ROUND_HALF_UP)) for k, v in w.items()})


def _sorted_top(ranked: Mapping[int, RankedEntry], top: frozenset[int]) -> list[int]:
    """TOP 5 표시 순서 = ``_ranking.display_order_key``(순위 → 같은 순위 안은 점수 높은 순 → complex_id, R7-FIX2)."""
    return sorted(top, key=lambda cid: display_order_key(ranked[cid].rank, ranked[cid].total, cid))


def compute_sensitivity(
    scores: Mapping[int, Mapping[ComponentKey, Decimal | None]],
    base_weights: Weights,
    *,
    snapshot_id: int,
    scenario_id: int,
    score_run_id: int | None = None,
) -> Sensitivity:
    """scores: 순위 대상 단지의 성분 점수. 결과 cells는 성분 순서 × (+, −) 12개."""
    base_w = weights_map(base_weights)
    base_ranked = rank_totals({cid: weighted_total(s, base_w) for cid, s in scores.items()})
    base_top = top_set(base_ranked)
    cells: list[SensitivityCell] = []
    unstable: set[int] = set()
    changed_by_component: dict[ComponentKey, bool] = {}
    for key in base_w:
        for sign in (1, -1):
            delta = DELTA * sign
            vw = variant_weights(base_weights, key, delta)
            totals = {cid: weighted_total(s, vw) for cid, s in scores.items()}
            ranked = rank_totals(totals)
            top = top_set(ranked)
            entered = sorted(top - base_top)
            exited = sorted(base_top - top)
            changed = top != base_top
            unstable.update(entered, exited)
            changed_by_component[key] = changed_by_component.get(key, False) or changed
            # 이 변형의 순위 순(같은 순위 안은 점수 높은 순 → complex_id, R7-FIX2 — C10 이 순위로 다시 정렬해도 같다)
            order = {
                cid: display_order_key(ranked[cid].rank if cid in ranked else None, totals.get(cid), cid)
                for cid in base_top | top
            }
            shown = sorted(order, key=order.__getitem__)
            cells.append(
                SensitivityCell(
                    variant=f"{key}{'+' if sign > 0 else '-'}0.10",
                    component=key,
                    delta=float(delta),
                    weights=_weights_model(vw),
                    top5=_sorted_top(ranked, top),
                    ranks=[
                        SensitivityRank(
                            complex_id=cid,
                            rank=ranked[cid].rank if cid in ranked else None,
                            total=to_float(totals.get(cid)),
                        )
                        for cid in shown
                    ],
                    changed=changed,
                    entered=entered,
                    exited=exited,
                )
            )
    return Sensitivity(
        snapshot_id=snapshot_id,
        scenario_id=scenario_id,
        score_run_id=score_run_id,
        base_weights=base_weights,
        base_top5=_sorted_top(base_ranked, base_top),
        cells=cells,
        unstable=bool(unstable),
        unstable_complex_ids=sorted(unstable),
        stable_components=[k for k, ch in changed_by_component.items() if not ch],
    )

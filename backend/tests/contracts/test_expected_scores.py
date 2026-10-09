"""contracts/fixtures/incheon_gimpo_2026-10-08/expected_scores.json — RA §9 (a)단계 골든 시드.

보고서 구성 점수 6개를 입력으로 고정하고 가중 합·순위·동점만 검증한다(T1, T2, T7, T12 기대값의 원천).
"""

# ruff: noqa: E501  (한국어 assertion 메시지·표)
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry

from ._support import FIXTURE, load_json

D = Decimal
COMPONENTS = ["p10", "rerank", "gap", "benchmark", "supply", "liquidity"]
EXPECTED = load_json(FIXTURE / "expected_scores.json")
TOL = D("0.01")
EPS = D("0.05")

# RA §9 T1 원문: 그란테르 5.87 > 엘리프 5.70 > 한내들 5.33 > 스위첸(김포) 5.00 > 센트레빌 = 더샵 AB23 4.61 (±0.01, 공동 5위)
T1 = [("granter", "5.87", 1), ("elif", "5.70", 2), ("hannaedeul", "5.33", 3), ("switzen", "5.00", 4),
      ("centreville_educity", "4.61", 5), ("thesharp_ab23", "4.61", 5)]  # fmt: skip


def weighted(components: dict[str, Any], weights: dict[str, Any]) -> D | None:
    if any(components[k] is None for k in COMPONENTS):
        return None
    return sum((D(str(components[k])) * D(str(weights[k])) for k in COMPONENTS), D(0))


def ranks_with_ties(
    totals: dict[str, D], ids: dict[str, int], eps: D = EPS
) -> dict[str, tuple[int, int | None]]:
    order = sorted(totals, key=lambda k: (-totals[k], ids[k]))
    out: dict[str, tuple[int, int | None]] = {}
    i, group = 0, 0
    while i < len(order):
        members = [order[i]]
        j = i + 1
        while j < len(order) and totals[order[i]] - totals[order[j]] < eps:
            members.append(order[j])
            j += 1
        if len(members) > 1:
            group += 1
        for m in members:
            out[m] = (i + 1, group if len(members) > 1 else None)
        i = j
    return out


def must(total: D | None) -> D:
    assert total is not None
    return total


def scored() -> dict[str, dict[str, Any]]:
    return {c["key"]: c for c in EXPECTED["complexes"] if c["computed_total"] is not None}


def test_validates_against_schema(schema_registry: Registry[Any]) -> None:
    validator = Draft202012Validator(
        {"$ref": "expected_scores.json"}, registry=schema_registry, format_checker=FormatChecker()
    )
    assert [e.message for e in validator.iter_errors(EXPECTED)] == []


def test_sixteen_complexes_with_unique_keys() -> None:
    cs = EXPECTED["complexes"]
    assert len(cs) == 16
    assert len({c["key"] for c in cs}) == 16
    assert sorted(c["complex_id"] for c in cs) == list(range(1, 17))
    assert len(scored()) == 12
    for c in cs:
        if c["computed_total"] is None:
            assert c["judge_scope"] in ("보류", "참고") and c["expected_rank"] is None


def test_weights_are_base_scenario_and_sum_to_one() -> None:
    w = EXPECTED["weights"]
    assert w == {
        "p10": 0.35,
        "rerank": 0.20,
        "gap": 0.15,
        "benchmark": 0.10,
        "supply": 0.10,
        "liquidity": 0.10,
    }
    assert sum(D(str(v)) for v in w.values()) == D(1)


@pytest.mark.parametrize("key", sorted(scored()))
def test_weighted_sum_reproduces_report_total(key: str) -> None:
    c = scored()[key]
    total = weighted(c["components"], EXPECTED["weights"])
    assert total is not None
    assert D(str(c["computed_total"])) == total
    assert abs(total - D(str(c["report_total"]))) <= TOL, f"{key}: {total} vs 보고서 {c['report_total']}"
    assert total.quantize(D("0.01"), rounding=ROUND_HALF_UP) == D(str(c["report_total"])).quantize(D("0.01"))


def test_tie_rule_ranks() -> None:
    cs = scored()
    totals = {k: D(str(c["computed_total"])) for k, c in cs.items()}
    ids = {k: c["complex_id"] for k, c in cs.items()}
    got = ranks_with_ties(totals, ids)
    for k, c in cs.items():
        assert got[k] == (c["expected_rank"], c["tie_group"]), k


def test_t1_top5() -> None:
    cs = scored()
    for key, total, rank in T1:
        c = cs[key]
        computed = weighted(c["components"], EXPECTED["weights"])
        assert computed is not None and abs(computed - D(total)) <= TOL, key
        assert c["expected_rank"] == rank, key
    assert cs["centreville_educity"]["tie_group"] == cs["thesharp_ab23"]["tie_group"] is not None
    assert [(e["key"], e["rank"]) for e in EXPECTED["t1"]["order"]] == [(k, r) for k, _, r in T1]
    assert EXPECTED["t1"]["matches_report"] is True
    top5 = {k for k, c in cs.items() if c["expected_rank"] <= 5}
    assert top5 == {k for k, _, _ in T1}


def test_t2_scenario_b_tie() -> None:
    t2 = EXPECTED["t2"]
    assert t2["scenario"] == "B" and t2["confidence"] == 0.48
    tie_threshold = EXPECTED["tie_rule"]["decide_tie_confidence"]
    assert tie_threshold == 0.6 and t2["confidence"] < tie_threshold
    top2 = sorted(t2["probs"], key=lambda k: -t2["probs"][k])[:2]
    assert top2 == ["cantavil", "elif"] and t2["probs"] == {"cantavil": 0.54, "elif": 0.42}
    assert t2["expected"]["tie"] is True and t2["expected"]["chosen"] == ["cantavil", "elif"]
    b = EXPECTED["decide_integrated"]["B"]
    assert b["tie"] is True and b["judgment_seq"] == 127
    others = [v for k, v in EXPECTED["decide_integrated"].items() if k != "B"]
    assert all(d["tie"] is False for d in others), "기본·A·C·D는 confidence ≥ 0.6"


def test_t7_rerank_delta() -> None:
    t7 = EXPECTED["t7_incheon_only"]
    assert t7["rerank_judgment_seq"] == 124
    for row in t7["rows"]:
        assert D(str(row["delta_rerank"])) == D(str(row["relevance"])) - D(str(row["relevance_prev"])), row[
            "key"
        ]
    deltas = [D(str(r["delta_rerank"])) for r in t7["rows"]]
    assert min(deltas) == D("-0.06") and max(deltas) == D("0"), "보고서: 0~0.06 하락"


def test_t12_sensitivity_is_consistent_with_inputs() -> None:
    cs = scored()
    ids = {k: c["complex_id"] for k, c in cs.items()}
    base = {k: D(str(v)) for k, v in EXPECTED["weights"].items()}
    t12 = EXPECTED["t12_sensitivity"]
    base_tot = {k: must(weighted(c["components"], base)) for k, c in cs.items()}
    base5 = sorted(
        (k for k, (r, _) in ranks_with_ties(base_tot, ids).items() if r <= 5), key=lambda k: ids[k]
    )
    assert t12["base_top5"] == base5
    changed_any = set()
    assert len(t12["cells"]) == 12
    for cell in t12["cells"]:
        comp, sign = cell["variant"][:-5], cell["variant"][-5]
        delta = D("0.10") if sign == "+" else D("-0.10")
        wi = min(max(base[comp] + delta, D(0)), D(1))
        weights = {k: (wi if k == comp else v * (D(1) - wi) / (D(1) - base[comp])) for k, v in base.items()}
        tot = {k: must(weighted(c["components"], weights)) for k, c in cs.items()}
        top5 = sorted((k for k, (r, _) in ranks_with_ties(tot, ids).items() if r <= 5), key=lambda k: ids[k])
        assert cell["top5"] == top5, cell["variant"]
        assert cell["changed"] is (set(top5) != set(base5)), cell["variant"]
        if cell["changed"]:
            changed_any |= set(top5) ^ set(base5)
    assert t12["unstable"] is bool(changed_any)
    assert sorted(t12["unstable_keys"], key=lambda k: ids[k]) == sorted(changed_any, key=lambda k: ids[k])


def test_discrepancies_are_recorded() -> None:
    whats = " ".join(d["what"] for d in EXPECTED["discrepancies"])
    for needle in ("엘리프", "공동 순위", "rerank"):
        assert needle in whats

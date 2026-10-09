"""T10 사다리 시점·연율 (RA §6-3) · 민감도 변형 가중치 (RA §6-6)."""

# ruff: noqa: E501
from __future__ import annotations

from decimal import Decimal

import pytest

from app.analysis.ladder import annualize, annualized, ladder_targets, proposition_texts, target_label
from app.analysis.sensitivity import variant_weights
from app.analysis.scenarios import builtin

from ._support import ASOF

D = Decimal


def test_t10_three_horizons_and_common_3y_target() -> None:
    """고촌(즉시 입주) vs 리버프론트(2031-01 입주): move_in_plus_1y는 다르고 asof_plus_3y는 같다."""
    gochon = ladder_targets(ASOF, move_in_ym=None, immediate=True)
    river = ladder_targets(ASOF, move_in_ym="2031-01", immediate=False)
    assert set(gochon) == set(river) == {"move_in_plus_1y", "asof_plus_3y", "asof_plus_5y"}
    assert gochon["move_in_plus_1y"].target_ym == "2027-10" and gochon["move_in_plus_1y"].months_from_asof == 12
    assert river["move_in_plus_1y"].target_ym == "2032-01" and river["move_in_plus_1y"].months_from_asof == 63
    assert gochon["asof_plus_3y"].target_ym == river["asof_plus_3y"].target_ym == "2029-10"
    assert gochon["asof_plus_3y"].months_from_asof == 36
    assert gochon["asof_plus_5y"].target_ym == "2031-10" and gochon["asof_plus_5y"].months_from_asof == 60
    assert target_label("2032-01") == "2032 상반기" and target_label("2029-10") == "2029 하반기"


def test_move_in_in_past_uses_asof_plus_12() -> None:
    t = ladder_targets(ASOF, move_in_ym="2025-06", immediate=False)
    assert t["move_in_plus_1y"].target_ym == "2027-10"


def test_t10_annualized_rate() -> None:
    assert annualize(D("0.10"), 36) == D("0.0323")
    assert annualize(D("0.05"), 29) == D("0.0204")
    a = annualized(29)
    assert (a.p5, a.p10, a.p20) == (0.0204, 0.0402, 0.0784)  # contracts/schemas/ladder.json 예시
    with pytest.raises(ValueError):
        annualize(D("0.1"), 0)


def test_proposition_texts_template() -> None:
    texts = proposition_texts(
        name="엘리프 검단 포레듀", type_code="84A", asof_date=ASOF, price_text="5.78~6.08억, 공급가+발코니",
        horizon="move_in_plus_1y", move_in_ym="2028-03", target_ym="2029-03",
    )
    assert set(texts) == {"p5", "p10", "p20", "p_flat"}
    assert texts["p10"] == (
        "엘리프 검단 포레듀 전용 84A을 2026-10-08 현재 구매가(5.78~6.08억, 공급가+발코니)로 매수할 경우, "
        "입주(2028-03) 후 1년 시점인 2029 상반기 실거래가가 현재 구매가 대비 +10% 이상이다"
    )
    assert texts["p_flat"].endswith("이하(보합·하락)이다")


def test_variant_weights_clip_and_renormalize() -> None:
    w = builtin("base").weights
    v = variant_weights(w, "p10", D("0.10"))
    assert v["p10"] == D("0.45")
    assert abs(sum(v.values()) - 1) < D("1e-20")
    assert round(v["rerank"], 6) == D("0.169231")
    z = variant_weights(w, "benchmark", D("-0.10"))
    assert z["benchmark"] == D(0) and abs(sum(z.values()) - 1) < D("1e-20")
    # 0~1로 자른다
    one = {"p10": D(1), "rerank": D(0), "gap": D(0), "benchmark": D(0), "supply": D(0), "liquidity": D(0)}
    up = variant_weights(one, "p10", D("0.10"))
    assert up["p10"] == D(1) and abs(sum(up.values()) - 1) < D("1e-20")
    down = variant_weights(one, "p10", D("-0.10"))
    assert down["p10"] == D("0.9") and abs(sum(down.values()) - 1) < D("1e-20")
    assert down["rerank"] == D("0.02")  # 나머지 비율이 0이면 균등 분배

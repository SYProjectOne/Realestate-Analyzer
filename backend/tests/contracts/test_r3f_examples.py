"""R3f CORE4 — R3 6차 minor 8 (계약 2026-10-09.11): 예시 ``market.json`` 생활권 시세 표본 수 Fact 가 근거 문구와 맞는다.

리뷰: la_2 ``n_trades`` 가 0건 '재가공'인데 basis 는 '건수 미상'(그리고 저가 거래가 있다) — 0건 Fact 와 범위 값이 같이 있을 수 없다.
"""

# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[3] / "contracts" / "examples" / "market.json"


def test_m8_market_example_trade_count_matches_basis() -> None:
    doc = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    rows = doc["value"]["living_area_prices"]
    assert rows
    for row in rows:
        n = row["n_trades"]
        unknown = any(w in (row.get("basis") or "") for w in ("미상", "미확보"))
        if unknown:
            assert n["label"] == "확인 불가" and n["v"] is None and n.get("reason"), row["living_area"]
        else:
            assert isinstance(n["v"], int) and n["v"] > 0 and n["label"] != "확인 불가", row["living_area"]
        if n["v"] == 0:  # 0건이면 시세(중앙·하한·상한)가 있을 수 없다
            assert row["median_won"]["v"] is None, row["living_area"]

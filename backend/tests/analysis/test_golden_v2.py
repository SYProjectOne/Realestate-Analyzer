"""expected_scores_v2.json 골든 고정(사람 확인 2026-10-09: 세대수만 실측으로 교체 후 고정) — 회귀(RA §9 (b)).

- 생활권 id 는 픽스처 region.json 의 la_* 이고, 미분양은 unsold_scope_codes(시군구 코드)로 고른다
  (2026-10-09.2).
- 생활권 세대수 = 행안부 주민등록 세대수(contracts/fixtures/reference/jumin_households_202609.csv, 행정동)를
  행정동↔법정동 매핑(jscode KIKmix)으로 1:N 균등 분할해 생활권 법정동에 합산한 값(라벨 '추정(주민등록 세대)').
- 파일 안의 inputs 로 다시 계산하면 종합 점수 ±0.01, 순위·tie_group 이 파일과 같아야 한다.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from app.analysis.scenarios import builtin
from app.analysis.score import run_detailed
from app.collectors.reference.jscode import parse_jscode_zip
from app.collectors.stats.households import parse_household_csv
from app.core.contracts_gen import ScoreInputs
from app.normalize.living_area import HouseholdInput, aggregate_households

from ._support import EXPECTED_V2_PATH, FIXTURE, REPO, load_json, snapshot

pytestmark = pytest.mark.regress

REFERENCE = REPO / "contracts" / "fixtures" / "reference"
STATUS = "사람 확인 완료(2026-10-09, 세대수 실측 교체)"
TOL = Decimal("0.01")


def _v2() -> dict[str, Any]:
    data: dict[str, Any] = load_json(EXPECTED_V2_PATH)
    return data


def _region() -> dict[str, Any]:
    data: dict[str, Any] = load_json(FIXTURE / "region.json")
    return data


def test_v2_is_fixed_golden_after_human_check() -> None:
    v2 = _v2()
    assert v2["stage"] == "b" and v2["status"] == STATUS
    assert any("주민등록" in a and "세대" in a for a in v2["assumptions"])


def test_v2_living_areas_use_fixture_ids_and_unsold_scope_codes() -> None:
    v2 = _v2()
    region_ids = {la["id"]: la for la in _region()["living_areas"]}
    las = v2["inputs"]["living_areas"]
    assert {la["id"] for la in las} == set(region_ids)
    for la in las:
        assert la["id"].startswith("la_") and la["unsold_scope_codes"], la
        assert {c[:5] for c in region_ids[la["id"]]["legal_dong_codes"]} == set(la["unsold_scope_codes"])
    complexes = {c["complex"]["id"]: c["complex"] for c in load_json(FIXTURE / "complexes.json")}
    for cx in v2["inputs"]["complexes"]:
        assert cx["living_area"] == complexes[cx["complex_id"]]["living_area"], cx["name"]
    used = {u["scope_code"] for u in v2["inputs"]["unsold"]}
    assert used <= {c for la in las for c in la["unsold_scope_codes"]}


def test_v2_households_are_measured_from_jumin_csv() -> None:
    ym, recs = parse_household_csv((REFERENCE / "jumin_households_202609.csv").read_bytes())
    assert ym == "2026-09"
    stats = [HouseholdInput(r.scope_code, r.households) for r in recs if r.scope_kind == "admin_dong"]
    mix = parse_jscode_zip((REFERENCE / "jscode20260930.zip").read_bytes()).mappings
    aggs = aggregate_households(_region()["living_areas"], stats, mix)
    got = {la["id"]: la["households"] for la in _v2()["inputs"]["living_areas"]}
    assert got == {aid: a.households for aid, a in aggs.items()}
    assert all(isinstance(v, int) and v > 0 for v in got.values())


def test_v2_golden_reproduces_totals_ranks_and_ties() -> None:
    v2 = _v2()
    inputs = ScoreInputs.model_validate(v2["inputs"])
    detail = run_detailed(snapshot(), builtin("base"), inputs)
    totals = {t.complex_id: t for t in detail.result.totals}
    assert len(v2["complexes"]) == 16
    for row in v2["complexes"]:
        t = totals[row["complex_id"]]
        if row["total"] is None:
            assert t.total is None, row["key"]
        else:
            assert t.total is not None, row["key"]
            assert abs(Decimal(str(t.total)) - Decimal(str(row["total"]))) <= TOL, row["key"]
        assert (t.rank, t.tie_group) == (row["rank"], row["tie_group"]), row["key"]
    top5 = [r["key"] for r in v2["summary"]["top5_b"]]
    assert len(top5) >= 5

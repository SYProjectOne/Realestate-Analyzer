"""WP4 테스트 공용: 경로·픽스처 로더·입력 빌더. 지역명은 픽스처·테스트에만 나온다(AGENTS 규칙 15)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.contracts_gen import (
    AgePremiumCoef,
    ComplexScoreInput,
    FixedComponents,
    LadderInput,
    RegionScoreParams,
    RerankAnchor,
    RerankItem,
    ScoreInputs,
    Snapshot,
)

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
FIXTURE = REPO / "contracts" / "fixtures" / "incheon_gimpo_2026-10-08"
EXPECTED_PATH = FIXTURE / "expected_scores.json"
EXPECTED_V2_PATH = FIXTURE / "expected_scores_v2.json"
MIGRATION_0001 = REPO / "contracts" / "migrations" / "versions" / "0001_init.py"
ASOF = "2026-10-08"
COMPONENTS6 = ("p10", "rerank", "gap", "benchmark", "supply", "liquidity")


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


EXPECTED: dict[str, Any] = load_json(EXPECTED_PATH)
KEY_TO_ID: dict[str, int] = {c["key"]: c["complex_id"] for c in EXPECTED["complexes"]}
ID_TO_KEY: dict[int, str] = {v: k for k, v in KEY_TO_ID.items()}


def snapshot(snapshot_id: int = 12, asof: str = ASOF) -> Snapshot:
    return Snapshot(
        id=snapshot_id,
        region_id=1,
        asof_date=asof,
        status="building",
        degraded=False,
        created_at=f"{asof}T07:00:00+09:00",
    )


def region_params(c: float = 0.015, cap: int = 8, pct: float = 0.08) -> RegionScoreParams:
    return RegionScoreParams(
        age_premium_coef=AgePremiumCoef(c_per_year=c, cap_years=cap, label="추정"), supply_ref_pct=pct
    )


def make_complex(complex_id: int = 1, **over: Any) -> ComplexScoreInput:
    base: dict[str, Any] = {
        "complex_id": complex_id,
        "name": f"단지{complex_id}",
        "living_area": "la_1",
        "judge_scope": "판정 대상",
        "price_low_won": 578_000_000,
        "price_high_won": 608_000_000,
        "price_label": "확인됨",
        "move_in_ym": "2028-03",
        "immediate_move_in": False,
        "completed_year": None,
        "ladders": [],
        "winner_date": "2025-09-10",
        "resale_months": 36,
        "resale_release_on_registration": True,
        "residency_months": 0,
        "down_payment_pct": 5,
        "interim_terms_text": "중도금 60% 이자후불",
        "intake_status": "가능",
        "intake_path": "official_popup",
        "regulated": False,
        "rewin_restriction_years": 10,
        "has_priority_supply": False,
        "fixed_components": None,
    }
    base.update(over)
    return ComplexScoreInput.model_validate(base)


def make_inputs(**over: Any) -> ScoreInputs:
    base: dict[str, Any] = {
        "snapshot_id": 12,
        "asof_date": ASOF,
        "region": region_params(),
        "rerank": RerankAnchor(judgment_seq=124, status="ok", items=[], prev=None),
        "living_areas": [{"id": "la_1", "name": "생활권1", "households": 100_000}],
        "trades": [],
        "benchmarks": [],
        "supply": [],
        "unsold": [],
        "complexes": [],
    }
    base.update(over)
    return ScoreInputs.model_validate(base)


def ladder(
    p10: float | None, *, horizon: str = "move_in_plus_1y", status: str = "ok", seq: int | None = 68
) -> LadderInput:
    return LadderInput(
        horizon=horizon,  # type: ignore[arg-type]
        target_ym="2029-03",
        months_from_asof=29,
        p5=None if p10 is None else min(1.0, p10 + 0.05),
        p10=p10,
        p20=None if p10 is None else max(0.0, p10 - 0.1),
        p_flat=0.5,
        status=status,  # type: ignore[arg-type]
        judgment_seq=seq,
    )


def a_stage_inputs() -> ScoreInputs:
    """RA §9 (a)단계: 보고서 구성 점수를 fixed_components로, rerank는 #124 relevance 그대로."""
    complexes: list[ComplexScoreInput] = []
    items: list[RerankItem] = []
    for c in EXPECTED["complexes"]:
        comps = c["components"]
        fixed = FixedComponents(source="보고서 §12-4-3", **{k: comps[k] for k in COMPONENTS6})
        complexes.append(
            make_complex(
                c["complex_id"],
                name=c["name"],
                judge_scope=c["judge_scope"],
                price_low_won=None,
                price_high_won=None,
                fixed_components=fixed,
            )
        )
        rel = c["raw"]["rerank_relevance"]
        items.append(
            RerankItem(
                candidate_id=f"complex:{c['complex_id']}", complex_id=c["complex_id"], relevance=rel, rank=1
            )
        )
    # rank는 relevance 내림차순 경쟁 순위(같은 값 같은 순위)
    ordered = sorted(items, key=lambda i: -i.relevance)
    ranked: list[RerankItem] = []
    for idx, it in enumerate(ordered):
        rank = idx + 1
        if idx and ordered[idx - 1].relevance == it.relevance:
            rank = ranked[-1].rank
        ranked.append(it.model_copy(update={"rank": rank}))
    return make_inputs(
        rerank=RerankAnchor(judgment_seq=124, status="ok", items=ranked, prev=None), complexes=complexes
    )

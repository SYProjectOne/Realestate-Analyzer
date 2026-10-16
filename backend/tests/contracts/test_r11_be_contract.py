"""계약 2026-10-09.22 (R11-BE, DECISIONS D30-5·D30-6) — 'API 필요' 값 2종 추가 · 서버 문구 · 마이그레이션 0019.

버전 표시 4곳·CHANGELOG `.22`(있음/추가 표 · FE 차이 · 문구 변경 표), 새 선택 필드(시장 unsold_latest · Gap comps_median)가
원본 스키마·번들·예시에 있고 옛 저장본(키 없음)도 통과, 예시의 합계 = 내역 합, 문구 W1~W5 가 예시에 남지 않음, 0019 왕복.
"""

# ruff: noqa: E501

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic import command
from jsonschema import Draft202012Validator

from ._support import CONTRACTS, EXAMPLES, SCHEMAS, alembic_config, load_json, load_yaml

VERSION = "2026-10-09.22"


def _example(name: str) -> Any:
    return load_json(EXAMPLES / name)["value"]


def test_contract_version_is_22_everywhere() -> None:
    from app.core.protocols import CONTRACT_VERSION

    assert CONTRACT_VERSION == VERSION
    assert load_yaml(CONTRACTS / "openapi.yaml")["info"]["version"] == VERSION
    assert load_yaml(CONTRACTS / "openapi.bundled.yaml")["info"]["version"] == VERSION
    decisions = (CONTRACTS.parent / "docs" / "design" / "DECISIONS.md").read_text(encoding="utf-8")
    assert f"계약 버전: `{VERSION}`" in decisions
    changelog = (CONTRACTS / "CHANGELOG.md").read_text(encoding="utf-8")
    top = re.search(r"^## (\d{4}-\d{2}-\d{2}\.\d+)\b", changelog, re.M)
    assert top is not None and top.group(1) == VERSION


def test_changelog_22_tables() -> None:
    changelog = (CONTRACTS / "CHANGELOG.md").read_text(encoding="utf-8")
    entry = changelog.split(f"## {VERSION}", 1)[1].split("\n## ", 1)[0]
    assert "D30-5" in entry and "D30-6" in entry and "SHAPE_VERSION" in entry and "0019" in entry
    assert "### FE 차이(화면이 맞출 것)" in entry and "| # | 대상 | .21 | .22 | 결정 |" in entry
    for row in ("A1", "A2", "A3", "A4", "A5", "F1", "F2", "F3", "W1", "W2", "W3", "W4", "W5"):
        assert f"| {row} |" in entry, row
    assert entry.count("**추가**") == 2 and entry.count("**이미 있음**") == 3
    assert "handlers.gen.ts" in entry  # MSW 재생성은 이 브랜치 몫이 아님을 적는다


def test_new_optional_fields_in_schemas_and_bundle() -> None:
    market = load_json(SCHEMAS / "market.json")
    assert "unsold_latest" in market["properties"] and "unsold_latest" not in market["required"]
    latest = market["$defs"]["UnsoldLatest"]
    assert latest["required"] == ["ym", "total", "post_completion", "breakdown"]
    kpi = load_json(SCHEMAS / "dashboard.json")["$defs"]["Kpis"]["properties"]["unsold"]
    assert set(latest["properties"]) == set(kpi["properties"])  # 대시보드 KpiUnsold 와 같은 모양
    gap = load_json(SCHEMAS / "complex_detail.json")["$defs"]["Gap"]
    for key in ("comps_median", "comps_median_unadjusted"):
        assert key in gap["properties"] and key not in gap["required"], key
    bundled = load_yaml(CONTRACTS / "openapi.bundled.yaml")["components"]["schemas"]
    assert "UnsoldLatest" in bundled
    assert "comps_median" in bundled["Gap"]["properties"]
    assert "unsold_latest" in bundled["Market"]["properties"]


def test_generated_models_carry_new_fields() -> None:
    from app.core.contracts_gen import Gap, Market, UnsoldLatest

    assert "comps_median" in Gap.model_fields and "comps_median_unadjusted" in Gap.model_fields
    assert "unsold_latest" in Market.model_fields
    assert set(UnsoldLatest.model_fields) == {"ym", "total", "post_completion", "breakdown"}


def test_examples_carry_new_fields_consistently() -> None:
    market = _example("market.json")
    latest = market["unsold_latest"]
    assert latest["ym"] == max(p["ym"] for p in market["unsold"] if p["total"]["v"] is not None)
    assert sum(p["total"]["v"] for p in latest["breakdown"]) == latest["total"]["v"]
    assert sum(p["post_completion"]["v"] for p in latest["breakdown"]) == latest["post_completion"]["v"]
    assert latest["total"]["reason"] == f"지역 합계(시군구 {len(latest['breakdown'])}곳)"
    dash = _example("dashboard_base.json")["kpis"]["unsold"]
    assert (latest["total"]["v"], latest["post_completion"]["v"]) == (
        dash["total"]["v"],
        dash["post_completion"]["v"],
    )
    gaps = [_example("complex_detail_elif.json")["gap"], *_example("compare_b.json")["gaps"].values()]
    for g in gaps:
        med = g["comps_median"]
        assert med["prov"] == g["gap_pct"]["prov"] and med["label"] in ("재가공", "추정"), med
        subst = any(c["substitute"] for c in g["comps"])
        assert (med["label"] == "추정") == subst, g
        assert (g["comps_median_unadjusted"] is None) == (g["gap_pct_unadjusted"] is None)
    kaive = _example("complex_detail_kaive.json")["gap"]
    assert kaive["comps_median"]["label"] == "확인 불가" and kaive["comps_median_unadjusted"] is None


def test_examples_validate_and_old_stored_views_without_new_keys_pass() -> None:
    """선택 필드라 .22 전 발행 저장본(키 없음)도 계약 통과 — SHAPE_VERSION 그대로 1."""
    from app.snapshot_view import SHAPE_VERSION

    assert SHAPE_VERSION == 1
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    registry: Registry[Any] = Registry()
    for p in SCHEMAS.rglob("*.json"):
        doc = load_json(p)
        registry = registry.with_resource(
            doc["$id"], Resource.from_contents(doc, default_specification=DRAFT202012)
        )
    market = load_json(SCHEMAS / "market.json")
    detail = load_json(SCHEMAS / "complex_detail.json")
    mv = Draft202012Validator(market, registry=registry)
    dv = Draft202012Validator(detail, registry=registry)
    m = _example("market.json")
    mv.validate(m)
    mv.validate({k: v for k, v in m.items() if k != "unsold_latest"})
    for name in ("complex_detail_elif.json", "complex_detail_kaive.json"):
        d = _example(name)
        dv.validate(d)
        old = dict(
            d, gap={k: v for k, v in d["gap"].items() if k not in ("comps_median", "comps_median_unadjusted")}
        )
        dv.validate(old)


def test_examples_have_no_old_wording() -> None:
    """W1~W5: 예시(MSW 데이터)에 'P_mid' 사유·영어 분류명 사유가 남지 않는다(점수 성분 식 formula_text 는 예외)."""
    for p in EXAMPLES.glob("*.json"):
        text = p.read_text(encoding="utf-8")
        for bad in ("산술(P_mid", "P_mid × 계약금%", "P_mid − 대출한도", "금액 = P_mid", "확인 불가(P_mid"):
            assert bad not in text, (p.name, bad)
        assert not re.search(
            r"classify (제외 클래스|미해결)\([^)]*(public_|private_|non_apartment|out_of_scope|review)", text
        ), p.name


def test_sqlite_0018_0019_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """0019: score_component.median_won(BIGINT NULL) — head 에서 값이 들어가고, downgrade 0018 이 열만 뺀다 → head 다시."""
    url = f"sqlite:///{(tmp_path / 'r11.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = alembic_config(url)
    command.upgrade(cfg, "0018")
    engine = sa.create_engine(url)
    try:
        assert "median_won" not in {c["name"] for c in sa.inspect(engine).get_columns("score_component")}
        engine.dispose()
        command.upgrade(cfg, "head")
        engine = sa.create_engine(url)
        cols = {c["name"]: c for c in sa.inspect(engine).get_columns("score_component")}
        assert "median_won" in cols and cols["median_won"]["nullable"]
        assert {"unadjusted_gap_pct", "unadjusted_median_won"} <= set(cols)
        engine.dispose()
        command.downgrade(cfg, "0018")
        engine = sa.create_engine(url)
        cols2 = {c["name"] for c in sa.inspect(engine).get_columns("score_component")}
        assert "median_won" not in cols2 and "unadjusted_median_won" in cols2
        engine.dispose()
        command.upgrade(cfg, "head")
    finally:
        engine.dispose()


def test_model_matches_migration_column() -> None:
    from app.models import ScoreComponent

    col = ScoreComponent.__table__.c.median_won  # type: ignore[attr-defined]
    assert col.nullable and isinstance(col.type, sa.BigInteger)

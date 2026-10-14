"""계약 2026-10-09.20 (R9-API, DECISIONS D28-5) — 초보자 UI 데이터 요청 Q1·Q4·Q5·Q6·Q7·Q8·Q9 의 계약 모양.

버전 표시·CHANGELOG FE 차이 표·사유 코드 enum(서버 표와 같다)·정렬 키 패턴(서버와 같다)·공급 종류 어휘(SUPPLY_KIND)·
설명만 바꾼 D27-3·D25-13·예시(MSW 데이터)에 새 필드가 서버 함수와 같은 값으로 들어 있는지.
"""

# ruff: noqa: E501

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

from ._support import CONTRACTS, EXAMPLES, SCHEMAS, load_json, load_yaml

VERSION = "2026-10-09.20"


def _example(name: str) -> Any:
    return load_json(EXAMPLES / name)["value"]


def test_contract_version_is_20_or_later_everywhere() -> None:
    """버전 표시(protocols·openapi 원본·번들·DECISIONS·CHANGELOG 맨 위)가 같고 .20 이상이다. .21(R10-FOLLOW) 이후에도 .20
    항목은 CHANGELOG 에 남는다(현재 버전 단언은 ``test_r10_follow_contract``)."""
    from app.core.protocols import CONTRACT_VERSION

    assert CONTRACT_VERSION.startswith("2026-10-09.") and int(CONTRACT_VERSION.rsplit(".", 1)[1]) >= 20
    assert load_yaml(CONTRACTS / "openapi.yaml")["info"]["version"] == CONTRACT_VERSION
    assert load_yaml(CONTRACTS / "openapi.bundled.yaml")["info"]["version"] == CONTRACT_VERSION
    decisions = (CONTRACTS.parent / "docs" / "design" / "DECISIONS.md").read_text(encoding="utf-8")
    assert f"계약 버전: `{CONTRACT_VERSION}`" in decisions
    changelog = (CONTRACTS / "CHANGELOG.md").read_text(encoding="utf-8")
    top = re.search(r"^## (\d{4}-\d{2}-\d{2}\.\d+)\b", changelog, re.M)
    assert top is not None and top.group(1) == CONTRACT_VERSION
    assert f"## {VERSION}" in changelog


def test_changelog_20_has_fe_difference_table() -> None:
    changelog = (CONTRACTS / "CHANGELOG.md").read_text(encoding="utf-8")
    entry = changelog.split(f"## {VERSION}", 1)[1].split("\n## ", 1)[0]
    assert "D28-5" in entry and "R9_TESTS_API.md" in entry
    assert "### FE 차이(화면이 맞출 것)" in entry
    assert "| # | 대상 | .19 | .20 | 결정 |" in entry
    for q in ("Q1", "Q4", "Q5", "Q6", "Q7", "Q8", "Q9"):
        assert q in entry, q
    assert "SHAPE_VERSION" in entry  # 저장 모양 버전을 올리지 않은 까닭(선택 필드만)


def test_reason_code_enum_matches_server_table() -> None:
    from app.api.reason_codes import REASON_CODES

    enum = load_json(SCHEMAS / "fact.json")["$defs"]["ReasonCode"]["enum"]
    assert tuple(enum) == REASON_CODES
    bundled = load_yaml(CONTRACTS / "openapi.bundled.yaml")["components"]["schemas"]
    assert tuple(bundled["ReasonCode"]["enum"]) == REASON_CODES
    for name in ("CompetitionSummary", "PaymentAmounts"):
        assert name in bundled, name


def test_sort_pattern_matches_server_and_has_intake() -> None:
    from app.api.routers.snapshots import SORT_PATTERN

    src = load_yaml(CONTRACTS / "openapi.yaml")["components"]["parameters"]["ComplexSort"]
    assert src["schema"]["pattern"] == SORT_PATTERN
    assert re.match(SORT_PATTERN, "intake") and re.match(SORT_PATTERN, "-intake")
    assert not re.match(SORT_PATTERN, "intake_status")
    assert "가능 → 미정 → 확인 불가" in src["description"]


def test_supply_kind_uses_supply_kind_vocabulary() -> None:
    from app.models.complex import SUPPLY_KIND

    prop = load_json(SCHEMAS / "intake.json")["properties"]["supply_kind"]
    assert [v for v in prop["enum"] if v is not None] == list(SUPPLY_KIND)


def test_description_only_followups_d27_3_and_d25_13() -> None:
    detail = load_json(SCHEMAS / "complex_detail.json")
    assert "D27-1" in detail["properties"]["intake_current"]["description"]
    assert "나중에 기록된 수집 성공 행" in load_json(SCHEMAS / "intake.json")["description"]
    rule = load_json(SCHEMAS / "scenario.json")["$defs"]["RequirementRule"]["description"]
    assert "D25-11" in rule and "공통 조건" in rule


def test_new_fields_are_optional_for_stored_revisions() -> None:
    """D15-3: 저장 모양 버전을 올리지 않는다 — .20 필드는 모두 선택(옛 발행 저장본에 키가 없어도 계약 통과)."""
    from app.snapshot_view import SHAPE_VERSION

    assert SHAPE_VERSION == 1
    checks = {
        "fact.json": ["reason_code"],
        "intake.json": ["reason_code", "supply_kind", "supply_kind_basis"],
        "complex_row.json": ["down_payment_won", "competition_summary"],
        "score_row.json": [
            "price_low",
            "price_high",
            "resale_end",
            "move_in_ym",
            "gap_pct",
            "competition_summary",
        ],
        "complex_detail.json": ["competition_summary"],
        "change_event.json": ["summary", "field_label", "value_kind"],
        "competition.json": ["winning_score_min", "winning_score_max", "winning_score_avg"],
    }
    for name, fields in checks.items():
        doc = load_json(SCHEMAS / name)
        for f in fields:
            assert f in doc["properties"], (name, f)
            assert f not in doc.get("required", []), (name, f)
    d = load_json(SCHEMAS / "complex_detail.json")["$defs"]
    assert "payment_amounts" not in d["PriceRange"]["required"]
    assert "gap_score" not in d["Gap"]["required"]


def test_examples_carry_new_fields_with_server_rules() -> None:
    from app.analysis.price import share_won
    from app.api.change_text import change_summary, value_kind
    from app.api.reason_codes import reason_code

    page = _example("complexes_page.json")
    for it in page["items"]:
        dw = it["down_payment_won"]
        if dw["label"] != "확인 불가":
            mid = (Decimal(it["price_low"]["v"]) + Decimal(it["price_high"]["v"])) / 2
            assert dw["v"] == share_won(mid, Decimal(str(it["down_payment_pct"]["v"]))), it["complex_id"]
        assert it["competition_summary"]["basis"] == "본청약 1순위 해당지역"
    rows = {it["complex_id"]: it for it in page["items"]}
    for name in ("dashboard_base.json", "dashboard_b.json"):
        dash = _example(name)
        for t in dash["top5"]:
            for k in ("price_low", "price_high", "resale_end", "move_in_ym", "gap_pct"):
                assert t[k] == rows[t["complex_id"]][k], (name, t["complex_id"], k)
        un = dash["kpis"]["unsold"]
        assert un["total"]["reason"].startswith("지역 합계(") and un["breakdown"]
        assert sum(p["total"]["v"] for p in un["breakdown"]) == un["total"]["v"]
    elif_ = _example("complex_detail_elif.json")
    pa = elif_["price"]["payment_amounts"]
    assert pa["down_payment_won"]["label"] == "추정" and pa["down_payment_won"]["reason"].startswith(
        "산술(P_mid × 계약금"
    )
    assert elif_["gap"]["gap_score"] == elif_["gap"]["score"]
    assert elif_["intake_current"]["supply_kind"] in (None, "본청약", "무순위", "임의", "선착순")
    for ev in _example("changes.json"):
        assert ev["summary"] == change_summary(ev["entity"], ev["field"], ev["old_text"], ev["new_text"])
        assert ev["value_kind"] == value_kind(ev["old_text"], ev["new_text"], field=ev["field"])
    market = _example("market.json")
    names = {a["id"]: a["name"] for a in market["living_areas"]}
    for p in market["supply"]:
        assert p["living_area_name"] == names.get(p["living_area"] or "")
    for g in _example("intake_queue.json")["groups"]:
        for it in g["items"]:
            assert it["reason_code"] == (
                reason_code(it["reason"], it["http_status"]) if it["reason"] else None
            )

    def facts(o: Any) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if isinstance(o, dict):
            if {"v", "label", "prov", "checked_at"} <= set(o):
                out.append(o)
            for v in o.values():
                out.extend(facts(v))
        elif isinstance(o, list):
            for v in o:
                out.extend(facts(v))
        return out

    for name in (
        "complexes_page.json",
        "dashboard_base.json",
        "complex_detail_elif.json",
        "complex_detail_kaive.json",
        "compare_b.json",
        "market.json",
    ):
        for f in facts(_example(name)):
            if f["label"] == "확인 불가":
                assert f.get("reason_code") == reason_code(f["reason"]), (name, f)
    assert json.dumps(_example("compare_b.json"), ensure_ascii=False).count("_gap.raw") >= 1

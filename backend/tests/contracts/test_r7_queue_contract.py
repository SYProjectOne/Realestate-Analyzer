"""계약 2026-10-09.19 (R7-QUEUE, DECISIONS D26-2) — G7 접수 확인 대기열 ``GET /ops/intake-queue``."""

from __future__ import annotations

import re
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from ._support import CONTRACTS, EXAMPLES, SCHEMAS, build_schema_registry, load_json, load_yaml

VERSION = "2026-10-09.19"


def test_contract_version_is_19_everywhere() -> None:
    """버전 표시 4곳: protocols·openapi(원본·번들)·DECISIONS 5행·CHANGELOG 맨 위."""
    from app.core.protocols import CONTRACT_VERSION

    assert CONTRACT_VERSION == VERSION
    assert load_yaml(CONTRACTS / "openapi.yaml")["info"]["version"] == VERSION
    assert load_yaml(CONTRACTS / "openapi.bundled.yaml")["info"]["version"] == VERSION
    decisions = (CONTRACTS.parent / "docs" / "design" / "DECISIONS.md").read_text(encoding="utf-8")
    assert f"계약 버전: `{VERSION}`" in decisions
    changelog = (CONTRACTS / "CHANGELOG.md").read_text(encoding="utf-8")
    top = re.search(r"^## (\d{4}-\d{2}-\d{2}\.\d+)\b", changelog, re.M)
    assert top is not None and top.group(1) == VERSION


def test_changelog_19_has_fe_difference_table() -> None:
    changelog = (CONTRACTS / "CHANGELOG.md").read_text(encoding="utf-8")
    entry = changelog.split(f"## {VERSION}", 1)[1].split("\n## ", 1)[0]
    assert "D26-2" in entry and "/ops/intake-queue" in entry
    assert "### FE 차이(화면이 맞출 것)" in entry
    assert "| # | 대상 | .18 | .19 | 결정 |" in entry
    assert "R7_TESTS_QUEUE.md" in entry


def _op() -> dict[str, Any]:
    op: dict[str, Any] = load_yaml(CONTRACTS / "openapi.yaml")["paths"]["/ops/intake-queue"]["get"]
    return op


def test_operation_shape() -> None:
    op = _op()
    assert op["operationId"] == "getIntakeQueue" and op["tags"] == ["ops"]
    names = {(p.get("name") or p.get("$ref", "").rsplit("/", 1)[-1]) for p in op["parameters"]}
    assert names == {"region_id", "SnapshotQuery"}
    assert set(op["responses"]) == {"200", "401", "403", "404", "422", "500"}
    assert op["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/IntakeQueue"
    }
    # 판정기·쓰기 없음과 공유 토큰 403 이 설명에 있다
    assert "판정기 호출·DB 쓰기 없음" in op["description"] and "공유 링크 토큰" in op["description"]


def test_components_registered() -> None:
    comps = load_yaml(CONTRACTS / "openapi.yaml")["components"]["schemas"]
    for name in (
        "IntakeQueue",
        "IntakeQueueCategory",
        "IntakeQueueGroup",
        "IntakeQueueItem",
        "IntakeQueuePendingCheck",
    ):
        assert name in comps, name
    bundled = load_yaml(CONTRACTS / "openapi.bundled.yaml")["components"]["schemas"]
    assert bundled["IntakeQueueCategory"]["enum"] == [
        "collect_failed", "identity", "no_phrase", "unresolved", "not_judged", "other", "undecided",
    ]  # fmt: skip
    item = bundled["IntakeQueueItem"]["properties"]
    for key in (
        "evidence_url",
        "screenshot_raw_document_id",
        "checked_at",
        "http_status",
        "complex_name",
        "human_check_pending",
    ):
        assert key in item, key
    assert item["http_status"]["x-nonfact"]
    assert bundled["IntakeQueueGroup"]["properties"]["count"]["x-nonfact"]
    assert bundled["IntakeQueue"]["properties"]["total"]["x-nonfact"]


def _validator() -> Draft202012Validator:
    return Draft202012Validator(
        {"$ref": "intake_queue.json"}, registry=build_schema_registry(), format_checker=FormatChecker()
    )


def test_examples_valid_and_consistent() -> None:
    order = load_json(SCHEMAS / "intake_queue.json")["$defs"]["IntakeQueueCategory"]["enum"]
    bodies = [load_json(SCHEMAS / "intake_queue.json")["examples"][0]]
    bodies += [
        load_json(EXAMPLES / name)["value"] for name in ("intake_queue.json", "intake_queue_empty.json")
    ]
    v = _validator()
    for body in bodies:
        errors = [e.message for e in v.iter_errors(body)]
        assert errors == [], errors
        assert body["total"] == sum(g["count"] for g in body["groups"])
        cats = [g["category"] for g in body["groups"]]
        assert cats == sorted(cats, key=order.index)
        for g in body["groups"]:
            assert g["count"] == len(g["items"])
            assert all(
                it["status"] == ("미정" if g["category"] == "undecided" else "확인 불가") for it in g["items"]
            )


def test_schema_rejects_unknown_category_and_unofficial_path() -> None:
    body = load_json(EXAMPLES / "intake_queue.json")["value"]
    bad = {**body, "groups": [{**body["groups"][0], "category": "기타"}]}
    assert list(_validator().iter_errors(bad))
    item = {**body["groups"][0]["items"][0], "path": "unofficial_ref"}
    bad2 = {**body, "groups": [{**body["groups"][0], "items": [item, *body["groups"][0]["items"][1:]]}]}
    assert list(_validator().iter_errors(bad2))

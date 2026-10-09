"""contracts/schemas/**/*.json — 메타스키마 검증, $id·description·examples, 예시 검증, 조건 규칙(음성 테스트)."""

# ruff: noqa: E501  (한국어 assertion 메시지·표)
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry

from ._support import SCHEMAS, load_json, schema_paths, schema_rel

REQUIRED_FILES = [
    "fact.json",
    "label.json",
    "intake.json",
    "judgment_envelope.json",
    "error.json",
    "region.json",
    "region_candidate.json",
    "complex.json",
    "complex_type.json",
    "payment_terms.json",
    "score_run.json",
    "score_component.json",
    "score_row.json",
    "scenario.json",
    "decision.json",
    "ladder.json",
    "change_event.json",
    "job_run.json",
    "job_payloads/collect_daily.json",
    "job_payloads/collect_weekly.json",
    "job_payloads/rejudge.json",
    "job_payloads/report.json",
    "job_payloads/snapshot_publish.json",
    "job_payloads/reference_refresh.json",
    "job_payloads/region_bootstrap.json",
    "raw_document.json",
    "field_candidate.json",
    "claim.json",
    "expected_scores.json",
]

ALL = schema_paths()
IDS = [schema_rel(p) for p in ALL]


def validator_for(rel: str, registry: Registry[Any], pointer: str = "") -> Draft202012Validator:
    schema: dict[str, Any] = {"$ref": rel + (f"#{pointer}" if pointer else "")}
    return Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())


def errors(rel: str, registry: Registry[Any], value: Any, pointer: str = "") -> list[str]:
    return [e.message for e in validator_for(rel, registry, pointer).iter_errors(value)]


def test_required_schema_files_exist() -> None:
    missing = [f for f in REQUIRED_FILES if not (SCHEMAS / f).is_file()]
    assert missing == []


@pytest.mark.parametrize("path", ALL, ids=IDS)
def test_schema_is_valid_2020_12(path: Path) -> None:
    doc = load_json(path)
    assert doc.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(doc)


@pytest.mark.parametrize("path", ALL, ids=IDS)
def test_schema_has_id_title_description_examples(path: Path) -> None:
    doc = load_json(path)
    assert doc.get("$id") == path.name, "$id는 파일 이름(상대 URI)"
    assert isinstance(doc.get("title"), str) and doc["title"]
    assert isinstance(doc.get("description"), str) and len(doc["description"]) >= 20
    examples = doc.get("examples")
    assert isinstance(examples, list) and examples, "examples가 비어 있다"


@pytest.mark.parametrize("path", ALL, ids=IDS)
def test_schema_examples_validate(path: Path, schema_registry: Registry[Any]) -> None:
    rel = schema_rel(path)
    for i, example in enumerate(load_json(path)["examples"]):
        assert errors(rel, schema_registry, example) == [], f"{rel} examples[{i}]"


def test_label_has_exactly_five_values() -> None:
    assert load_json(SCHEMAS / "label.json")["enum"] == ["확인됨", "추정", "비공식", "재가공", "확인 불가"]


FACT_OK = {"v": 1, "label": "확인됨", "prov": "fp_1", "checked_at": "2026-10-07"}


@pytest.mark.parametrize(
    ("fact", "ok"),
    [
        (FACT_OK, True),
        ({"v": None, "label": "확인 불가", "reason": "403", "prov": None, "checked_at": "2026-10-07"}, True),
        ({"v": None, "label": "확인 불가", "prov": None, "checked_at": "2026-10-07"}, False),  # 사유 없음
        ({"v": None, "label": "확인 불가", "reason": "", "prov": None, "checked_at": None}, False),  # 빈 사유
        ({"v": None, "label": "확인됨", "prov": "fp_1", "checked_at": "2026-10-07"}, False),  # 값 없는 확인됨
        ({"v": 3, "label": "추정", "prov": None, "checked_at": "2026-10-07"}, False),  # 출처 없는 수치
        ({"v": 3, "label": "추정", "prov": "fp_1", "checked_at": "2026-10-07", "human": True}, False),
        ({"v": "가능", "label": "확인됨", "prov": "hc_1", "checked_at": "2026-10-07", "human": True}, True),
        ({"v": 3, "label": "빈칸", "prov": "fp_1", "checked_at": "2026-10-07"}, False),  # 라벨 5종 밖
        ({"v": 3, "label": "추정", "prov": "xx_1", "checked_at": "2026-10-07"}, False),  # prov 접두어
        ({"v": 3, "label": "추정", "prov": "fp_1", "checked_at": "2026/10/07"}, False),  # 날짜 형식
        ({"v": 3, "label": "추정", "prov": "fp_1"}, False),  # checked_at 필수
        (
            {"v": True, "label": "확인됨", "prov": "fp_1", "checked_at": "2026-10-07"},
            False,
        ),  # v는 number|string|null
    ],
)
def test_fact_rules(fact: dict[str, Any], ok: bool, schema_registry: Registry[Any]) -> None:
    assert (errors("fact.json", schema_registry, fact) == []) is ok


def test_intake_rules(schema_registry: Registry[Any]) -> None:
    base = {"status": "가능", "path": "official_popup", "checked_at": "2026-10-07"}
    assert errors("intake.json", schema_registry, base) == []
    assert errors("intake.json", schema_registry, {**base, "path": "unofficial_ref"}), (
        "비공식은 '가능'이 될 수 없다"
    )
    unknown = {
        "status": "확인 불가",
        "path": "official_popup",
        "checked_at": "2026-10-07",
        "http_status": 403,
    }
    assert errors("intake.json", schema_registry, unknown), "확인 불가는 reason 필수"
    assert errors("intake.json", schema_registry, {**unknown, "reason": "403"}) == []


def test_job_payloads_cover_every_job_name(schema_registry: Registry[Any]) -> None:
    job_names = load_json(SCHEMAS / "job_run.json")["$defs"]["JobName"]["enum"]
    assert job_names == [
        "collect.daily",
        "collect.weekly",
        "rejudge",
        "report",
        "snapshot.publish",
        "reference.refresh",
        "region.bootstrap",
        "claim.reverify",
        "backup",  # 계약 2026-10-09.8 (D11-8)
        "region.expand",  # 계약 2026-10-09.8 (D11-7)
    ]
    files = {p.stem for p in (SCHEMAS / "job_payloads").glob("*.json")}
    assert files == {n.replace(".", "_") for n in job_names}
    ok = {"job_name": "rejudge", "payload": {"snapshot_id": 1, "scenario_id": None, "reason": "x"}}
    assert errors("job_run.json", schema_registry, ok, "/$defs/JobCreate") == []
    bad = {"job_name": "rejudge", "payload": {"scenario_id": None, "reason": "x"}}
    assert errors("job_run.json", schema_registry, bad, "/$defs/JobCreate"), (
        "payload는 job_name별 스키마로 검증"
    )
    bad_fmt = {"job_name": "report", "payload": {"snapshot_id": 1, "format": "docx"}}
    assert errors("job_run.json", schema_registry, bad_fmt, "/$defs/JobCreate"), "보고서 형식은 html|pdf"


def test_weights_need_exactly_one_of_liquidity_or_move_in(schema_registry: Registry[Any]) -> None:
    w = {"p10": 0.35, "rerank": 0.2, "gap": 0.15, "benchmark": 0.1, "supply": 0.1}
    ptr = "/$defs/Weights"
    assert errors("scenario.json", schema_registry, {**w, "liquidity": 0.1}, ptr) == []
    assert errors("scenario.json", schema_registry, {**w, "move_in": 0.1}, ptr) == []
    assert errors("scenario.json", schema_registry, w, ptr)
    assert errors("scenario.json", schema_registry, {**w, "liquidity": 0.1, "move_in": 0.1}, ptr)


def test_judgment_envelope_result_shape_is_checked_per_tool(schema_registry: Registry[Any]) -> None:
    env = load_json(SCHEMAS / "judgment_envelope.json")["examples"][0]
    assert errors("judgment_envelope.json", schema_registry, env) == []
    broken = {**env, "result": {"probs": {}}}  # decide ok인데 selected·escaped 없음
    assert errors("judgment_envelope.json", schema_registry, broken)
    review = {**env, "status": "review", "result": {}}
    assert errors("judgment_envelope.json", schema_registry, review) == [], (
        "review 봉투는 result 모양을 강제하지 않는다"
    )


def test_report_format_is_html_or_pdf() -> None:
    fmt = load_json(SCHEMAS / "job_payloads" / "report.json")["properties"]["format"]["enum"]
    assert fmt == ["html", "pdf"]

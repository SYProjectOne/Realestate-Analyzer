"""contracts/openapi.yaml (원본) + openapi.bundled.yaml (자립 번들) — OAS 3.1 검증, 엔드포인트, 예시, Fact 규칙."""

# ruff: noqa: E501  (한국어 assertion 메시지·표)
from __future__ import annotations

import json
import re
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from ._support import OPENAPI_BUNDLED, OPENAPI_SRC, load_yaml

METHODS = ("get", "post", "put", "patch", "delete")

# RA §4-2 + DECISIONS D2-3 + /health (+ 목록 화면용으로 더한 GET /jobs, GET /reports)
REQUIRED_OPERATIONS = {
    ("get", "/health"),
    ("get", "/regions"),
    ("post", "/regions"),
    ("get", "/regions/resolve"),
    ("get", "/regions/{id}"),
    ("put", "/regions/{id}/living-areas"),
    ("get", "/regions/{id}/snapshots"),
    ("get", "/snapshots/{sid}/dashboard"),
    ("get", "/snapshots/{sid}/complexes"),
    ("get", "/snapshots/{sid}/complexes.csv"),
    ("get", "/complexes/{id}"),
    ("get", "/provenance/{prov_id}"),
    ("get", "/raw/{raw_document_id}"),
    ("get", "/snapshots/{sid}/compare"),
    ("get", "/snapshots/{sid}/sensitivity"),
    ("get", "/scenarios"),
    ("post", "/scenarios"),
    ("get", "/scenarios/{id}/preview"),
    ("post", "/jobs"),
    ("get", "/jobs"),
    ("get", "/jobs/{id}"),
    ("get", "/snapshots/{sid}/market"),
    ("get", "/snapshots/{sid}/changes"),
    ("get", "/ops/sources"),
    ("get", "/ops/judgments"),
    ("get", "/ops/checklist"),
    ("patch", "/ops/checklist/{id}"),
    ("post", "/ops/human-checks"),
    ("post", "/reports"),
    ("get", "/reports"),
    ("get", "/reports/{id}"),
    # 계약 2026-10-09.4 (R3 F3)
    ("get", "/snapshots/{sid}/claims"),
    ("patch", "/claims/{id}"),
    ("post", "/catalysts"),
    ("post", "/share-links"),
    ("get", "/share-links"),
    ("delete", "/share-links/{id}"),
}


def _bundled() -> dict[str, Any]:
    doc = load_yaml(OPENAPI_BUNDLED)
    assert isinstance(doc, dict)
    return doc


def _operations(doc: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    return [(m, p, op) for p, item in doc["paths"].items() for m, op in item.items() if m in METHODS]


def _resolve_response(doc: dict[str, Any], resp: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in resp:
        resolved: dict[str, Any] = doc["components"]["responses"][resp["$ref"].rsplit("/", 1)[1]]
        return resolved
    return resp


def _collect_examples() -> list[tuple[str, dict[str, Any], Any]]:
    doc = _bundled()
    out: list[tuple[str, dict[str, Any], Any]] = []
    for method, path, op in _operations(doc):
        for ctype, media in (op.get("requestBody", {}).get("content") or {}).items():
            for name, ex in (media.get("examples") or {}).items():
                out.append((f"{method} {path} request {ctype} {name}", media["schema"], ex["value"]))
        for code, resp in op["responses"].items():
            for ctype, media in (_resolve_response(doc, resp).get("content") or {}).items():
                if "schema" not in media or ctype != "application/json":
                    continue
                for name, ex in (media.get("examples") or {}).items():
                    out.append((f"{method} {path} {code} {name}", media["schema"], ex["value"]))
    return out


EXAMPLES = _collect_examples()


def test_source_openapi_is_valid_3_1() -> None:
    src = load_yaml(OPENAPI_SRC)
    assert src["openapi"].startswith("3.1")
    validate(src, base_uri=OPENAPI_SRC.as_uri())


def test_bundled_openapi_is_valid_and_self_contained(bundled: dict[str, Any]) -> None:
    validate(bundled)
    text = OPENAPI_BUNDLED.read_text(encoding="utf-8")
    refs = re.findall(r"\$ref: ['\"]?([^'\"\s}]+)", text)
    assert refs and all(r.startswith("#/") for r in refs), "번들에는 내부 $ref만 남아야 한다"
    assert "$id" not in json.dumps(bundled["components"]["schemas"]), "번들 스키마에서 $id를 지워야 한다"


def test_contract_version(bundled: dict[str, Any], source_openapi: dict[str, Any]) -> None:
    """info.version = CHANGELOG 맨 위 항목 = protocols.CONTRACT_VERSION."""
    from app.core.protocols import CONTRACT_VERSION

    changelog = (OPENAPI_SRC.parent / "CHANGELOG.md").read_text(encoding="utf-8")
    top = re.search(r"^## (\d{4}-\d{2}-\d{2}\.\d+)", changelog, re.M)
    assert top is not None
    assert CONTRACT_VERSION == top.group(1) == "2026-10-09.15"
    assert source_openapi["info"]["version"] == CONTRACT_VERSION
    assert bundled["info"]["version"] == CONTRACT_VERSION


def test_required_operations_present(bundled: dict[str, Any]) -> None:
    present = {(m, p) for m, p, _ in _operations(bundled)}
    assert REQUIRED_OPERATIONS - present == set()
    assert all(op.get("operationId") for _, _, op in _operations(bundled))


def test_servers_use_api_prefix_and_health_is_at_root_too(bundled: dict[str, Any]) -> None:
    assert bundled["servers"][0]["url"] == "/api"
    assert not any(p.startswith("/api") for p in bundled["paths"])
    assert {s["url"] for s in bundled["paths"]["/health"]["servers"]} == {"/", "/api"}


def test_bearer_security_and_readonly_rule(bundled: dict[str, Any]) -> None:
    scheme = bundled["components"]["securitySchemes"]["bearerAuth"]
    assert scheme == {**scheme, "type": "http", "scheme": "bearer"}
    assert "GET" in scheme["description"] and "403" in scheme["description"]
    assert bundled["security"] == [{"bearerAuth": []}]
    assert bundled["paths"]["/health"]["get"]["security"] == []


def test_operations_declare_error_responses(bundled: dict[str, Any]) -> None:
    problems = []
    for method, path, op in _operations(bundled):
        codes = set(op["responses"])
        if path != "/health" and "401" not in codes:
            problems.append(f"{method} {path}: 401")
        if "500" not in codes:
            problems.append(f"{method} {path}: 500")
        if method != "get" and "403" not in codes:
            problems.append(f"{method} {path}: 403 (읽기 전용 토큰)")
        if "requestBody" in op and "422" not in codes:
            problems.append(f"{method} {path}: 422")
        if "{" in path and path not in ("/regions/resolve",) and "404" not in codes:
            problems.append(f"{method} {path}: 404")
        if not any(c.startswith("2") for c in codes):
            problems.append(f"{method} {path}: 2xx")
        for code in codes - {"200", "201", "202"}:
            media = (_resolve_response(bundled, op["responses"][code]).get("content") or {}).get(
                "application/json"
            )
            # 헬스체크 503 = 같은 Health 본문
            want = "Health" if (path, code) == ("/health", "503") else "Error"
            if media is None or media["schema"] != {"$ref": f"#/components/schemas/{want}"}:
                problems.append(f"{method} {path} {code}: {want} 스키마")
    assert problems == []


def test_success_codes(bundled: dict[str, Any]) -> None:
    ops = {(m, p): op for m, p, op in _operations(bundled)}
    assert "201" in ops[("post", "/regions")]["responses"]
    assert "201" in ops[("post", "/scenarios")]["responses"]
    assert "201" in ops[("post", "/ops/human-checks")]["responses"]
    assert "202" in ops[("post", "/jobs")]["responses"]
    assert "202" in ops[("post", "/reports")]["responses"]


def test_every_json_body_has_an_example(bundled: dict[str, Any]) -> None:
    missing = []
    for method, path, op in _operations(bundled):
        for ctype, media in (op.get("requestBody", {}).get("content") or {}).items():
            if not media.get("examples"):
                missing.append(f"{method} {path} request {ctype}")
        for code, resp in op["responses"].items():
            media = (_resolve_response(bundled, resp).get("content") or {}).get("application/json")
            if media is not None and not media.get("examples"):
                missing.append(f"{method} {path} {code}")
    assert missing == []


@pytest.mark.parametrize(("where", "schema", "value"), EXAMPLES, ids=[e[0] for e in EXAMPLES])
def test_example_validates(where: str, schema: dict[str, Any], value: Any, bundled: dict[str, Any]) -> None:
    registry: Registry[Any] = Registry().with_resource(
        "urn:oas", Resource.from_contents(bundled, default_specification=DRAFT202012)
    )
    rewritten = json.loads(json.dumps(schema).replace('"#/components/', '"urn:oas#/components/'))
    validator = Draft202012Validator(rewritten, registry=registry, format_checker=FormatChecker())
    errs = [f"{list(e.absolute_path)}: {e.message}" for e in validator.iter_errors(value)]
    assert errs == [], where


def test_examples_cover_all_screens() -> None:
    """G0~G8 모든 화면을 MSW로 그릴 수 있는 예시가 있다(특수 상태 포함)."""
    names = {e[0] for e in EXAMPLES}
    must = [
        "get /regions/resolve 200",  # G0
        "put /regions/{id}/living-areas 202",  # G0-2 (계약 .11 — 202 + job_id)
        "get /snapshots/{sid}/dashboard 200 base",  # G1
        "get /snapshots/{sid}/dashboard 200 scenarioB",  # G1 상황 토글(동률)
        "get /snapshots/{sid}/complexes 200",  # G2
        "get /complexes/{id} 200 elif",  # G3 모든 탭
        "get /complexes/{id} 200 preNotice",  # G3 공고 전 빈 상태
        "get /snapshots/{sid}/compare 200",  # G4
        "get /snapshots/{sid}/sensitivity 200",  # C10
        "get /scenarios/{id}/preview 200",  # G5
        "get /snapshots/{sid}/market 200",  # G6
        "get /ops/sources 200",  # G7
        "get /ops/judgments 200",
        "post /ops/human-checks 201",
        "get /reports 200",  # G8
    ]
    assert [m for m in must if not any(n.startswith(m) for n in names)] == []
    values = {e[0]: e[2] for e in EXAMPLES}
    detail = next(v for k, v in values.items() if k.startswith("get /complexes/{id} 200 elif"))
    for tab in ("types", "payment", "events", "competition", "intake", "catalysts", "judgments"):
        assert detail[tab], f"ComplexDetail 예시의 {tab} 탭이 비었다"
    assert {r["horizon"] for r in detail["ladder"]} == {"move_in_plus_1y", "asof_plus_3y", "asof_plus_5y"}
    assert detail["gap"]["comps"]
    compare = next(v for k, v in values.items() if k.startswith("get /snapshots/{sid}/compare 200"))
    assert len(compare["ids"]) == 3
    tie = compare["decisions"]["B"]
    assert tie["tie"] is True and tie["confidence"]["v"] == 0.48
    tied = [i for i in tie["items"] if i["tie"]]
    assert sorted(i["prob"]["v"] for i in tied) == [0.42, 0.54] and all(i["chosen"] for i in tied)
    sens = next(v for k, v in values.items() if k.startswith("get /snapshots/{sid}/sensitivity 200"))
    assert len(sens["cells"]) == 12
    market = next(v for k, v in values.items() if k.startswith("get /snapshots/{sid}/market 200"))
    for key in ("benchmarks", "supply", "unsold", "catalysts"):
        assert market[key], f"Market.{key}"
    assert len([u for u in market["unsold"] if u["scope_code"] == "41570"]) == 24, "C5는 24개월"


FACT_NAME = re.compile(
    r"(_won|_m2|_pct)$|^(total|p10|p5|p20|p_flat|households|stage_prob|inclusion_prob|move_in_ym|resale_end)$"
)
# Fact가 아닌 숫자를 의도적으로 허용하는 곳: 설정값·가중치 가정·연율 표시 계산
FACT_EXEMPT = {
    ("Region", "supply_ref_pct"),
    ("Weights", "p10"),
    ("LadderAnnualized", "p5"),
    ("LadderAnnualized", "p10"),
    ("LadderAnnualized", "p20"),
    ("SensitivityRank", "total"),  # 민감도 변형 점수: 가중치 가정의 산출물(C10 표·선 전용)
    ("ComplexRowPage", "total"),  # 목록 건수
    ("JudgmentOps", "total"),  # 목록 건수
    ("Components", "p10"),  # ComponentView(score: Fact …)를 감싼 객체
    ("ScenarioParams", "equity_won"),  # 사용자가 입력한 조건값(출처 데이터가 아님)
    ("ScenarioParams", "loan_limit_won"),
    ("ScenarioParams", "preferred_area_m2"),
}


def _reachable_components(doc: dict[str, Any]) -> set[str]:
    seen: set[str] = set()
    stack: list[Any] = [doc["paths"], doc["components"]["responses"]]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
                name = ref.rsplit("/", 1)[1]
                if name not in seen:
                    seen.add(name)
                    stack.append(doc["components"]["schemas"][name])
            stack.extend(v for k, v in node.items() if k not in ("examples", "example"))
        elif isinstance(node, list):
            stack.extend(node)
    return seen


def _is_fact(prop: dict[str, Any]) -> bool:
    fact = {"$ref": "#/components/schemas/Fact"}
    return (
        prop == fact
        or (prop.get("description") is not None and prop.get("$ref") == fact["$ref"])
        or any(alt == fact for alt in prop.get("anyOf", []))
    )


def test_numeric_fields_in_api_responses_are_facts(bundled: dict[str, Any]) -> None:
    """RA §4-1: 수치·날짜는 맨값으로 나가지 않는다 — 금액·면적·퍼센트·확률·점수 이름의 필드는 Fact."""
    schemas = bundled["components"]["schemas"]
    bad = []
    for name in sorted(_reachable_components(bundled)):
        props = schemas[name].get("properties") or {}
        for prop_name, prop in props.items():
            if FACT_NAME.search(prop_name) and (name, prop_name) not in FACT_EXEMPT and not _is_fact(prop):
                bad.append(f"{name}.{prop_name}")
    assert bad == []

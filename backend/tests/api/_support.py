"""API 테스트 공용: 경로·토큰·계약 응답 검증기 (WP5)."""

from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
CONTRACTS = REPO / "contracts"
FIXTURE = CONTRACTS / "fixtures" / "incheon_gimpo_2026-10-08"
OPENAPI_BUNDLED = CONTRACTS / "openapi.bundled.yaml"

WRITE_TOKEN = "w" * 32
READ_TOKEN = "r" * 32
WRITE = {"Authorization": f"Bearer {WRITE_TOKEN}"}
READ = {"Authorization": f"Bearer {READ_TOKEN}"}

_URN = "urn:openapi-bundled"


@functools.cache
def bundled() -> dict[str, Any]:
    with OPENAPI_BUNDLED.open(encoding="utf-8") as f:
        doc: dict[str, Any] = yaml.safe_load(f)
    return doc


@functools.cache
def _registry() -> Registry[Any]:
    return Registry().with_resource(
        _URN, Resource.from_contents(bundled(), default_specification=DRAFT202012)
    )


def _operation(op_id: str) -> tuple[str, str, dict[str, Any]]:
    for path, item in bundled()["paths"].items():
        for method, op in item.items():
            if isinstance(op, dict) and op.get("operationId") == op_id:
                return path, method, op
    raise KeyError(op_id)


def response_schema(op_id: str, status: int, content_type: str = "application/json") -> dict[str, Any]:
    _, _, op = _operation(op_id)
    resp = op["responses"][str(status)]
    if "$ref" in resp:
        name = resp["$ref"].rsplit("/", 1)[-1]
        resp = bundled()["components"]["responses"][name]
    schema: dict[str, Any] = resp["content"][content_type]["schema"]
    return schema


def _rewrite(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: (_URN + v if k == "$ref" and isinstance(v, str) and v.startswith("#") else _rewrite(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_rewrite(v) for v in obj]
    return obj


def validate(op_id: str, status: int, body: Any) -> None:
    """응답 본문이 openapi.bundled.yaml 의 그 operation·status 스키마를 통과하는지(형식 검사 포함)."""
    schema = _rewrite(response_schema(op_id, status))
    validator = Draft202012Validator(schema, registry=_registry(), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(body), key=lambda e: list(e.absolute_path))
    if errors:
        msgs = [f"{'/'.join(map(str, e.absolute_path))}: {e.message[:300]}" for e in errors[:10]]
        raise AssertionError(f"{op_id} {status} 응답이 계약과 다르다:\n" + "\n".join(msgs))


FACT_KEYS = {"v", "label", "prov", "checked_at"}
_PROV_RE = re.compile(r"^(fp|sc|st|jl|hc|rd|cs)_[0-9A-Za-z_.:-]+$")


def iter_facts(obj: Any, path: str = "$") -> list[tuple[str, dict[str, Any]]]:
    """응답 안의 Fact 전부(경로, Fact)."""
    out: list[tuple[str, dict[str, Any]]] = []
    if isinstance(obj, dict):
        if set(obj) >= FACT_KEYS and isinstance(obj.get("label"), str):
            out.append((path, obj))
        for k, v in obj.items():
            out.extend(iter_facts(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(iter_facts(v, f"{path}[{i}]"))
    return out


def assert_facts_labelled(body: Any) -> int:
    """모든 Fact 에 라벨이 있고, '확인 불가'가 아니면 v·prov 가 있다(AGENTS 규칙 5)."""
    facts = iter_facts(body)
    for path, f in facts:
        assert f["label"], path
        if f["label"] == "확인 불가":
            assert f.get("reason"), f"{path}: 확인 불가인데 reason 없음"
        else:
            assert f["v"] is not None, f"{path}: 값 없음 {f}"
            assert f["prov"] and _PROV_RE.match(f["prov"]), f"{path}: prov 없음 {f}"
    return len(facts)

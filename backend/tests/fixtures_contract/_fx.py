"""회귀 픽스처 테스트 공용 경로·로더 (WP9).

픽스처: contracts/fixtures/incheon_gimpo_2026-10-08/ (RA §4-5, §9). 스키마: contracts/schemas/.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
CONTRACTS = REPO / "contracts"
SCHEMAS = CONTRACTS / "schemas"
FIXTURES = CONTRACTS / "fixtures"
FIXTURE = FIXTURES / "incheon_gimpo_2026-10-08"
TOOLS = FIXTURES / "tools"
JUDGMENTS = FIXTURE / "judgments"
RAW = FIXTURE / "raw"

LABELS = {"확인됨", "추정", "비공식", "재가공", "확인 불가"}
FACT_KEYS = {"v", "label", "prov", "checked_at"}


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@cache
def registry() -> Registry[Any]:
    reg: Registry[Any] = Registry()
    for path in sorted(SCHEMAS.rglob("*.json")):
        rel = path.relative_to(SCHEMAS).as_posix()
        reg = reg.with_resource(rel, Resource.from_contents(load_json(path), default_specification=DRAFT202012))
    return reg


@cache
def validator(ref: str) -> Draft202012Validator:
    """ref 예: 'region.json', 'complex.json#/$defs/ComplexBundle'."""
    return Draft202012Validator({"$ref": ref}, registry=registry(), format_checker=FormatChecker())


def schema_errors(ref: str, value: Any) -> list[str]:
    return [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in validator(ref).iter_errors(value)]


def is_fact(node: Any) -> bool:
    return isinstance(node, dict) and FACT_KEYS <= set(node)


def iter_facts(node: Any, path: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    """JSON 트리 안의 Fact({v, label, prov, checked_at})를 경로와 함께 전부 돌려준다."""
    if is_fact(node):
        yield path, node
        return
    if isinstance(node, dict):
        for k, v in node.items():
            yield from iter_facts(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from iter_facts(v, f"{path}/{i}")


def load_tool(name: str) -> ModuleType:
    """contracts/fixtures/tools/<name>.py 를 모듈로 읽는다(패키지 아님)."""
    path = TOOLS / f"{name}.py"
    mod_name = f"_fixture_tool_{name}"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, path)
    assert spec is not None and spec.loader is not None, f"{path} 없음"
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module

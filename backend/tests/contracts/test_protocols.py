"""backend/app/core/protocols.py — RA §4-3 Protocol 전부, 시그니처, docstring 규칙, input_hash, mypy·ruff."""

# ruff: noqa: E501  (한국어 assertion 메시지·표)
from __future__ import annotations

import inspect
import re
import subprocess
import sys
import typing
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.core import protocols as p

from ._support import BACKEND, SCHEMAS, load_json

PROTOCOLS = ["Collector", "Parser", "Resolver", "JudgeAdapter", "ClaimSplitter", "ScoreEngine", "RequirementPrecalc",
             "Exporter"]  # fmt: skip
JUDGE_METHODS = ["screen", "extract", "audit", "classify", "compare", "noul", "rerank", "decide", "verify"]
DTOS = ["RawDocument", "FieldCandidate", "ResolvedFields", "JudgmentEnvelope", "Claim", "ScoreInputs",
        "ScoreRunResult", "ComponentScore", "RequirementResult"]  # fmt: skip


@pytest.mark.parametrize("name", PROTOCOLS)
def test_protocol_exists_with_rules_docstring(name: str) -> None:
    proto = getattr(p, name)
    assert getattr(proto, "_is_protocol", False), name
    assert getattr(proto, "_is_runtime_protocol", False), f"{name}는 runtime_checkable"
    doc = inspect.getdoc(proto) or ""
    assert "규칙" in doc and len(doc) > 150, f"{name} docstring에 RA §4-3 규칙이 없다"


@pytest.mark.parametrize("name", DTOS)
def test_dto_is_generated_pydantic_model(name: str) -> None:
    model = getattr(p, name)
    assert issubclass(model, BaseModel)
    assert model.__module__ == "app.core.contracts_gen", "DTO는 스키마에서 생성한다"


def _signature(proto: type, method: str) -> inspect.Signature:
    return inspect.signature(getattr(proto, method))


def test_method_signatures_follow_ra() -> None:
    hints = {
        ("Collector", "fetch"): ["self", "region", "snapshot", "since"],
        ("Parser", "parse"): ["self", "raw"],
        ("Resolver", "resolve"): ["self", "candidates"],
        ("ClaimSplitter", "split"): ["self", "text", "section", "snapshot_id", "complex_id"],
        ("ScoreEngine", "run"): ["self", "snapshot", "scenario", "inputs"],
        ("RequirementPrecalc", "evaluate"): ["self", "complex", "scenario", "asof_date"],
        ("Exporter", "render"): ["self", "snapshot", "fmt", "compare_snapshot"],
    }
    for (proto, method), params in hints.items():
        assert list(_signature(getattr(p, proto), method).parameters) == params, f"{proto}.{method}"
    assert _signature(p.Exporter, "render").parameters["compare_snapshot"].default is None
    returns = {
        ("Collector", "fetch"): "list[RawDocument]",
        ("Parser", "parse"): "list[FieldCandidate]",
        ("Resolver", "resolve"): "ResolvedFields",
        ("ClaimSplitter", "split"): "list[Claim]",
        ("ScoreEngine", "run"): "ScoreRunResult",
        ("RequirementPrecalc", "evaluate"): "RequirementResult",
        ("Exporter", "render"): "Path",
    }
    for (proto, method), ret in returns.items():
        assert _signature(getattr(p, proto), method).return_annotation == ret, f"{proto}.{method}"


def test_judge_adapter_has_nine_methods() -> None:
    assert tuple(JUDGE_METHODS) == p.JUDGE_TOOLS
    assert typing.get_args(p.JudgeTool) == tuple(JUDGE_METHODS)
    for method in JUDGE_METHODS:
        sig = _signature(p.JudgeAdapter, method)
        assert list(sig.parameters) == ["self", "payload", "purpose"], method
        assert sig.return_annotation == "JudgmentEnvelope", method
    assert issubclass(p.JudgeUnavailable, Exception)
    schema_tools = load_json(SCHEMAS / "judgment_envelope.json")["$defs"]["JudgeTool"]["enum"]
    assert schema_tools == JUDGE_METHODS


def test_exporter_formats_are_html_and_pdf() -> None:
    assert typing.get_args(p.ExportFormat) == ("html", "pdf")
    assert _signature(p.Exporter, "render").parameters["fmt"].annotation == "ExportFormat"


def test_runtime_checkable_with_a_stub() -> None:
    class Stub:
        adapter_version = "0+jev-mcp@test"

    for method in JUDGE_METHODS:
        setattr(Stub, method, lambda self, payload, purpose: None)
    assert isinstance(Stub(), p.JudgeAdapter)

    class NotAnAdapter:
        def screen(self, payload: object, purpose: str) -> None: ...

    assert not isinstance(NotAnAdapter(), p.JudgeAdapter)


def test_input_hash_is_canonical() -> None:
    a = p.input_hash("decide", "decide:scenario_B", {"b": 1, "a": [1, "가"]}, "0.1.0+jev-mcp@1.13.0")
    b = p.input_hash("decide", "decide:scenario_B", {"a": [1, "가"], "b": 1}, "0.1.0+jev-mcp@1.13.0")
    assert a == b
    pattern = load_json(SCHEMAS / "judgment_envelope.json")["properties"]["input_hash"]["pattern"]
    assert re.fullmatch(pattern, a)
    assert a != p.input_hash("decide", "decide:scenario_A", {"a": [1, "가"], "b": 1}, "0.1.0+jev-mcp@1.13.0")
    assert a != p.input_hash("decide", "decide:scenario_B", {"a": [1, "가"], "b": 1}, "0.1.0+jev-mcp@1.14.0")
    # 고정값 회귀: 정의(키 정렬, 구분자 ',' ':', ensure_ascii=False)가 바뀌면 전체 캐시가 무효가 된다
    assert p.input_hash("screen", "x", {}, "v") == (
        "sha256:"
        + __import__("hashlib")
        .sha256(b'{"adapter_version":"v","payload":{},"purpose":"x","tool":"screen"}')
        .hexdigest()
    )


def test_contract_version_matches_changelog() -> None:
    changelog = (BACKEND.parent / "contracts" / "CHANGELOG.md").read_text(encoding="utf-8")
    top = re.search(r"^## (\d{4}-\d{2}-\d{2}\.\d+)\b", changelog, re.M)
    assert top is not None, "CHANGELOG에 버전 항목"
    assert p.CONTRACT_VERSION == top.group(1) == "2026-10-09.7", "맨 위 항목 = 현재 계약"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", *args],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


@pytest.mark.slow
def test_mypy_strict_models_and_protocols() -> None:
    proc = _run("mypy", "--strict", "app/models", "app/core/protocols.py", "app/core/contracts_gen.py")
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.slow
def test_ruff_clean() -> None:
    targets = ["app/models", "app/core/protocols.py", "app/core/contracts_gen.py", "scripts/gen_contracts.py",
               "tests/contracts"]  # fmt: skip
    assert all((BACKEND / t).exists() for t in targets)
    proc = _run("ruff", "check", *targets)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    proc = _run("ruff", "format", "--check", *targets)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_protocols_module_has_no_region_names() -> None:
    """AGENTS 15: 지역명은 코드에 하드코딩하지 않는다(픽스처·테스트·예시 제외)."""
    names = ["인천", "김포", "송도", "검단", "계양", "Incheon", "Gimpo"]
    sources = [BACKEND / "app" / "core" / "protocols.py", *sorted((BACKEND / "app" / "models").glob("*.py"))]
    hits = [(Path(s).name, n) for s in sources for n in names if n in Path(s).read_text(encoding="utf-8")]
    assert hits == []

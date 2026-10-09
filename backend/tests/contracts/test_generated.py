"""생성물: openapi.bundled.yaml·contracts_gen.py 재생성 diff 0, 번들 = 스키마 파일, 생성 모델이 예시를 받아들인다."""

from __future__ import annotations

import subprocess
import sys
from typing import Any

import pytest
from pydantic import BaseModel

from ._support import BACKEND, OPENAPI_BUNDLED, load_json, load_yaml, schema_paths

ScenarioExample = tuple[str, str, Any]


def test_gen_contracts_check_is_clean() -> None:
    """원본(schemas/·openapi.yaml·examples/)을 고치고 생성물을 안 돌렸으면 실패한다."""
    proc = subprocess.run(
        [sys.executable, "scripts/gen_contracts.py", "--check"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_bundle_components_mirror_schema_files() -> None:
    bundled = load_yaml(OPENAPI_BUNDLED)
    comps = bundled["components"]["schemas"]
    for path in schema_paths():
        doc = load_json(path)
        assert doc["title"] in comps, path.name
        assert comps[doc["title"]].get("description") == doc["description"]
        for key, sub in (doc.get("$defs") or {}).items():
            assert (sub.get("title") or key) in comps, f"{path.name}#/$defs/{key}"


def _model_examples() -> list[ScenarioExample]:
    bundled = load_yaml(OPENAPI_BUNDLED)
    out: list[ScenarioExample] = []
    for path, item in bundled["paths"].items():
        for method, op in item.items():
            if method not in ("get", "post", "put", "patch"):
                continue
            bodies = [("request", op.get("requestBody", {}).get("content", {}).get("application/json"))]
            for code, resp in op["responses"].items():
                if "$ref" in resp:
                    resp = bundled["components"]["responses"][resp["$ref"].rsplit("/", 1)[1]]
                bodies.append((code, (resp.get("content") or {}).get("application/json")))
            for where, media in bodies:
                if not media:
                    continue
                schema = media["schema"]
                for name, ex in (media.get("examples") or {}).items():
                    if "$ref" in schema:
                        out.append((f"{method} {path} {where} {name}", schema["$ref"].rsplit("/", 1)[1], ex["value"]))
                    elif schema.get("type") == "array" and "$ref" in schema.get("items", {}):
                        model = schema["items"]["$ref"].rsplit("/", 1)[1]
                        for i, item_value in enumerate(ex["value"]):
                            out.append((f"{method} {path} {where} {name}[{i}]", model, item_value))
    return out


MODEL_EXAMPLES = _model_examples()


@pytest.mark.parametrize(("where", "model_name", "value"), MODEL_EXAMPLES, ids=[e[0] for e in MODEL_EXAMPLES])
def test_generated_models_accept_examples(where: str, model_name: str, value: Any) -> None:
    from app.core import contracts_gen

    model = getattr(contracts_gen, model_name)
    assert issubclass(model, BaseModel)
    parsed = model.model_validate(value)
    assert parsed.model_dump(mode="json", exclude_unset=True) == value, where

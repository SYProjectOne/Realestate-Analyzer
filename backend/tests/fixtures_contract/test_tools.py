"""contracts/fixtures/tools/ — hash.py(input_hash 계산), synth.py(T16 합성 1,000단지), build_incheon_gimpo.py(재생성 일치)."""

# ruff: noqa: E501  (한국어 assertion 메시지)
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.protocols import input_hash

from ._fx import BACKEND, TOOLS, load_tool, schema_errors

pytestmark = pytest.mark.regress


def test_hash_tool_uses_protocols_input_hash() -> None:
    mod = load_tool("hash")
    payload = {"text": "엘리프 검단 포레듀", "n": 1}
    assert mod.fixture_hash("screen", "screen:notice:2", payload, "v1") == input_hash(
        "screen", "screen:notice:2", payload, "v1"
    )
    assert mod.input_hash is input_hash, "규칙 복제 금지: app.core.protocols.input_hash를 그대로 쓴다"


def test_hash_tool_cli(tmp_path: Path) -> None:
    payload = {"a": 1, "b": "가"}
    p = tmp_path / "payload.json"
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    out = subprocess.run(
        [sys.executable, str(TOOLS / "hash.py"), "--tool", "rerank", "--purpose", "rerank:region",
         "--adapter-version", "v1", str(p)],
        capture_output=True, text=True, encoding="utf-8", cwd=BACKEND, check=True,
    )  # fmt: skip
    assert out.stdout.strip() == input_hash("rerank", "rerank:region", payload, "v1")


def test_synth_generates_1000_valid_bundles() -> None:
    synth = load_tool("synth")
    bundles = synth.generate(1000, seed=16)
    assert len(bundles) == 1000
    ids = [b["complex"]["id"] for b in bundles]
    assert len(set(ids)) == 1000
    applyhome = [b["complex"]["applyhome_id"] for b in bundles]
    assert len(set(applyhome)) == 1000
    for b in bundles:
        errs = schema_errors("complex.json#/$defs/ComplexBundle", b)
        assert errs == [], errs[:3]


def test_synth_is_deterministic_and_labelled() -> None:
    synth = load_tool("synth")
    a = synth.generate(50, seed=7)
    assert a == synth.generate(50, seed=7)
    assert a != synth.generate(50, seed=8)
    for b in a:
        assert b["fixture_key"].startswith("synth_")
        assert "합성" in b["complex"]["name"], "합성 단지는 이름으로 구별된다"


def test_synth_cli_writes_file(tmp_path: Path) -> None:
    out = tmp_path / "synth.json"
    subprocess.run(
        [sys.executable, str(TOOLS / "synth.py"), "--n", "20", "--out", str(out)], cwd=BACKEND, check=True
    )
    assert len(json.loads(out.read_text(encoding="utf-8"))) == 20


def test_fixture_is_reproducible_from_builder() -> None:
    """build_incheon_gimpo.py --check: 생성기와 커밋된 픽스처가 바이트 단위로 같다(손으로 고치면 실패)."""
    res = subprocess.run(
        [sys.executable, str(TOOLS / "build_incheon_gimpo.py"), "--check"],
        capture_output=True, text=True, encoding="utf-8", cwd=BACKEND,
    )  # fmt: skip
    assert res.returncode == 0, res.stdout + res.stderr

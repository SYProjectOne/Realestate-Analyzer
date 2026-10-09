"""R3 minor 6: 픽스처를 바꾸면 CHANGELOG 에 사유를 남기도록 강제한다.

contracts/fixtures.sha256.json(``scripts/fixture_manifest.py`` 생성) = 픽스처 파일 sha256 + 사유.
(1) 지금 파일 해시가 매니페스트와 같다 — 다르면 매니페스트를 다시 만들어야 하고, (2) 그 사유 문장은 CHANGELOG 에 그대로
있어야 한다. 그래서 사유 없이 픽스처만 바꾸면 테스트가 실패한다.
"""

# ruff: noqa: E501  (한국어 docstring·메시지)
from __future__ import annotations

import importlib.util
from types import ModuleType

from ._support import BACKEND, CONTRACTS


def _tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "fixture_manifest", BACKEND / "scripts" / "fixture_manifest.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_fixture_files_match_manifest() -> None:
    tool = _tool()
    changes = tool.diff(tool.load_manifest())
    assert changes == [], (
        "픽스처가 매니페스트와 다르다 — 사유를 contracts/CHANGELOG.md 에 적고 "
        "`uv run python scripts/fixture_manifest.py --reason '<사유>'` 로 다시 만든다:\n"
        + "\n".join(changes[:30])
    )


def test_manifest_reason_is_in_changelog() -> None:
    reason = _tool().load_manifest()["reason"]
    assert isinstance(reason, str) and len(reason.strip()) >= 8
    changelog = (CONTRACTS / "CHANGELOG.md").read_text(encoding="utf-8")
    assert reason in changelog, f"매니페스트 사유가 CHANGELOG 에 없다: {reason!r}"


def test_manifest_detects_a_change(tmp_path: object) -> None:
    tool = _tool()
    manifest = tool.load_manifest()
    files = dict(manifest["files"])
    first = next(iter(files))
    files[first] = "0" * 64
    assert tool.diff({**manifest, "files": files}) == [f"~ {first}"]

"""R3 minor 6: 픽스처를 바꾸면 CHANGELOG 에 사유를 남기도록 강제한다.

contracts/fixtures.sha256.json(``scripts/fixture_manifest.py`` 생성) = 픽스처 파일 sha256 + 사유.
(1) 지금 파일 해시가 매니페스트와 같다 — 다르면 매니페스트를 다시 만들어야 하고, (2) 그 사유 문장은 CHANGELOG 에 그대로
있어야 한다. 그래서 사유 없이 픽스처만 바꾸면 테스트가 실패한다.
"""

# ruff: noqa: E501  (한국어 docstring·메시지)
from __future__ import annotations

import importlib.util
from types import ModuleType
from typing import Any

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


def test_manifest_refuses_reason_reuse_on_change(tmp_path: Any, monkeypatch: Any) -> None:
    """R3 3차 RA 부분: 픽스처가 바뀌면 사유도 새로 — 이전 사유(이력 포함)를 다시 쓰면 거부."""
    import json

    import pytest

    tool = _tool()
    path = tmp_path / "m.json"
    cur = tool.file_hashes()
    first = next(iter(cur))
    old = {
        "reason": "이전 변경 사유 문장",
        "files": {**cur, first: "0" * 64},
        "history": [{"reason": "더 오래된 사유", "files_digest": "x"}],
    }
    path.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    for reused in ("이전 변경 사유 문장", "더 오래된 사유"):
        with pytest.raises(tool.ReasonReused):
            tool.write_manifest(reused, path)
    data = tool.write_manifest("이번 변경의 새 사유 문장", path)
    assert data["files_digest"] == tool.files_digest(cur)
    assert [h["reason"] for h in data["history"]] == ["더 오래된 사유", "이전 변경 사유 문장"]
    # 픽스처가 그대로면 같은 사유로 다시 써도 된다(재생성 멱등)
    assert tool.write_manifest("이번 변경의 새 사유 문장", path)["reason"] == "이번 변경의 새 사유 문장"


def test_manifest_detects_a_change(tmp_path: object) -> None:
    tool = _tool()
    manifest = tool.load_manifest()
    files = dict(manifest["files"])
    first = next(iter(files))
    files[first] = "0" * 64
    assert tool.diff({**manifest, "files": files}) == [f"~ {first}"]

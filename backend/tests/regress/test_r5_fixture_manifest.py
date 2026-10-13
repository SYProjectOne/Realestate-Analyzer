"""R5 OPS 7(PIPE 가 픽스처 소유 — D25): 픽스처 매니페스트가 CHANGELOG 의 **과거 사유**도 검사한다.

| 테스트 | 확인 |
| --- | --- |
| ``test_every_manifest_reason_is_in_changelog`` | 지금 매니페스트의 사유 + 이력(history)의 모든 과거 사유가 contracts/CHANGELOG.md 에 문장 그대로 있다(수정 전: R3f CORE4 사유 1건 누락) |
| ``test_missing_reasons_detects_dropped_history`` | 과거 사유가 CHANGELOG 에 없으면 ``missing_reasons`` 가 그 사유를 돌려주고 ``--check`` 는 exit 1 |
| ``test_fixture_readme_households_is_current`` | 픽스처 README 주의 7 이 '세대수 확인 불가'(파일 없음)라는 옛 문구가 아니라 공식 사본·사람 확인(2026-10-09)을 적는다 |
"""

# ruff: noqa: E501

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

BACKEND = Path(__file__).resolve().parents[2]
CONTRACTS = BACKEND.parent / "contracts"


def _tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "fixture_manifest_r5", BACKEND / "scripts" / "fixture_manifest.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_manifest_reason_is_in_changelog() -> None:
    tool = _tool()
    missing = tool.missing_reasons(tool.load_manifest())
    assert missing == [], f"CHANGELOG 에 없는 매니페스트 사유(과거 포함): {missing}"


def test_missing_reasons_detects_dropped_history(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tool = _tool()
    manifest = tool.load_manifest()
    fake = {
        **manifest,
        "history": [
            *manifest.get("history", []),
            {"reason": "CHANGELOG 에 없는 과거 사유 문장", "files_digest": "x"},
        ],
    }
    assert tool.missing_reasons(fake) == ["CHANGELOG 에 없는 과거 사유 문장"]
    assert tool.missing_reasons(fake, changelog="") == [h["reason"] for h in fake["history"]] + [
        manifest["reason"]
    ]
    monkeypatch.setattr(tool, "load_manifest", lambda path=None: fake)
    assert tool.main(["--check"]) == 1
    assert "CHANGELOG 에 없는 사유" in capsys.readouterr().out


def test_fixture_readme_households_is_current() -> None:
    text = (CONTRACTS / "fixtures" / "incheon_gimpo_2026-10-08" / "README.md").read_text(encoding="utf-8")
    item = text.split("\n7. ", 1)[1].split("\n8. ", 1)[0]
    assert "파일이 없어 `확인 불가`다" not in item, item
    assert "jumin_households_202609.csv" in item and "2026-10-09" in item and "사람" in item, item

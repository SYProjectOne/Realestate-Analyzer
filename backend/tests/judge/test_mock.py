"""mock.py — 픽스처 재생: input_hash로 녹화를 찾고(봉투 동일), 없으면 status=review, 다운 시뮬레이션(T18)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from app.judge.mock import MockAdapter, recording_path, write_recording

from app.core.contracts_gen import JudgmentEnvelope
from app.core.protocols import JudgeAdapter, JudgeUnavailable, input_hash

VERSION = "0.1.0+jev-mcp@0.14.1"
PAYLOAD: dict[str, Any] = {"query": "q", "candidates": [{"id": "complex:1", "text": "단지 1"}]}


@pytest.fixture
def fixture_dir(tmp_path: Path) -> Path:
    d = tmp_path / "fx"
    (d / "judgments").mkdir(parents=True)
    (d / "judgments" / "_meta.json").write_text(
        json.dumps({"adapter_version": VERSION, "recorded_at": "2026-10-08"}), encoding="utf-8"
    )
    return d


def recorded(purpose: str = "rerank:region:1") -> JudgmentEnvelope:
    return JudgmentEnvelope(
        tool="rerank",
        purpose=purpose,
        input_hash=input_hash("rerank", purpose, PAYLOAD, VERSION),
        input_len=80,
        status="ok",
        confidence=None,
        cached=False,
        result={
            "query": "q",
            "items": [{"candidate_id": "complex:1", "complex_id": 1, "relevance": 0.9, "rank": 1}],
        },
        raw={
            "tool": "jev_rerank",
            "ranked": [{"rank": 1, "id": "complex:1", "relevance": 0.9, "text": "단지 1"}],
        },
        duration_ms=200,
        judgment_seq=124,
        created_at="2026-10-07T15:00:00+09:00",
        adapter_version=VERSION,
    )


def test_protocol(fixture_dir: Path) -> None:
    assert isinstance(MockAdapter(fixture_dir), JudgeAdapter)


def test_adapter_version_from_meta(fixture_dir: Path) -> None:
    assert MockAdapter(fixture_dir).adapter_version == VERSION


def test_replay_returns_identical_envelope(fixture_dir: Path) -> None:
    env = recorded()
    path = write_recording(fixture_dir, env)
    assert path == recording_path(fixture_dir, "rerank", env.input_hash)
    assert path.name == env.input_hash.removeprefix("sha256:") + ".json"

    got = MockAdapter(fixture_dir).rerank(PAYLOAD, "rerank:region:1")
    assert got == env.model_copy(update={"cached": True})
    again = MockAdapter(fixture_dir).rerank(PAYLOAD, "rerank:region:1")
    assert again == got


def test_missing_recording_is_review_not_silent(fixture_dir: Path) -> None:
    env = MockAdapter(fixture_dir).rerank(PAYLOAD, "rerank:region:2")
    assert env.status == "review"
    assert env.result == {}
    assert env.raw == {"reason": "no recording"}
    assert env.confidence is None
    assert env.input_hash == input_hash("rerank", "rerank:region:2", PAYLOAD, VERSION)


def test_unavailable_simulation_raises(fixture_dir: Path) -> None:
    """T18: MockAdapter가 JudgeUnavailable을 던진다(다운 시뮬레이션 전용)."""
    with pytest.raises(JudgeUnavailable):
        MockAdapter(fixture_dir, unavailable=True).noul(
            {"propositions": ["x"]}, "noul:ladder:asof_plus_3y:2029-10:c1"
        )


def test_guard_applies_in_mock(fixture_dir: Path) -> None:
    env = MockAdapter(fixture_dir).screen({"text": "문의 010-1234-5678"}, "screen:notice:1")
    assert env.status == "blocked"
    assert "010-1234-5678" not in env.model_dump_json()


def test_all_nine_methods(fixture_dir: Path) -> None:
    m = MockAdapter(fixture_dir)
    for tool in ("screen", "extract", "audit", "classify", "compare", "noul", "rerank", "decide", "verify"):
        env = getattr(m, tool)({"x": "공개 텍스트"}, f"{tool}:t")
        assert env.tool == tool
        assert env.status == "review"

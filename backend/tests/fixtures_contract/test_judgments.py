"""판정 녹화(judgments/) — 보고서 부록 A 호출 로그 #1~#132 (WP9, RA §4-5, contracts/fixtures/README.md).

- 파일 = judgments/<tool>/<hex>.json, <hex> = input_hash에서 'sha256:'을 뺀 64자.
- input_hash는 app.core.protocols.input_hash로 다시 계산해 맞춘다(규칙 복제 금지).
- adapter_version은 judgments/_meta.json 값 하나(MockAdapter가 그대로 쓴다).
"""

# ruff: noqa: E501  (한국어 assertion 메시지)
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.core.protocols import JUDGE_TOOLS, input_hash

from ._fx import FIXTURE, JUDGMENTS, load_json, schema_errors

pytestmark = pytest.mark.regress

META = load_json(JUDGMENTS / "_meta.json") if (JUDGMENTS / "_meta.json").is_file() else {}
INDEX: list[dict[str, Any]] = load_json(JUDGMENTS / "_index.json") if (JUDGMENTS / "_index.json").is_file() else []
EXPECTED = load_json(FIXTURE / "expected_scores.json")
FILES = sorted(p for p in JUDGMENTS.glob("*/*.json"))


def envelope(seq: int) -> dict[str, Any]:
    row = next(r for r in INDEX if r["judgment_seq"] == seq)
    doc: dict[str, Any] = load_json(JUDGMENTS / row["file"])
    return doc


def test_meta() -> None:
    assert META["adapter_version"] == "mock-fixture-2026-10-08"
    assert META["recorded_at"][:10] == "2026-10-07"
    assert META["source"].endswith("incheon_gimpo_report.md")


def test_index_covers_report_calls_1_to_132() -> None:
    seqs = [r["judgment_seq"] for r in INDEX]
    assert sorted(seqs) == list(range(1, 133)), "부록 A #1~#132가 한 번씩"
    assert len(FILES) == 132, "녹화 파일 132개"


@pytest.mark.parametrize("path", FILES, ids=[p.relative_to(JUDGMENTS).as_posix() for p in FILES])
def test_envelope_schema_and_hash(path: Path) -> None:
    env = load_json(path)
    errs = schema_errors("judgment_envelope.json", env)
    assert errs == [], errs[:5]
    assert path.parent.name == env["tool"] and env["tool"] in JUDGE_TOOLS
    assert env["input_hash"] == "sha256:" + path.stem
    assert env["adapter_version"] == META["adapter_version"]
    assert env["cached"] is False, "녹화 원본은 cached=false(MockAdapter가 돌려줄 때 true로 바꾼다)"


@pytest.mark.parametrize("row", INDEX, ids=[f"#{r['judgment_seq']}" for r in INDEX])
def test_index_payload_reproduces_hash(row: dict[str, Any]) -> None:
    """_index.json의 (tool, purpose, payload)로 protocols.input_hash를 다시 계산하면 파일 이름과 같다."""
    h = input_hash(row["tool"], row["purpose"], row["payload"], META["adapter_version"])
    assert h == row["input_hash"]
    env = load_json(JUDGMENTS / row["file"])
    assert env["input_hash"] == h and env["judgment_seq"] == row["judgment_seq"]
    assert env["purpose"] == row["purpose"] and env["tool"] == row["tool"]
    assert row["file"] == f"{row['tool']}/{h.removeprefix('sha256:')}.json"
    assert row["report_ref"].startswith("부록 A #")


def test_input_hashes_unique() -> None:
    hashes = [r["input_hash"] for r in INDEX]
    assert len(hashes) == len(set(hashes)), "input_hash UNIQUE(judgment_log)"


def test_tool_counts_match_appendix() -> None:
    """부록 A 집계: 인천 #1~89(screen 28·extract 22·audit 12·classify 2·noul 6·rerank 1·compare 6·decide 5·verify 7)
    + 김포 #90~132(screen 8·extract 6·audit 6·classify 2·compare 6·noul 6·rerank 1·decide 5·verify 3)."""
    counts: dict[str, int] = {}
    for r in INDEX:
        counts[r["tool"]] = counts.get(r["tool"], 0) + 1
    assert counts == {"screen": 36, "extract": 28, "audit": 18, "classify": 4, "noul": 12, "rerank": 2,
                      "compare": 12, "decide": 10, "verify": 10}  # fmt: skip


def test_unreceived_extracts_are_error_envelopes() -> None:
    """#30~38: 응답 미수신(사용자 턴 전환) → status=error, result={} (실패도 데이터)."""
    for seq in range(30, 39):
        env = envelope(seq)
        assert env["tool"] == "extract" and env["status"] == "error" and env["result"] == {}
        assert env["error_text"]


def test_t2_decide_tie_recording() -> None:
    env = envelope(127)
    assert env["tool"] == "decide" and env["status"] == "ok" and env["confidence"] == 0.48
    assert env["result"]["probs"]["complex:7"] == 0.54 and env["result"]["probs"]["complex:2"] == 0.42


def test_t7_rerank_8_then_16() -> None:
    first, second = envelope(71), envelope(124)
    assert len(first["result"]["items"]) == 8 and len(second["result"]["items"]) == 16
    prev = {r["key"]: r for r in EXPECTED["t7_incheon_only"]["rows"]}
    ids = {c["key"]: c["complex_id"] for c in EXPECTED["complexes"]}
    rel71 = {i["complex_id"]: i["relevance"] for i in first["result"]["items"]}
    rel124 = {i["complex_id"]: i["relevance"] for i in second["result"]["items"]}
    for key, row in prev.items():
        assert rel71[ids[key]] == row["relevance_prev"]
        assert rel124[ids[key]] == row["relevance"]
    for c in EXPECTED["complexes"]:
        assert rel124[c["complex_id"]] == c["raw"]["rerank_relevance"]


def test_noul_p10_matches_expected_scores() -> None:
    p10: dict[int, float] = {}
    for r in INDEX:
        if r["tool"] != "noul":
            continue
        env = load_json(JUDGMENTS / r["file"])
        props = {p["key"]: p["prob"] for p in env["result"]["propositions"]}
        assert env["status"] == "ok" and env["result"]["horizon"] == "move_in_plus_1y"
        assert env["complex_id"] is not None
        p10[env["complex_id"]] = props["p10"]
    for c in EXPECTED["complexes"]:
        if c["raw"].get("p10_prob") is not None:
            assert p10[c["complex_id"]] == c["raw"]["p10_prob"], c["key"]


def test_decide_integrated_matches_expected_scores() -> None:
    ids = {c["key"]: c["complex_id"] for c in EXPECTED["complexes"]}
    for name, block in EXPECTED["decide_integrated"].items():
        env = envelope(block["judgment_seq"])
        assert env["confidence"] == block["confidence"], name
        for key, prob in block["probs"].items():
            option = f"complex:{ids[key]}" if key in ids else key
            assert env["result"]["probs"][option] == prob, (name, key)


def test_t6_verify_contradicted_composite_claim() -> None:
    env = envelope(131)
    contradicted = [c for c in env["result"]["claims"] if c["verdict"] == "contradicted"]
    assert len(contradicted) == 1 and contradicted[0]["confidence"] == 0.35
    assert env["status"] == "review"


def test_payloads_are_public_info_only() -> None:
    """녹화 payload에 전화번호·이메일·주민번호 모양이 없어야 한다(AGENTS 6, T14의 반대 사례)."""
    import json
    import re

    bad = re.compile(r"\d{2,3}-\d{3,4}-\d{4}|[\w.+-]+@[\w-]+\.[\w.]+|\d{6}-[1-4]\d{6}")
    for r in INDEX:
        text = json.dumps(r["payload"], ensure_ascii=False)
        assert not bad.search(text), f"#{r['judgment_seq']} payload에 개인정보 모양"

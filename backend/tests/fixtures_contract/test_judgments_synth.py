"""합성 판정 녹화(judgments_synth/) — CEO W2 (WP9-후속).

- 생성기 ``contracts/fixtures/tools/record_synth_judgments.py`` 가 실제 파이프라인(devseed → rejudge, T3 사람 확인 흐름)을
  결정적 가짜 판정기(ReportSynthJev = WP7 SynthJev + 보고서 수치)로 한 번 돌려 payload hash 그대로 봉투를 저장한다.
- MockAdapter fixture_dir = ``judgments_synth``(그 아래 ``judgments/`` — MockAdapter 고정 구조). 라벨 '합성'.
- 재생성 바이트 일치(``--check``)는 test_tools 와 같은 방식으로 여기서 본다.
"""

# ruff: noqa: E501
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.core.protocols import JUDGE_TOOLS, input_hash

from ._fx import BACKEND, FIXTURE, JUDGMENTS, TOOLS, load_json, schema_errors

pytestmark = pytest.mark.regress

SYNTH = FIXTURE / "judgments_synth"
SJ = SYNTH / "judgments"
META = load_json(SJ / "_meta.json")
INDEX: list[dict[str, Any]] = load_json(SJ / "_index.json")
FILES = sorted(SJ.glob("*/*.json"))
REPORT_INDEX = load_json(JUDGMENTS / "_index.json")


def _env(row: dict[str, Any]) -> dict[str, Any]:
    doc: dict[str, Any] = load_json(SJ / row["file"])
    return doc


def test_meta_label_and_version() -> None:
    assert META["label"] == "합성"
    # devseed judgment_log(보고서 녹화)와 같은 버전 — 다르면 mock 재판정이 '판정기 버전 변경' critical 을 만든다
    assert META["adapter_version"] == load_json(JUDGMENTS / "_meta.json")["adapter_version"]
    assert set(META["runs"]) == {"full", "t3"}
    assert (SYNTH / "README.md").is_file() and "합성" in (SYNTH / "README.md").read_text(encoding="utf-8")


def test_index_covers_every_file_once() -> None:
    assert sorted(r["file"] for r in INDEX) == [p.relative_to(SJ).as_posix() for p in FILES]
    assert len({r["input_hash"] for r in INDEX}) == len(INDEX)
    assert META["counts"] == {
        t: sum(1 for r in INDEX if r["tool"] == t) for t in sorted({r["tool"] for r in INDEX})
    }


@pytest.mark.parametrize("row", INDEX, ids=[r["file"][:20] for r in INDEX])
def test_envelope_schema_hash_label(row: dict[str, Any]) -> None:
    env = _env(row)
    assert schema_errors("judgment_envelope.json", env) == []
    assert env["tool"] in JUDGE_TOOLS and env["tool"] == row["tool"] and env["purpose"] == row["purpose"]
    h = input_hash(row["tool"], row["purpose"], row["payload"], META["adapter_version"])
    assert h == row["input_hash"] == env["input_hash"]
    assert row["file"] == f"{row['tool']}/{h.removeprefix('sha256:')}.json"
    assert env["cached"] is False and env["judgment_seq"] is None
    assert env["raw"]["synth"]["label"] == "합성" and env["raw"]["synth"]["basis"] == row["basis"]


def test_no_overlap_with_report_recordings() -> None:
    """보고서 재구성 녹화(judgments/)는 그대로 — 같은 hash 가 없다(payload 가 다르다)."""
    assert not ({r["input_hash"] for r in INDEX} & {r["input_hash"] for r in REPORT_INDEX})


def test_values_follow_report() -> None:
    """noul(입주 후 1년)·rerank·decide 결과가 보고서 녹화 값과 같다(합성 판정기 구성 확인)."""
    rep = {r["judgment_seq"]: load_json(JUDGMENTS / r["file"]) for r in REPORT_INDEX}
    report_ladder = {
        r["payload"]["complex_id"]: [p["prob"] for p in rep[r["judgment_seq"]]["result"]["propositions"]]
        for r in REPORT_INDEX
        if r["tool"] == "noul" and r["payload"].get("horizon") == "move_in_plus_1y"
    }
    n_ok = 0
    for row in INDEX:
        env = _env(row)
        if row["tool"] == "noul":
            cid = int(row["purpose"].rsplit(":c", 1)[1])
            if ":move_in_plus_1y:" in row["purpose"]:
                assert env["status"] == "ok"
                assert [p["prob"] for p in env["result"]["propositions"]] == report_ladder[cid], cid
                n_ok += 1
            else:  # 보고서에 3년·5년 사다리 없음 → 지어내지 않고 review
                assert env["status"] == "review" and env["result"]["propositions"] == []
        elif row["tool"] == "rerank":
            rel = {i["complex_id"]: i["relevance"] for i in rep[124]["result"]["items"]}
            assert all(i["relevance"] == rel[i["complex_id"]] for i in env["result"]["items"])
        elif row["tool"] == "decide" and row["purpose"] == "decide:scenario_B":
            assert env["result"]["selected"] == rep[127]["result"]["selected"] == "complex:7"
            assert env["confidence"] == rep[127]["confidence"]  # T2: 0.48 → tie
    assert n_ok >= 10


def test_inclusion_classify_follows_report_review() -> None:
    """포함/제외 classify = 보고서(#62·#110) — 스위첸(4)·지엔하임(14)·그랑포레(16)는 review(D9-1 미해결)."""
    rows = [r for r in INDEX if r["tool"] == "classify" and r["purpose"].startswith("classify:inclusion")]
    assert len(rows) == 1
    items = {it["id"]: it for it in _env(rows[0])["result"]["items"]}
    review = {int(k.split(":")[1]) for k, it in items.items() if it["decision"] != "auto"}
    assert review == {4, 14, 16}


def test_recorder_is_reproducible() -> None:
    """record_synth_judgments.py --check: 다시 돌린 녹화가 커밋된 judgments_synth/ 와 바이트 단위로 같다."""
    res = subprocess.run(
        [sys.executable, str(TOOLS / "record_synth_judgments.py"), "--check"],
        capture_output=True, text=True, encoding="utf-8", cwd=BACKEND, timeout=600,
    )  # fmt: skip
    assert res.returncode == 0, res.stdout[-2000:] + res.stderr[-2000:]


def test_files_are_lf_utf8(tmp_path: Path) -> None:
    for p in FILES[:20]:
        assert b"\r\n" not in p.read_bytes()

"""expected_scores_v2.json (RA §9 (b)단계 draft): §6-4 식으로 다시 계산한 값 — 사람 확인 대기.

파일에 들어 있는 입력(inputs, 보고서 수치 + 표시된 가정)을 엔진에 넣으면 파일에 적힌 결과가 그대로 나와야 한다.
(a)단계와의 차이는 파일의 diff_vs_a에 설명이 있어야 한다.
"""

# ruff: noqa: E501  (한국어 docstring·식 문자열은 화면 폭 기준으로 길다)

from __future__ import annotations

from decimal import Decimal

from app.analysis.scenarios import builtin
from app.analysis.score import run_detailed
from app.core.contracts_gen import ScoreInputs

from ._support import EXPECTED, EXPECTED_V2_PATH, load_json, snapshot


def _v2() -> dict:  # type: ignore[type-arg]
    return load_json(EXPECTED_V2_PATH)


def test_v2_is_draft_waiting_for_human_check() -> None:
    v2 = _v2()
    assert v2["stage"] == "b"
    assert v2["status"] == "사람 확인 대기"
    assert v2["inputs_source"].startswith("docs/source/incheon_gimpo_report.md")
    assert v2["assumptions"], "보고서에 없는 값은 가정으로 적어야 한다"


def test_v2_recomputes_from_embedded_inputs() -> None:
    v2 = _v2()
    inputs = ScoreInputs.model_validate(v2["inputs"])
    detail = run_detailed(snapshot(), builtin("base"), inputs)
    totals = {t.complex_id: t for t in detail.result.totals}
    comps = {(c.complex_id, c.component): c for c in detail.result.components}
    assert len(v2["complexes"]) == 16
    for row in v2["complexes"]:
        cid = row["complex_id"]
        t = totals[cid]
        assert t.total == row["total"], row["key"]
        assert t.rank == row["rank"] and t.tie_group == row["tie_group"] and t.unstable == row["unstable"], (
            row["key"]
        )
        for key, comp in row["components"].items():
            got = comps[(cid, key)]
            assert got.score_0_10 == comp["score"], (row["key"], key)
            assert got.formula_text == comp["formula_text"], (row["key"], key)
            assert got.label == comp["label"], (row["key"], key)


def test_v2_explains_every_difference_from_a() -> None:
    v2 = _v2()
    a = {c["key"]: c for c in EXPECTED["complexes"]}
    for row in v2["complexes"]:
        diff = row["diff_vs_a"]
        for key, comp in row["components"].items():
            a_score = a[row["key"]]["components"][key]
            if a_score is None or comp["score"] is None:
                continue
            delta = Decimal(str(comp["score"])) - Decimal(str(a_score))
            if abs(delta) >= Decimal("0.01"):
                assert diff.get(key, "").strip(), (row["key"], key)
    assert v2["summary"]["top5_a"] and v2["summary"]["top5_b"] and v2["summary"]["explanation"]

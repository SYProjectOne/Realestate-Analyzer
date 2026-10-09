"""T12 민감도 (RA §9, §6-6) — 시스템 경계: devseed 적재(T1 입력 = (a) 구성 점수 고정) → API(C10 민감도·G2 리스트·G1),
(b) 골든(expected_scores_v2.json) 재현, worker 재판정 뒤 저장 플래그와 API 의 일치.

RA §9 T12 기대 결과(그대로): "12 변형 계산, TOP 5 집합 변동 여부가 골든 파일과 일치, `unstable` 플래그"
§6-6: 가중치 6개 각각 ±0.10, 나머지 비례 재정규화 → 12 변형마다 TOP 5 집합(rank ≤ 5, 공동 5위 포함).
한 번이라도 집합이 바뀌면 score_total.unstable=true("순위 불안정" 배지). 변동 없는 가중치는 화면에서 회색(stable_components).
골든: expected_scores.json t12_sensitivity((a) 입력), expected_scores_v2.json summary.sensitivity·complexes[].unstable((b)).
"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

import pytest

from .conftest import FIXTURE, SNAP, WRITE, RegressEnv, api_get, by_key, cur, load_json

pytestmark = pytest.mark.regress


def _golden() -> dict[str, Any]:
    g: dict[str, Any] = load_json(FIXTURE / "expected_scores.json")["t12_sensitivity"]
    return g


def test_t12_sensitivity_api_matches_golden(env: RegressEnv) -> None:
    """GET /snapshots/12/sensitivity?scenario=base = t12_sensitivity: 12 변형·변형별 TOP 5 집합·changed·entered·exited·가중치·unstable."""
    g = _golden()
    ids = by_key()
    body = api_get(env, f"/snapshots/{cur(env)}/sensitivity", scenario="base")
    assert body["snapshot_id"] == cur(env) and body["score_run_id"] is not None
    cells = body["cells"]
    assert len(cells) == 12 == len(g["cells"])
    assert [c["variant"] for c in cells] == [c["variant"] for c in g["cells"]]
    assert set(body["base_top5"]) == {ids[k] for k in g["base_top5"]}
    bad: list[str] = []
    for got, want in zip(cells, g["cells"], strict=True):
        v = want["variant"]
        if got["changed"] is not want["changed"]:
            bad.append(f"{v}: changed {got['changed']} != {want['changed']}")
        if set(got["top5"]) != {ids[k] for k in want["top5"]}:
            bad.append(f"{v}: top5 {sorted(got['top5'])} != {sorted(ids[k] for k in want['top5'])}")
        if set(got["entered"]) != {ids[k] for k in want["entered"]}:
            bad.append(f"{v}: entered {got['entered']} != {want['entered']}")
        if set(got["exited"]) != {ids[k] for k in want["exited"]}:
            bad.append(f"{v}: exited {got['exited']} != {want['exited']}")
        for comp, w in want["weights"].items():
            if abs(float(got["weights"].get(comp, -1)) - w) > 1e-6:
                bad.append(f"{v}: weight {comp} {got['weights'].get(comp)} != {w}")
        if abs(sum(got["weights"].values()) - 1) > 1e-5:
            bad.append(f"{v}: 가중치 합 {sum(got['weights'].values())}")
    assert not bad, "\n".join(bad)
    assert body["unstable"] is g["unstable"] is True
    assert set(body["unstable_complex_ids"]) == {ids[k] for k in g["unstable_keys"]}
    assert body["stable_components"] == g["stable_components"]


def test_t12_unstable_flags_exposed_in_rows(env: RegressEnv) -> None:
    """score_total.unstable = 골든 unstable_keys — G2 리스트·G1 TOP 5 행의 unstable 플래그로 보인다."""
    g = _golden()
    ids = by_key()
    want = {ids[k] for k in g["unstable_keys"]}
    body = api_get(env, f"/snapshots/{cur(env)}/complexes", scenario="base", size=100)
    flags = {r["complex_id"]: r["unstable"] for r in body["items"]}
    assert {cid for cid, f in flags.items() if f} == want, flags
    dash = api_get(env, f"/snapshots/{cur(env)}/dashboard", scenario="base")
    for r in dash["top5"]:
        assert r["unstable"] is (r["complex_id"] in want), r["complex_id"]
    sens = api_get(env, f"/snapshots/{cur(env)}/sensitivity", scenario="base")
    assert set(sens["unstable_complex_ids"]) == {cid for cid, f in flags.items() if f}


def test_t12_v2_golden_sensitivity_from_file_inputs() -> None:
    """(b) 골든: v2 inputs → 공개 점수 API(run_detailed, 민감도 포함) = summary.sensitivity·complexes[].unstable."""
    from app.analysis.scenarios import builtin
    from app.analysis.score import run_detailed
    from app.core.contracts_gen import ScoreInputs, Snapshot

    v2 = load_json(FIXTURE / "expected_scores_v2.json")
    want = v2["summary"]["sensitivity"]
    ids = {c["key"]: c["complex_id"] for c in v2["complexes"]}
    inputs = ScoreInputs.model_validate(v2["inputs"])
    snaps = {s["id"]: s for s in load_json(FIXTURE / "snapshots.json")}
    detail = run_detailed(
        Snapshot.model_validate(snaps[inputs.snapshot_id]), builtin("base"), inputs, with_sensitivity=True
    )
    sens = detail.sensitivity
    assert sens is not None
    assert len(sens.cells) == 12
    assert sens.unstable is want["unstable"]
    assert set(sens.unstable_complex_ids) == {ids[k] for k in want["unstable_keys"]}
    assert list(sens.stable_components) == want["stable_components"]
    assert set(sens.base_top5) == {ids[k] for k in want["base_top5"]}
    flags = {t.complex_id: t.unstable for t in detail.result.totals}
    for c in v2["complexes"]:
        assert flags.get(c["complex_id"], False) is c["unstable"], c["key"]


def test_t12_pipeline_stored_unstable_equals_sensitivity_api(env: RegressEnv) -> None:
    """worker 재판정(FakeJev, base) 뒤: 새 run 의 score_total.unstable 집합 = 민감도 API unstable_complex_ids, 12 변형."""
    r = env.client.post(
        "/api/jobs",
        headers=WRITE,
        json={
            "job_name": "rejudge",
            "payload": {"snapshot_id": SNAP, "scenario_id": 1, "complex_ids": None, "reason": "T12 회귀"},
        },
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]
    env.worker(env.ctx("fake"))
    assert api_get(env, f"/jobs/{job_id}")["status"] == "done"
    sens = api_get(env, f"/snapshots/{cur(env)}/sensitivity", scenario="base")
    assert sens["score_run_id"] is not None and sens["score_run_id"] > 5, "새 run 이 아니다"
    assert len(sens["cells"]) == 12
    assert sens["unstable"] is any(c["changed"] for c in sens["cells"])
    moved = set().union(*({*c["entered"], *c["exited"]} for c in sens["cells"]))
    assert set(sens["unstable_complex_ids"]) == moved
    body = api_get(env, f"/snapshots/{cur(env)}/complexes", scenario="base", size=100)
    stored = {r["complex_id"] for r in body["items"] if r["unstable"]}
    assert stored == set(sens["unstable_complex_ids"]), (sorted(stored), sens["unstable_complex_ids"])

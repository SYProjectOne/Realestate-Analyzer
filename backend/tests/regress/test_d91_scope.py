"""DECISIONS D9-1 판정 범위 — 파이프라인·API 경로(WP9-후속, 보고서와의 차이는 픽스처 README 'D9-1로 인한 차이').

- mock(합성 판정 녹화 = 보고서 classify) 재판정 뒤 API 의 judge_scope 가 README 표와 같다.
- '참고 후보(순위만)'·'미해결'·'보류'는 종합 점수·순위가 없다(사다리 미실행 → p10 null → 종합 미판정, analysis/scope.py 표).
"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

import pytest

from .conftest import SNAP, WRITE, RegressEnv, api_get

pytestmark = pytest.mark.regress

# 합성 녹화(보고서 classify #62·#110) + 픽스처 접수 행 → D9-1. 계약 .4 전에는 '미해결'이 score_total 에 '제외'로 실린다.
EXPECTED_SCOPE: dict[int, tuple[str, ...]] = {
    1: ("판정 대상",), 2: ("판정 대상",), 3: ("판정 대상",), 4: ("미해결", "제외"), 5: ("판정 대상",), 6: ("판정 대상",),
    7: ("판정 대상",), 8: ("판정 대상",), 9: ("판정 대상",), 10: ("판정 대상",), 11: ("판정 대상",), 12: ("참고",),
    13: ("참고",), 14: ("미해결", "제외"), 15: ("보류",), 16: ("미해결", "제외"),
}  # fmt: skip


def _full_rejudge(env: RegressEnv, judge: str) -> None:
    r = env.client.post(
        "/api/jobs",
        headers=WRITE,
        json={"job_name": "rejudge", "payload": {"snapshot_id": SNAP, "scenario_id": None, "complex_ids": None, "reason": "D9-1 회귀"}},
    )
    assert r.status_code == 202, r.text
    assert env.worker(env.ctx(judge)) == 0
    job = api_get(env, f"/jobs/{r.json()['id']}")
    assert job["status"] == "done", job


def _rows(env: RegressEnv) -> dict[int, dict[str, Any]]:
    body = api_get(env, f"/snapshots/{SNAP}/complexes", scenario="base", size=100)
    return {r["complex_id"]: r for r in body["items"]}


def test_d91_scope_after_mock_rejudge_matches_readme(env: RegressEnv) -> None:
    _full_rejudge(env, "mock")
    assert env.mock_misses == [], env.mock_misses[:5]
    rows = _rows(env)
    bad = {cid: rows[cid].get("judge_scope") for cid, ok in EXPECTED_SCOPE.items() if rows[cid].get("judge_scope") not in ok}
    assert not bad, bad
    top5 = [t["complex_id"] for t in api_get(env, f"/snapshots/{SNAP}/dashboard", scenario="base")["top5"]]
    assert top5 and not set(top5) & {4, 14, 16}


@pytest.mark.xfail(strict=True, reason="WP9-후속 발견(F2 scheduler/inputs·analysis — 읽기만): 같은 스냅샷에 남은 ladder 행이 "
                   "'참고'(사다리 미실행) 단지에도 ScoreInputs.ladders 로 들어가 종합 점수·순위가 생긴다(마리나베이 4.18, 8위)")  # fmt: skip
def test_d91_reference_scope_has_no_total_or_rank(env: RegressEnv) -> None:
    """D9-1 '참고 후보(순위만)': 사다리 미실행 → 종합 미판정·순위 없음. 마리나베이(12, 접수 불가)는 devseed(보고서 #67) 사다리 행이
    남아 있어도 점수에 쓰이면 안 된다(해링턴 13 은 사다리 행이 없어 이미 미판정)."""
    _full_rejudge(env, "mock")
    rows = _rows(env)
    bad = {cid: (r["total"]["v"], r.get("rank")) for cid, r in rows.items()
           if r.get("judge_scope") in ("참고", "보류", "미해결", "제외") and (r["total"]["v"] is not None or r.get("rank") is not None)}  # fmt: skip
    assert not bad, bad

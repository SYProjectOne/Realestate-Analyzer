"""T3 스위첸 홈페이지 403 (RA §9).

기대: official_site 403 응답 녹화 → ``intake_status=확인 불가``, ``http_status=403``, 화면 "확인 불가(403, 날짜)";
상황 후보 제외; G7에서 사람 확인 "가능" 입력 → intake 행 추가 + rejudge job 1 → 후보 포함.

시스템 경계: devseed DB → API(GET 단지·리스트, POST /ops/human-checks, POST /jobs) → worker(--once) → API.
- 판정기 ``fake``(실제 어댑터 경로 + 결정적 전송): 흐름 자체(사람 확인 → 재판정 → D 후보 포함)를 본다.
- 판정기 ``mock``(JUDGE_ADAPTER=mock — e2e 와 같은 구성): 같은 흐름이 후보 포함까지 가야 한다(RA §9 + e2e 흐름 b).
"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import func, select

from .conftest import FIXTURE, SNAP, WRITE, RegressEnv, api_get, load_json

pytestmark = pytest.mark.regress

CID = 4  # 오퍼스 한강 스위첸
SCENARIO_D = "D"  # 즉시 구매: 접수 '가능'이 아니면 후보 제외


def _row(env: RegressEnv, scenario: str) -> dict[str, Any]:
    body = api_get(env, f"/snapshots/{SNAP}/complexes", scenario=scenario, size=100)
    return next(r for r in body["items"] if r["complex_id"] == CID)


def _human_check_then_rejudge(env: RegressEnv, judge: str) -> dict[str, Any]:
    from app.models import JobRun

    req = load_json(FIXTURE / "raw" / "human_check" / "t3_switzen_possible.json")
    r = env.client.post("/api/ops/human-checks", headers=WRITE, json=req)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created_intake"]["status"] == "가능" and body["created_intake"]["path"] == "human_check"
    job = env.client.post("/api/jobs", headers=WRITE, json=body["suggested_job"])
    assert job.status_code == 202, job.text
    with env.session() as s:
        n_rejudge = s.scalar(select(func.count()).select_from(JobRun).where(JobRun.job_name == "rejudge"))
    assert n_rejudge == 1  # rejudge job 1
    assert env.worker(env.ctx(judge)) == 0
    with env.session() as s:
        jobs = {j.id: (j.job_name, j.status, j.error_text) for j in s.scalars(select(JobRun))}
    rj = jobs[job.json()["id"]]
    assert rj[1] == "done", jobs
    return jobs


def test_t03_before_unknown_403_and_excluded_from_d(env: RegressEnv) -> None:
    from app.models import RawDocument

    detail = api_get(env, f"/complexes/{CID}")
    cur = detail["intake_current"]
    assert (cur["status"], cur["http_status"]) == ("확인 불가", 403), cur
    assert "403" in (cur.get("reason") or ""), cur
    assert cur.get("checked_at"), cur  # 화면 "확인 불가(403, 날짜)"의 날짜
    with env.session() as s:
        failed = s.scalars(
            select(RawDocument).where(RawDocument.source_kind == "official_site", RawDocument.http_status == 403)
        ).all()
    assert failed, "official_site 403 원문 행(실패도 데이터)이 없다"
    # 상황 후보 제외(D)
    assert _row(env, SCENARIO_D).get("rank") is None
    top5 = api_get(env, f"/snapshots/{SNAP}/dashboard", scenario=SCENARIO_D)["top5"]
    assert CID not in [t["complex_id"] for t in top5]


def test_t03_human_check_rejudge_includes_candidate_fake_judge(env: RegressEnv) -> None:
    _human_check_then_rejudge(env, "fake")
    row = _row(env, SCENARIO_D)
    assert row["intake"]["status"] == "가능" and row["intake"]["path"] == "human_check", row["intake"]
    assert row.get("rank") is not None and row["total"]["v"] is not None, row  # 후보 포함
    assert "jev_rerank" in env.jev.tools()  # 재판정이 실제 어댑터 경로로 돌았다


def test_t03_human_check_rejudge_includes_candidate_mock_judge(env: RegressEnv) -> None:
    """e2e(JUDGE_ADAPTER=mock)와 같은 구성. RA §9: 재판정 후 후보 포함 + G1 TOP 5 유지."""
    before = [t["complex_id"] for t in api_get(env, f"/snapshots/{SNAP}/dashboard", scenario="base")["top5"]]
    assert before
    _human_check_then_rejudge(env, "mock")
    row = _row(env, SCENARIO_D)
    assert row["intake"]["status"] == "가능", row["intake"]
    after = [t["complex_id"] for t in api_get(env, f"/snapshots/{SNAP}/dashboard", scenario="base")["top5"]]
    assert after, "mock 재판정 후 G1 통합 TOP 5 가 비었다(종합 점수 전부 미계산)"
    assert row.get("rank") is not None and row["total"]["v"] is not None, row

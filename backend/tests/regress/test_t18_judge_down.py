"""T18 판정기 다운 (RA §9) — 시스템 경계: collect.daily 잡(worker, 판정기 다운) → DB·API(G1·G7 배너 자료) → 복구 감지(worker 시작).

RA §9 기대 결과(원문 그대로): "수집·정규화 성공, `degraded=true`, 점수 미계산, G1·G7 배너, 복구 후 재판정 job 자동 등록"
(케이스: MockAdapter가 `JudgeUnavailable`). 픽스처 ``raw/scenarios/t18_judge_down.json``(rejudge_jobs_after_recovery = 1).

- 2026-10-09: 엘리프 팝업이 바뀐 날(``t8_popup_pairs.json`` today_changed) — 변경 단지 재판정이 필요하다.
  판정기 = ``MockAdapter(unavailable=True)``(env.ctx("down")) → collect.daily done(원문·접수 상태 행 저장),
  rejudge failed('judge_unavailable'), 스냅샷 degraded=true·building, score_run 0.
- 배너 자료: ``/api/health`` judge=degraded, 대시보드(G1) degraded=true·점수 없음, ``/api/ops/judgments``(G7·G8) degraded=true,
  ``/api/jobs``(G7) 실패 rejudge.
- 복구: 판정기 아직 다운(probe False) → worker 시작 시 재판정 등록 0. 복구(probe True) → 정확히 1개 자동 등록 → 판정·점수 → degraded=false.
- 보강(픽스처 'judgment_log: 호출마다 status=error 행, 같은 hash 재시도는 UPDATE'): 판정기 프로세스가 호출 중 죽는 경우(JevMcpAdapter).
"""

# ruff: noqa: E501

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .conftest import FIXTURE, WRITE, FakeJev, RegressEnv, api_get, load_json

pytestmark = pytest.mark.regress

SCEN = load_json(FIXTURE / "raw" / "scenarios" / "t18_judge_down.json")
PAIRS = load_json(FIXTURE / "raw" / "official_site" / "t8_popup_pairs.json")


def _count(s: Session, model: Any, *where: Any) -> int:
    return int(s.scalar(select(func.count()).select_from(model).where(*where)) or 0)


class PopupCollector:
    """공식 홈페이지 팝업(바뀐 PNG) → WP1 RawStore(fetched_at = 수집 시각)."""

    def __init__(self, ctx: Any, key: str = "today_changed") -> None:
        self.ctx = ctx
        self.key = key

    def fetch(self, region: Any, snapshot: Any, since: str | None) -> list[Any]:
        from app.collectors.reference.rawstore import RawStore

        p = PAIRS[self.key]
        with self.ctx.session_factory() as s:
            out = [
                RawStore(s).save_content(
                    source_kind="official_site",
                    url=p["url"],
                    content=(FIXTURE / "raw" / p["path"]).read_bytes(),
                    ext="png",
                    content_type="image/png",
                    fetched_at=self.ctx.now(),
                    region_id=region.id,
                    complex_id=p["complex_id"],
                    image_hash=p["image_hash"],
                )
            ]
            s.commit()
        return out


def _prewarm(env: RegressEnv) -> None:
    """정상 운영 상태: 판정기(FakeJev) 버전이 judgment_log 에 이미 기록돼 있다(D6 버전 변경 재판정과 분리)."""
    from app.judge.jev_mcp import JevMcpAdapter

    JevMcpAdapter(transport=env.jev, session_factory=env.factory, secrets=[]).call(
        "screen", {"text": "warm", "purpose": "warm"}, "screen:regress:t18-warm"
    )
    env.jev.calls.clear()


def _collect(env: RegressEnv, judge: str) -> int:
    r = env.client.post(
        "/api/jobs",
        headers=WRITE,
        json={"job_name": "collect.daily", "payload": {"region_id": 1, "sources": ["official_site"]}},
    )
    assert r.status_code == 202, r.text
    job_id = int(r.json()["id"])
    env.worker(env.ctx(judge, collectors={"official_site": PopupCollector}, probe_judge=lambda: False))
    return job_id


def test_t18_judge_down_degraded_banner_then_recovery_one_rejudge(env: RegressEnv) -> None:
    from app.models import ChangeEvent, IntakeStatus, JobRun, RawDocument, ScoreRun, Snapshot
    from app.scheduler.degraded import RECOVERY_REASON

    _prewarm(env)
    env.clock.day = date(2026, 10, 9)
    exp = SCEN["expected_snapshot"]
    with env.session() as s:
        raw0 = _count(s, RawDocument)
    assert api_get(env, "/health")["judge"] == "ok"

    collect_id = _collect(env, "down")
    job = api_get(env, f"/jobs/{collect_id}")
    assert job["status"] == "done", job  # 수집·정규화 성공
    rejudge_id = job["stats"]["rejudge_job_id"]
    rj = api_get(env, f"/jobs/{rejudge_id}")
    assert rj["status"] == "failed" and "judge_unavailable" in (rj["error_text"] or ""), rj
    assert rj["stats"]["degraded"] is True and rj["stats"]["score_runs"] == 0, rj["stats"]
    with env.session() as s:
        snap = s.scalars(select(Snapshot).where(Snapshot.asof_date == exp["asof_date"])).one()
        sid = snap.id
        assert (snap.id, snap.region_id, snap.status, snap.degraded) == (
            exp["id"],
            exp["region_id"],
            exp["status"],
            exp["degraded"],
        )
        assert snap.published_at is None
        assert _count(s, RawDocument) == raw0 + 1  # 원문 행 저장
        assert _count(s, IntakeStatus, IntakeStatus.snapshot_id == sid) > 0  # 정규화(접수 상태 행)
        assert _count(s, ChangeEvent, ChangeEvent.snapshot_id == sid, ChangeEvent.severity == "critical") == 1
        assert _count(s, ScoreRun, ScoreRun.snapshot_id == sid) == 0  # 점수 미계산
        assert _count(s, JobRun, JobRun.job_name == "snapshot.publish") == 0

    # G1·G7 배너가 읽는 API 자료
    health = api_get(env, "/health")
    assert health["judge"] == "degraded" and health["status"] == "degraded", health
    raw_health = env.client.get("/health")
    assert raw_health.status_code == 200 and raw_health.json()["judge"] == "degraded"
    dash = api_get(env, f"/snapshots/{sid}/dashboard", scenario="base")
    assert dash["degraded"] is True and dash["score_run_id"] is None and dash["top5"] == [], dash.get("top5")
    assert api_get(env, "/ops/judgments")["stats"]["degraded"] is True
    failed = api_get(env, "/jobs", status="failed", job_name="rejudge")
    assert [j["id"] for j in failed] == [rejudge_id]

    # 아직 다운: worker 시작 시 복구 감지 → 등록 0
    env.worker(env.ctx("down", probe_judge=lambda: False))
    with env.session() as s:
        assert _count(s, JobRun, JobRun.job_name == "rejudge") == 1

    # 복구: worker 시작 시 degraded 스냅샷마다 rejudge 1개 자동 등록 → 실행
    env.worker(env.ctx("fake", probe_judge=lambda: True))
    with env.session() as s:
        jobs = list(s.scalars(select(JobRun).where(JobRun.job_name == "rejudge").order_by(JobRun.id)))
        auto = [j for j in jobs if (j.payload or {}).get("reason") == RECOVERY_REASON]
        assert len(auto) == SCEN["expected"]["rejudge_jobs_after_recovery"] == 1, [
            (j.id, j.payload) for j in jobs
        ]
        assert len(jobs) == 2, [(j.id, j.payload, j.status) for j in jobs]  # 실패 1 + 복구 1(중복 없음)
        assert auto[0].payload["snapshot_id"] == sid and auto[0].status == "done", auto[0].error_text
        snap = s.get(Snapshot, sid)
        assert snap is not None and snap.degraded is False and snap.status == "published"
        assert _count(s, ScoreRun, ScoreRun.snapshot_id == sid) > 0
    assert env.jev.calls  # 복구 후 실제 판정
    assert api_get(env, "/health")["judge"] == "ok"
    dash = api_get(env, f"/snapshots/{sid}/dashboard", scenario="base")
    assert dash["degraded"] is False and len(dash["top5"]) >= 5

    # 복구 뒤 다시 시작해도 추가 등록 없음
    env.worker(env.ctx("fake", probe_judge=lambda: True))
    with env.session() as s:
        assert _count(s, JobRun, JobRun.job_name == "rejudge") == 2


class DyingJev(FakeJev):
    """판정기 프로세스가 연결(initialize)은 되지만 도구 호출에서 죽는다."""

    def call(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        from app.core.protocols import JudgeUnavailable

        raise JudgeUnavailable("regress: 판정기 프로세스 종료")


def test_t18_call_failure_writes_error_row_retry_updates_same_row(env: RegressEnv) -> None:
    from app.models import JudgmentLog, Snapshot

    env.clock.day = date(2026, 10, 9)
    # 판정기를 이미 쓰던 운영 상태(모델을 아는 adapter_version) — 실패 행과 재시도의 hash 가 같다
    _prewarm(env)
    healthy = env.jev
    env.jev = DyingJev()
    with env.session() as s:
        seq0 = max(s.scalars(select(JudgmentLog.seq)))
        version = s.get(JudgmentLog, seq0).adapter_version
    collect_id = _collect(env, "fake")
    assert api_get(env, f"/jobs/{collect_id}")["status"] == "done"
    with env.session() as s:
        snap = s.scalars(select(Snapshot).where(Snapshot.asof_date == "2026-10-09")).one()
        assert snap.degraded is True
        errors = list(s.scalars(select(JudgmentLog).where(JudgmentLog.seq > seq0)))
        assert errors and all(r.status == "error" for r in errors), [(r.tool, r.status) for r in errors]
        assert {r.adapter_version for r in errors} == {version}
        err_seqs = {r.seq for r in errors}

    env.jev = healthy
    env.worker(env.ctx("fake", probe_judge=lambda: True))
    with env.session() as s:
        snap = s.scalars(select(Snapshot).where(Snapshot.asof_date == "2026-10-09")).one()
        assert snap.degraded is False
        rows = {r.seq: r for r in s.scalars(select(JudgmentLog).where(JudgmentLog.seq.in_(err_seqs)))}
        # 같은 입력 재시도는 그 error 행을 갱신(UPDATE) — 새 행이 아니라 같은 seq 가 최종 상태가 된다
        assert set(rows) == err_seqs and all(r.status != "error" for r in rows.values()), [
            (r.seq, r.status) for r in rows.values()
        ]
        # 녹화(devseed)의 error 행 9개는 제외하고 센다
        assert _count(s, JudgmentLog, JudgmentLog.seq > seq0, JudgmentLog.status == "error") == 0

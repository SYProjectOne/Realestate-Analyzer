"""R4-FIX C1·m2 (D18-1·D18-2) — 잡 stats 의 실제 호출 = tools/call 수(수집 단계 판정 포함), 모델 변경 → 다음 실행 재판정.

| 테스트 | 확인 |
| --- | --- |
| ``test_m2_collect_stage_screen_counts_in_job_stats`` | 수집 단계 호재 screen 이 잡 ``judge_calls``·``tools_calls`` 에 들어간다 |
| ``test_second_rejudge_sends_no_tools_call_with_local_extract`` | provider none(extract) 섞인 파이프라인: 2회차 전송 0 · 잡 stats 0 |
| ``test_pipeline_model_change_event_and_next_run_rejudges`` | 응답 모델이 바뀐 실행은 키 그대로, change_event 1건, 다음 실행(새 어댑터)에서 새 키로 재판정 |
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.judge.base import ToolResponse
from app.models import ChangeEvent, JobRun, JudgmentLog
from app.scheduler import runner
from app.scheduler.context import SchedulerContext
from app.scheduler.jobs import enqueue
from app.scheduler.rejudge import enqueue_rejudge

from .conftest import Clock, SynthJev
from .test_assemble_f1a import FakeNews, _seed


class LocalExtractJev(SynthJev):
    """JEV 0.14.1 실제 모양: extract 가 후보를 못 찾으면 모델을 부르지 않고 ``provider: none``·``model: jev-latest``.
    이 픽스처 파이프라인에는 공고문 조각(extract)이 없어 classify 도 로컬 응답으로 섞는다 — 모델 호출 응답(noul·rerank·
    decide·verify)과 번갈아 오는 모양이 R4 의 screen↔extract 와 같다(메커니즘 시험)."""

    LOCAL = frozenset({"jev_extract", "jev_classify"})

    def call(self, tool_name: str, arguments: dict[str, Any]) -> ToolResponse:
        resp = super().call(tool_name, arguments)
        if tool_name in self.LOCAL:
            return ToolResponse(
                raw={**resp.raw, "model": "jev-latest", "provider": "none"}, is_error=False, duration_ms=1
            )
        return ToolResponse(raw={**resp.raw, "provider": "typesafe"}, is_error=False, duration_ms=1)


def _job(factory: sessionmaker[Session], job_id: int) -> JobRun:
    with factory() as s:
        row = s.get(JobRun, job_id)
        assert row is not None
        return row


def test_m2_collect_stage_screen_counts_in_job_stats(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], clock: Clock, jev: SynthJev
) -> None:
    _seed(factory)
    ctx = make_ctx(collectors={"news": lambda c: FakeNews(factory)})
    with factory() as s:
        job = enqueue(s, "collect.weekly", {"region_id": 1, "sources": ["news"], "asof_date": "2026-10-08"})
        s.commit()
        jid = job.id
    runner.run_until_idle(ctx)
    stats = _job(factory, jid).stats or {}
    # 호재 screen 1 + 공고 예정 screen 1(D20-2) + 단지 이름 extract 1(이름 없음 → 끝)
    assert sorted(jev.calls) == ["jev_extract", "jev_screen", "jev_screen"]
    assert stats.get("tools_calls") == 3 and stats.get("tools_calls_by_tool") == {"extract": 1, "screen": 2}
    assert stats.get("judge_calls") == 3, "수집 단계 판정도 잡 집계에 들어간다(m2)"


def _rejudge_once(factory: sessionmaker[Session], ctx: SchedulerContext, sid: int) -> dict[str, Any]:
    with factory() as s:
        job = enqueue_rejudge(s, sid, None, "test")
        s.commit()
        jid = job.id
    runner.run_until_idle(ctx)
    return dict(_job(factory, jid).stats or {})


def test_second_rejudge_sends_no_tools_call_with_local_extract(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int
) -> None:
    from app.judge.jev_mcp import JevMcpAdapter

    jev = LocalExtractJev()

    def ctx_() -> SchedulerContext:
        return make_ctx(
            adapter_factory=lambda: JevMcpAdapter(transport=jev, session_factory=factory, secrets=[])
        )

    first = _rejudge_once(factory, ctx_(), seeded)
    sent = len(jev.calls)
    second = _rejudge_once(factory, ctx_(), seeded)  # 새 문맥 = 새 어댑터(다음 실행)
    assert len(jev.calls) == sent, (
        f"2회차 tools/call {len(jev.calls) - sent}건: {sorted(set(jev.calls[sent:]))}"
    )
    with factory() as s:
        versions = set(s.scalars(select(JudgmentLog.adapter_version).where(JudgmentLog.status != "blocked")))
    assert len(versions) == 1 and next(iter(versions)).endswith("+jev-1.13.0")
    assert first["tools_calls"] == sent > 0
    assert second["tools_calls"] == 0 and second.get("judge_calls", 0) == 0


def test_pipeline_model_change_event_and_next_run_rejudges(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    from app.models import Complex

    _rejudge_once(factory, make_ctx(), seeded)
    with factory() as s:
        before_rows = s.scalar(select(func.count()).select_from(JudgmentLog))
        cx = s.get(Complex, 2)
        assert cx is not None
        cx.move_in_ym = "2028-06"  # 새 입력이 있어야 판정기 응답(model)을 본다
        s.commit()
    jev.model = "jev-1.14.0"
    jev.calls.clear()
    ctx = make_ctx()
    with factory() as s:
        job = enqueue_rejudge(s, seeded, [2], "단지 2 변경")
        s.commit()
        jid = job.id
    assert runner.run_once(ctx) == jid
    changed_run_calls = list(jev.calls)
    with factory() as s:
        new_rows = list(s.scalars(select(JudgmentLog).where(JudgmentLog.seq > (before_rows or 0))))
        assert new_rows and {r.adapter_version for r in new_rows} == {new_rows[0].adapter_version}
        assert new_rows[0].adapter_version.endswith("+jev-1.13.0"), "모델이 바뀐 실행은 옛 키 그대로(D18-1)"
        assert {r.output_json.get("model") for r in new_rows} == {"jev-1.14.0"}
        [ev] = s.scalars(select(ChangeEvent).where(ChangeEvent.entity == "judge")).all()
        assert (ev.field, ev.severity) == ("version", "critical")
        assert (ev.old_text or "").endswith("+jev-1.13.0") and (ev.new_text or "").endswith("+jev-1.14.0")
    assert changed_run_calls
    jev.calls.clear()
    runner.run_until_idle(ctx)  # 등록된 전체 재판정 = 다음 실행(어댑터를 새로 만든다)
    assert jev.calls, "다음 실행은 새 키(jev-1.14.0)로 전체 재판정"
    with factory() as s:
        latest = s.scalars(select(JudgmentLog).order_by(JudgmentLog.seq.desc())).first()
        assert latest is not None and latest.adapter_version.endswith("+jev-1.14.0")
        assert (
            s.scalar(select(func.count()).select_from(ChangeEvent).where(ChangeEvent.entity == "judge")) == 1
        )

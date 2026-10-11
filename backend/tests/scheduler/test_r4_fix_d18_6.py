"""R4-FIX M5 (D18-6) — bootstrap 뒤 같은 날 변화 없는 ``collect.daily`` 는 새 판정 0 (T8 실데이터, 녹화 원문 재생).

R4: bootstrap 1시간 뒤 같은 기준일 daily 가 change_event 29 · 재판정 7단지 · 새 판정 16(+숨은 9)을 만들었다 — 잔여 공고 원문이
저장 순서에 따라 다른 단지에 묶였고(공식 홈페이지 URL·시행사·접수일이 1회차에 비어 있다가 채워짐), 숨은 판정기 호출(C1)로
접수 분류가 다시 돌았다. 녹화 재생은 ``test_r4_fix_d18_4`` 와 같은 R4 원문(청약홈·공고문 — 나머지 수집기는 없음).
판정기는 R4 모양(extract = provider none·jev-latest)의 결정적 가짜(``LocalExtractJev``).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import Settings
from app.judge.jev_mcp import JevMcpAdapter
from app.models import JobRun, JudgmentLog, Region
from app.scheduler import runner
from app.scheduler.context import SchedulerContext
from app.scheduler.jobs import enqueue

from .test_r4_fix_c1_jobs import LocalExtractJev
from .test_r4_fix_d18_4 import _setup


def _job(factory: sessionmaker[Session], name: str) -> JobRun:
    with factory() as s:
        row = s.scalars(select(JobRun).where(JobRun.job_name == name).order_by(JobRun.id.desc())).first()
        assert row is not None, name
        return row


def test_same_day_daily_after_bootstrap_makes_no_new_judgment(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], test_settings: Settings
) -> None:
    ah, pdf = _setup(test_settings, factory)
    jev = LocalExtractJev()
    collectors: dict[str, Any] = {"applyhome": lambda c: ah, "notice_pdf": lambda c: pdf}
    ctx = make_ctx(
        collectors=collectors,
        adapter_factory=lambda: JevMcpAdapter(transport=jev, session_factory=factory, secrets=[]),
    )
    with factory() as s:
        region = s.get(Region, 1)
        assert region is not None
        region.status = "bootstrapping"
        enqueue(s, "region.bootstrap", {"region_id": 1}, kind="manual")
        s.commit()
    runner.run_until_idle(ctx)
    boot = _job(factory, "region.bootstrap")
    assert boot.status == "done", (boot.error_text, (boot.stats or {}).get("errors"))
    with factory() as s:
        rows_before = s.scalar(select(func.count()).select_from(JudgmentLog))
    sent = len(jev.calls)
    assert sent > 0

    with factory() as s:
        enqueue(s, "collect.daily", {"region_id": 1, "sources": ["applyhome_list", "applyhome_detail"]})
        s.commit()
    runner.run_until_idle(ctx)
    daily = _job(factory, "collect.daily")
    stats = daily.stats or {}
    assert stats.get("change_events") == 0, stats.get("change_events")
    assert stats.get("rejudge_complex_ids") == []
    assert len(jev.calls) == sent, (
        f"같은 날 daily 의 tools/call {len(jev.calls) - sent}건: {sorted(set(jev.calls[sent:]))}"
    )
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(JudgmentLog)) == rows_before
        assert s.scalar(select(func.count()).select_from(JobRun).where(JobRun.job_name == "rejudge")) == 0
    assert (boot.stats or {}).get("tools_calls") == sent and stats.get("tools_calls", 0) == 0

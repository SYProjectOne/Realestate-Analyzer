"""R5-PIPE 2(D25 — D24-1 N16 확인): degraded·이월(carry) 발행 경로에서도 같은 날 daily 가 이벤트 없이 체크리스트를 바꾸지 않는다.

CORE11 수정(``pipeline._sync_checklist``)은 판정 파이프라인이 **끝까지 성공**할 때만 체크리스트를 다시 맞춘다. 그 밖의 경로:

| 테스트 | 경로 | 확인 |
| --- | --- | --- |
| ``test_degraded_bootstrap_then_same_day_daily`` | ``region.bootstrap`` 의 판정이 P6(noul)에서 판정기 장애(JudgeUnavailable) → degraded(발행 없음) | degraded 직후 체크리스트 = 그 시점 사실로 다시 맞춘 것(주간 단계 트랙 A 후보·P4 제외 반영) · 판정기 복구 뒤 같은 날 ``collect.daily`` 의 수집 조립 체크리스트 동기화가 바꾸는 행 0 · 그 뒤 같은 날 daily 한 번 더 → 체크리스트 행 그대로 |
| ``test_carry_publish_then_same_day_daily`` | bootstrap 성공·발행 → 같은 날 ``collect.weekly``(변경 없음 → 이월 carry 발행 또는 빈 리비전 정리) → 같은 날 ``collect.daily`` | 주간 잡 뒤 체크리스트 = 사실로 다시 맞춘 것 · daily 체크리스트 동기화가 바꾸는 행 0 · 체크리스트 행 그대로 · 사실 change_event 0 |

재생 세트(CORE10·CORE11 과 같은 저장소 녹화 ``r4b``·``r4d``) + 녹화 뉴스 1건(주간 단계), 가짜 판정기(``BootJev``). 외부 호출 없음.
"""

# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.protocols import JudgeUnavailable
from app.core.settings import Settings, set_settings
from app.judge.jev_mcp import JevMcpAdapter, ToolResponse
from app.models import Complex, Snapshot
from app.scheduler.context import SchedulerContext

from . import _idem
from .conftest import Clock
from .test_core10_idempotency import DAILY, TickClock, _fact_events, _max_event, _run, _set
from .test_core11_bootstrap_idempotency import BootJev, _checklist_rows, _resync_changes

N16_SETS = ["r4b", "r4d"]
MOVED = ("inserted", "updated", "closed", "reopened")


@dataclass
class FlakyJev(BootJev):
    """``down_at`` 도구를 처음 받는 순간부터 장애(JudgeUnavailable) — 그 전 단계(P1~P5·주간 단계 판정)는 정상."""

    down_at: str | None = None

    def call(self, tool_name: str, arguments: dict[str, Any]) -> ToolResponse:
        if self.down_at is not None and tool_name == f"jev_{self.down_at}":
            self.down = True
        return super().call(tool_name, arguments)

    def recover(self) -> None:
        self.down_at = None
        self.down = False


def _setup(
    name: str, tmp_path: Path, make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session],
    test_settings: Settings, jev: BootJev, clock: Clock, monkeypatch: pytest.MonkeyPatch,
) -> tuple[_idem.ReplaySet, SchedulerContext]:  # fmt: skip
    rs = _idem.with_default_news(_set(name, tmp_path))
    if rs.in_place:
        set_settings(test_settings.model_copy(update={"raw_dir": rs.raw_root}))
    else:
        rs.install(test_settings.raw_dir)
    y, m, d = (int(x) for x in rs.asof.split("-"))
    tick = TickClock(day=date(y, m, d))
    monkeypatch.setattr(clock, "day", tick.day)
    monkeypatch.setattr(clock, "now", tick.now)
    monkeypatch.setattr("app.normalize.changes.now_kst", tick.now)
    rs.seed(factory)
    cols = _idem.collectors(rs, factory, weekly=True)
    ctx = make_ctx(
        collectors=cols.as_ctx(),
        adapter_factory=lambda: JevMcpAdapter(transport=jev, session_factory=factory, secrets=[]),
    )
    return rs, ctx


def _moved(stats: dict[str, Any]) -> dict[str, Any]:
    cl = stats.get("assembled", {}).get("checklist", {}) or {}
    return {k: cl[k] for k in MOVED if cl.get(k)}


def _track_a(factory: sessionmaker[Session]) -> list[int]:
    with factory() as s:
        return [c.id for c in s.scalars(select(Complex).where(Complex.track == "A", Complex.applyhome_id.is_(None)))]


@pytest.mark.parametrize("name", N16_SETS)
def test_degraded_bootstrap_then_same_day_daily(
    name: str, tmp_path: Path, make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session],
    test_settings: Settings, clock: Clock, monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    jev = FlakyJev(extract_values={"balance_pct": "30%", "down_payment_pct": "10%"}, down_at="noul")
    rs, ctx = _setup(name, tmp_path, make_ctx, factory, test_settings, jev, clock, monkeypatch)
    boot = _run(factory, ctx, "region.bootstrap", {"region_id": 1})
    assert boot.get("degraded") is True and not boot.get("published"), {k: boot.get(k) for k in ("degraded", "published")}
    # 사전 조건: 주간 단계가 트랙 A 후보를 만들었다(N16 경로)
    assert _track_a(factory), boot["weekly"].get("assembled")
    with factory() as s:
        snap = s.scalars(select(Snapshot).order_by(Snapshot.id.desc())).first()
        assert snap is not None and snap.degraded

    problems: list[str] = []
    resync = _resync_changes(factory, rs.asof)
    if resync:
        problems.append(f"[degraded bootstrap 직후] 체크리스트가 그 시점 사실과 어긋남 — 다시 맞추면 {resync}")

    jev.recover()
    ctx.reset_adapter()
    # 복구 뒤 daily 는 첫 판정(전체 재판정)을 등록한다 — 그 판정 결과 이벤트는 정당하므로 여기서는 수집 조립의 체크리스트만 본다
    out = _run(factory, ctx, "collect.daily", {"region_id": 1, "sources": DAILY})
    moved = _moved(out)
    if moved:
        problems.append(f"[복구 뒤 같은 날 첫 daily] 수집 조립 체크리스트 동기화가 행을 바꿈 {moved}")
    cl1 = _checklist_rows(factory)
    out2 = _run(factory, ctx, "collect.daily", {"region_id": 1, "sources": DAILY})
    moved2 = _moved(out2)
    if moved2:
        problems.append(f"[같은 날 두 번째 daily] 체크리스트 동기화가 행을 바꿈 {moved2}")
    if _checklist_rows(factory) != cl1:
        problems.append("[같은 날 두 번째 daily] 체크리스트 행이 바뀜")
    assert not problems, f"{name}: degraded 경로 N16 위반\n" + "\n".join(problems)


@pytest.mark.parametrize("name", N16_SETS)
def test_carry_publish_then_same_day_daily(
    name: str, tmp_path: Path, make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session],
    test_settings: Settings, clock: Clock, monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    jev = BootJev(extract_values={"balance_pct": "30%", "down_payment_pct": "10%"})
    rs, ctx = _setup(name, tmp_path, make_ctx, factory, test_settings, jev, clock, monkeypatch)
    boot = _run(factory, ctx, "region.bootstrap", {"region_id": 1})
    assert boot.get("published") is True, {k: boot.get(k) for k in ("published", "degraded", "errors")}
    problems: list[str] = []
    ev0 = _max_event(factory)
    weekly = _run(factory, ctx, "collect.weekly", {"region_id": 1})
    resync = _resync_changes(factory, rs.asof)
    if resync:
        problems.append(f"[같은 날 weekly({weekly.get('carry_forward') or weekly.get('rejudge_job_id')}) 뒤] 체크리스트가 사실과 어긋남 — 다시 맞추면 {resync}")
    cl0 = _checklist_rows(factory)
    out = _run(factory, ctx, "collect.daily", {"region_id": 1, "sources": DAILY})
    moved = _moved(out)
    if moved:
        problems.append(f"[weekly 뒤 같은 날 daily] 수집 조립 체크리스트 동기화가 행을 바꿈 {moved}")
    if _checklist_rows(factory) != cl0:
        problems.append("[weekly 뒤 같은 날 daily] 체크리스트 행이 바뀜")
    facts = _fact_events(factory, ev0)
    if facts:
        problems.append(f"[weekly·daily] 사실 change_event {len(facts)}건: {facts[:8]}")
    assert not problems, f"{name}: 이월 경로 N16 위반\n" + "\n".join(problems)


def test_flaky_jev_raises_unavailable() -> None:
    """테스트 도구 자체 확인: down_at 도구에서 JudgeUnavailable, recover 뒤 정상."""
    j = FlakyJev(down_at="noul")
    j.call("jev_screen", {"text": "a", "purpose": "b"})
    with pytest.raises(JudgeUnavailable):
        j.call("jev_noul", {"propositions": ["x"]})
    with pytest.raises(JudgeUnavailable):
        j.call("jev_screen", {"text": "a", "purpose": "b"})
    j.recover()
    j.call("jev_screen", {"text": "a", "purpose": "b"})

"""D23-1(R4 4차 재시험 N13·N14 — R4-CORE10): **재정규화 멱등성 속성 테스트**.

같은 원문을 다시 정규화하면 DB 의 모든 엔티티(단지·타입·납부 조건·경쟁률·잔여 이력·출처 행·채택 표식(추출·감사·compare)·
체크리스트·접수 상태 등)가 바이트 단위로 그대로여야 한다. 개별 결함을 하나씩 막는 대신 녹화 원문 전체로:

1. ``region.bootstrap``(일일 단계 + 판정 P1~P9 + 발행) → DB 스냅샷 S0
2. 같은 날 ``collect.daily``(같은 원문, 같은 순서) → S0 그대로 · 사실 change_event 0 · ``tools/call`` 0
3. 같은 날 ``collect.daily``(같은 원문, **순서를 섞어서** — 시드 2개) → S0 그대로 · 이벤트 0 · ``tools/call`` 0
4. 같은 스냅샷 재판정 → ``tools/call`` 0(가짜 판정기 전송 계층 계수) · S0 그대로
5. **다음 날** ``collect.daily``(같은 원문, 섞어서) → S0 그대로 · 이벤트 0 · 수집 단계 ``tools/call`` 0(그 뒤 재판정은 기준일 상대 명제가
   바뀌어 새 호출이 정상이라 세지 않는다 — D18-6 은 같은 날 기준)

DB 스냅샷 = 실행·리비전 기록(``_idem.RUN_TABLES`` — 사유와 함께)을 뺀 모든 테이블의 모든 행·모든 열(새 테이블은 자동으로 대상) +
최신 리비전 접수 상태 행(리비전 id·행 id·분류 복사 표식 제외).

재생 세트(R4 1~4차 녹화 — 저장소에 있는 것 전부):

- ``r4``: R4 1차(2026-10-12, ``r4_remnant`` — 잔여 공고·원 공고 다시 받기 4단지).
- ``r4b``: R4 재시험(2차, ``r4b_core8`` — 엘리프 원·잔여 공고, 단위 표, NUL, 동 없는 주소).
- ``r4c``: R4 3차(``r4c_core9`` — 판정기 추출 6단지, 법정동 보정, 원 번호 인용 + 원 공고 응답).
- ``r4d``: R4 4차(``r4d_core10.zip`` — bootstrap 일일 단계 원문 중 단지 18개: N13 중복 경쟁률 11단지 · N14 compare 채택 단지 ·
  N9 추출 · 원 공고 다시 받기 · 공식 홈페이지 DOM 텍스트, 청약홈 목록 전부).
- ``r4d-full``(로컬): R4 4차 bootstrap 일일 단계 원문 **전부**(청약홈 559 + 원 공고 77 + 공고문 137 + 공식 홈페이지 90). 녹화가
  수십 MB 라 저장소에 넣지 않고 ``R4_REPLAY_MANIFEST=<docs.json>`` 이 있을 때만 돈다(없으면 skip — ``R4_CORE10_TESTS.md`` §1).

판정기는 가짜(``SynthJev`` — 실제 호출 수 = 전송 계층 ``tools/call``), 외부 사이트 없음.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import Settings, set_settings
from app.core.time import KST
from app.judge.jev_mcp import JevMcpAdapter
from app.models import ChangeEvent, JobRun, Snapshot
from app.scheduler import runner
from app.scheduler.context import SchedulerContext
from app.scheduler.jobs import enqueue
from app.scheduler.rejudge import enqueue_rejudge

from . import _idem
from .conftest import Clock, SynthJev

FIX = Path(__file__).resolve().parents[1] / "normalize" / "fixtures"
FACT_ENTITIES = frozenset(
    {"complex", "complex_type", "payment_terms", "competition", "remaining_event", "notice"}
)
DAILY = ["applyhome_list", "applyhome_detail", "official_site"]


@dataclass
class TickClock(Clock):
    """호출마다 1초 흐르는 시계(실제 실행처럼 — 고정 시각이면 이벤트와 잡 끝 시각이 같아 이월 판정이 흔들린다)."""

    tick: int = 0

    def now(self) -> datetime:
        self.tick += 1
        return datetime(self.day.year, self.day.month, self.day.day, 2, 0, tzinfo=KST) + timedelta(
            seconds=self.tick
        )


@pytest.fixture
def jev() -> SynthJev:
    return SynthJev(extract_values={"balance_pct": "30%", "down_payment_pct": "10%"})


def _set(name: str, tmp: Path) -> _idem.ReplaySet:
    if name == "r4":
        return _idem.remnant_set(FIX / "r4_remnant")
    if name == "r4b":
        return _idem.grouped_set("r4b", FIX / "r4b_core8", ["elif", "n1", "n2", "n7"], asof="2026-10-12")
    if name == "r4c":
        return _idem.grouped_set(
            "r4c", FIX / "r4c_core9", ["n9", "n10", "n12"], originals=("n10_orig",), asof="2026-10-12"
        )
    if name == "r4d":
        return _idem.load_zip("r4d", FIX / "r4d_core10.zip", tmp / "r4d")
    full = os.environ.get("R4_REPLAY_MANIFEST")
    if not full:
        pytest.skip("R4_REPLAY_MANIFEST 없음(로컬 전체 재생 — R4 4차 원문 전부)")
    return _idem.load_manifest("r4d-full", Path(full), in_place=True)


SETS = ["r4", "r4b", "r4c", "r4d", "r4d-full"]


def _run(
    factory: sessionmaker[Session], ctx: SchedulerContext, name: str, payload: dict[str, Any]
) -> dict[str, Any]:
    with factory() as s:
        job = enqueue(s, name, payload, kind="manual")
        s.commit()
        jid = job.id
    runner.run_until_idle(ctx)
    with factory() as s:
        row = s.get(JobRun, jid)
        assert row is not None and row.status == "done", (
            name,
            row.status if row else None,
            row.error_text if row else None,
        )
        return dict(row.stats or {})


def _fact_events(factory: sessionmaker[Session], after_id: int) -> list[tuple[Any, ...]]:
    with factory() as s:
        return [
            (e.entity, e.entity_id, e.field, e.old_text, e.new_text, e.severity)
            for e in s.scalars(select(ChangeEvent).where(ChangeEvent.id > after_id).order_by(ChangeEvent.id))
            if e.entity in FACT_ENTITIES
        ]


def _max_event(factory: sessionmaker[Session]) -> int:
    with factory() as s:
        return int(s.scalar(select(func.max(ChangeEvent.id))) or 0)


def _rejudge_latest(factory: sessionmaker[Session], ctx: SchedulerContext) -> None:
    with factory() as s:
        sid = s.scalar(select(func.max(Snapshot.id)))
        assert sid is not None
        enqueue_rejudge(s, int(sid), None, "같은 스냅샷 재판정")
        s.commit()
    runner.run_until_idle(ctx)


@pytest.mark.parametrize("name", SETS)
def test_renormalize_is_idempotent(
    name: str,
    tmp_path: Path,
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    test_settings: Settings,
    jev: SynthJev,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """bootstrap → 같은 원문 재정규화 → 순서를 섞어 재정규화 → 다음 날 재정규화 → 재판정: DB 스냅샷 동일 · 사실 change_event 0 ·
    tools/call 0."""
    rs = _set(name, tmp_path)
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
    cols = _idem.collectors(rs, factory)
    ctx = make_ctx(
        collectors=cols.as_ctx(),
        adapter_factory=lambda: JevMcpAdapter(transport=jev, session_factory=factory, secrets=[]),
    )
    boot = _run(factory, ctx, "region.bootstrap", {"region_id": 1})
    assert not boot["daily"].get("store_errors"), boot["daily"]["store_errors"]
    s0 = _idem.db_state(factory)
    assert s0["complex"] and s0["field_provenance"], "재생 세트가 단지·출처를 만들었다"
    calls0 = len(jev.calls)
    problems: list[str] = []

    def renormalize(step: str, seed: int | None, days: int) -> None:
        nonlocal s0
        cols.shuffle(seed)
        if days:
            nxt = tick.day + timedelta(days=days)
            monkeypatch.setattr(tick, "day", nxt)
            monkeypatch.setattr(clock, "day", nxt)
        ev0 = _max_event(factory)
        sent = len(jev.calls)
        daily = _run(factory, ctx, "collect.daily", {"region_id": 1, "sources": DAILY})
        st = _idem.db_state(factory)
        diff = _idem.state_diff(s0, st)
        if diff:
            problems.append(f"[{step}] DB 스냅샷 차이 {_idem.changed_cells(s0, st)}:\n" + "\n".join(diff))
        facts = _fact_events(factory, ev0)
        if facts:
            problems.append(f"[{step}] 사실 change_event {len(facts)}건: {facts[:10]}")
        if len(jev.calls) != sent:
            problems.append(f"[{step}] tools/call {len(jev.calls) - sent}건: {sorted(set(jev.calls[sent:]))}")
        if daily.get("store_errors"):
            problems.append(f"[{step}] store_errors {daily['store_errors'][:5]}")
        s0 = s0 if not diff else st  # 다음 단계는 직전 상태 기준(차이가 겹쳐 보고되지 않게)

    renormalize("같은 원문 재정규화", None, 0)
    renormalize("순서를 섞어 재정규화", 20261013, 0)
    renormalize("순서를 다시 섞어 재정규화", 7, 0)
    sent = len(jev.calls)
    _rejudge_latest(factory, ctx)
    if len(jev.calls) != sent:
        problems.append(f"[재정규화 뒤 재판정] tools/call {len(jev.calls) - sent}건: {jev.calls[sent:][:20]}")
    st = _idem.db_state(factory)
    diff = _idem.state_diff(s0, st)
    if diff:
        problems.append(
            f"[재정규화 뒤 재판정] DB 스냅샷 차이 {_idem.changed_cells(s0, st)}:\n" + "\n".join(diff)
        )
    # 다음 날(기준일이 바뀜) 같은 원문 — 정규화 테이블·사실 이벤트·수집 단계 판정 0. 그 뒤 재판정은 기준일 상대 명제(noul 사다리
    # 목표월 등)가 바뀌어 새 호출이 정상이므로 세지 않는다(D18-6 은 같은 날 기준)
    renormalize("다음 날 같은 원문 재정규화(섞어서)", 13, 1)
    assert not problems, (
        f"{rs.name}: 재정규화 멱등성 위반 {len(problems)}건 (bootstrap tools/call {calls0})\n"
        + "\n".join(problems)
    )

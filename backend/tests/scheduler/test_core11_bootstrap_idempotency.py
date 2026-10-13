"""D24-1(R4 5차 재시험 N16 — R4-CORE11): **첫 수집 전체 → 같은 날 daily 멱등성 속성 테스트**(D23-1 범위 확장).

N16: ``region.bootstrap`` 은 일일 단계 조립(청약홈·공고문)에서만 체크리스트를 맞추고, 그 뒤 주간 단계(뉴스 → 트랙 (A) 공고 예정
후보 단지 생성)와 판정(P4 포함 classify → 제외 단지)이 체크리스트 근거를 바꿔도 발행 전에 다시 맞추지 않았다. 그래서 같은 날 첫
``collect.daily`` 가 **같은 원문**을 다시 정규화하며 체크리스트를 이벤트 없이 바꿨다(R4 5차: 트랙 A 2단지 6행 생김 · 제외 단지 법적
확인 2행 na — 리비전 5 보고서 저장본 체크리스트 200 → 206).

CORE10 속성 테스트(``test_core10_idempotency``)는 주간 단계 원문이 없고 가짜 판정기가 모든 단지를 포함으로 분류해 이 경로를 밟지
않았다. 여기서는 같은 재생 세트로:

1. ``region.bootstrap`` — 일일 단계 + **주간 단계 뉴스 원문**(매니페스트 ``news`` 또는 저장소 R4 1차 뉴스 녹화) + 판정 P1~P9(가짜
   판정기 ``BootJev``: 뉴스 공고 예정 신호·이름 추출 → 트랙 A 후보, **포함 classify 첫 배치의 가장 작은 단지 = public_sale auto(제외)**)
   + 발행 → 사전 조건(트랙 A 후보 생김 · 제외 단지 있음 — 수정 전에도 성립) + **발행 시점 체크리스트 = 그 시점 사실로 다시 맞춘
   체크리스트**(``sync_checklist`` 를 돌려 보고 되돌림 — 바뀌는 행 0) · 트랙 A 후보마다 '모집공고 예정' open · 제외 단지 자동 항목 open
   0 · 발행 보고서 저장본 체크리스트가 그 상태
2. 같은 날 ``collect.daily``(같은 원문·같은 순서) → DB 스냅샷(체크리스트 포함 정규화 테이블 전부) 그대로 · 사실 change_event 0 ·
   ``tools/call`` 0 · **새 발행 리비전 보고서 체크리스트 = bootstrap 리비전 것**
3. 같은 날 ``collect.daily``(순서를 섞어서) → 같음
4. 같은 스냅샷 재판정 → ``tools/call`` 0 · DB 스냅샷 그대로

재생 세트는 CORE10 과 같다(``r4``·``r4b``·``r4c``·``r4d`` + 로컬 ``r4d-full`` — ``R4_REPLAY_MANIFEST``; R4 5차 원문 매니페스트는
``scripts/replay_manifest.py`` 가 뉴스 원문도 담는다). 판정기는 가짜, 외부 사이트 없음.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import Settings, set_settings
from app.judge.jev_mcp import JevMcpAdapter
from app.judge.payloads import INCLUSION_CLASSES
from app.models import ChecklistItem, Complex, Scenario, Snapshot
from app.normalize.checklist import excluded_for_checklist, item_key, sync_checklist
from app.scheduler.context import SchedulerContext

from . import _idem
from .conftest import Clock, SynthJev
from .test_core10_idempotency import (
    DAILY,
    SETS,
    TickClock,
    _fact_events,
    _max_event,
    _rejudge_latest,
    _run,
    _set,
)

QUOTED = re.compile(r"[‘'\"“]([^’'\"”]{2,40})[’'\"”]")
INCLUSION_IDS = [c["id"] for c in INCLUSION_CLASSES]
EXCLUDED_LABEL = "public_sale"


@dataclass
class BootJev(SynthJev):
    """첫 수집 전체를 밟는 가짜 판정기(판정 자체는 가짜가 정한다 — 코드는 판정기 결과만 쓴다):

    - screen: '입주를 시작' 기사는 skip(오피스텔 입주 기사 — 공고 예정·호재 아님), 나머지 pass
    - extract: 공고 예정 이름 추출(문서가 '제목:' 으로 시작)은 발췌의 따옴표 안 이름, 그 밖은 ``SynthJev``(extract_values)
    - classify: 포함/제외 배치면 **처음 본 배치의 가장 작은 단지 id** 를 public_sale(auto)로 — 그 뒤 같은 단지는 늘 같은 답,
      나머지는 첫 클래스(private_sale_apt). 공고 예정·접수 상태 등 다른 classify 는 ``SynthJev`` 그대로(첫 클래스)
    """

    excluded_item: str | None = None

    def _screen(self, a: dict[str, Any]) -> dict[str, Any]:
        if "입주를 시작" in str(a.get("text", "")):
            return {"probabilities": {"relevance": 0.05}, "recommendation": {"action": "skip"}}
        return super()._screen(a)

    def _extract(self, a: dict[str, Any]) -> dict[str, Any]:
        doc = str(a.get("document", ""))
        if not doc.startswith("제목:"):
            return super()._extract(a)
        found = list(dict.fromkeys(QUOTED.findall(doc.split("발췌:", 1)[-1])))
        out = []
        for i, f in enumerate(a["fields"]):
            v = found[i] if i < len(found) else None
            out.append({"id": f["id"], "value": v, "status": "auto" if v else "not_found", "confidence": 0.9})
        return {"results": out}

    def _classify(self, a: dict[str, Any]) -> dict[str, Any]:
        out = super()._classify(a)
        if [c["id"] for c in a["classes"]] != INCLUSION_IDS:
            return out
        if self.excluded_item is None:
            self.excluded_item = min((it["id"] for it in a["items"]), key=lambda i: int(i.split(":")[1]))
        for r in out["results"]:
            if r["id"] == self.excluded_item:
                r.update(classification=EXCLUDED_LABEL, probabilities={EXCLUDED_LABEL: 0.96})
        return out


@pytest.fixture
def jev() -> BootJev:
    return BootJev(extract_values={"balance_pct": "30%", "down_payment_pct": "10%"})


def _checklist_rows(factory: sessionmaker[Session]) -> list[tuple[Any, ...]]:
    with factory() as s:
        return [
            (i.id, i.complex_id, i.kind, i.title, i.due_date, i.status, i.closed_by, i.note)
            for i in s.scalars(select(ChecklistItem).order_by(ChecklistItem.id))
        ]


def _resync_changes(factory: sessionmaker[Session], asof: str) -> dict[str, Any]:
    """지금 사실로 체크리스트를 다시 맞추면 바뀌는 수(돌려 보고 되돌린다 — DB 는 그대로)."""
    with factory() as s:
        st = sync_checklist(s, 1, asof_date=asof).stats()
        s.rollback()
    return {k: st[k] for k in ("inserted", "updated", "closed", "reopened") if st[k]}


def _report_checklist(factory: sessionmaker[Session], snapshot_id: int) -> list[tuple[Any, ...]]:
    """발행 리비전 보고서 저장본(기본 시나리오)의 체크리스트 행."""
    from app.reports.codec import decode_data
    from app.snapshot_view import stored

    with factory() as s:
        base = s.scalars(select(Scenario.id).where(Scenario.code == "base")).one()
        rep = stored(s, snapshot_id, "report", scenario=str(base))
    assert rep is not None, f"리비전 {snapshot_id} 보고서 저장본 없음"
    data = decode_data(rep["data"])
    return [(c.kind, c.title, c.complex_name, c.due, c.status, c.note) for c in data.checklist]


def _latest_published(factory: sessionmaker[Session]) -> int:
    with factory() as s:
        sid = s.scalar(select(func.max(Snapshot.id)).where(Snapshot.status == "published"))
    assert sid is not None, "발행 리비전 없음"
    return int(sid)


@pytest.mark.parametrize("name", SETS)
def test_full_bootstrap_then_same_day_daily_is_idempotent(
    name: str,
    tmp_path: Path,
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    test_settings: Settings,
    jev: BootJev,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """bootstrap(일일·주간·판정·발행) → 같은 날 daily(같은 순서·섞은 순서) → 재판정: 체크리스트 포함 DB 스냅샷 동일 · 사실 이벤트 0 ·
    tools/call 0 · 발행 보고서 체크리스트 동일. bootstrap 발행 체크리스트 = 그 시점 사실로 다시 맞춘 것(N16)."""
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
    boot = _run(factory, ctx, "region.bootstrap", {"region_id": 1})
    assert not boot["daily"].get("store_errors"), boot["daily"]["store_errors"]
    assert boot.get("published") is True, {k: boot.get(k) for k in ("published", "degraded", "errors")}

    # 사전 조건(수정 전에도 성립 — 이 세트가 N16 경로를 밟는다): 주간 단계가 트랙 A 후보를, 판정이 제외 단지를 만들었다.
    # r4(R4 1차 녹화)는 법정동 참조 행이 없어 청약홈 단지가 전부 '범위 경계'(포함 classify 대상 없음) — 트랙 A 경로만 밟는다
    upcoming = boot["weekly"].get("assembled", {}).get("upcoming", {})
    excluded_id: int | None = None
    with factory() as s:
        track_a = [
            c.id
            for c in s.scalars(select(Complex).where(Complex.track == "A", Complex.applyhome_id.is_(None)))
        ]
        if jev.excluded_item is None:
            classes = sorted(
                {
                    c.inclusion_class
                    for c in s.scalars(select(Complex).where(Complex.applyhome_id.is_not(None)))
                }
            )
            assert name == "r4" and classes == ["범위 경계"], ("포함 classify 배치가 없었다", classes)
        else:
            ex = s.get(Complex, int(jev.excluded_item.split(":")[1]))
            assert ex is not None and excluded_for_checklist(ex), (
                (ex.inclusion_class, ex.inclusion_decision) if ex else None
            )
            excluded_id = ex.id
    assert upcoming.get("created", 0) >= 1 and track_a, ("주간 단계 트랙 A 후보 없음", upcoming)

    problems: list[str] = []
    # 1. bootstrap 발행 체크리스트 = 그 시점 사실로 다시 맞춘 체크리스트(N16)
    resync = _resync_changes(factory, rs.asof)
    if resync:
        problems.append(f"[bootstrap 직후] 체크리스트가 bootstrap 최종 사실과 어긋남 — 다시 맞추면 {resync}")
    with factory() as s:
        items = list(
            s.scalars(select(ChecklistItem).where(ChecklistItem.complex_id.in_([*track_a, excluded_id or 0])))
        )
    no_notice = [
        c
        for c in track_a
        if not any(i.complex_id == c and i.title == "모집공고 예정" and i.status == "open" for i in items)
    ]
    if no_notice:
        problems.append(
            f"[bootstrap 직후] 트랙 A 후보 {no_notice} 에 '모집공고 예정' open 없음(주간 단계 뒤 체크리스트 미동기화)"
        )
    still_open = [
        (i.id, i.title)
        for i in items
        if i.complex_id == excluded_id
        and i.status == "open"
        and not item_key(i.kind, i.title).startswith("title:")
    ]
    if still_open:
        problems.append(
            f"[bootstrap 직후] 제외 단지 {excluded_id} 자동 항목 open {still_open}(판정 뒤 체크리스트 미동기화)"
        )
    boot_sid = _latest_published(factory)
    rep0 = _report_checklist(factory, boot_sid)
    rep_titles = {(r[2], r[1]) for r in rep0}
    with factory() as s:
        a_names = {cx.name for cx in s.scalars(select(Complex).where(Complex.id.in_(track_a)))}
    missing = sorted(n for n in a_names if (n, "모집공고 예정") not in rep_titles)
    if missing:
        problems.append(f"[bootstrap 발행 보고서] 트랙 A 후보 '모집공고 예정' 행 없음: {missing}")

    s0 = _idem.db_state(factory)
    cl0 = _checklist_rows(factory)
    calls0 = len(jev.calls)

    def daily(step: str, seed: int | None) -> None:
        nonlocal s0, rep0
        cols.shuffle(seed)
        ev0 = _max_event(factory)
        sent = len(jev.calls)
        out = _run(factory, ctx, "collect.daily", {"region_id": 1, "sources": DAILY})
        st = _idem.db_state(factory)
        diff = _idem.state_diff(s0, st)
        if diff:
            problems.append(f"[{step}] DB 스냅샷 차이 {_idem.changed_cells(s0, st)}:\n" + "\n".join(diff))
        facts = _fact_events(factory, ev0)
        if facts:
            problems.append(f"[{step}] 사실 change_event {len(facts)}건: {facts[:10]}")
        if len(jev.calls) != sent:
            problems.append(f"[{step}] tools/call {len(jev.calls) - sent}건: {sorted(set(jev.calls[sent:]))}")
        assembled = out.get("assembled", {}).get("checklist", {})
        moved = {k: assembled[k] for k in ("inserted", "updated", "closed", "reopened") if assembled.get(k)}
        if moved:
            problems.append(f"[{step}] daily 체크리스트 동기화가 행을 바꿈 {moved}")
        sid = _latest_published(factory)
        rep = _report_checklist(factory, sid)
        if rep != rep0:
            only_a = [r for r in rep0 if r not in rep]
            only_b = [r for r in rep if r not in rep0]
            problems.append(
                f"[{step}] 발행 보고서 체크리스트 차이(리비전 {boot_sid} → {sid}): 사라짐 {len(only_a)} {only_a[:6]} · 생김 {len(only_b)} {only_b[:6]}"
            )
        s0 = s0 if not diff else st
        rep0 = rep0 if rep == rep0 else rep

    daily("같은 날 첫 daily(같은 원문·같은 순서)", None)
    daily("같은 날 daily(순서를 섞어서)", 20261013)
    sent = len(jev.calls)
    _rejudge_latest(factory, ctx)
    if len(jev.calls) != sent:
        problems.append(f"[같은 날 재판정] tools/call {len(jev.calls) - sent}건: {jev.calls[sent:][:20]}")
    st = _idem.db_state(factory)
    diff = _idem.state_diff(s0, st)
    if diff:
        problems.append(f"[같은 날 재판정] DB 스냅샷 차이 {_idem.changed_cells(s0, st)}:\n" + "\n".join(diff))
    if not problems:
        assert _checklist_rows(factory) == cl0
    assert not problems, (
        f"{rs.name}: 첫 수집 전체 → 같은 날 daily 멱등성 위반 {len(problems)}건 (bootstrap tools/call {calls0}, "
        f"트랙 A {track_a}, 제외 단지 {excluded_id})\n" + "\n".join(problems)
    )

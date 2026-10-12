"""R4 재시험 N3·N4(major, D21-3) — 원 번호 하이픈 인용 + 같은 날 재수집 멱등. R4 재시험 원문 녹화 재생(``r4b_core8``).

R4 재시험(2026-10-12):
- N3: 잔여 공고문이 원 번호를 '최초 주택관리번호는 2025-000302' 처럼 **하이픈**으로 적으면 인용으로 읽지 못해 잔여 공고 번호
  (2025910193·2025940252)로 단지 행 74·75 를 만들었다(이름 = 번호, 범위 '보류 — 분양가 미공개'). 공고문 137개 중 11개가 하이픈.
- N4: 같은 날 변화 없는 ``collect.daily`` 가 change_event 19 · 재판정 2단지 · 새 판정 15 — 1회차에는 청약홈 잔여 공고 원문이 원
  단지 17 의 ``remaining_event`` 로 갔고, 2회차에는 이미 있던 74·75 행(같은 번호)에 붙어 단지 단위 값을 썼다(저장 순서 의존).

D21-3: 하이픈·공백 표기도 인용으로 읽는다. 같은 원문의 귀속은 저장 순서와 무관하게 결정적이다. 같은 날 변화 없는 재수집은
change_event 0·판정 0(D18-6) — 실데이터 재생으로 고정한다. 녹화: 엘리프 검단 포레듀(원 2025000302 + 무순위 2025910193 + 임의공급
2025940252), NUL 잔여 공고 2건(N2 — 원 2020000611·2019000711, 원 공고 응답 없음), 중흥S-클래스(N1).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import Settings
from app.judge.jev_mcp import JevMcpAdapter
from app.models import Complex, JobRun, JudgmentLog, Region, RemainingEvent
from app.normalize.notice_parser import notice_numbers
from app.scheduler import runner
from app.scheduler.collect import collect
from app.scheduler.context import SchedulerContext
from app.scheduler.jobs import enqueue

from ..normalize import _r4b
from .conftest import seed_region, seed_scenarios
from .test_r4_fix_c1_jobs import LocalExtractJev
from .test_r4_fix_d18_4 import Replay

ASOF = "2026-10-12"
REMNANT_NOS = {"2025910193", "2025940252", "2025910104", "2025930032"}
HYPHEN_PDFS = {605: ("2025910193", "2025000302"), 646: ("2025940252", "2025000302")}


def _docs(kind: str) -> list[dict[str, Any]]:
    """그룹 순서(엘리프 → N1 → N2), 그룹 안은 수집 순서."""
    out: list[dict[str, Any]] = []
    for g in ("elif", "n1", "n2"):
        out += [r for r in _r4b.rows(g) if (r["source_kind"] == "notice_pdf") == (kind == "notice_pdf")]
    return out


def _setup(
    test_settings: Settings, factory: sessionmaker[Session], *, bootstrapping: bool = False
) -> tuple[Replay, Replay]:
    _r4b.install(test_settings.raw_dir)
    with factory() as s:
        seed_scenarios(s)
        seed_region(s, status="bootstrapping" if bootstrapping else "ready")
        s.commit()
    return Replay(factory, _docs("applyhome")), Replay(factory, _docs("notice_pdf"))


def _complexes(factory: sessionmaker[Session]) -> dict[str, tuple[int, str]]:
    with factory() as s:
        return {str(c.applyhome_id): (c.id, c.name) for c in s.scalars(select(Complex))}


def _anchors(factory: sessionmaker[Session]) -> dict[str, str]:
    with factory() as s:
        by_id = {c.id: str(c.applyhome_id) for c in s.scalars(select(Complex))}
        return {str(e.notice_no): by_id[e.complex_id] for e in s.scalars(select(RemainingEvent))}


def test_hyphenated_original_number_is_cited(raw_dir: Any, db_session: Session) -> None:
    _r4b.install(raw_dir)
    for rid, expected in HYPHEN_PDFS.items():
        (dto,) = _r4b.insert(db_session, [_r4b.row("elif", rid)], region_id=None)
        assert notice_numbers(dto, raw_dir=raw_dir) == expected, f"rd{rid}: '2025-000302'(하이픈)도 인용"


def test_remnant_notices_attach_to_original_and_recollect_is_unchanged(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], test_settings: Settings
) -> None:
    ah, pdf = _setup(test_settings, factory)
    ctx = make_ctx(collectors={"applyhome": lambda c: ah, "notice_pdf": lambda c: pdf})
    first = collect(ctx, 1, ["applyhome_list", "applyhome_detail"], asof_date=ASOF)
    assert not first.store_errors, first.store_errors
    rows = _complexes(factory)
    assert set(rows) & REMNANT_NOS == set(), f"잔여 공고 번호로 단지 행: {sorted(set(rows) & REMNANT_NOS)}"
    anchors = _anchors(factory)
    assert anchors.get("2025910193") == "2025000302" and anchors.get("2025940252") == "2025000302", anchors
    assert rows["2025000302"][1] == "엘리프 검단 포레듀(AA32블록)"
    before = rows
    again = collect(ctx, 1, ["applyhome_list", "applyhome_detail"], asof_date=ASOF)
    assert _complexes(factory) == before
    assert _anchors(factory) == anchors
    assert again.change_event_ids == [], f"같은 날 다시 수집한 change_event {len(again.change_event_ids)}건"


def test_attribution_does_not_depend_on_storage_order(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], test_settings: Settings
) -> None:
    """1회차에 공고문만(잔여 공고 청약홈 원문 없이), 2회차에 청약홈 잔여 공고 원문 — 한 번에 받은 것과 같은 귀속(R4 N4)."""
    ah, pdf = _setup(test_settings, factory)
    originals_only = Replay(
        factory, [r for r in _docs("applyhome") if "Remndr" not in r["url"] and "OPT" not in r["url"]]
    )
    ctx1 = make_ctx(collectors={"applyhome": lambda c: originals_only, "notice_pdf": lambda c: pdf})
    collect(ctx1, 1, ["applyhome_list", "applyhome_detail"], asof_date=ASOF)
    ctx2 = make_ctx(collectors={"applyhome": lambda c: ah, "notice_pdf": lambda c: pdf})
    collect(ctx2, 1, ["applyhome_list", "applyhome_detail"], asof_date=ASOF)
    rows = _complexes(factory)
    assert set(rows) & REMNANT_NOS == set(), sorted(set(rows) & REMNANT_NOS)
    anchors = _anchors(factory)
    assert anchors.get("2025910193") == "2025000302" and anchors.get("2025940252") == "2025000302", anchors
    with factory() as s:
        cx = s.scalars(select(Complex).where(Complex.applyhome_id == "2025000302")).one()
        assert cx.units_total not in (43, 185), (
            "잔여 공고의 단지 단위 값(남은 세대수)이 원 단지를 덮지 않는다(D11-4)"
        )


def _job(factory: sessionmaker[Session], name: str) -> JobRun:
    with factory() as s:
        row = s.scalars(select(JobRun).where(JobRun.job_name == name).order_by(JobRun.id.desc())).first()
        assert row is not None, name
        return row


def test_same_day_daily_after_bootstrap_is_noop_on_r4b_replay(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], test_settings: Settings
) -> None:
    """bootstrap → 같은 날 collect.daily: change_event 0 · 재판정 0 · tools/call 0 · judgment_log 새 행 0(D18-6·D21-3)."""
    ah, pdf = _setup(test_settings, factory, bootstrapping=True)
    jev = LocalExtractJev()
    ctx = make_ctx(
        collectors={"applyhome": lambda c: ah, "notice_pdf": lambda c: pdf},
        adapter_factory=lambda: JevMcpAdapter(transport=jev, session_factory=factory, secrets=[]),
    )
    with factory() as s:
        enqueue(s, "region.bootstrap", {"region_id": 1}, kind="manual")
        s.commit()
    runner.run_until_idle(ctx)
    boot = _job(factory, "region.bootstrap")
    assert boot.status == "done", (boot.error_text, (boot.stats or {}).get("errors"))
    with factory() as s:
        rows_before = s.scalar(select(func.count()).select_from(JudgmentLog))
        assert s.get(Region, 1) is not None
    sent = len(jev.calls)
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
    assert set(_complexes(factory)) & REMNANT_NOS == set()

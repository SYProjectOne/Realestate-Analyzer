"""R4 3차 재시험 N9(critical, D22-1) — 공고문을 다시 정규화해도 판정기 extract 로 얻은 출처 행은 유지된다. + m-b(D22-4).

R4 3차 2회차 (b): 같은 날 ``collect.daily`` 가 change_event 0 · 판정 0 인데도 발행 스냅샷 3 에서 판정기 추출 값 6건(납부 조건
잔금·계약금 비율 — 단지 12·18·25·27·34·38)이 '확인됨' → '확인 불가(출처 누락)'로 바뀌었다(``missing_provenance`` 0 → 40).
원인: 재정규화(``store._reparse_existing``)가 같은 원문(``raw_document_id == exclude_raw_id``)의 출처 행을 후보에서 빼면서
판정기 추출 행(reason '판정기 추출 jl_…·감사 jl_…', 같은 공고문)도 뺐다 → 파서 행('잔금 비율 표기 해석 실패')이 다시 chosen,
사실 테이블 값(30·10)은 그대로 → 발행 저장본 '출처 누락'. 다음 재판정이 추출을 다시 적용해 돌아오는 왕복.

D22-1: 재정규화만으로 '확인됨' 사실이 '확인 불가'로 바뀌어서는 안 되고(같은 원문·같은 입력이면 기존 판정 행 보존), 값이 실제로
바뀌면 change_event 를 남긴다. 발행 결과는 사실 변경 없이 바뀌지 않는다(D11-1).

m-b(D22-4): 첫 적재(bootstrap) 안의 **판정 단계** 값 변경(판정기 추출 적용 · compare 채택)도 first_load 요약에 넣는다 — R4 3차
bootstrap 에 남은 13건(추출 납부 조건 빈 값→값 6 critical · compare 채택 타입 값 7).

녹화: ``r4c_core9`` 그룹 ``n9``(R4 3차 원문 — 6단지 청약홈 API·웹 상세 + 공고문 텍스트·표). 판정기는 가짜(``SynthJev`` —
추출 값 '30%'·'10%' 는 R4 3차 실제 추출 결과와 같다), 외부 사이트 없음.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.contracts_gen import RawDocument as RawDTO
from app.core.contracts_gen import Region as RegionDTO
from app.core.contracts_gen import Snapshot as SnapshotDTO
from app.core.settings import Settings
from app.core.time import KST
from app.judge.jev_mcp import JevMcpAdapter
from app.models import (
    ChangeEvent,
    Complex,
    FieldProvenance,
    JobRun,
    PaymentTerms,
    RawDocument,
    Scenario,
    Snapshot,
)
from app.normalize.fields import EXTRACT_REASON
from app.normalize.store import raw_dto
from app.scheduler import runner
from app.scheduler.context import SchedulerContext
from app.scheduler.jobs import enqueue
from app.scheduler.rejudge import enqueue_rejudge

from ..normalize import _r4c
from .conftest import Clock, SynthJev, seed_region, seed_scenarios
from .test_r4_fix_d18_4 import Replay

ASOF = "2026-10-12"
# R4 3차 실데이터: (주택관리번호, 필드) — 판정기 추출로 '확인됨'이 된 납부 조건 6건(스냅샷 2 → 3 에서 사라짐)
R4_EXTRACTED = {
    ("2026000065", "balance_pct"),
    ("2025000253", "down_payment_pct"),
    ("2026000367", "balance_pct"),
    ("2026000219", "balance_pct"),
    ("2025000499", "balance_pct"),
    ("2025000222", "balance_pct"),
}
FACT_ENTITIES = {"complex", "complex_type", "payment_terms", "competition", "remaining_event", "notice"}


@pytest.fixture
def jev() -> SynthJev:
    return SynthJev(extract_values={"balance_pct": "30%", "down_payment_pct": "10%"})


@dataclass
class TickClock(Clock):
    """실제 실행처럼 시각이 흐르는 시계(호출마다 1초) — 고정 시각이면 판정 중 이벤트와 잡 끝 시각이 같아 같은 날 daily 가
    이월 대신 재판정을 걸어(``changed_after_runs``) R4 3차 (b)(판정 0 · 이월 발행) 흐름이 재현되지 않는다."""

    tick: int = 0

    def now(self) -> datetime:
        self.tick += 1
        return datetime(self.day.year, self.day.month, self.day.day, 6, 0, tzinfo=KST) + timedelta(
            seconds=self.tick
        )


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    c = TickClock(day=date(2026, 10, 12))
    # 판정 단계 이벤트(``changes.detected_now`` — now 를 받지 않는 경로)도 같은 시계로(벽시계와 섞이면 시각 비교가 뒤집힌다)
    monkeypatch.setattr("app.normalize.changes.now_kst", c.now)
    return c


class NoticeReplay(Replay):
    """공고문 수집기 재생: 실제 수집기처럼 그 공고의 단지(주택관리번호 → complex)에 원문을 단다(``raw_document.complex_id`` —
    파이프라인 P1~P3 가 대상 단지의 공고문을 고르는 열)."""

    def fetch(self, region: RegionDTO, snapshot: SnapshotDTO, since: str | None) -> list[RawDTO]:
        got = super().fetch(region, snapshot, since)
        out: list[RawDTO] = []
        with self.factory() as s:
            for d in got:
                row = s.get(RawDocument, d.id)
                assert row is not None
                cx = s.scalars(select(Complex).where(Complex.applyhome_id == _r4c.house_no(row.url))).first()
                if cx is not None and row.complex_id is None:
                    row.complex_id = cx.id
                s.flush()
                out.append(raw_dto(row))
            s.commit()
        return out


def _setup(test_settings: Settings, factory: sessionmaker[Session]) -> tuple[Replay, Replay]:
    _r4c.install(test_settings.raw_dir)
    with factory() as s:
        seed_scenarios(s)
        seed_region(s, status="bootstrapping")
        s.commit()
    docs = _r4c.rows("n9")
    return (
        Replay(factory, [r for r in docs if r["source_kind"] != "notice_pdf"]),
        NoticeReplay(factory, [r for r in docs if r["source_kind"] == "notice_pdf"]),
    )


def _ctx(
    make_ctx: Callable[..., SchedulerContext],
    ah: Replay,
    pdf: Replay,
    jev: SynthJev,
    factory: sessionmaker[Session],
) -> SchedulerContext:
    return make_ctx(
        collectors={"applyhome": lambda c: ah, "notice_pdf": lambda c: pdf},
        adapter_factory=lambda: JevMcpAdapter(transport=jev, session_factory=factory, secrets=[]),
    )


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


def _judged(factory: sessionmaker[Session]) -> dict[tuple[str, str], tuple[int, str | None, str, bool]]:
    """(주택관리번호, 필드) → (출처 행 id, 값, 라벨, chosen) — 판정기 추출 출처 행(납부 조건 비율)."""
    with factory() as s:
        out: dict[tuple[str, str], tuple[int, str | None, str, bool]] = {}
        for fp in s.scalars(
            select(FieldProvenance)
            .where(
                FieldProvenance.entity == "payment_terms",
                FieldProvenance.field.in_(["balance_pct", "down_payment_pct"]),
                FieldProvenance.reason.startswith(EXTRACT_REASON),
            )
            .order_by(FieldProvenance.id)
        ):
            pt = s.get(PaymentTerms, fp.entity_id)
            assert pt is not None
            out[(str(pt.notice_no), fp.field)] = (fp.id, fp.value_norm, fp.label, fp.chosen)
        return out


def _chosen_labels(
    factory: sessionmaker[Session],
) -> dict[tuple[str, str], tuple[str | None, str, str | None]]:
    """(주택관리번호, 필드) → chosen 출처 행 (값, 라벨, 사유) + 사실 테이블 값."""
    with factory() as s:
        out: dict[tuple[str, str], tuple[str | None, str, str | None]] = {}
        for pt in s.scalars(select(PaymentTerms)):
            for f in ("balance_pct", "down_payment_pct"):
                fp = s.scalars(
                    select(FieldProvenance).where(
                        FieldProvenance.entity == "payment_terms",
                        FieldProvenance.entity_id == pt.id,
                        FieldProvenance.field == f,
                        FieldProvenance.chosen.is_(True),
                    )
                ).first()
                if fp is not None:
                    v = getattr(pt, f)
                    out[(str(pt.notice_no), f)] = (
                        None if v is None else format(v.normalize(), "f"),
                        fp.label,
                        fp.reason,
                    )
        return out


def _walk(obj: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        if "label" in obj and "prov" in obj:
            out.append(obj)
        for v in obj.values():
            out.extend(_walk(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_walk(v))
    return out


def _published_facts(
    factory: sessionmaker[Session], prov_ids: set[str]
) -> tuple[int, set[tuple[int, str, Any, str]], int]:
    """최신 발행 리비전 저장본(단지 상세 전부)에서 (판정기 추출 출처 Fact 들, '출처 누락' Fact 수)."""
    from app import snapshot_view

    with factory() as s:
        snap = s.scalars(
            select(Snapshot).where(Snapshot.status == "published").order_by(Snapshot.id.desc())
        ).first()
        assert snap is not None
        sc = s.scalars(select(Scenario).order_by(Scenario.id)).first()
        assert sc is not None
        hits: set[tuple[int, str, Any, str]] = set()
        missing = 0
        for cx in s.scalars(select(Complex).order_by(Complex.id)):
            body = snapshot_view.details(s, snap, sc, cx)
            for f in _walk(body):
                if f.get("prov") in prov_ids:
                    hits.add((cx.id, str(f["prov"]), f.get("v"), str(f["label"])))
                if f.get("label") == "확인 불가" and "출처 누락" in str(f.get("reason") or ""):
                    missing += 1
        return snap.id, hits, missing


def _rejudge_latest(factory: sessionmaker[Session], ctx: SchedulerContext) -> int:
    with factory() as s:
        sid = s.scalar(select(func.max(Snapshot.id)))
        assert sid is not None
        enqueue_rejudge(s, int(sid), None, "같은 스냅샷 재판정")
        s.commit()
    runner.run_until_idle(ctx)
    return int(sid)


@pytest.mark.parametrize(
    "first_rejudge",
    [
        pytest.param(False, id="bootstrap-daily-rejudge"),  # D22-1 완료 기준 순서
        pytest.param(
            True, id="r4c-order"
        ),  # R4 3차 실제 순서: bootstrap → (a) 재판정 → (b) daily → (a2) 재판정
    ],
)
def test_same_day_daily_keeps_judged_extract_facts_on_r4c_replay(
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    test_settings: Settings,
    jev: SynthJev,
    first_rejudge: bool,
) -> None:
    """bootstrap → (재판정) → 같은 날 collect.daily → 재판정: 판정기 추출 납부 조건이 '확인됨' 그대로, change_event 0, 발행 결과 불변."""
    ah, pdf = _setup(test_settings, factory)
    ctx = _ctx(make_ctx, ah, pdf, jev, factory)
    _run(factory, ctx, "region.bootstrap", {"region_id": 1})
    if first_rejudge:
        sent0 = len(jev.calls)
        _rejudge_latest(factory, ctx)
        assert len(jev.calls) == sent0, f"(a) 재판정 tools/call {jev.calls[sent0:]}"
    judged = _judged(factory)
    assert set(judged) >= R4_EXTRACTED, f"R4 3차 추출 6건이 bootstrap 에서 반영: {sorted(judged)}"
    assert all(lbl == "확인됨" and chosen for _, _, lbl, chosen in judged.values()), judged
    chosen_before = _chosen_labels(factory)
    prov_ids = {f"fp_{fid}" for fid, *_ in judged.values()}
    sid1, facts1, missing1 = _published_facts(factory, prov_ids)
    assert {(p, lbl) for _, p, _, lbl in facts1} >= {
        (f"fp_{judged[k][0]}", "확인됨") for k in R4_EXTRACTED
    }, facts1

    # 같은 날 collect.daily — 같은 원문을 다시 정규화(R4 3차 2회차 (b))
    with factory() as s:
        events_before = s.scalar(select(func.max(ChangeEvent.id))) or 0
    daily = _run(
        factory, ctx, "collect.daily", {"region_id": 1, "sources": ["applyhome_list", "applyhome_detail"]}
    )
    assert daily.get("change_events") == 0 and daily.get("rejudge_complex_ids") == [], daily
    assert "rejudge_job_id" not in daily and isinstance(daily.get("carry_forward"), dict), (
        "R4 3차 (b) 와 같이 판정 0 — 이전 발행 리비전의 판정·점수를 이월해 발행",
        daily.get("carry_forward"),
        daily.get("rejudge_job_id"),
    )
    after = _judged(factory)
    lost = {k: after.get(k) for k in judged if after.get(k) != judged[k]}
    assert not lost, f"재정규화가 판정기 추출 출처 행을 내렸다(N9): {lost}"
    assert _chosen_labels(factory) == chosen_before
    sid2, facts2, missing2 = _published_facts(factory, prov_ids)
    assert sid2 > sid1, "같은 날 재수집 리비전이 발행됐다"
    assert facts2 == facts1, f"발행 결과가 사실 변경 없이 바뀌었다: {sorted(facts1 ^ facts2)[:6]}"
    assert missing2 == missing1, f"발행 저장본 '출처 누락' {missing1} → {missing2}"

    # 같은 스냅샷 재판정 — tools/call 0, 이벤트 0, 값 그대로
    sent = len(jev.calls)
    assert _rejudge_latest(factory, ctx) == sid2
    assert len(jev.calls) == sent, (
        f"재판정 tools/call {len(jev.calls) - sent}건: {sorted(set(jev.calls[sent:]))}"
    )
    assert _judged(factory) == judged and _chosen_labels(factory) == chosen_before
    with factory() as s:
        fact_events = list(
            s.scalars(
                select(ChangeEvent).where(
                    ChangeEvent.id > events_before, ChangeEvent.entity.in_(sorted(FACT_ENTITIES))
                )
            )
        )
    assert fact_events == [], [(e.entity, e.field, e.old_text, e.new_text) for e in fact_events]
    _, facts3, missing3 = _published_facts(factory, prov_ids)
    assert facts3 == facts1 and missing3 == missing1


def test_bootstrap_folds_judge_stage_changes_into_first_load(
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    test_settings: Settings,
    jev: SynthJev,
) -> None:
    """m-b(D22-4): bootstrap 안의 판정기 추출 적용(빈 값 → 값)도 change_event 대신 first_load 요약 수."""
    ah, pdf = _setup(test_settings, factory)
    stats = _run(factory, _ctx(make_ctx, ah, pdf, jev, factory), "region.bootstrap", {"region_id": 1})
    assert (stats.get("pipeline") or {}).get("extract_applied", 0) > 0 or _judged(factory), stats.get(
        "pipeline"
    )
    with factory() as s:
        evs = list(s.scalars(select(ChangeEvent).order_by(ChangeEvent.id)))
    facts = [e for e in evs if e.entity in FACT_ENTITIES]
    assert facts == [], (
        f"첫 적재 중 판정 단계 값 변경 이벤트 {len(facts)}건: {[(e.entity, e.field, e.old_text, e.new_text, e.severity) for e in facts][:8]}"
    )
    summary = [e for e in evs if (e.entity, e.field) == ("region", "first_load")]
    assert len(summary) == 1, [(e.entity, e.field, e.new_text) for e in summary]

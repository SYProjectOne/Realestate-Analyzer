"""R3 수정 F2 — 파이프라인·API 정합 (C2 · M3 · D9-3 · minor 1·13·14·20·21·32·33 · W7·W10·W12b).

지역명은 픽스처에만 있다(AGENTS 규칙 15).
"""

# ruff: noqa: E501  (한국어 docstring·픽스처 행)

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.gap import unadjusted_from_flags
from app.analysis.score import SCORE_DECIMALS
from app.api.facts import FactMaker
from app.api.views import (
    bundle_price,
    judge_scope,
    load_bundles,
    price_range,
    provenance_for,
    scope_result,
    score_input,
)
from app.core.contracts_gen import RawDocument as RawDTO
from app.judge.jev_mcp import JevMcpAdapter
from app.models import (
    ChangeEvent,
    Complex,
    Decision,
    FieldProvenance,
    IntakeStatus,
    JobRun,
    JudgmentLog,
    Ladder,
    PaymentTerms,
    ScoreComponent,
    ScoreRun,
    ScoreTotal,
    Snapshot,
)
from app.normalize.store import StoreResult
from app.scheduler import handlers, runner
from app.scheduler.context import NetConfig, SchedulerContext, default_context, net_config_from_env
from app.scheduler.inputs import complex_input, load_facts
from app.scheduler.jobs import enqueue
from app.scheduler.notify import Notifier
from app.scheduler.pipeline import CountingCaller, _prev_anchor, run_pipeline
from app.scheduler.rejudge import enqueue_rejudge

from .conftest import APPLYHOME_RECORDING, Clock, RowsCollector, SynthJev, popup_row


def _count(s: Session, model: Any, *where: Any) -> int:
    return int(s.scalar(select(func.count()).select_from(model).where(*where)) or 0)


def _cid(item_id: str) -> int:
    return int(re.sub(r"\D", "", item_id))


@dataclass
class ReviewJev(SynthJev):
    """포함/제외 classify 에서 지정 단지만 review(미해결), rerank 후보 id 를 기록."""

    review_ids: set[str] = field(default_factory=set)
    rerank_ids: list[list[str]] = field(default_factory=list)

    def _classify(self, a: dict[str, Any]) -> dict[str, Any]:
        out = super()._classify(a)
        if a["classes"][0]["id"] != "open":
            for r in out["results"]:
                if r["id"] in self.review_ids:
                    r["decision"] = "review"
        return out

    def _rerank(self, a: dict[str, Any]) -> dict[str, Any]:
        self.rerank_ids.append([c["id"] for c in a["candidates"]])
        return super()._rerank(a)


def _ctx_with(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], jev: SynthJev, **kw: Any
) -> SchedulerContext:
    return make_ctx(
        adapter_factory=lambda: JevMcpAdapter(transport=jev, session_factory=factory, secrets=[]), **kw
    )


# ---------------------------------------------------------------- C2 (D9-1) 파이프라인


# 기대값 갱신(R3 마무리): 그란테르(1, W1)·마리나베이(12, CEO 결정)의 접수가 '불가' → '미정'(공고 이력 있음 + 추가
# 공급 미정, meta §1-3-4)이 되어 참고 → 판정 대상.
JUDGED = {1, 2, 5, 6, 7, 8, 9, 10, 11, 12}  # 단지 3 은 classify review → 미해결
REFERENCE = {4, 13, 14}  # 접수 확인 불가(4·13·14)
HOLD = {15, 16}  # 분양가 미공개


def test_c2_pipeline_scope_ladder_rerank_score_and_api(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int
) -> None:
    jev = ReviewJev(review_ids={"complex:3"})
    res = run_pipeline(_ctx_with(make_ctx, factory, jev), seeded)
    assert not res.degraded, res.error
    with factory() as s:
        # 사다리: 판정 대상만(참고·보류·미해결 미실행)
        laddered = set(s.scalars(select(Ladder.complex_id).where(Ladder.snapshot_id == seeded)))
        assert laddered == JUDGED
        # rerank 후보: 판정 대상·참고·보류(미해결·제외 빼고)
        assert jev.rerank_ids and {_cid(i) for i in jev.rerank_ids[-1]} == JUDGED | REFERENCE | HOLD
        # 저장 범위 = D9-1 값 그대로, 미해결은 점수 행 없음
        base = s.scalars(
            select(ScoreRun).where(ScoreRun.snapshot_id == seeded, ScoreRun.scenario_id == 1)
        ).one()
        stored = {
            t.complex_id: t.judge_scope
            for t in s.scalars(select(ScoreTotal).where(ScoreTotal.score_run_id == base.id))
        }
        assert 3 not in stored
        assert {c for c, v in stored.items() if v == "판정 대상"} == JUDGED
        assert {c for c, v in stored.items() if v == "참고"} == REFERENCE
        assert {c for c, v in stored.items() if v == "보류"} == HOLD
        # 참고 = 순위만: p10 null → 종합 미계산, rerank 성분은 있음
        comps = {
            (c.complex_id, c.component): c
            for c in s.scalars(select(ScoreComponent).where(ScoreComponent.score_run_id == base.id))
        }
        for cid in REFERENCE:
            assert comps[(cid, "p10")].score_0_10 is None and comps[(cid, "rerank")].score_0_10 is not None
        # decide 후보 ⊆ 판정 대상
        decided = {
            d.complex_id
            for d in s.scalars(select(Decision).where(Decision.score_run_id == base.id))
            if d.complex_id is not None
        }
        assert decided and decided <= JUDGED
        # API 도 같은 공용 함수: 미해결(계약 .4 전에는 응답 값 '제외'), 참고·보류는 그대로
        cxs = list(s.scalars(select(Complex).where(Complex.region_id == 1)))
        bundles = load_bundles(s, cxs, seeded)
        assert scope_result(bundles[3]).scope == "미해결" and judge_scope(bundles[3]) in ("미해결", "제외")
        assert {judge_scope(bundles[c]) for c in REFERENCE} == {"참고"}
        assert {judge_scope(bundles[c]) for c in HOLD} == {"보류"}
        assert {c for c in JUDGED if judge_scope(bundles[c]) == "판정 대상"} == JUDGED


# ---------------------------------------------------------------- M3 · minor 20 · 21


def test_m3_minor20_minor21_api_and_pipeline_share_price_inputs_and_intake(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, test_settings: Any
) -> None:
    run_pipeline(make_ctx(), seeded)
    with factory() as s:
        cxs = list(s.scalars(select(Complex).where(Complex.region_id == 1)))
        bundles = load_bundles(s, cxs, seeded)
        basis = bundle_price(bundles[7]).basis_type_code
        assert basis is not None
        # M3: 임의공급 최신 공고 가격(price_by_type) — 화면·점수가 같은 값
        pt = PaymentTerms(
            complex_id=7, notice_no="R3F2-임의", notice_kind="임의", effective_from="2026-10-01",
            down_payment_pct=Decimal(5), interim_schedule=[],
            price_by_type={basis: {"max_price_won": 640_000_000, "floor_sample_price_won": 630_000_000}},
        )  # fmt: skip
        s.add(pt)
        s.flush()
        s.add(
            FieldProvenance(
                entity="payment_terms", entity_id=pt.id, field=f"price_by_type.{basis}.max_price_won",
                value_text="640,000,000", url="https://example.test/notice", checked_at="2026-10-01",
                label="확인됨", source_rank=1, chosen=True,
            )
        )  # fmt: skip
        s.add(
            FieldProvenance(
                entity="payment_terms", entity_id=pt.id, field=f"price_by_type.{basis}.floor_sample_price_won",
                value_text="630,000,000", url="https://example.test/notice", checked_at="2026-10-01",
                label="확인됨", source_rank=1, chosen=True,
            )
        )  # fmt: skip
        # minor 21: 같은 날 날짜만(사람) vs 시각 포함(수집) — 같은 경로 두 행, 나중 기록이 이긴다
        s.add_all(
            [
                IntakeStatus(
                    complex_id=9,
                    snapshot_id=seeded,
                    status="불가",
                    path="official_popup",
                    checked_at="2026-10-07T09:00:00+09:00",
                ),
                IntakeStatus(
                    complex_id=9,
                    snapshot_id=seeded,
                    status="가능",
                    path="official_popup",
                    checked_at="2026-10-07",
                ),
            ]
        )
        s.commit()
        snap = s.get(Snapshot, seeded)
        assert snap is not None
        region_facts = {
            f.complex_id: f
            for f in load_facts(s, snap, snap.region if hasattr(snap, "region") else _region(s))
        }
        bundles = load_bundles(s, cxs, seeded)
        f7, b7 = region_facts[7], bundles[7]
        view = bundle_price(b7)
        assert view.from_terms and (view.low_won, view.high_won) == (f7.price_low, f7.price_high)
        assert f7.price_label == "확인됨"
        for (
            ref
        ) in view.extra_refs:  # 시드에 옵션 출처 행이 없다 — 출처 행을 채워 dev 규칙(누락 = 예외) 그대로
            if not s.scalars(
                select(FieldProvenance.id).where(
                    FieldProvenance.entity == ref.entity,
                    FieldProvenance.entity_id == ref.entity_id,
                    FieldProvenance.field == ref.field,
                )
            ).first():
                s.add(
                    FieldProvenance(
                        entity=ref.entity,
                        entity_id=ref.entity_id,
                        field=ref.field,
                        value_text=str(ref.value),
                        url="https://example.test/n",
                        checked_at="2026-10-01",
                        label="확인됨",
                        source_rank=1,
                        chosen=True,
                    )
                )
        s.commit()
        fm = FactMaker(test_settings, provenance_for(s, bundles.values()))
        pr = price_range(fm, b7)
        assert (pr["price_low"]["v"], pr["price_high"]["v"]) == (view.low_won, view.high_won)
        max_fp = s.scalars(
            select(FieldProvenance.id).where(
                FieldProvenance.entity == "payment_terms", FieldProvenance.entity_id == pt.id,
                FieldProvenance.field == f"price_by_type.{basis}.max_price_won",
            )
        ).one()  # fmt: skip
        assert pr["price_high"]["prov"] == f"fp_{max_fp}"  # 출처 = 최신 공고 가격 행
        # minor 21: 파이프라인·API 가 같은 접수 행
        assert region_facts[9].intake is not None and region_facts[9].intake.status == "가능"
        assert scope_result(bundles[9]).scope == region_facts[9].scope
        # minor 20: 요건 사전 계산 입력 = 파이프라인 입력(라벨 제외 필드 전부)
        ladders = {
            cid: list(s.scalars(select(Ladder).where(Ladder.snapshot_id == seeded, Ladder.complex_id == cid)))
            for cid in bundles
        }
        skip = {"price_label", "resale_label", "residency_label", "down_payment_label", "move_in_label"}
        for cid, b in bundles.items():
            api = score_input(b).model_dump(exclude=skip)
            pipe = complex_input(region_facts[cid], snap.asof_date, ladders[cid]).model_dump(exclude=skip)
            api["ladders"] = sorted(api["ladders"], key=lambda x: x["horizon"])
            assert api == pipe, cid


def _region(s: Session) -> Any:
    from app.models import Region

    r = s.get(Region, 1)
    assert r is not None
    return r


# ---------------------------------------------------------------- D9-3 접수 상태 변경


def _day2(factory: sessionmaker[Session], day1: int, changes: dict[int, str]) -> int:
    with factory() as s:
        snap = Snapshot(
            region_id=1,
            asof_date="2026-10-08",
            status="building",
            degraded=False,
            created_at="2026-10-08T06:00:00+09:00",
        )
        s.add(snap)
        s.flush()
        for r in s.scalars(select(IntakeStatus).where(IntakeStatus.snapshot_id == day1)):
            status = changes.get(r.complex_id, r.status) if r.path == "official_popup" else r.status
            s.add(
                IntakeStatus(
                    complex_id=r.complex_id,
                    snapshot_id=snap.id,
                    status=status,
                    path=r.path,
                    checked_at="2026-10-08",
                    reason=r.reason,
                )
            )
        s.commit()
        return snap.id


def test_d9_3_intake_change_critical_event_notified_once_and_rescoped(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int
) -> None:
    sent: list[dict[str, Any]] = []
    notifier = Notifier(
        webhook_url="https://hooks.example.test/x", post=lambda u, b: sent.append(b) or 200, secrets=[]
    )
    ctx = make_ctx(notifier=notifier)
    with factory() as s:
        enqueue_rejudge(s, seeded, None, "1일차")
        s.commit()
    runner.run_until_idle(ctx)
    day2 = _day2(factory, seeded, {2: "불가"})
    res = run_pipeline(ctx, day2)
    with factory() as s:
        evs = list(
            s.scalars(
                select(ChangeEvent).where(
                    ChangeEvent.snapshot_id == day2, ChangeEvent.entity == "intake_status"
                )
            )
        )
        assert len(evs) == 1
        ev = evs[0]
        assert (ev.complex_id, ev.field, ev.old_text, ev.new_text, ev.severity, ev.triggers_rejudge) == (
            2,
            "status",
            "가능",
            "불가",
            "critical",
            True,
        )
        assert res.intake_events == [ev.id]
        # 범위가 참고로 → 사다리 미실행
        assert _count(s, Ladder, Ladder.snapshot_id == day2, Ladder.complex_id == 2) == 0
    assert len(sent) == 1 and sent[0]["events"][0]["field"] == "status"
    run_pipeline(ctx, day2)  # 재실행: 같은 변경 이벤트 다시 안 만듦, 알림 다시 안 보냄
    with factory() as s:
        assert (
            _count(s, ChangeEvent, ChangeEvent.snapshot_id == day2, ChangeEvent.entity == "intake_status")
            == 1
        )
    assert len(sent) == 1


# ---------------------------------------------------------------- minor 13 알림


def _ev(eid: int, new_text: str) -> ChangeEvent:
    return ChangeEvent(
        id=eid, snapshot_id=1, entity="complex", entity_id=2, field="official_popup_hash", old_text="a", new_text=new_text,
        detected_at="2026-10-08T06:00:00+09:00", severity="critical", triggers_rejudge=True, complex_id=2,
    )  # fmt: skip


def test_minor13_guard_is_per_event_and_dedupes() -> None:
    sent: list[dict[str, Any]] = []
    n = Notifier(
        webhook_url="https://hooks.example.test/x", post=lambda u, b: sent.append(b) or 200, secrets=[]
    )
    r = n.notify([_ev(1, "팝업 변경"), _ev(2, "문의 010-1234-5678"), _ev(3, "선착순 안내")])
    assert (r.sent, r.blocked, r.skipped) == (2, 1, None)
    assert [e["new"] for e in sent[0]["events"]] == ["팝업 변경", "선착순 안내"]
    again = n.notify([_ev(1, "팝업 변경")])
    assert again.skipped == "already_sent" and len(sent) == 1


def test_minor13_rejudge_job_notifies_api_created_critical_events(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int
) -> None:
    """사람 확인·생활권 편집처럼 API 가 만든 critical 이벤트도 rejudge 잡에서 알림."""
    sent: list[dict[str, Any]] = []
    ctx = make_ctx(
        notifier=Notifier(
            webhook_url="https://hooks.example.test/x", post=lambda u, b: sent.append(b) or 200, secrets=[]
        )
    )
    with factory() as s:
        ce = ChangeEvent(
            snapshot_id=seeded, entity="region", entity_id=1, field="living_areas", old_text="[]", new_text="[1]",
            detected_at="2026-10-07T10:00:00+09:00", severity="critical", triggers_rejudge=True, complex_id=None,
        )  # fmt: skip
        s.add(ce)
        s.flush()
        job = enqueue(
            s,
            "rejudge",
            {
                "snapshot_id": seeded,
                "scenario_id": None,
                "complex_ids": None,
                "reason": "생활권 편집",
                "change_event_ids": [ce.id],
            },
        )
        s.commit()
        jid, eid = job.id, ce.id
    runner.run_until_idle(ctx)
    with factory() as s:
        row = s.get(JobRun, jid)
        assert row is not None and row.status == "done" and row.stats["notify"]["sent"] == 1
    assert sent and sent[0]["events"][0]["field"] == "living_areas"
    assert eid in ctx.notifier.sent_ids


# ---------------------------------------------------------------- minor 14 · 33 runner


def test_minor14_job_stats_error_text_redacted(
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    test_settings: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sha = "a01012345678b" + "0" * 51

    def boom(ctx: SchedulerContext, job: JobRun) -> dict[str, Any]:
        raise handlers.JobError(
            "수집 단계 오류",
            {
                "errors": {"rtms": "HTTPError: https://x.test/a?serviceKey=abc123def&p=1 문의 010-1234-5678"},
                "sha256": sha,
                "daily": {"store_errors": ["rd1:x 홍길동 900101-1234567"]},
            },
        )

    monkeypatch.setitem(handlers.HANDLERS, "reference.refresh", boom)
    ctx = make_ctx()
    with factory() as s:
        jid = enqueue(s, "reference.refresh", {}).id
        s.commit()
    runner.run_until_idle(ctx)
    with factory() as s:
        row = s.get(JobRun, jid)
        assert row is not None and row.status == "failed"
        text = json.dumps(row.stats, ensure_ascii=False)
        assert "abc123def" not in text and "010-1234-5678" not in text and "900101-1234567" not in text
        assert "[REDACTED" in text and row.stats["sha256"] == sha  # 오류 키 밖의 값은 그대로


def test_minor33_heartbeat_written_while_running(
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    test_settings: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runner, "_heartbeat_s", lambda: 0.05)

    def slow(ctx: SchedulerContext, job: JobRun) -> dict[str, Any]:
        time.sleep(0.4)
        with ctx.session_factory() as s:
            row = s.get(JobRun, job.id)
            assert row is not None
            return {"beat": (row.stats or {}).get("heartbeat_at")}

    monkeypatch.setitem(handlers.HANDLERS, "reference.refresh", slow)
    ctx = make_ctx()
    with factory() as s:
        jid = enqueue(s, "reference.refresh", {}).id
        s.commit()
    runner.run_until_idle(ctx)
    with factory() as s:
        row = s.get(JobRun, jid)
        assert row is not None and row.status == "done" and row.stats["beat"]


def test_minor33_stale_running_requeued_once_then_failed(
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    test_settings: Any,
    clock: Clock,
) -> None:
    ctx = make_ctx()
    with factory() as s:
        stale = enqueue(s, "reference.refresh", {})
        stale.status, stale.locked_by, stale.started_at = (
            "running",
            "dead-worker",
            "2026-10-08T05:00:00+09:00",
        )
        fresh = enqueue(s, "collect.weekly", {"region_id": 1, "sources": ["rtms"]})
        fresh.status, fresh.locked_by, fresh.started_at = (
            "running",
            "live-worker",
            "2026-10-08T05:00:00+09:00",
        )
        fresh.stats = {"heartbeat_at": clock.now().isoformat()}
        s.commit()
        sid, fid = stale.id, fresh.id
    assert runner.recover_stale(ctx) == [sid]
    with factory() as s:
        row = s.get(JobRun, sid)
        assert (
            row is not None
            and row.status == "queued"
            and row.locked_by is None
            and row.stats["stale_recoveries"] == 1
        )
        assert (s.get(JobRun, fid) or JobRun()).status == "running"  # 하트비트가 살아 있으면 그대로
        row.status, row.locked_by, row.started_at = "running", "dead-again", "2026-10-08T05:00:00+09:00"
        s.commit()
    assert runner.recover_stale(ctx) == [sid]
    with factory() as s:
        row = s.get(JobRun, sid)
        assert row is not None and row.status == "failed" and (row.error_text or "").startswith("stale:")


def test_minor33_enqueue_dedupes_against_running(factory: sessionmaker[Session], test_settings: Any) -> None:
    payload = {"region_id": 1, "sources": ["applyhome_list", "official_site"]}
    with factory() as s:
        first = enqueue(s, "collect.daily", payload)
        first.status = "running"
        s.flush()
        assert enqueue(s, "collect.daily", payload).id == first.id
        first.status = "done"
        s.flush()
        assert enqueue(s, "collect.daily", payload).id != first.id


# ---------------------------------------------------------------- minor 32


class _NoCall:
    adapter_version = "v"

    def call(self, *a: Any, **k: Any) -> Any:
        raise AssertionError("이전 앵커 때문에 판정기를 부르면 안 된다")


def test_minor32_prev_anchor_reads_cache_row_only(factory: sessionmaker[Session], test_settings: Any) -> None:
    with factory() as s:
        row = JudgmentLog(
            tool="rerank", purpose="rerank:region:1", input_hash="h" * 64, input_json={"candidates": []}, input_len=10,
            output_json={}, result_json={"items": [{"candidate_id": "complex:1", "complex_id": 1, "relevance": 0.9, "rank": 1}]},
            status="ok", adapter_version="v", created_at="2026-10-07T00:00:00+09:00",
        )  # fmt: skip
        s.add(row)
        s.commit()
        prev = _prev_anchor(s, CountingCaller(_NoCall()), row.seq)  # type: ignore[arg-type]
        assert prev is not None and prev.judgment_seq == row.seq and prev.items[0].complex_id == 1
        other = _prev_anchor(s, CountingCaller(type("V", (_NoCall,), {"adapter_version": "w"})()), row.seq)  # type: ignore[arg-type]
        assert other is None  # 판정기 버전이 다르면 앵커 없음(호출도 없음)


# ---------------------------------------------------------------- minor 1 (T8 목록 diff)


def _list_row(day: str, ids: list[int]) -> dict[str, Any]:
    d = popup_row("yesterday")
    d.update(
        source_kind="applyhome_list", url=f"https://list.example.test/{day}?ids={','.join(map(str, ids))}",
        fetched_at=f"{day}T06:00:00+09:00", sha256=hashlib.sha256(f"{day}{ids}".encode()).hexdigest(),
        path=None, content_type="application/json", complex_id=None, image_hash=None,
    )  # fmt: skip
    return d


def test_minor1_t8_list_diff_notice_event_no_rejudge(
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    seeded: int,
    jev: SynthJev,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """목록 diff(detect.list_changes): 같은 목록 → 이벤트 0, 단지가 빠지면 notice 1(재판정·판정기 호출 0)."""

    def stub(session: Session, doc: RawDTO, *, snapshot_id: int) -> StoreResult:
        ids = [int(i) for i in (doc.url or "").split("ids=")[1].split(",")]
        return StoreResult(
            raw_document_id=doc.id or 0,
            candidates=[],
            resolved=None,
            provenance_ids=[],
            change_events=[],
            complex_ids=ids,
            extract_requests=[],
        )  # type: ignore[arg-type]

    monkeypatch.setattr("app.scheduler.collect.store_raw_document", stub)
    all_ids = list(range(1, 17))
    lister = RowsCollector(factory, [_list_row("2026-10-07", all_ids)])
    ctx = make_ctx(collectors={"applyhome": lambda c: lister})

    def daily() -> int:
        with factory() as s:
            jid = enqueue(s, "collect.daily", {"region_id": 1, "sources": ["applyhome_list"]}).id
            s.commit()
        assert runner.run_once(ctx) == jid
        return jid

    clock.day = date(2026, 10, 7)
    daily()
    runner.run_until_idle(ctx)  # 1일차 전체 판정·publish
    calls = len(jev.calls)
    with factory() as s:
        rejudges = _count(s, JobRun, JobRun.job_name == "rejudge")
    # 2일차 같은 목록 → 변경 0
    clock.day = date(2026, 10, 8)
    lister.rows = [_list_row("2026-10-08", all_ids)]
    j2 = daily()
    with factory() as s:
        job = s.get(JobRun, j2)
        assert job is not None, j2
        assert job.stats.get("list_complex_ids") == all_ids, (job.status, job.stats.get("errors"))
        assert job.stats["change_events"] == 0
    # 3일차 단지 16 이 목록에서 빠짐 → notice 1, rejudge 0
    clock.day = date(2026, 10, 9)
    lister.rows = [_list_row("2026-10-09", all_ids[:-1])]
    j3 = daily()
    runner.run_until_idle(ctx)
    with factory() as s:
        snap3 = s.scalars(select(Snapshot).where(Snapshot.asof_date == "2026-10-09")).one()
        evs = list(s.scalars(select(ChangeEvent).where(ChangeEvent.snapshot_id == snap3.id)))
        assert [(e.field, e.complex_id, e.severity, e.triggers_rejudge) for e in evs] == [
            ("applyhome_list", 16, "notice", False)
        ]
        assert _count(s, JobRun, JobRun.job_name == "rejudge") == rejudges
        job = s.get(JobRun, j3)
        assert job is not None and job.stats["change_events"] == 1
    assert len(jev.calls) == calls  # 판정기 실제 호출 0


# ---------------------------------------------------------------- W7 · W12b


def test_w7_w12b_unadjusted_gap_persisted_and_score_precision(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int
) -> None:
    run_pipeline(make_ctx(), seeded)
    with factory() as s:
        base = s.scalars(
            select(ScoreRun).where(ScoreRun.snapshot_id == seeded, ScoreRun.scenario_id == 1)
        ).one()
        gaps = [
            c
            for c in s.scalars(
                select(ScoreComponent).where(
                    ScoreComponent.score_run_id == base.id, ScoreComponent.component == "gap"
                )
            )
            if c.raw_value is not None
        ]
        assert gaps
        for c in gaps:
            # 계약 2026-10-09.4: 미보정 갭·중앙값은 컬럼(score_component.unadjusted_*) — flags 태그는 저장 시 뺀다
            gap_u, median_u = c.unadjusted_gap_pct, c.unadjusted_median_won
            assert unadjusted_from_flags(c.flags) == (None, None)
            assert gap_u is not None and median_u is not None and median_u > 0, c.complex_id
            if "substitute" not in (c.flags or []):
                assert abs(gap_u - Decimal(c.raw_value)) < Decimal("0.0002")  # 대체 없으면 보정 = 미보정
        assert SCORE_DECIMALS == 4
        # 저장 성분 점수는 엔진 정밀도(4자리)로 넘긴다 — 컬럼 scale 이 3이면 F3 마이그레이션 필요(보고)
        col_scale = ScoreComponent.__table__.c.score_0_10.type.scale  # type: ignore[attr-defined]
        if col_scale is not None and col_scale >= SCORE_DECIMALS:
            totals = {
                t.complex_id: t.total
                for t in s.scalars(select(ScoreTotal).where(ScoreTotal.score_run_id == base.id))
            }
            w = {k: Decimal(str(v)) for k, v in (base.weights or {}).items() if v is not None}
            comps: dict[int, Decimal] = {}
            for c in s.scalars(select(ScoreComponent).where(ScoreComponent.score_run_id == base.id)):
                if c.score_0_10 is not None and c.component in w:
                    comps[c.complex_id] = comps.get(c.complex_id, Decimal(0)) + w[c.component] * c.score_0_10
            for cid, t in totals.items():
                if t is not None:
                    assert abs(comps[cid] - t) < Decimal("0.0001"), cid


def test_w12b_persist_passes_engine_precision() -> None:
    from app.scheduler.persist import to_dec

    assert to_dec(Decimal("4.44385")) == Decimal("4.4439") and to_dec(4.4438) == Decimal("4.4438")


# ---------------------------------------------------------------- W10


def test_w10_net_mode_from_env_and_replay_offline_collectors(
    factory: sessionmaker[Session], test_settings: Any, tmp_path: Path
) -> None:
    assert net_config_from_env({}).mode == "live"
    with pytest.raises(ValueError):
        net_config_from_env({"WORKER_NET_MODE": "bogus"})
    with pytest.raises(ValueError):
        net_config_from_env({"WORKER_NET_MODE": "replay"})  # 녹화 경로 필수
    net = net_config_from_env(
        {
            "WORKER_NET_MODE": "replay",
            "WORKER_REPLAY_ARCHIVE": str(APPLYHOME_RECORDING),
            "WORKER_TODAY": "2026-10-09",
        }
    )
    ctx = default_context(test_settings, net=net)
    assert ctx.today() == date(2026, 10, 9) and ctx.now().date() == date(2026, 10, 9)
    from app.scheduler.snapshots import region_dto, snapshot_dto

    from .conftest import seed_region

    with factory() as s:
        region = seed_region(s)
        snap = Snapshot(
            region_id=region.id,
            asof_date="2026-10-09",
            status="building",
            degraded=False,
            created_at="2026-10-09T06:00:00+09:00",
        )
        s.add(snap)
        s.commit()
        rdto, sdto = region_dto(region), snapshot_dto(snap)
    docs = ctx.collectors["applyhome"](ctx).fetch(rdto, sdto, None)  # 녹화 재생 — 실제 사이트 접속 없음
    assert any(d.source_kind == "applyhome_list" and d.http_status == 200 for d in docs)
    off = default_context(test_settings, net=NetConfig(mode="offline"))
    stats_docs = off.collectors["stats"](off).fetch(rdto, sdto, None)  # 오프라인: 예외 없이 실패 행
    assert all(d.http_status != 200 for d in stats_docs)

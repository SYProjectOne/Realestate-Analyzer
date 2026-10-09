"""R2.5 (계약 2026-10-09.3) WP7: 접수 상태 classify 종단, extract 반영·audit flagged, inclusion 배치 1회,
score_total.judge_scope·judgment_log.result_json 저장, 시나리오 → 판정 payload 빌더(미리보기 cache_hits)."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import respx
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.collectors.official_site import OfficialSiteCollector, PopupShot, RenderResult, SiteTarget
from app.core.http import HttpClient
from app.core.snapshot import store_raw
from app.models import (
    Complex,
    ComplexType,
    FieldProvenance,
    IntakeStatus,
    JudgmentLog,
    RawDocument,
    ScoreRun,
    ScoreTotal,
    Snapshot,
)
from app.normalize.store import store_raw_document
from app.scheduler.collect import collect
from app.scheduler.context import SchedulerContext
from app.scheduler.payloads import cache_status, scenario_payloads
from app.scheduler.pipeline import load_scenarios, run_pipeline

from .conftest import REPO, SynthJev

WP1B_FIXTURES = REPO / "backend" / "tests" / "collectors" / "official_site" / "fixtures"
NOTICE_FIXTURES = REPO / "backend" / "tests" / "normalize" / "fixtures" / "notice"
SITE = "https://site.example.test/"
ROBOTS = "https://site.example.test/robots.txt"
PNG = b"\x89PNG\r\n\x1a\n" + b"fake-png-bytes"
CX = 4  # 픽스처 단지(공식 홈페이지 403 이던 단지) — 이 테스트에서는 녹화 페이지가 열린다


def _count(s: Session, model: Any, *where: Any) -> int:
    return int(s.scalar(select(func.count()).select_from(model).where(*where)) or 0)


class FakeRenderer:
    """WP1b 테스트와 같은 렌더 결과(팝업 문구 = 렌더 후 DOM 텍스트)."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def render(self, url: str) -> RenderResult:
        self.calls.append(url)
        return RenderResult(
            url=url,
            final_url=url,
            status=200,
            screenshot_png=PNG,
            dom_text="잔여 세대 선착순 동호지정 계약 중",
            popups=(PopupShot(selector="#layer_popup", sha256="a" * 64, width=300, height=200),),
        )


@pytest.fixture
def site_ctx(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session]
) -> Iterator[SchedulerContext]:
    """공식 홈페이지 수집기 = WP1b OfficialSiteCollector + 녹화 HTML(respx) + 가짜 렌더러."""
    http = HttpClient(sleep=lambda _s: None, max_retries=0, jitter=0)

    def official(_ctx: SchedulerContext) -> OfficialSiteCollector:
        return OfficialSiteCollector(
            http=http, renderer=FakeRenderer(), targets=[SiteTarget(SITE, CX)], session_factory=factory
        )

    with respx.mock(assert_all_called=False) as router:
        router.get(ROBOTS).respond(200, content=(WP1B_FIXTURES / "hndapt_robots.txt").read_bytes())
        router.get(SITE).respond(
            200,
            content=(WP1B_FIXTURES / "hndapt_index.html").read_bytes(),
            headers={"content-type": "text/html; charset=utf-8"},
        )
        yield make_ctx(collectors={"official_site": official})
    http.close()


def _collect_and_judge(ctx: SchedulerContext, factory: sessionmaker[Session]) -> tuple[int, Any]:
    res = collect(ctx, 1, ["official_site"])
    assert res.errors == {} and res.intake_rows == 1, res.stats()
    with factory() as s:
        row = s.scalars(
            select(IntakeStatus).where(
                IntakeStatus.snapshot_id == res.snapshot_id,
                IntakeStatus.complex_id == CX,
                IntakeStatus.path == "headless_shot",
            )
        ).one()
        # 수집 직후: 분류 전(판정기 몫) — 문구 후보는 note 에 원문 그대로
        assert (row.status, row.reason, row.path) == ("확인 불가", "접수 문구 미분류", "headless_shot")
        assert row.note and "선착순" in row.note
    return res.snapshot_id, run_pipeline(ctx, res.snapshot_id)


def test_intake_classify_end_to_end_official_site_recording(
    site_ctx: SchedulerContext, factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    sid, out = _collect_and_judge(site_ctx, factory)
    assert not out.degraded and out.intake_classified == 1
    with factory() as s:
        row = s.scalars(
            select(IntakeStatus).where(
                IntakeStatus.snapshot_id == sid,
                IntakeStatus.complex_id == CX,
                IntakeStatus.path == "headless_shot",
            )
        ).one()
        assert (row.status, row.reason) == ("가능", None)  # 판정기 classify auto → 가능
        log = s.scalars(select(JudgmentLog).where(JudgmentLog.purpose == "classify:intake:batch0")).one()
        assert log.tool == "classify" and log.status == "ok" and log.snapshot_id == sid
        assert row.note and f"jl_{log.seq}" in row.note
        text = log.input_json["items"][0]["text"]
        assert "선착순" in text  # 렌더 후 DOM 텍스트의 접수 문구
        assert log.result_json and log.result_json["label"] == "open"
        # 다른 단지의 복사된 접수 행(이전 스냅샷)은 그대로
        assert _count(s, IntakeStatus, IntakeStatus.snapshot_id == sid) > 1


def test_intake_classify_review_is_unresolved_not_pending(
    site_ctx: SchedulerContext, factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    jev.intake_decision = "review"
    sid, _ = _collect_and_judge(site_ctx, factory)
    with factory() as s:
        row = s.scalars(
            select(IntakeStatus).where(
                IntakeStatus.snapshot_id == sid,
                IntakeStatus.complex_id == CX,
                IntakeStatus.path == "headless_shot",
            )
        ).one()
        assert (row.status, row.reason) == ("확인 불가", "판정 미해결")  # '미정'이 아니다


# ---------------------------------------------------------------- P2·P3 반영


def _seed_notice(factory: sessionmaker[Session]) -> tuple[int, int]:
    """판정 대상이 될 공고문(파서가 120P 가격을 못 읽음 → needs_extract) → (단지 id, 120P 타입 id)."""
    fname = "2025000435_centreville.txt"
    data = (NOTICE_FIXTURES / fname).read_bytes()
    manifest = json.loads((NOTICE_FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    url = next(m["url"] for m in manifest if m["file"] == fname)  # 주택관리번호(houseManageNo)가 든 원문 URL
    stored = store_raw(data, source="notice_pdf", day=date(2026, 10, 7), ext="txt")
    with factory() as s:
        raw = RawDocument(
            source_kind="notice_pdf", url=url, fetched_at="2026-10-07T06:00:00+09:00", http_status=200,
            sha256=stored.sha256, path=stored.relpath, content_type="text/plain", text_path=stored.relpath,
            region_id=1,
        )  # fmt: skip
        s.add(raw)
        s.flush()
        store_raw_document(s, raw)
        cx = s.scalars(select(Complex).where(Complex.applyhome_id == "2025000435")).one()
        raw.complex_id = cx.id
        t = s.scalars(
            select(ComplexType).where(ComplexType.complex_id == cx.id, ComplexType.type_code == "120P")
        ).one()
        assert t.max_price_won is None
        s.commit()
        return cx.id, t.id


def _price_rows(s: Session, tid: int) -> list[FieldProvenance]:
    stmt = select(FieldProvenance).where(
        FieldProvenance.entity == "complex_type",
        FieldProvenance.entity_id == tid,
        FieldProvenance.field == "max_price_won",
    )
    return list(s.scalars(stmt.order_by(FieldProvenance.id)))


def test_p2_p3_extract_is_applied_with_audit(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    cid, tid = _seed_notice(factory)
    jev.extract_values = {"max_price_won": "699,400,000원"}
    out = run_pipeline(make_ctx(), seeded, complex_ids=[cid])
    assert out.extract_applied >= 1 and out.extract_flagged == 0
    assert out.by_tool.get("extract") and out.by_tool.get("audit")
    with factory() as s:
        t = s.get(ComplexType, tid)
        assert t is not None and t.max_price_won == 699_400_000
        chosen = next(r for r in _price_rows(s, tid) if r.chosen)
        assert chosen.label == "확인됨" and chosen.reason and chosen.reason.startswith("판정기 추출 jl_")
        assert "감사 jl_" in chosen.reason


def test_p3_audit_flagged_is_not_applied(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    cid, tid = _seed_notice(factory)
    jev.extract_values = {"max_price_won": "699,400,000원"}
    jev.audit_flags = {"max_price_won"}
    out = run_pipeline(make_ctx(), seeded, complex_ids=[cid])
    assert out.extract_flagged >= 1
    with factory() as s:
        t = s.get(ComplexType, tid)
        assert t is not None and t.max_price_won is None
        flagged = [r for r in _price_rows(s, tid) if (r.reason or "").startswith("판정기 감사 flagged")]
        assert len(flagged) == 1 and flagged[0].label == "확인 불가" and not flagged[0].chosen


# ---------------------------------------------------------------- 배치·저장


def test_inclusion_batch_one_call_judge_scope_and_result_json(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    out = run_pipeline(make_ctx(), seeded)
    assert not out.degraded
    assert jev.calls.count("jev_classify") == 1  # 16단지 포함/제외 = 1회(호재·접수 미분류 없음)
    with factory() as s:
        seqs = set(s.scalars(select(Complex.inclusion_judgment_seq).where(Complex.region_id == 1)))
        assert len(seqs) == 1 and None not in seqs
        log = s.get(JudgmentLog, next(iter(seqs)))
        assert log is not None and log.purpose == "classify:inclusion:batch0"
        assert len(log.input_json["items"]) == 16 and len(log.result_json["items"]) == 16  # type: ignore[index]
        # result_json: 판정기로 간 모든 행에 정규화 결과
        rows = list(s.scalars(select(JudgmentLog).where(JudgmentLog.status.in_(("ok", "review")))))
        assert rows and all(isinstance(r.result_json, dict) and r.result_json for r in rows)
        # score_total.judge_scope: 모든 행에 이 실행의 판정 범위
        runs = [r.id for r in s.scalars(select(ScoreRun).where(ScoreRun.snapshot_id == seeded))]
        totals = list(s.scalars(select(ScoreTotal).where(ScoreTotal.score_run_id.in_(runs))))
        assert totals and all(t.judge_scope for t in totals)
        scopes = {t.complex_id: t.judge_scope for t in totals}
        assert scopes[15] == scopes[16] == "보류"  # 분양가 미공개
        assert scopes[2] == "판정 대상"
    # 두 번째 실행: 같은 입력 → 분류 호출 0(배치 payload 가 집합으로 같다)
    run_pipeline(make_ctx(), seeded, complex_ids=[2])
    assert jev.calls.count("jev_classify") == 1


# ---------------------------------------------------------------- 미리보기 빌더


def test_scenario_payloads_match_pipeline_hashes(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    with factory() as s:
        (base,) = load_scenarios(s, 1)
        before = cache_status(s, scenario_payloads(s, seeded, base))
        assert before.hits == 0 and before.misses > 0  # 판정 전: 전부 미스
    run_pipeline(make_ctx(), seeded)
    n_calls = len(jev.calls)
    with factory() as s:
        plan = scenario_payloads(s, seeded, base)
        tools = [c.tool for c in plan.calls]
        assert tools.count("rerank") == 1 and tools.count("decide") == 1 and tools.count("noul") >= 30
        decide = next(c for c in plan.calls if c.tool == "decide")
        assert decide.payload is not None
        st = cache_status(s, plan)
        assert (st.hits, st.misses) == (len(plan.calls), 0)  # 같은 payload hash 가 전부 judgment_log 에 있다
        key = decide.input_hash(plan.adapter_version or "")
        row = s.scalars(select(JudgmentLog).where(JudgmentLog.input_hash == key)).one()
        assert row.tool == "decide" and row.purpose == "decide:scenario_base"
        # 사실이 바뀐 단지(입주월) → 그 단지 noul 미스, decide 는 앞 단계 미스라 미스
        cx = s.get(Complex, 2)
        assert cx is not None
        cx.move_in_ym = "2028-06"
        s.commit()
        changed = cache_status(s, scenario_payloads(s, seeded, base))
        assert changed.calls_by_tool["noul"] >= 1 and changed.calls_by_tool["decide"] == 1
        assert changed.hits == len(plan.calls) - changed.misses
    assert len(jev.calls) == n_calls  # 빌더는 판정기를 부르지 않는다


def test_path_constant_points_to_wp1b_fixture() -> None:
    assert (WP1B_FIXTURES / "hndapt_index.html").is_file() and isinstance(WP1B_FIXTURES, Path)
    assert Snapshot.__tablename__ == "snapshot"

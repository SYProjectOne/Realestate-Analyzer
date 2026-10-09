"""R3b G2 — 재리뷰(R3_REVIEW2) 파이프라인·스케줄러 항목 (계약 2026-10-09.5, DECISIONS D10).

N-C2(D10-2) 변경 없는 날 범위·순위 불변(리뷰 재현) · F2 copy_intake = pick_intake · N-M8 판정기 다운 + 전부 캐시 ·
N-M2(D10-6) 뉴스 후보 screen → classify('호재 아님' 폐기) · N-M4 벤치마크 '대체(지역 전체)' · C3 OCR 값 null·32필드 분할 ·
M2 당첨일 라벨 · m13 서버 쪽 알림·sent_ids 영속 · m23 도구별 캐시 집계 · F2 가격 출처 라벨·wait_new 12개월.
지역명은 픽스처에만 있다(AGENTS 규칙 15).
"""

# ruff: noqa: E501  (한국어 docstring·픽스처 행)

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
import respx
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.complex_input import resale_input_label
from app.analysis.score import SUBSTITUTE_TEXT, benchmark_component, liquidity_component
from app.api.views import load_bundles, rejudge_needed, scope_result, score_input, shown_scope
from app.collectors.official_site import OfficialSiteCollector, SiteTarget
from app.core.contracts_gen import BenchmarkInput
from app.core.http import HttpClient
from app.judge.jev_mcp import JevMcpAdapter
from app.judge.payloads import NOT_CATALYST
from app.models import (
    Benchmark,
    Catalyst,
    ChangeEvent,
    Complex,
    ComplexType,
    FieldProvenance,
    IntakeStatus,
    JobRun,
    PaymentTerms,
    RawDocument,
    Region,
    ScoreComponent,
    ScoreRun,
    ScoreTotal,
    Snapshot,
)
from app.normalize.benchmark import SUBSTITUTE_NOTE
from app.scheduler import pipeline as pl
from app.scheduler import runner
from app.scheduler.context import SchedulerContext
from app.scheduler.inputs import complex_input, load_facts
from app.scheduler.intake import COPIED_MARK
from app.scheduler.jobs import enqueue
from app.scheduler.notify import Notifier
from app.scheduler.payloads import wait_new_evidence
from app.scheduler.persist import copy_intake
from app.scheduler.pipeline import run_pipeline

from .conftest import REPO, Clock, SynthJev

WP1B_FIXTURES = REPO / "backend" / "tests" / "collectors" / "official_site" / "fixtures"
SITE = "https://site.example.test/"
ROBOTS = "https://site.example.test/robots.txt"
CX = 4  # 픽스처에서 공식 홈페이지가 403 이던 단지 — 이 테스트에서는 녹화 페이지가 열린다


def _count(s: Session, model: Any, *where: Any) -> int:
    return int(s.scalar(select(func.count()).select_from(model).where(*where)) or 0)


def _ctx(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], jev: SynthJev, **kw: Any
) -> SchedulerContext:
    return make_ctx(
        adapter_factory=lambda: JevMcpAdapter(transport=jev, session_factory=factory, secrets=[]), **kw
    )


def _base_totals(s: Session, sid: int) -> dict[int, tuple[str | None, int | None, Decimal | None]]:
    run = s.scalars(
        select(ScoreRun)
        .where(ScoreRun.snapshot_id == sid, ScoreRun.scenario_id == 1)
        .order_by(ScoreRun.id.desc())
    ).first()
    assert run is not None, sid
    return {
        t.complex_id: (t.judge_scope, t.rank, t.total)
        for t in s.scalars(select(ScoreTotal).where(ScoreTotal.score_run_id == run.id))
    }


# ====================================================================== N-C2 (D10-2) — 리뷰 재현 그대로


@pytest.fixture
def site_ctx(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session]
) -> Iterator[SchedulerContext]:
    """공식 홈페이지 수집기 = WP1b OfficialSiteCollector + 녹화 HTML(respx), 렌더 없음 → 접수 경로 official_popup."""
    http = HttpClient(sleep=lambda _s: None, max_retries=0, jitter=0)

    def official(_ctx: SchedulerContext) -> OfficialSiteCollector:
        return OfficialSiteCollector(
            http=http, render="never", targets=[SiteTarget(SITE, CX)], session_factory=factory
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


def _daily(factory: sessionmaker[Session], ctx: SchedulerContext, clock: Clock, day: date) -> int:
    clock.day = day
    with factory() as s:
        enqueue(s, "collect.daily", {"region_id": 1, "sources": ["official_site"]})
        s.commit()
    done = runner.run_until_idle(ctx)
    with factory() as s:
        jobs = [s.get(JobRun, i) for i in done]
        assert jobs and all(j is not None and j.status == "done" for j in jobs), [
            (j.job_name, j.error_text) for j in jobs if j
        ]
        snap = s.scalars(select(Snapshot).where(Snapshot.asof_date == day.isoformat())).one()
        assert snap.status == "published", (day, snap.status)
        return snap.id


def test_n_c2_no_change_day_keeps_scope_rank_and_no_event_flood(
    site_ctx: SchedulerContext, factory: sessionmaker[Session], seeded: int, jev: SynthJev, clock: Clock
) -> None:
    """리뷰 재현: 1일차 접수 문구 classify '가능' → publish. 2일차 같은 문구(변경 없음)면 분류를 복사해(판정 호출 0)
    published 스냅샷의 접수·판정 범위·순위가 전날과 같다(전에는 '확인 불가(접수 문구 미분류)' → '참고'인데 순위 유지).
    3일차 다른 단지 변경으로 재판정해도 D9-3 접수 변경 critical 이벤트가 단지마다 쏟아지지 않는다."""
    day1 = _daily(factory, site_ctx, clock, date(2026, 10, 8))
    with factory() as s:
        row = s.scalars(
            select(IntakeStatus).where(
                IntakeStatus.snapshot_id == day1,
                IntakeStatus.complex_id == CX,
                IntakeStatus.path == "official_popup",
            )
        ).one()
        assert row.status == "가능" and "판정기 classify" in (row.note or "")
        totals1 = _base_totals(s, day1)
        assert totals1[CX][0] == "판정 대상"
    calls = len(jev.calls)

    day2 = _daily(factory, site_ctx, clock, date(2026, 10, 9))
    assert len(jev.calls) == calls  # 변경 없는 날 판정기 실제 호출 0
    with factory() as s:
        row2 = s.scalars(
            select(IntakeStatus).where(
                IntakeStatus.snapshot_id == day2,
                IntakeStatus.complex_id == CX,
                IntakeStatus.path == "official_popup",
            )
        ).one()
        assert row2.status == "가능" and COPIED_MARK in (row2.note or "")  # D10-2 분류 복사
        assert _count(s, ChangeEvent, ChangeEvent.snapshot_id == day2) == 0
        assert _base_totals(s, day2) == totals1  # 범위·순위·총점 그대로
        # API: 현재 사실로 계산한 범위 = 저장 범위(재판정 필요 없음)
        cxs = list(s.scalars(select(Complex).where(Complex.region_id == 1)))
        bundles = load_bundles(s, cxs, day2)
        for cid, b in bundles.items():
            assert shown_scope(b) == totals1[cid][0], cid
            assert not rejudge_needed(b), (cid, scope_result(b).scope, totals1[cid][0])

    day3 = _daily(factory, site_ctx, clock, date(2026, 10, 10))
    res = run_pipeline(site_ctx, day3, complex_ids=[2], reason="다른 단지 변경")
    assert not res.degraded and res.intake_events == []
    with factory() as s:
        assert (
            _count(s, ChangeEvent, ChangeEvent.snapshot_id == day3, ChangeEvent.entity == "intake_status")
            == 0
        )
        # 재판정(기준일이 바뀌어 점수 값은 다를 수 있다)에서도 판정 범위는 전날과 같다
        assert {c: v[0] for c, v in _base_totals(s, day3).items()} == {c: v[0] for c, v in totals1.items()}


def test_n_c2_changed_phrase_is_not_carried_and_reclassified_before_publish(
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    seeded: int,
    jev: SynthJev,
    clock: Clock,
) -> None:
    """N-C2 반대 경우(R3 3차 minor 8): 2일차 접수 문구가 바뀌면 분류를 복사하지 않고(미분류 → 재판정 대상) 판정기가 다시
    분류한 뒤 publish 한다 — 이전 분류를 복사한 채 publish 하지 않는다."""
    http = HttpClient(sleep=lambda _s: None, max_retries=0, jitter=0)
    page = {"html": (WP1B_FIXTURES / "hndapt_index.html").read_bytes()}

    def official(_ctx: SchedulerContext) -> OfficialSiteCollector:
        return OfficialSiteCollector(
            http=http, render="never", targets=[SiteTarget(SITE, CX)], session_factory=factory
        )

    with respx.mock(assert_all_called=False) as router:
        router.get(ROBOTS).respond(200, content=(WP1B_FIXTURES / "hndapt_robots.txt").read_bytes())
        router.get(SITE).mock(
            side_effect=lambda _req: __import__("httpx").Response(
                200, content=page["html"], headers={"content-type": "text/html; charset=utf-8"}
            )
        )
        ctx = make_ctx(collectors={"official_site": official})
        day1 = _daily(factory, ctx, clock, date(2026, 10, 8))
        page["html"] = page["html"].replace("마감재리스트".encode(), "잔여세대 선착순 계약 안내".encode())
        calls = len(jev.calls)
        day2 = _daily(factory, ctx, clock, date(2026, 10, 9))
    http.close()
    with factory() as s:
        row2 = s.scalars(
            select(IntakeStatus).where(
                IntakeStatus.snapshot_id == day2,
                IntakeStatus.complex_id == CX,
                IntakeStatus.path == "official_popup",
            )
        ).one()
        assert COPIED_MARK not in (row2.note or ""), row2.note  # 문구가 바뀌었으니 복사하지 않는다
        assert (
            "판정기 classify" in (row2.note or "") and row2.reason != "접수 문구 미분류"
        )  # publish 전에 다시 분류
        assert len(jev.calls) > calls  # 판정기 실제 호출(접수 classify)
        snap2 = s.get(Snapshot, day2)
        assert snap2 is not None and snap2.status == "published" and day2 != day1


def test_f2_copy_intake_uses_pick_intake_rule(factory: sessionmaker[Session], seeded: int) -> None:
    """같은 경로 두 행: 나중 id 가 더 옛 날짜면 표시 행(pick_intake = 날짜 우선)을 복사한다 — id 순이면 가짜 D9-3."""
    with factory() as s:
        s.add_all(
            [
                IntakeStatus(complex_id=9, snapshot_id=seeded, status="가능", path="official_popup", checked_at="2026-10-08"),
                IntakeStatus(complex_id=9, snapshot_id=seeded, status="불가", path="official_popup", checked_at="2026-10-01T09:00:00+09:00"),
            ]
        )  # fmt: skip
        dst = Snapshot(
            region_id=1,
            asof_date="2026-10-09",
            status="building",
            degraded=False,
            created_at="2026-10-09T06:00:00+09:00",
        )
        s.add(dst)
        s.flush()
        copy_intake(s, seeded, dst.id)
        s.commit()
        [copied] = s.scalars(
            select(IntakeStatus).where(IntakeStatus.snapshot_id == dst.id, IntakeStatus.complex_id == 9)
        ).all()
        assert (copied.status, copied.checked_at) == ("가능", "2026-10-08")


# ====================================================================== N-M8


def test_n_m8_judge_down_all_cached_completes_without_version_call(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    first = run_pipeline(_ctx(make_ctx, factory, jev), seeded)
    assert not first.degraded and first.judge_calls > 0
    calls = len(jev.calls)
    jev.down = True  # 판정기 다운: server_version 도 예외
    again = run_pipeline(_ctx(make_ctx, factory, jev), seeded)  # 새 문맥(어댑터가 버전을 모른다)
    assert not again.degraded, again.error
    assert again.judge_calls == 0 and again.cached > 0 and len(jev.calls) == calls
    assert again.version_event_id is None
    with factory() as s:
        snap = s.get(Snapshot, seeded)
        assert snap is not None and snap.status == "ready" and not snap.degraded


# ====================================================================== N-M2 (D10-6) 호재 후보


@dataclass
class NewsJev(SynthJev):
    """screen: '분양' 기사 = skip(호재 관련 없음). 호재 단계 classify: '견본주택' = '호재 아님'."""

    screened: list[str] = field(default_factory=list)

    def _screen(self, a: dict[str, Any]) -> dict[str, Any]:
        self.screened.append(a["text"])
        if "분양" in a["text"]:
            return {
                "probabilities": {"injection": 0.0, "substance": 0.9, "relevance": 0.05},
                "recommendation": {"action": "skip"},
            }
        return super()._screen(a)

    def _classify(self, a: dict[str, Any]) -> dict[str, Any]:
        out = super()._classify(a)
        if a["classes"][0]["id"] == "확정":  # 호재 단계(5단계 + '호재 아님')
            for r, it in zip(out["results"], a["items"], strict=True):
                if "견본주택" in it["text"]:
                    r["classification"] = NOT_CATALYST
        return out


@dataclass
class NewsCollector:
    factory: sessionmaker[Session]
    items: list[dict[str, str]]

    def fetch(self, region: Any, snapshot: Any, since: str | None) -> list[Any]:
        import hashlib as _h
        import json as _json

        from app.core.snapshot import store_raw
        from app.normalize.store import raw_dto

        data = _json.dumps({"items": self.items}, ensure_ascii=False).encode("utf-8")
        with self.factory() as s:
            row = s.scalars(
                select(RawDocument).where(RawDocument.sha256 == _h.sha256(data).hexdigest())
            ).first()
            if row is None:
                stored = store_raw(data, source="news", day=date(2026, 10, 7), ext="json")
                row = RawDocument(
                    source_kind="news", url="https://naverapihub.apigw.ntruss.com/search/v1/news?query=q",
                    fetched_at="2026-10-07T06:00:00+09:00", http_status=200, sha256=stored.sha256,
                    path=stored.relpath, content_type="application/json", region_id=1,
                )  # fmt: skip
                s.add(row)
                s.flush()
            dto = raw_dto(row)
            s.commit()
        return [dto]


def test_n_m2_news_screen_at_collect_then_classify_discards_not_catalyst(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int
) -> None:
    """D10-6: 뉴스 항목 → P1 screen(수집, skip 은 후보 아님) → 후보 → P4 단계 classify('호재 아님'은 폐기·기록) → 종류 classify."""
    from app.scheduler.collect import collect

    jev = NewsJev()
    items = [
        {
            "title": "검단 신도시 아파트 분양 일정",
            "originallink": "https://news.example.com/a",
            "description": "발췌",
        },
        {
            "title": "송도 모델하우스 견본주택 개관",
            "originallink": "https://news.example.com/b",
            "description": "발췌",
        },
        {"title": "트램 기본계획 고시", "originallink": "https://news.example.com/c", "description": "발췌"},
    ]
    ctx = _ctx(make_ctx, factory, jev, collectors={"news": lambda c: NewsCollector(factory, items)})
    res = collect(ctx, 1, ["news"], asof_date="2026-10-07")
    assert res.errors == {}, res.errors
    assert res.stats()["assembled"]["catalyst"]["rejected"] == 1  # screen skip → 후보를 만들지 않는다
    assert len(jev.screened) == 3
    with factory() as s:
        _cand(s, None, "사람 입력 호재", "https://gov.example.go.kr/d")  # 사람 URL 입력 — screen 없이 분류
        s.commit()
        assert {c.name for c in s.scalars(select(Catalyst))} == {
            "송도 모델하우스 견본주택 개관", "트램 기본계획 고시", "사람 입력 호재",
        }  # fmt: skip
    out = run_pipeline(ctx, seeded)
    assert not out.degraded, out.error
    with factory() as s:
        kept = {c.name: c for c in s.scalars(select(Catalyst))}
        # '호재 아님'은 지우지 않고 단계로 남긴다(R3 3차 M-10 · D11-2)
        assert kept["송도 모델하우스 견본주택 개관"].stage == "호재 아님"
        assert {n for n, c in kept.items() if c.stage != "호재 아님"} == {
            "트램 기본계획 고시",
            "사람 입력 호재",
        }
        tram = kept["트램 기본계획 고시"]
        assert (
            tram.stage == "확정" and tram.judgment_seq is not None and tram.kind == "교통"
        )  # 종류도 classify
    assert [(d["name"], d["reason"]) for d in out.catalysts_discarded] == [
        ("송도 모델하우스 견본주택 개관", "호재 아님(판정기 classify)")
    ]
    assert out.catalysts_discarded[0]["judgment_seq"] is not None  # 기록(judgment_log 근거)
    # 다음 주 같은 기사가 다시 들어와도(screen·classify 키 = 출처·제목 해시) 판정 재호출 없음
    n = len(jev.calls)
    collect(ctx, 1, ["news"], asof_date="2026-10-07")
    run_pipeline(ctx, seeded)
    assert len(jev.calls) == n


def _cand(s: Session, doc_id: int | None, name: str, url: str) -> None:
    s.add(
        Catalyst(
            region_id=1, name=name, kind="기타", stage="미확정", location_confirmed=False,
            raw_document_id=doc_id, source_url=url, note="발췌",
        )
    )  # fmt: skip


# ====================================================================== N-M4 대체 표기


def test_n_m4_benchmark_substitute_marked_in_formula_and_label() -> None:
    from app.core.contracts_gen import ComplexScoreInput

    cx = ComplexScoreInput.model_validate(
        {"complex_id": 1, "name": "x", "living_area": "la_9", "judge_scope": "판정 대상", "price_low_won": 1, "price_high_won": 2,
         "move_in_ym": None, "ladders": [], "winner_date": None, "resale_months": None, "resale_release_on_registration": None,
         "residency_months": None, "down_payment_pct": None, "intake_status": None, "intake_path": None}
    )  # fmt: skip

    def rows_(substitute: bool) -> list[BenchmarkInput]:
        return [
            BenchmarkInput(id=i, living_area="la_9", name=f"b{i}", completed_year=2022, sale_year=2024,
                           sale_price_84_won=500_000_000, trade_median_won=600_000_000, is_presale=False,
                           substitute=substitute, label="확인됨")
            for i in (1, 2, 3)
        ]  # fmt: skip

    own = benchmark_component(cx, rows_(False), asof_date="2026-10-07")
    assert SUBSTITUTE_TEXT not in own.formula_text and own.label == "확인됨"
    # 계약 2026-10-09.7: 대체 표식 = BenchmarkInput.substitute(호출자가 id 목록을 넘기지 않는다)
    sub = benchmark_component(cx, rows_(True), asof_date="2026-10-07")
    assert SUBSTITUTE_TEXT in sub.formula_text and sub.label == "추정"
    assert sub.reason and SUBSTITUTE_TEXT in sub.reason and "substitute_region" in sub.flags
    assert sub.score == own.score  # 표기만 — 값은 같은 식


def test_n_m4_pipeline_passes_substitute_label_to_stored_component(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    with factory() as s:
        la = s.get(Complex, 2)
        assert la is not None
        for b in s.scalars(select(Benchmark).where(Benchmark.living_area == la.living_area)):
            b.note = f"{SUBSTITUTE_NOTE} — 생활권 {la.living_area} 자체 표본 0"
            b.substitute = True  # 계약 2026-10-09.7: 판별은 컬럼(note 는 설명)
        s.commit()
        area = la.living_area
    run_pipeline(_ctx(make_ctx, factory, jev), seeded)
    with factory() as s:
        run = s.scalars(
            select(ScoreRun).where(ScoreRun.snapshot_id == seeded, ScoreRun.scenario_id == 1)
        ).one()
        comp = s.scalars(
            select(ScoreComponent).where(
                ScoreComponent.score_run_id == run.id,
                ScoreComponent.complex_id == 2,
                ScoreComponent.component == "benchmark",
            )
        ).one()
        if comp.score_0_10 is not None:
            assert SUBSTITUTE_TEXT in (comp.formula_text or "") and comp.label == "추정", (
                area,
                comp.formula_text,
            )
            assert comp.reason and SUBSTITUTE_TEXT in comp.reason


# ====================================================================== C3 OCR 값 · 32필드 분할


def _ocr(s: Session, entity: str, eid: int, name: str, value: str) -> None:
    for fp in s.scalars(
        select(FieldProvenance).where(
            FieldProvenance.entity == entity, FieldProvenance.entity_id == eid, FieldProvenance.field == name
        )
    ):
        fp.chosen = False
    s.add(
        FieldProvenance(
            entity=entity, entity_id=eid, field=name, value_text=value, url="https://example.test/notice.pdf",
            checked_at="2026-10-07", label="추정", reason="OCR", source_rank=1, chosen=True,
        )
    )  # fmt: skip


def test_c3_ocr_values_are_null_in_score_inputs_until_extracted(
    factory: sessionmaker[Session], seeded: int
) -> None:
    """screen 거부·extract 실패로 chosen 출처가 OCR 판독('추정(OCR)')으로 남은 값은 점수·범위 입력에서 null.
    화면 가격은 그대로(라벨 '추정(OCR)'). API 미리보기 입력도 같은 규칙(minor 20 동일성)."""
    with factory() as s:
        _ocr(s, "complex", 2, "resale_months", "6")
        basis7 = min(
            s.scalars(select(ComplexType).where(ComplexType.complex_id == 7)),
            key=lambda t: abs(float(t.area_m2 or 0) - 84),
        )
        for t in s.scalars(select(ComplexType).where(ComplexType.complex_id == 7)):
            _ocr(s, "complex_type", t.id, "max_price_won", str(t.max_price_won))
        s.commit()
        snap = s.get(Snapshot, seeded)
        region = s.get(Region, 1)
        assert snap is not None and region is not None
        facts = {f.complex_id: f for f in load_facts(s, snap, region)}
        assert facts[2].row.resale_months is not None  # 사실 행은 그대로
        assert complex_input(facts[2], snap.asof_date).resale_months is None
        assert facts[7].price_high is None and complex_input(facts[7], snap.asof_date).price_high_won is None
        bundles = load_bundles(s, list(s.scalars(select(Complex).where(Complex.id.in_([2, 7])))), seeded)
        assert score_input(bundles[2]).resale_months is None
        assert (
            score_input(bundles[7]).price_high_won is None
            and scope_result(bundles[7]).scope == facts[7].scope
        )
        from app.api.views import bundle_price

        assert (
            bundle_price(bundles[7]).high_won is not None and basis7.max_price_won
        )  # 화면 표시 가격은 남는다


@dataclass
class FieldCountJev(SynthJev):
    extract_fields: list[int] = field(default_factory=list)

    def _extract(self, a: dict[str, Any]) -> dict[str, Any]:
        self.extract_fields.append(len(a["fields"]))
        return super()._extract(a)


def test_c3_extract_over_32_fields_is_split_not_truncated(
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    seeded: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.normalize.extract_request import ExtractRequest

    names = [f"type_{i}.max_price_won" for i in range(40)]
    req = ExtractRequest(
        raw_document_id=None,
        source_url=None,
        entity="complex_type",
        entity_key=None,
        fields=names,
        text="공고문 발췌 " * 20,
    )

    class _Parser:
        def parse(self, raw: Any) -> list[Any]:
            return []

    monkeypatch.setattr(pl, "parser_for", lambda kind: _Parser())
    monkeypatch.setattr(pl, "build_extract_requests", lambda cands: [req])
    monkeypatch.setattr(
        pl, "apply_extracted", lambda *a, **k: type("A", (), {"applied": [], "flagged": []})()
    )
    with factory() as s:
        s.add(
            RawDocument(
                source_kind="notice_pdf", url="https://example.test/n.pdf", fetched_at="2026-10-07T06:00:00+09:00",
                http_status=200, sha256="c" * 64, path="notice_pdf/x.txt", content_type="text/plain", region_id=1, complex_id=2,
            )
        )  # fmt: skip
        s.commit()
    jev = FieldCountJev()
    res = run_pipeline(_ctx(make_ctx, factory, jev), seeded, complex_ids=[2])
    assert sorted(jev.extract_fields) == [8, 32]  # 잘라 버리지 않고 32 + 8
    assert res.carried["extract_requests"] == 2


# ====================================================================== M2 당첨일 라벨


def test_m2_winner_date_label_in_liquidity_label(factory: sessionmaker[Session], seeded: int) -> None:
    with factory() as s:
        for fp in s.scalars(
            select(FieldProvenance).where(
                FieldProvenance.entity == "complex", FieldProvenance.entity_id == 2, FieldProvenance.chosen.is_(True),
                FieldProvenance.field.in_(("winner_date", "resale_months")),
            )
        ):  # fmt: skip
            fp.label = "추정" if fp.field == "winner_date" else "확인됨"
        s.commit()
        snap = s.get(Snapshot, seeded)
        region = s.get(Region, 1)
        assert snap is not None and region is not None
        f2 = next(f for f in load_facts(s, snap, region) if f.complex_id == 2)
        assert f2.labels["winner"] == "추정" and f2.labels["resale"] == "확인됨"
        ci = complex_input(f2, snap.asof_date)
        assert ci.winner_date is not None and ci.resale_label == "확인됨"
    # 계약 2026-10-09.7: 빌더(파이프라인 입력 조립)가 당첨일 라벨을 winner_label 로 싣는다
    assert ci.winner_label == "추정"
    # 전매 종료 = 당첨일 + 기간 → 라벨은 약한 쪽(유동성 성분 라벨 합성에 포함)
    assert resale_input_label("확인됨", "추정") == "추정" and resale_input_label(None, None) is None
    liq = liquidity_component(ci, asof_date="2026-10-07")
    assert liq.score is not None, liq
    assert liq.label == "추정" and liq.reason and "전매 추정" in liq.reason
    plain = liquidity_component(ci.model_copy(update={"winner_label": None}), asof_date="2026-10-07")
    assert plain.label != "추정" or "전매 추정" not in (plain.reason or "")


# ====================================================================== F2 가격 출처 라벨 · wait_new 12개월


def test_f2_terms_price_without_provenance_is_not_type_label(
    factory: sessionmaker[Session], seeded: int
) -> None:
    with factory() as s:
        snap = s.get(Snapshot, seeded)
        region = s.get(Region, 1)
        assert snap is not None and region is not None
        f7 = next(f for f in load_facts(s, snap, region) if f.complex_id == 7)
        assert f7.price_label is not None and f7.basis is not None
        s.add(
            PaymentTerms(
                complex_id=7, notice_no="R3B-임의", notice_kind="임의", effective_from="2026-10-01",
                down_payment_pct=Decimal(5), interim_schedule=[],
                price_by_type={f7.basis.type_code: {"max_price_won": 640_000_000}},
            )
        )  # fmt: skip
        s.commit()
        f7b = next(f for f in load_facts(s, snap, region) if f.complex_id == 7)
        assert f7b.price is not None and f7b.price.from_terms and f7b.price_high is not None
        assert f7b.price_label is None  # 출처 행 없음 → '확인 불가(가격 출처 누락)', 타입 행 라벨 대용 금지


def test_f2_wait_new_window_12_months(factory: sessionmaker[Session], seeded: int) -> None:
    with factory() as s:
        for cx in s.scalars(select(Complex).where(Complex.region_id == 1)):
            cx.inclusion_class, cx.inclusion_decision = "private_sale_apt", "auto"
        a15, a16 = s.get(Complex, 15), s.get(Complex, 16)
        assert a15 is not None and a16 is not None
        a15.notice_date, a16.notice_date = "2027-12-01", "2026-12-15"  # 15 = 12개월 창 밖, 16 = 창 안
        s.flush()
        snap = s.get(Snapshot, seeded)
        region = s.get(Region, 1)
        assert snap is not None and region is not None
        text = wait_new_evidence(load_facts(s, snap, region), snap.asof_date)
        assert text.startswith("지역 (A) 트랙 공고 예정 1곳") and a16.name in text and a15.name not in text


# ====================================================================== m13 서버 쪽 알림 · sent_ids 영속 / m23


def test_m13_api_critical_event_notified_server_side_once_across_restart(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, clock: Clock
) -> None:
    sent: list[dict[str, Any]] = []

    def notifier() -> Notifier:
        return Notifier(
            webhook_url="https://hooks.example.test/x", post=lambda u, b: sent.append(b) or 200, secrets=[]
        )

    with factory() as s:  # API(사람 확인 입력)가 만드는 행 — 토스트 '재판정' 클릭 없음
        row = IntakeStatus(
            complex_id=4,
            snapshot_id=seeded,
            status="가능",
            path="human_check",
            checked_at="2026-10-08",
            entered_by="운영자",
        )
        s.add(row)
        s.flush()
        ev = ChangeEvent(
            snapshot_id=seeded, entity="intake_status", entity_id=row.id, field="status", old_text="확인 불가(403) [official_popup]",
            new_text="가능", detected_at=clock.now().isoformat(), severity="critical", triggers_rejudge=True, complex_id=4,
        )  # fmt: skip
        s.add(ev)
        s.commit()
        eid = ev.id
    runner.run_until_idle(make_ctx(notifier=notifier()))
    assert len(sent) == 1 and sent[0]["events"][0]["field"] == "status"
    with factory() as s:
        job = s.scalars(select(JobRun).where(JobRun.job_name == "rejudge")).one()
        assert job.status == "done" and job.payload["change_event_ids"] == [eid]
        assert job.stats["notify"]["notified_event_ids"] == [eid]  # 영속 기록
    # worker 재시작(새 Notifier — 메모리 기록 없음): 다시 보내지 않고, 재판정도 다시 등록하지 않는다
    ctx2 = make_ctx(notifier=notifier())
    runner.run_until_idle(ctx2)
    with factory() as s:
        events = list(s.scalars(select(ChangeEvent).where(ChangeEvent.id == eid)))
        assert ctx2.notifier.notify(events).skipped == "already_sent"
        assert _count(s, JobRun, JobRun.job_name == "rejudge") == 1
    assert len(sent) == 1


def test_m23_cached_by_tool_in_job_stats_and_ops_counts(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    from app.api.routers.ops import cache_hits

    ctx = _ctx(make_ctx, factory, jev)
    for _ in range(2):
        with factory() as s:
            enqueue(
                s,
                "rejudge",
                {"snapshot_id": seeded, "scenario_id": None, "complex_ids": None, "reason": "m23"},
                kind="rejudge",
                dedupe=False,
            )
            s.commit()
        runner.run_until_idle(ctx)
    with factory() as s:
        jobs = list(s.scalars(select(JobRun).where(JobRun.job_name == "rejudge").order_by(JobRun.id)))
        second = jobs[-1].stats
        assert second["cached"] > 0 and second["cached_by_tool"].get("noul", 0) > 0
        assert sum(second["cached_by_tool"].values()) == second["cached"]
        total, by_tool = cache_hits(s, "2000-01-01")
        assert total >= second["cached"] and by_tool.get("noul", 0) >= second["cached_by_tool"]["noul"]


# ====================================================================== 계약 .6 (G3) 연동: P9 주장 대상 · 강등 정리


def test_p9_claims_carry_fact_target_and_pipeline_syncs_demotions(
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    seeded: int,
    jev: SynthJev,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api import demotion
    from app.models import Claim

    synced: list[set[int] | None] = []
    real = demotion.sync_demotions

    def spy(session: Session, complex_ids: set[int] | None = None) -> int:
        synced.append(complex_ids)
        return real(session, complex_ids)

    monkeypatch.setattr(demotion, "sync_demotions", spy)
    run_pipeline(_ctx(make_ctx, factory, jev), seeded, complex_ids=[2])
    assert synced == [{2}]  # load_facts 앞에서 강등 정리(D10-3)
    with factory() as s:
        claims = list(s.scalars(select(Claim).where(Claim.snapshot_id == seeded, Claim.complex_id == 2)))
        assert claims
        by_field = {c.field: c for c in claims if c.field}
        assert by_field["resale_months"].entity == "complex" and by_field["resale_months"].entity_id == 2
        if "max_price_won" in by_field:
            t = s.get(ComplexType, by_field["max_price_won"].entity_id)
            assert by_field["max_price_won"].entity == "complex_type" and t is not None and t.complex_id == 2
        if "down_payment_pct" in by_field:
            pt = s.get(PaymentTerms, by_field["down_payment_pct"].entity_id)
            assert (
                by_field["down_payment_pct"].entity == "payment_terms"
                and pt is not None
                and pt.complex_id == 2
            )
        for c in claims:  # 대상이 정해진 주장은 API 의 판별(claim_target)과 같은 대상
            if c.field:
                tgt = demotion.claim_target(s, c)
                assert tgt is not None and (tgt.field, tgt.entity, tgt.entity_id) == (
                    c.field,
                    c.entity,
                    c.entity_id,
                )

"""region.bootstrap 종단 (DECISIONS D2-4): 참조 표(공식 사본 폴백) → 청약홈 녹화 재생 수집 → 정규화 → 스냅샷 →
판정 P1~P9(MockAdapter, contracts/fixtures/incheon_gimpo_2026-10-08/judgments) → 점수 → publish.

- 청약홈은 WP1a 녹화(tests/collectors/applyhome/fixtures/applyhome_2026-10-09.zip)를 respx 로 재생한다.
- 참조 파일 서버는 전부 DNS 실패 → contracts/fixtures/reference 공식 사본으로 적재(collectors.reference 폴백).
- 녹화 판정 payload 는 보고서 재구성이라 파이프라인 payload 와 hash 가 다르다 → MockAdapter 는 전부 status=review
  (조용히 통과하지 않음). 포함/제외 classify 도 review 라 D9-1 판정 범위 '미해결' — 사다리·점수 행이 없다(R3 C2).
  행이 만들어지고 publish 까지 가는 흐름을 본다(점수 값 재현은 test_pipeline.py 의 SynthJev 쪽).
"""

# ruff: noqa: E501  (한국어 docstring·픽스처 행)

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable, Iterator
from datetime import date
from types import ModuleType
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.scope import judge_scope
from app.collectors.applyhome import ApplyhomeCollector
from app.collectors.reference import ReferenceCollector
from app.core.contracts_gen import RawDocument as RawDTO
from app.core.http import HttpClient
from app.judge.mock import MockAdapter
from app.models import Complex, Decision, JobRun, Ladder, LegalDong, Region, ScoreRun, ScoreTotal, Snapshot
from app.scheduler import runner
from app.scheduler.context import SchedulerContext, default_collectors
from app.scheduler.jobs import enqueue

from .conftest import APPLYHOME_RECORDING, FIXTURE, REFERENCE_COPY, Clock, seed_region, seed_scenarios

TODAY = date(2026, 10, 9)  # 청약홈 녹화일(목록 조회 창이 녹화와 같아야 한다)


def _load_replay() -> ModuleType:
    path = APPLYHOME_RECORDING.parents[1] / "replay.py"
    spec = importlib.util.spec_from_file_location("wp7_applyhome_replay", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += max(0.0, seconds)


class _Empty:
    """녹화가 없는 소스(공고문 PDF·공식 홈페이지·통계) — 빈 결과."""

    def fetch(self, region: Any, snapshot: Any, since: str | None) -> list[RawDTO]:
        return []


@pytest.fixture
def router() -> Iterator[respx.MockRouter]:
    recording = _load_replay().Recording.load(APPLYHOME_RECORDING)
    with respx.mock(assert_all_called=False) as r:
        r.route(host="www.applyhome.co.kr").mock(side_effect=recording.handler)
        r.route(host="static.applyhome.co.kr").mock(side_effect=recording.handler)
        r.route().mock(side_effect=httpx.ConnectError("[Errno 11001] getaddrinfo failed"))
        yield r


def _count(s: Session, model: Any, *where: Any) -> int:
    return int(s.scalar(select(func.count()).select_from(model).where(*where)) or 0)


def test_region_bootstrap_end_to_end_with_mock_judge(
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    clock: Clock,
    router: respx.MockRouter,
    raw_dir: Any,
) -> None:
    clock.day = TODAY
    fake = _FakeClock()
    http = HttpClient(rate_per_host=1.0, max_retries=0, jitter=0.0, sleep=fake.sleep, clock=fake.monotonic)
    ref_http = HttpClient(sleep=lambda _s: None, max_retries=0, jitter=0.0)

    def reference(day: date) -> dict[str, Any]:
        rep = ReferenceCollector(http=ref_http, fallback_dir=REFERENCE_COPY, today=day).refresh()
        return {
            "used_fallback": rep.used_fallback,
            "legal_dong": rep.legal_dong.inserted if rep.legal_dong else 0,
        }

    ctx = make_ctx(
        adapter_factory=lambda: MockAdapter(FIXTURE),
        reference_refresh=reference,
        collectors={
            "applyhome": lambda c: ApplyhomeCollector(
                http=http, today=lambda: TODAY, window=("2025-12", "2026-11")
            ),
            "notice_pdf": lambda c: _Empty(),
            "official_site": lambda c: _Empty(),
            "stats": lambda c: _Empty(),
            "rtms": default_collectors()["rtms"],  # 키 없음 → 비활성
            "news": default_collectors()["news"],  # 키 없음 → 비활성
        },
    )
    with factory() as s:
        seed_scenarios(s)
        seed_region(s, status="resolving")
        ref = enqueue(s, "reference.refresh", {}).id
        boot = enqueue(s, "region.bootstrap", {"region_id": 1}, kind="manual").id
        s.commit()
    done = runner.run_until_idle(ctx)
    http.close()
    ref_http.close()
    assert done[:2] == [ref, boot]
    with factory() as s:
        jobs = {i: s.get(JobRun, i) for i in done}
        assert all(j is not None and j.status == "done" for j in jobs.values()), {
            i: (j.job_name, j.error_text) for i, j in jobs.items() if j is not None
        }
        assert _count(s, LegalDong) > 50_000  # 참조 표(공식 사본 폴백)
        region = s.get(Region, 1)
        assert region is not None and region.status == "ready"
        stats = jobs[boot].stats  # type: ignore[union-attr]
        assert stats["daily"]["documents"]["applyhome"] > 0 and stats["daily"]["stored"] > 0
        assert stats["daily"]["store_errors"] == [], stats["daily"]
        assert stats["weekly"]["skipped"]["rtms"] == "비활성(키 없음)"  # 키 없음 → 비활성(호출 0)
        assert "news" in stats["weekly"]["skipped"]
        assert stats["pipeline"]["statuses"].get("review", 0) > 0  # 녹화 없는 판정 = review(조용한 통과 없음)
        # R3b m23: 캐시 집계를 잡 stats 최상위에도(/ops/judgments cached_hits 가 최상위를 읽는다) — 도구별 포함
        assert stats["cached"] == stats["pipeline"]["cached"]
        assert stats["cached_by_tool"] == stats["pipeline"]["cached_by_tool"]
        assert sum(stats["cached_by_tool"].values()) == stats["cached"]
        snap = s.scalars(select(Snapshot).where(Snapshot.region_id == 1)).one()
        assert snap.asof_date == TODAY.isoformat() and snap.status == "published" and not snap.degraded
        in_region = _count(s, Complex, Complex.region_id == 1, Complex.living_area.is_not(None))
        assert in_region > 0
        # 포함/제외 classify 가 전부 review → D9-1 '미해결': 판정 대상 아님 — 사다리·점수·decide 후보 없음(R3 C2)
        cxs = list(s.scalars(select(Complex).where(Complex.region_id == 1)))
        scopes = {
            judge_scope(
                inclusion_class=c.inclusion_class, inclusion_decision=c.inclusion_decision,
                has_price=True, intake_status="가능",
            ).scope
            for c in cxs
        }  # fmt: skip
        assert scopes <= {"미해결", "제외"}, scopes
        assert _count(s, Ladder, Ladder.snapshot_id == snap.id) == 0
        runs = list(s.scalars(select(ScoreRun).where(ScoreRun.snapshot_id == snap.id)))
        assert len(runs) == 5
        # R3b N-C1(D10-1): 점수 밖 단지도 이 실행의 판정 범위를 남긴다 — 총점·순위 없음
        totals = list(s.scalars(select(ScoreTotal).where(ScoreTotal.score_run_id.in_([r.id for r in runs]))))
        assert all(t.total is None and t.rank is None for t in totals)
        assert {t.judge_scope for t in totals} <= {"미해결", "제외"}
        assert _count(s, Decision, Decision.chosen.is_(True)) == 0  # review 는 추천하지 않는다

"""R4 4차 재시험 N15(major, D23-4) — 청약홈 API 빈 데이터셋 수집은 degraded 이고, 그런 수집으로 bootstrap 스냅샷을 발행하지 않는다.

R4 4차 첫 시도(00:01 KST, 데이터셋 재적재 중): bootstrap 이 단지 24개(정상 72)로 끝나 스냅샷 1 이 ``published`` · ``degraded false`` ·
지역 ``ready`` · G7 출처 실패 0 으로 보였다(판정기 실제 호출 131 도 그대로 썼다). D23-4: 실패 행 + degraded, 그 bootstrap 은 판정·
발행하지 않고(지역 bootstrapping 그대로) 지연 재큐잉(재시도) — 데이터셋이 돌아오면 같은 잡이 처음부터 멱등하게 다시 수집·발행한다.
같은 날·다음 날 ``collect.daily`` 도 degraded 면 재판정·발행(이월 포함)을 하지 않는다(이전 발행 리비전 유지 — 재시도).

원문은 R4 4차 녹화(``r4d_core10.zip``의 단지 1개 — 첫 시도처럼 일부만 들어온 수집), 빈 데이터셋 표시는 수집기의 ``empty_datasets``
(수집기 단위 동작은 ``tests/collectors/applyhome/test_core10_n15_empty_dataset.py``). 판정기는 가짜(``SynthJev``).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.contracts_gen import RawDocument as RawDTO
from app.core.contracts_gen import Region as RegionDTO
from app.core.contracts_gen import Snapshot as SnapshotDTO
from app.core.settings import Settings
from app.judge.jev_mcp import JevMcpAdapter
from app.models import JobRun, Region, Snapshot
from app.scheduler import runner
from app.scheduler.context import SchedulerContext
from app.scheduler.handlers import handle_region_bootstrap
from app.scheduler.jobs import JobError, enqueue

from ..normalize import _r4d
from . import _idem
from .conftest import Clock, SynthJev

HOUSE = "2026000073"
EMPTY_URL = "https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail?page=1&perPage=100"


@dataclass
class _Applyhome(_idem.Replay):
    """청약홈 재생 + 그 실행에서 API 가 빈 데이터셋을 준 조회 주소(실제 수집기의 ``empty_datasets``)."""

    empty_datasets: list[str] = field(default_factory=list)
    empty: bool = True

    def fetch(self, region: RegionDTO, snapshot: SnapshotDTO, since: str | None) -> list[RawDTO]:
        self.empty_datasets = [EMPTY_URL] if self.empty else []
        return super().fetch(region, snapshot, since)


@pytest.fixture
def clock() -> Clock:
    return Clock(day=date(2026, 10, 13))


def _setup(
    test_settings: Settings,
    factory: sessionmaker[Session],
    make_ctx: Callable[..., SchedulerContext],
    jev: SynthJev,
) -> tuple[_Applyhome, SchedulerContext]:
    _r4d.install(test_settings.raw_dir)
    m = _r4d.manifest()
    rs = _idem.ReplaySet("r4d", m, Path("."))
    rs.seed(factory)
    rows = [r for r in _r4d.all_rows() if _r4d.house_no(str(r["url"])) == HOUSE]
    ah = _Applyhome(factory, [r for r in rows if r["source_kind"] != "notice_pdf"])
    pdf = _idem.NoticeReplay(factory, [r for r in rows if r["source_kind"] == "notice_pdf"])
    ctx = make_ctx(
        collectors={"applyhome": lambda c: ah, "notice_pdf": lambda c: pdf},
        adapter_factory=lambda: JevMcpAdapter(transport=jev, session_factory=factory, secrets=[]),
    )
    return ah, ctx


def _job(factory: sessionmaker[Session], jid: int) -> JobRun:
    with factory() as s:
        row = s.get(JobRun, jid)
        assert row is not None
        s.expunge(row)
        return row


def _enqueue(factory: sessionmaker[Session], name: str, payload: dict[str, Any]) -> int:
    with factory() as s:
        job = enqueue(s, name, payload, kind="manual")  # type: ignore[arg-type]
        s.commit()
        return job.id


def _release(factory: sessionmaker[Session], jid: int) -> None:
    """지연 재큐잉 잡의 ``not_before`` 를 지난 시각으로(테스트가 기다리지 않게 — 재시도 시각이 됐다)."""
    with factory() as s:
        row = s.get(JobRun, jid)
        assert row is not None
        row.stats = {**(row.stats or {}), "not_before": "2026-10-13T00:00:00+09:00"}
        s.commit()


def _published(factory: sessionmaker[Session]) -> list[int]:
    with factory() as s:
        return list(
            s.scalars(select(Snapshot.id).where(Snapshot.status == "published").order_by(Snapshot.id))
        )


def test_bootstrap_with_empty_dataset_does_not_judge_or_publish_and_retries(
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    test_settings: Settings,
    jev: SynthJev,
) -> None:
    ah, ctx = _setup(test_settings, factory, make_ctx, jev)
    jid = _enqueue(factory, "region.bootstrap", {"region_id": 1})
    runner.run_until_idle(ctx)
    job = _job(factory, jid)
    stats = dict(job.stats or {})
    assert job.status == "queued" and stats.get("requeue_count") == 1, (
        "빈 데이터셋 bootstrap 은 지연 재큐잉(재시도)이어야 한다(N15)",
        job.status,
        job.error_text,
        {k: stats.get(k) for k in ("requeue_count", "requeue_reason", "degraded")},
    )
    assert "degraded_source" in str(stats.get("requeue_reason")) and stats.get("not_before")
    assert (
        (stats.get("daily") or {})
        .get("degraded_sources", {})
        .get("applyhome", "")
        .startswith("청약홈 API 빈 데이터셋")
    )
    assert jev.calls == [], f"판정하지 않는다: {jev.calls[:5]}"
    assert _published(factory) == [], "발행하지 않는다"
    with factory() as s:
        region = s.get(Region, 1)
        assert region is not None and region.status == "bootstrapping"

    # 데이터셋이 돌아왔다(재적재 끝) — 같은 잡이 다시 수집·판정·발행
    ah.empty = False
    _release(factory, jid)
    runner.run_until_idle(ctx)
    job = _job(factory, jid)
    assert job.status == "done", (job.status, job.error_text)
    assert len(_published(factory)) == 1 and jev.calls
    with factory() as s:
        region = s.get(Region, 1)
        assert region is not None and region.status == "ready"


def test_bootstrap_gives_up_after_max_retries(
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    test_settings: Settings,
    jev: SynthJev,
) -> None:
    from app.scheduler.handlers import EMPTY_DATASET_RETRIES  # D23-4 새 상수(수정 전에는 없다)

    _ah, ctx = _setup(test_settings, factory, make_ctx, jev)
    job = JobRun(
        id=99, job_name="region.bootstrap", kind="manual", payload={"region_id": 1}, status="running",
        scheduled_at="2026-10-13T00:00:00+09:00", stats={"requeue_count": EMPTY_DATASET_RETRIES},
    )  # fmt: skip
    with pytest.raises(JobError, match="degraded_source"):
        handle_region_bootstrap(ctx, job)
    assert jev.calls == [] and _published(factory) == []


def test_daily_with_empty_dataset_keeps_previous_publication(
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    test_settings: Settings,
    jev: SynthJev,
    clock: Clock,
) -> None:
    ah, ctx = _setup(test_settings, factory, make_ctx, jev)
    ah.empty = False
    boot = _enqueue(factory, "region.bootstrap", {"region_id": 1})
    runner.run_until_idle(ctx)
    assert _job(factory, boot).status == "done"
    published = _published(factory)
    with factory() as s:
        snaps = s.scalar(select(func.count()).select_from(Snapshot))
    clock.day = date(2026, 10, 14)  # 다음 날 06:00 daily 가 재적재 중에 걸렸다(가정)
    ah.empty = True
    sent = len(jev.calls)
    jid = _enqueue(factory, "collect.daily", {"region_id": 1, "sources": ["applyhome_list"]})
    runner.run_until_idle(ctx)
    job = _job(factory, jid)
    stats = dict(job.stats or {})
    assert job.status == "queued" and stats.get("requeue_count") == 1, (job.status, job.error_text)
    assert stats.get("degraded_sources", {}).get("applyhome", "").startswith("청약홈 API 빈 데이터셋")
    assert "list_complex_ids" not in stats, "불완전한 목록은 다음 날 비교 기준으로 남기지 않는다"
    assert "carry_forward" not in stats and "rejudge_job_id" not in stats
    assert _published(factory) == published, "이전 발행 리비전 유지 — 새 리비전을 발행하지 않는다"
    assert len(jev.calls) == sent
    with factory() as s:
        assert (
            s.scalar(select(func.count()).select_from(Snapshot)) == snaps + 1
        )  # 새 기준일 리비전은 building 그대로

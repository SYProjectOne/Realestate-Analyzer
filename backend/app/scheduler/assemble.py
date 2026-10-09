"""수집 뒤 데이터 조립 (R3 F1a: C1·M5·M6·M7) — ``collect.collect`` 가 수집 단계를 다 돈 다음 부른다.

| 수집 단계(이번 잡에서 돈 것) | 조립 | 결과 |
| --- | --- | --- |
| applyhome | ``normalize.remaining.sync_remaining_events`` | remaining_event(+ 새 공고 critical change_event) |
| applyhome · notice_pdf | ``normalize.checklist.sync_checklist`` | checklist_item |
| rtms (= collect.weekly) | 청약홈 과거 공고(``fetch_history``, 기본 10년) + rtms 과거 월(``backfill``, 36개월) 수집 →
  ``normalize.benchmark.build_benchmarks`` | benchmark + 출처(+ 바뀌면 notice change_event → 주간 rejudge) |
| news | ``normalize.catalyst.catalysts_from_news`` | catalyst 후보(분류는 판정기 P4) |

과거 공고·과거 월 수집은 ``ctx.collectors`` 의 ``applyhome``·``rtms`` 수집기에 그 메서드가 있을 때만 한다(가짜 수집기·
키 없음이면 건너뛰고, 이미 받아 둔 원문으로 조립한다). 조립 단계마다 예외를 ``errors['assemble.<단계>']`` 에 남기고
(비밀값·개인정보 가림) 다른 단계는 계속한다 — collect 의 수집 단계와 같은 규칙.
"""

# ruff: noqa: E501  (한국어 docstring·로그 필드)

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy.orm import Session

from app.core.contracts_gen import RawDocument as RawDTO
from app.core.contracts_gen import Region as RegionDTO
from app.core.contracts_gen import Snapshot as SnapshotDTO
from app.core.logging import get_logger
from app.core.redact import redact_text
from app.core.settings import get_settings
from app.models import ChangeEvent
from app.normalize.benchmark import build_benchmarks
from app.normalize.catalyst import catalysts_from_news
from app.normalize.checklist import sync_checklist
from app.normalize.remaining import sync_remaining_events

if TYPE_CHECKING:
    from app.scheduler.context import SchedulerContext

__all__ = ["BENCHMARK_HISTORY_YEARS", "RTMS_BACKFILL_MONTHS", "AssembleResult", "assemble", "safe_error"]

log = get_logger("app.scheduler.assemble")

BENCHMARK_HISTORY_YEARS: Final = 10  # D9-2 기본 N년 (청약홈 API 자료는 2020년부터 — 2026-10-09 확인)
RTMS_BACKFILL_MONTHS: Final = 36  # 입주 후 실거래(고점 포함)를 볼 과거 월 수


@dataclass
class AssembleResult:
    stats: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    events: list[ChangeEvent] = field(default_factory=list)  # 저장됨(id 있음)


def safe_error(exc: BaseException) -> str:
    """잡 stats·errors 로 나가는 예외 문구 — 비밀값·개인정보를 가리고 자른다."""
    try:
        secrets = get_settings().secret_values()
    except Exception:  # 설정을 못 읽어도 문구는 남긴다(형태 패턴은 그대로 가린다)
        secrets = []
    return redact_text(f"{type(exc).__name__}: {str(exc)[:200]}", secrets)


def assemble(
    ctx: SchedulerContext,
    region: RegionDTO,
    snapshot: SnapshotDTO,
    *,
    steps: Collection[str],
    docs: Mapping[str, Sequence[RawDTO]],
    detected_at: str,
) -> AssembleResult:
    res = AssembleResult()

    def run(name: str, fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception as exc:  # 조립 버그·환경 오류: 다른 단계는 계속, 잡은 failed
            res.errors[f"assemble.{name}"] = safe_error(exc)
            log.exception("worker.assemble.error", extra={"part": name, "region_id": region.id})

    def remaining() -> None:
        with ctx.session_factory() as s:
            out = sync_remaining_events(s, region.id, snapshot_id=snapshot.id, detected_at=detected_at)
            s.commit()
            res.stats["remaining"] = out.stats()
            res.events.extend(out.events)

    def checklist() -> None:
        with ctx.session_factory() as s:
            out = sync_checklist(s, region.id, asof_date=snapshot.asof_date)
            s.commit()
            res.stats["checklist"] = out.stats()

    def history() -> None:
        factory = ctx.collectors.get("applyhome")
        collector = factory(ctx) if factory is not None else None
        fetch = getattr(collector, "fetch_history", None)
        if not callable(fetch):
            res.stats["benchmark_history"] = {"skipped": "수집기에 과거 공고 조회 없음"}
            return
        got = fetch(region, snapshot, years=BENCHMARK_HISTORY_YEARS)
        res.stats["benchmark_history"] = {
            "documents": len(got),
            "failed": sum(1 for d in got if d.http_status != 200),
            **dict(getattr(collector, "history_stats", {}) or {}),
        }

    def backfill() -> None:
        factory = ctx.collectors.get("rtms")
        collector = factory(ctx) if factory is not None else None
        fill = getattr(collector, "backfill", None)
        if not callable(fill) or getattr(collector, "enabled", True) is False:
            res.stats["rtms_backfill"] = {"skipped": "수집기에 과거 월 채우기 없음(또는 비활성)"}
            return
        got = fill(region, snapshot, months=RTMS_BACKFILL_MONTHS)
        load = getattr(collector, "load_stats", None)
        res.stats["rtms_backfill"] = {
            "documents": len(got),
            "failed": sum(1 for d in got if d.http_status != 200),
            "inserted": int(getattr(load, "inserted", 0) or 0),
        }

    def benchmark() -> None:
        with ctx.session_factory() as s:
            out = build_benchmarks(s, region.id, asof_date=snapshot.asof_date)
            if out.changed:
                res.events.append(_event(s, snapshot.id, out.inserted, out.updated, out.removed, detected_at))
            s.commit()
            res.stats["benchmark"] = out.stats()

    def catalyst() -> None:
        with ctx.session_factory() as s:
            out = catalysts_from_news(s, region.id, docs.get("news", []))
            s.commit()
            res.stats["catalyst"] = out.stats()

    if "applyhome" in steps:
        run("remaining", remaining)
    if "applyhome" in steps or "notice_pdf" in steps:
        run("checklist", checklist)
    if "rtms" in steps:
        run("benchmark_history", history)
        run("rtms_backfill", backfill)
        run("benchmark", benchmark)
    if "news" in steps:
        run("catalyst", catalyst)
    return res


def _event(s: Session, snapshot_id: int, ins: int, upd: int, rem: int, detected_at: str) -> ChangeEvent:
    ev = ChangeEvent(
        snapshot_id=snapshot_id,
        entity="benchmark",
        entity_id=None,
        field="rows",
        old_text=None,
        new_text=f"추가 {ins}건, 갱신 {upd}건, 삭제 {rem}건",
        detected_at=detected_at,
        severity="notice",
        triggers_rejudge=False,
        complex_id=None,
    )
    s.add(ev)
    s.flush()
    return ev

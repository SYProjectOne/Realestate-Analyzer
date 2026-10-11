"""잡 이름 → 처리 함수 (RA §4-4 + DECISIONS D2-4). 처리 함수는 stats(dict)를 돌려주고, 실패는 예외(JobError 면
그 stats 도 남긴다). runner.py 가 job_run 상태를 바꾼다.

| job_name | 처리 |
| --- | --- |
| collect.daily | 수집(청약홈·공고문·공식 홈페이지) → 변경 감지 → 변경 단지만 rejudge 등록 / 변경 없으면 이전 스냅샷 파생 행 복사 + publish(T8) → critical 웹훅 |
| collect.weekly | 실거래·미분양·입주물량·뉴스 → 시장 자료가 바뀌면 점수 재계산 rejudge(판정 대상 단지 0개) |
| rejudge | pipeline P1~P9 (rejudge.py) → snapshot.publish 등록 |
| snapshot.publish | contradicted claim 0 이면 published, 아니면 failed(publish_blocked) |
| reference.refresh | 법정동·행정동·매핑·세대 현황 갱신(collectors.reference) |
| region.bootstrap | region.status=bootstrapping → daily+weekly 수집 → 전체 파이프라인 → publish → ready(실패 failed) |
| claim.reverify | contradicted 주장의 고친 문장 → 원자 분할 → verify → parent_claim_id 자식 행(reverify.py, 계약 2026-10-09.4) |
| report | WP8 ``app.reports.job.run_report_job(payload, session=…)`` (예외 → failed: blocked·not_found·invalid_payload) |
"""

# ruff: noqa: E501  (한국어 docstring·로그 필드)

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import func, select

from app.core.logging import get_logger
from app.models import ChangeEvent, Complex, JobRun, Region, ScoreRun, Snapshot
from app.scheduler import snapshots
from app.scheduler.collect import collect
from app.scheduler.jobs import DAILY_SOURCES, WEEKLY_SOURCES, JobError, JobRequeue
from app.scheduler.persist import carry_forward
from app.scheduler.rejudge import enqueue_rejudge, handle_rejudge
from app.scheduler.reverify import handle_claim_reverify

if TYPE_CHECKING:
    from app.scheduler.context import SchedulerContext

__all__ = ["HANDLERS", "Handler"]

log = get_logger("app.scheduler.handlers")

Handler = Callable[["SchedulerContext", JobRun], dict[str, Any]]


def _since(session: Any, region_id: int, job_name: str, exclude_id: int) -> str | None:
    """같은 지역의 직전 성공 수집 잡 시작 시각(수집기 since)."""
    for job in session.scalars(
        select(JobRun)
        .where(JobRun.job_name == job_name, JobRun.status == "done", JobRun.id != exclude_id)
        .order_by(JobRun.id.desc())
    ):
        if (job.payload or {}).get("region_id") == region_id:
            return str(job.started_at) if job.started_at else None
    return None


def _names(session: Any, ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    return {c.id: c.name for c in session.scalars(select(Complex).where(Complex.id.in_(ids)))}


def _notify(ctx: SchedulerContext, event_ids: list[int]) -> dict[str, Any]:
    if not event_ids:
        return {"sent": 0, "skipped": "no_events"}
    with ctx.session_factory() as session:
        events = list(session.scalars(select(ChangeEvent).where(ChangeEvent.id.in_(event_ids))))
        names = _names(session, sorted({e.complex_id for e in events if e.complex_id is not None}))
    return ctx.notifier.notify(events, names).stats()


JUDGING_JOBS: Final = ("rejudge", "region.bootstrap", "region.expand")
"""단지를 실제로 판정하는 잡(D14-7 — 단지별 마지막 성공 판정 시각의 근거). 이월(carry_forward)은 판정이 아니다."""


def _job_complexes(
    job: JobRun, region_id: int, region_ids: set[int], region_snaps: set[int]
) -> set[int] | None:
    """그 잡이 판정한(하려던) 지역 단지. 그 지역 잡이 아니면 None. rejudge ``complex_ids`` None = 전부, [] = 없음(점수만)."""
    p = job.payload or {}
    if job.job_name == "rejudge":
        if p.get("snapshot_id") not in region_snaps:
            return None
        ids = p.get("complex_ids")
        if ids is None:
            return set(region_ids)
        return {int(i) for i in ids if int(i) in region_ids}
    if p.get("region_id") != region_id:
        return None
    return set(region_ids)


def _judged_revision(job: JobRun) -> int | None:
    """그 판정 잡이 실제로 판정을 쓴 리비전(파이프라인 ``writable`` — 발행 리비전 요청이면 새 리비전). 기록이 없으면 payload."""
    st = job.stats or {}
    pipe = st.get("pipeline")
    for v in ((pipe or {}).get("snapshot_id") if isinstance(pipe, dict) else None, st.get("snapshot_id")):
        if isinstance(v, int):
            return v
    v = (job.payload or {}).get("snapshot_id")
    return v if isinstance(v, int) else None


def _at_or_before(a: str, b: str) -> bool:
    """시각 문자열 a ≤ b(시간대가 달라도 — ``core.time.parse_datetime``). 못 읽으면 문자열 비교."""
    from app.core.time import parse_datetime

    da, db = parse_datetime(a), parse_datetime(b)
    if da is not None and db is not None:
        return da <= db
    return a <= b


def changed_after_runs(session: Any, snap: Snapshot) -> list[int]:
    """이월(옛 점수 복사) 대신 재판정할 단지 — **단지 단위**(D14-7, R3 6차 N-M5) · **D15-4**(R3 7차 M3·m14).

    ``snap`` = 복사 원본(prev) 리비전. 단지마다 기준 시각 = 그 단지를 판정한 마지막 성공 잡(rejudge·region.bootstrap·
    region.expand — done)의 끝 시각인데, **그 판정이 prev 에 들어 있을 때만** 센다: 잡이 판정을 쓴 리비전이 prev 이거나
    prev 이전의 발행 리비전(prev 가 그 값을 이어받았다)이어야 한다. 다른(발행 안 된) 리비전의 성공은 prev 의 점수를 바꾸지
    않았으니 세지 않는다. 시나리오를 지정한 rejudge 는 그 시나리오만 판정된 것으로 센다 — 단지 기준 시각은 prev 의 점수 실행
    시나리오 전부 중 가장 이른 것. 그런 잡 기록이 없으면 그 스냅샷의 **첫** 점수 실행 시각. 그 뒤에

    - 그 단지의 사실 변경(change_event triggers_rejudge — 어느 스냅샷에 붙었든, D13-4)이나 지역 단위 변경(생활권 편집·
      지역 확장/축소 — complex_id 없음)이 있었거나,
    - 그 단지를 포함한 rejudge 잡이 실패했으면(판정기 장애 등 — 어느 리비전이든)

    그 단지를 재판정한다."""
    first_run = session.scalar(select(func.min(ScoreRun.created_at)).where(ScoreRun.snapshot_id == snap.id))
    if not first_run:
        return []
    region_ids = set(session.scalars(select(Complex.id).where(Complex.region_id == snap.region_id)))
    region_rows = list(
        session.execute(
            select(Snapshot.id, Snapshot.asof_date, Snapshot.revision, Snapshot.status).where(
                Snapshot.region_id == snap.region_id
            )
        )
    )
    region_snaps = {int(r[0]) for r in region_rows}
    me = (snap.asof_date, int(snap.revision or 1), snap.id)
    lineage = {
        int(i)
        for i, a, r, st in region_rows
        if int(i) == snap.id or (st == "published" and (a, int(r or 1), int(i)) < me)
    }
    prev_scenarios = sorted(
        {int(x) for x in session.scalars(select(ScoreRun.scenario_id).where(ScoreRun.snapshot_id == snap.id))}
    )
    judged_all: dict[int, str] = {}
    judged_sc: dict[tuple[int, int], str] = {}
    failed: list[tuple[str, set[int]]] = []
    for job in session.scalars(
        select(JobRun).where(JobRun.job_name.in_(JUDGING_JOBS), JobRun.status.in_(("done", "failed")))
    ):
        ids = _job_complexes(job, snap.region_id, region_ids, region_snaps)
        if (
            ids is not None
            and not ids
            and job.status == "failed"
            and job.job_name == "rejudge"
            and (job.payload or {}).get("complex_ids") == []
        ):
            ids = set(
                region_ids
            )  # R3 8차 m7: 점수만 재계산(complex_ids=[]) 실패 = 그 지역 모든 단지 점수가 옛 값
        if not ids:
            continue
        at = str(job.finished_at or job.scheduled_at or "")
        if job.status == "done":
            wrote = _judged_revision(job)
            if wrote not in lineage:
                continue  # D15-4: prev 에 들어 있지 않은 판정(다른·미발행 리비전)
            if wrote != snap.id and not _at_or_before(at, str(snap.created_at or "")):
                continue  # R3 8차 m10: prev 를 만든 뒤 옛 리비전에 쓴 판정은 prev 가 이어받지 않았다
            # R3 8차 m9: 판정 기준 시각 = 잡이 사실을 읽기 시작한 시각(실행 중 들어온 변경은 판정이 못 봤다)
            at = str(job.started_at or job.scheduled_at or at)
            sc = (job.payload or {}).get("scenario_id") if job.job_name == "rejudge" else None
            for c in ids:
                if sc is None:
                    if at > judged_all.get(c, ""):
                        judged_all[c] = at
                elif at > judged_sc.get((c, int(sc)), ""):
                    judged_sc[(c, int(sc))] = at
        elif job.job_name == "rejudge":
            failed.append((at, ids))

    def since(c: int) -> str:
        base = judged_all.get(c, "")
        per_sc = [max(base, judged_sc.get((c, s), "")) for s in prev_scenarios] or [base]
        return min(per_sc) or str(first_run)

    floor = min((since(c) for c in region_ids), default=str(first_run))
    rows = list(
        session.execute(
            select(
                ChangeEvent.complex_id, ChangeEvent.entity, ChangeEvent.entity_id, ChangeEvent.detected_at
            ).where(
                ChangeEvent.triggers_rejudge.is_(True),
                ChangeEvent.detected_at > floor,
            )
        )
    )
    out: set[int] = set()
    region_level = [
        str(at)
        for (c, e, eid, at) in rows
        if c is None and ((e == "region" and eid == snap.region_id) or e == "judge")
    ]  # R3 8차 m8: 판정기 버전 변경(entity 'judge', 단지·지역 없음)은 모든 지역의 모든 단지
    for c in region_ids:
        t = since(c)
        if any(at > t for at in region_level):
            out.add(c)
    for c, _e, _i, at in rows:
        if c is not None and c in region_ids and str(at) > since(int(c)):
            out.add(int(c))
    for at, ids in failed:
        out |= {c for c in ids if at > since(c)}
    return sorted(out)


def _after_daily(
    ctx: SchedulerContext,
    snapshot_id: int,
    rejudge_ids: list[int],
    event_ids: list[int],
    *,
    job_id: int | None = None,
) -> dict[str, Any]:
    """변경 단지만 rejudge. 변경이 없으면(T8) 이전 publish 스냅샷의 판정·점수를 복사하고 publish — 판정기 호출 0."""
    with ctx.session_factory() as session:
        snap = session.get(Snapshot, snapshot_id)
        assert snap is not None
        has_runs = session.scalar(
            select(func.count()).select_from(ScoreRun).where(ScoreRun.snapshot_id == snapshot_id)
        )
        first = not has_runs and snapshots.previous(session, snap, published_only=True) is None
        if rejudge_ids and not first:
            job = enqueue_rejudge(
                session, snapshot_id, rejudge_ids, f"변경 감지 {len(rejudge_ids)}단지",
                change_event_ids=event_ids, now=ctx.now(),
            )  # fmt: skip
            session.commit()
            return {"rejudge_job_id": job.id}
        if snap.status == "published" or has_runs:
            return {"carry_forward": "이미 판정됨"}
        prev = snapshots.previous(session, snap, published_only=True)
        if prev is None:  # 첫 판정: 변경·미분류 접수 단지만이 아니라 전부(복사할 이전 판정이 없다)
            job = enqueue_rejudge(
                session, snapshot_id, None, "이전 publish 스냅샷 없음 — 전체 판정",
                change_event_ids=event_ids or None, now=ctx.now(),
            )  # fmt: skip
            session.commit()
            return {"rejudge_job_id": job.id}
        stale = changed_after_runs(session, prev)
        if stale:
            # D12-5(R3 4차 M-3): 이전 판정 뒤 사실이 바뀐 단지(사람 확인·강등·생활권 편집 등 — triggers_rejudge)가 있으면
            # 옛 점수를 created_at=now 로 복사하지 않고 그 단지를 재판정한다(나머지는 rejudge 파이프라인이 복사)
            job = enqueue_rejudge(
                session, snapshot_id, stale, f"이전 판정 뒤 사실 변경 {len(stale)}단지 — 이월 대신 재판정",
                change_event_ids=event_ids or None, now=ctx.now(),
            )  # fmt: skip
            session.commit()
            return {"rejudge_job_id": job.id, "carry_forward": "사실 변경 — 재판정"}
        copied = carry_forward(session, prev.id, snapshot_id, created_at=ctx.iso_now())
        snap.status = "ready"
        session.commit()
        return {
            "carry_forward": {"from_snapshot_id": prev.id, **copied},
            **publish_or_retry(ctx, session, snapshot_id, job_id=job_id),
        }


def handle_collect_daily(ctx: SchedulerContext, job: JobRun) -> dict[str, Any]:
    p = job.payload or {}
    region_id = int(p["region_id"])
    with ctx.session_factory() as session:
        since = _since(session, region_id, "collect.daily", job.id)
    res = collect(
        ctx, region_id, p.get("sources") or list(DAILY_SOURCES), asof_date=p.get("asof_date"), since=since
    )
    stats = res.stats()
    stats.update(
        _after_daily(ctx, res.snapshot_id, res.rejudge_complex_ids, res.change_event_ids, job_id=job.id)
    )
    stats["notify"] = _notify(ctx, res.change_event_ids)
    if res.errors:
        raise JobError(f"수집 단계 오류: {', '.join(sorted(res.errors))}", stats)
    return stats


def handle_collect_weekly(ctx: SchedulerContext, job: JobRun) -> dict[str, Any]:
    p = job.payload or {}
    region_id = int(p["region_id"])
    with ctx.session_factory() as session:
        since = _since(session, region_id, "collect.weekly", job.id)
    res = collect(
        ctx, region_id, p.get("sources") or list(WEEKLY_SOURCES), asof_date=p.get("asof_date"), since=since
    )
    stats = res.stats()
    if res.change_event_ids:
        with ctx.session_factory() as session:
            snap = session.get(Snapshot, res.snapshot_id)
            has_runs = session.scalar(
                select(func.count()).select_from(ScoreRun).where(ScoreRun.snapshot_id == res.snapshot_id)
            )
            if snap is not None and (has_runs or snapshots.previous(session, snap, published_only=True)):
                rj = enqueue_rejudge(
                    session, res.snapshot_id, [], "주간 시장 자료 변경 — 점수 재계산",
                    change_event_ids=res.change_event_ids, now=ctx.now(),
                )  # fmt: skip
                session.commit()
                stats["rejudge_job_id"] = rj.id
    if "rejudge_job_id" not in stats:
        done = _finish_unchanged_revision(ctx, res.snapshot_id, job_id=job.id)
        if done is not None:
            stats["carry_forward"] = done
    if res.errors:
        raise JobError(f"수집 단계 오류: {', '.join(sorted(res.errors))}", stats)
    return stats


def _discard_empty_revision(session: Any, snap: Snapshot) -> bool:
    """D13-4: 변경 없는 주간 수집이 발행된 기준일에 만든 빈 리비전(수집 재시작 '같은 기준일 재수집' — 이벤트·점수·판정·잡 없음)은
    지운다(직전 발행 리비전 유지, 같은 내용 리비전을 다시 발행하지 않는다). 복사된 접수 행·조립한 벤치마크만 같이 지운다."""
    from sqlalchemy import delete

    from app.models import (
        Benchmark,
        Claim,
        ComparableSet,
        FactDemotion,
        IntakeStatus,
        JudgmentLog,
        Ladder,
        SnapshotView,
        SnapshotViewUnit,
    )

    sid = snap.id
    if snap.revision_reason != "같은 기준일 재수집":
        return False
    for model in (
        ScoreRun,
        Ladder,
        Claim,
        JudgmentLog,
        ChangeEvent,
        FactDemotion,
        ComparableSet,
        SnapshotView,
        SnapshotViewUnit,
    ):
        m: Any = model
        if session.scalar(select(func.count()).select_from(m).where(m.snapshot_id == sid)):
            return False
    if session.scalars(select(Snapshot.id).where(Snapshot.revision_of == sid).limit(1)).first() is not None:
        return False
    for job in session.scalars(
        select(JobRun).where(JobRun.job_name.in_(("rejudge", "snapshot.publish", "report")))
    ):
        if (job.payload or {}).get("snapshot_id") == sid:
            return False
    session.execute(delete(IntakeStatus).where(IntakeStatus.snapshot_id == sid))
    session.execute(delete(Benchmark).where(Benchmark.snapshot_id == sid))
    session.delete(snap)
    session.flush()
    return True


def _finish_unchanged_revision(
    ctx: SchedulerContext, snapshot_id: int, *, job_id: int | None = None
) -> dict[str, Any] | None:
    """변경 없는 주간 수집 뒤의 리비전 정리(R3 4차 minor · **D13-4**).

    - 이 수집이 발행된 기준일에 만든 빈 리비전 → 지운다(새 리비전 없음 — 직전 발행 리비전 유지).
    - 그 밖의 판정 전 리비전(사람 확인·강등이 만든 리비전 등): 바탕 발행 리비전 실행 뒤 사실 변경·실패한 rejudge·이 리비전에
      붙은 변경이 있으면 이월하지 않고 그 단지 재판정 잡을 등록한다(옛 점수를 now 로 발행하지 않는다, R3 5차 M2). 없을 때만
      바탕 리비전 파생 행을 복사해 발행한다(판정기 호출 0).
    대기·실행 중인 잡이 그 스냅샷을 쓰거나 이미 점수 실행이 있으면 그대로 둔다."""
    with ctx.session_factory() as session:
        snap = session.get(Snapshot, snapshot_id)
        if (
            snap is None
            or snap.status != "building"
            or int(snap.revision or 1) <= 1
            or snap.revision_of is None
        ):
            return None
        if session.scalar(
            select(func.count()).select_from(ScoreRun).where(ScoreRun.snapshot_id == snapshot_id)
        ):
            return None
        for job in session.scalars(select(JobRun).where(JobRun.status.in_(("queued", "running")))):
            if (job.payload or {}).get("snapshot_id") == snapshot_id:
                return None
        base = session.get(Snapshot, snap.revision_of)
        if base is None or base.status != "published":
            return None
        if _discard_empty_revision(session, snap):
            session.commit()
            return {"discarded_revision": snapshot_id, "kept": base.id}
        stale = changed_after_runs(session, base)
        if stale:
            job = enqueue_rejudge(
                session, snapshot_id, stale, f"이전 판정 뒤 사실 변경·실패한 재판정 {len(stale)}단지 — 이월 대신 재판정",
                now=ctx.now(),
            )  # fmt: skip
            session.commit()
            return {"rejudge_job_id": job.id, "stale": stale}
        copied = carry_forward(session, base.id, snapshot_id, created_at=ctx.iso_now())
        snap.status = "ready"
        session.commit()
        return {
            "from_snapshot_id": base.id,
            **copied,
            **publish_or_retry(ctx, session, snapshot_id, job_id=job_id),
        }


def handle_snapshot_publish(ctx: SchedulerContext, job: JobRun) -> dict[str, Any]:
    """발행(D14-5 — 저장본 materialize 는 이 잡에서만): 계산 → 나눠 쓰기 → 짧은 전환. ``carry_from_snapshot_id`` 면 그 발행
    리비전의 파생 행을 먼저 복사한다(호재 연결 PATCH — 판정기 호출 없음). stats 에 저장본 통계(출처 누락 건수 등, D14-8).

    D15-6: 리비전마다 발행은 하나만(임대 보유자 = 이 잡) — 다른 발행이 하고 있으면 failed ``publish_in_progress``(아무것도
    지우지 않는다). ``follow_up``(후속 발행 잡) = 발행 계산 중에 들어온 쓰기 — ``_follow_up`` 참고."""
    p = job.payload or {}
    if p.get("follow_up"):
        return _follow_up(ctx, job, int(p["snapshot_id"]))
    sid = int(p["snapshot_id"])
    carry = p.get("carry_from_snapshot_id")
    with ctx.session_factory() as session:
        stats: dict[str, Any] = {"snapshot_id": sid}
        t_carry = time.perf_counter()
        if carry is not None and session.get_bind().dialect.name == "sqlite":
            # 복사(쓰기)할 트랜잭션은 쓰기 잠금부터 잡는다 — 먼저 읽고 나중에 쓰면 그 사이 API 쓰기가 커밋됐을 때 WAL 이 읽기
            # 스냅샷을 쓰기로 올리지 못해 즉시 'database is locked'(R3 6차 m15 와 같은 원인, D14-5 부하 측정에서 재현)
            from app.scheduler.rejudge import _sqlite_write_lock

            _sqlite_write_lock(session)
        snap = session.get(Snapshot, sid)
        if carry is not None and snap is not None and snap.status == "building":
            has_runs = session.scalar(
                select(func.count()).select_from(ScoreRun).where(ScoreRun.snapshot_id == sid)
            )
            if not has_runs:
                stats["carry_forward"] = {"from_snapshot_id": int(carry), **carry_forward(
                    session, int(carry), sid, created_at=ctx.iso_now()
                )}  # fmt: skip
                snap.status = "ready"
            session.commit()
            stats["carry_lock_s"] = round(
                time.perf_counter() - t_carry, 3
            )  # 복사 트랜잭션(쓰기 잠금) 시간 — D14-5
        _publish_or_raise(ctx, session, sid, stats, holder=f"job:{job.id}", job=job)
    return stats


PUBLISH_REQUEUE_MAX: Final = 40
"""D16-3: 발행 임대가 바쁠 때 지연 재큐잉 상한(대기 2·4·8·16·30·30… 초 — 합 약 18분, 임대 TTL 15분보다 길다). 넘으면 failed
``publish_in_progress``."""
PUBLISH_REQUEUE_CAP_S: Final = 30.0


def requeue_delay(count: int) -> float:
    """n 번째 재큐잉(0부터)의 대기 초 — 짧은 지수 backoff, 상한 ``PUBLISH_REQUEUE_CAP_S``."""
    return float(min(2 ** (count + 1), PUBLISH_REQUEUE_CAP_S))


def _publish_or_raise(
    ctx: SchedulerContext,
    session: Any,
    sid: int,
    stats: dict[str, Any],
    *,
    holder: str,
    job: JobRun | None = None,
) -> None:
    ok, n, mstats = snapshots.publish_with_stats(session, sid, now=ctx.iso_now(), holder=holder)
    snap = session.get(Snapshot, sid)
    session.commit()
    stats.update({"published": ok, "contradicted": n, **mstats})
    if holder.startswith("job:"):
        stats["publish_job_id"] = int(holder[4:])  # 계약 .12: 발행하는 잡 = 이 잡
    if not ok:
        if mstats.get("publish_in_progress"):
            why = f"publish_in_progress: 같은 리비전을 {mstats['publish_in_progress']} 가 발행 중"
            # D16-3(R3 8차 N-M3): 바쁘면 실패가 아니라 지연 재큐잉 — 먼저 돈 발행이 끝난 뒤 이 잡이 다시 돌아 (후속 잡이면) 그
            # 발행이 못 읽은 변경을 새 리비전으로 이어 발행한다. 상한을 넘으면 failed(무한 대기 없음)
            count = int(((job.stats if job is not None else None) or {}).get("requeue_count") or 0)
            if job is not None and count < PUBLISH_REQUEUE_MAX:
                raise JobRequeue(why, requeue_delay(count), stats)
            raise JobError(why, stats)
        why = f"publish_blocked: contradicted {n}건" if n else "publish_blocked: degraded(점수 미계산)"
        if snap is not None and snap.status == "building" and not snap.degraded:
            why = "publish_blocked: 판정·점수 미완료"
        raise JobError(why, stats)


def _follow_up(ctx: SchedulerContext, job: JobRun, target: int) -> dict[str, Any]:
    """후속 발행 잡(D15-6·R3 7차 M5): 판정 중·발행 계산 중인 리비전에 들어온 판정 무관 쓰기(호재 연결). 이 잡이 아직 queued
    로 돌았다는 것은 그 뒤 어떤 발행 계산도 이 잡(= 그 쓰기)을 읽지 못했다는 뜻이다(읽었으면 전환이 '포함됨'으로 닫는다).

    - 지역의 가장 새 리비전이 발행됨 → 그 리비전 위 새 리비전에 파생 행을 복사해 지금 발행(이 계산은 쓰기 뒤에 읽는다)
    - 가장 새 리비전이 ready(발행 대기) → 지금 그 리비전을 발행(계산이 쓰기를 읽는다)
    - building·degraded(판정 중·판정기 장애) → 그 리비전의 발행이 나중에 계산하며 쓰기를 읽는다 — 미룸(done, ``deferred_to``)"""
    from app.scheduler.rejudge import _sqlite_write_lock

    stats: dict[str, Any] = {"follow_up": True, "requested_snapshot_id": target}
    with ctx.session_factory() as session:
        base = session.get(Snapshot, target)
        if base is None:
            raise JobError(f"snapshot {target} 없음", stats)
        if session.get_bind().dialect.name == "sqlite":
            _sqlite_write_lock(session)
        newest = snapshots.latest_for_region(session, base.region_id)
        assert newest is not None
        if newest.status == "published":
            rev = snapshots.new_revision(
                session,
                newest,
                reason=f"후속 발행(잡 {job.id}: 발행 계산 중 들어온 변경)",
                created_at=ctx.iso_now(),
            )
            stats["carry_forward"] = {"from_snapshot_id": newest.id, **carry_forward(
                session, newest.id, rev.id, created_at=ctx.iso_now()
            )}  # fmt: skip
            rev.status = "ready"
            sid = rev.id
            session.commit()
        elif newest.status == "ready" and not newest.degraded:
            sid = newest.id
            session.commit()
        else:
            session.commit()
            stats.update({"published": False, "deferred_to": newest.id, "publish_job_id": None})
            return stats
        stats["snapshot_id"] = sid
        _publish_or_raise(ctx, session, sid, stats, holder=f"job:{job.id}", job=job)
    return stats


def publish_or_retry(
    ctx: SchedulerContext, session: Any, sid: int, *, job_id: int | None = None
) -> dict[str, Any]:
    """발행 경로(daily 이월·주간 마감·지역 확장·bootstrap) 공용(D15-6·R3 7차 m13): 발행이 예외로 실패하면 수집·판정 결과는
    그대로 두고 ``snapshot.publish`` 재시도 잡을 남긴다(stats ``publish_retry_job_id``). contradicted·degraded 로 막힌 것은
    실패가 아니다(``published`` False 그대로).

    계약 .12(FE6 요청): stats ``publish_job_id`` = 발행을 하는(한) 잡 — 이 잡이 그 자리에서 발행했으면 이 잡(``job_id``),
    실패해 재시도 잡을 남겼으면 그 재시도 잡(``publish_retry_job_id`` 와 같음). 화면은 이 id 를 따라가면 발행 완료를 안다."""
    holder = f"job:{job_id}" if job_id is not None else None  # D16-3·m5: 그 자리 발행도 임대 보유자 = 이 잡
    try:
        ok, n, mstats = snapshots.publish_with_stats(session, sid, now=ctx.iso_now(), holder=holder)
        session.commit()
    except Exception as exc:
        session.rollback()
        from app.scheduler.jobs import enqueue

        retry = enqueue(session, "snapshot.publish", {"snapshot_id": sid}, now=ctx.now())
        session.commit()
        log.error("worker.publish_failed", extra={"snapshot_id": sid, "error": type(exc).__name__})
        return {
            "published": False,
            "publish_error": type(exc).__name__,
            "publish_retry_job_id": retry.id,
            "publish_job_id": retry.id,
        }
    out: dict[str, Any] = {"published": ok, "contradicted": n, "publish_job_id": job_id}
    if mstats.get("publish_in_progress"):
        # D16-3: 다른 발행이 같은 리비전을 들고 있다 — 그 자리에서 실패로 끝내지 않고 snapshot.publish 잡을 남긴다(그 잡이
        # 지연 재큐잉으로 기다렸다 발행하거나, 먼저 돈 발행이 끝냈으면 '이미 발행됨'으로 닫는다). 화면은 publish_job_id 를 따라간다
        from app.scheduler.jobs import enqueue

        retry = enqueue(session, "snapshot.publish", {"snapshot_id": sid}, now=ctx.now())
        session.commit()
        out.update(
            publish_in_progress=mstats["publish_in_progress"],
            publish_retry_job_id=retry.id,
            publish_job_id=retry.id,
        )
    return out


def handle_reference_refresh(ctx: SchedulerContext, job: JobRun) -> dict[str, Any]:
    return {"reference": ctx.reference_refresh(ctx.today())}


def handle_region_bootstrap(ctx: SchedulerContext, job: JobRun) -> dict[str, Any]:
    from app.scheduler.pipeline import run_pipeline

    region_id = int((job.payload or {})["region_id"])
    with ctx.session_factory() as session:
        region = session.get(Region, region_id)
        if region is None:
            raise JobError(f"region {region_id} 없음")
        region.status = "bootstrapping"
        session.commit()
    try:
        daily = collect(ctx, region_id, [*DAILY_SOURCES, "notice_pdf"], detect_list=False)
        weekly = collect(ctx, region_id, list(WEEKLY_SOURCES), detect_list=False)
        result = run_pipeline(ctx, daily.snapshot_id, complex_ids=None, reason="region.bootstrap")
        stats: dict[str, Any] = {
            "region_id": region_id,
            "snapshot_id": daily.snapshot_id,
            "asof_date": daily.asof_date,
            "daily": daily.stats(),
            "weekly": weekly.stats(),
            "pipeline": result.stats(),
            "degraded": result.degraded,
            # 판정 호출·캐시 집계를 최상위에도(/ops/judgments cached_hits 가 잡 stats 최상위를 읽는다, R3 m23)
            "judge_calls": result.judge_calls,
            "cached": result.cached,
            "cached_by_tool": dict(result.cached_by_tool),
        }
        if daily.list_complex_ids is not None:
            stats["list_complex_ids"] = daily.list_complex_ids
        with ctx.session_factory() as session:
            if not result.degraded:
                # 수집·판정은 끝났다 — 발행이 실패해도 지역은 ready, 발행은 snapshot.publish 재시도 잡(m19·m13)
                stats.update(publish_or_retry(ctx, session, result.snapshot_id, job_id=job.id))
            region = session.get(Region, region_id)
            assert region is not None
            region.status = "ready"
            session.commit()
        errors = {**daily.errors, **weekly.errors}
        if errors:
            stats["errors"] = errors
        return stats
    except Exception:
        with ctx.session_factory() as session:
            region = session.get(Region, region_id)
            if region is not None:
                region.status = "failed"
                session.commit()
        raise


def handle_report(ctx: SchedulerContext, job: JobRun) -> dict[str, Any]:
    """WP8 잡 규약(app/reports/README.md '잡 규약'): ``run_report_job(payload, session=…)`` → stats.

    ReportBlocked → failed ``blocked: <사유>`` + stats.blocked_reason, ReportNotFound → ``not_found: <사유>``,
    ValueError(payload 검증) → ``invalid_payload: …``.
    """
    from app.reports import job as report_job
    from app.reports.errors import ReportBlocked, ReportNotFound
    from app.snapshot_view import MaterializePending, NotInRevision

    try:
        with ctx.session_factory() as session:
            stats = report_job.run_report_job(dict(job.payload or {}), session=session, job_id=job.id)
            session.commit()
    except ReportBlocked as exc:
        raise JobError(f"blocked: {exc.reason}", {"blocked_reason": exc.reason}) from exc
    except ReportNotFound as exc:
        raise JobError(f"not_found: {exc.reason}") from exc
    except NotInRevision as exc:  # D14-3: 대상 리비전에 그 시나리오 저장본 없음(POST 는 422 로 먼저 거른다)
        raise JobError(f"scenario_not_in_revision: {str(exc)[:300]}") from exc
    except MaterializePending as exc:
        raise JobError(f"materialize_pending: {str(exc)[:300]}") from exc
    except ValueError as exc:
        raise JobError(f"invalid_payload: {str(exc)[:300]}") from exc
    return dict(stats)


def handle_backup(ctx: SchedulerContext, job: JobRun) -> dict[str, Any]:
    """D11-8 백업(``scheduler.backup.run_backup``): DB 덤프·파일 복사 + 원문 증분 복사. 실패는 stats 와 함께 failed."""
    from app.core.settings import get_settings
    from app.scheduler.backup import run_backup

    keep = (job.payload or {}).get("keep_days")
    try:
        return run_backup(get_settings(), now=ctx.now(), keep_days=int(keep) if keep else None)
    except RuntimeError as exc:
        raise JobError(str(exc)[:300], getattr(exc, "stats", {})) from exc


def handle_region_expand(ctx: SchedulerContext, job: JobRun) -> dict[str, Any]:
    """D11-7 지역 선택 확장(PATCH /regions/{id}): 단지 법정동·생활권 재배정 → 추가 선택 포함 수집(daily+weekly) →
    기준일 리비전(발행됐으면 새 리비전, 사유 '지역 확장') → 후보 전체 판정·rerank 1회 → publish. 보고서는 바탕 리비전 비교로
    §12 '지역 추가' 장을 만든다(``reports.export`` — revision_of)."""
    from app.normalize.living_area import assign_complex_area
    from app.scheduler.pipeline import run_pipeline

    p = job.payload or {}
    region_id = int(p["region_id"])
    asof = ctx.today().isoformat()
    added = ", ".join(str(s.get("full_name")) for s in p.get("added") or []) or "-"
    reason = f"지역 확장: 추가 {added}"[:200]
    with ctx.session_factory() as session:
        region = session.get(Region, region_id)
        if region is None:
            raise JobError(f"region {region_id} 없음")
        moved = 0
        for cx in session.scalars(select(Complex).where(Complex.region_id == region_id)):
            before = (cx.legal_dong_code, cx.living_area, cx.inclusion_class)
            res = assign_complex_area(session, cx)
            if res.in_region and cx.inclusion_class == "범위 경계":
                cx.inclusion_class = (
                    "미분류"  # 범위 밖이던 단지가 확장으로 들어왔다 — 포함 분류는 다음 P4 classify
                )
            if (cx.legal_dong_code, cx.living_area, cx.inclusion_class) != before:
                moved += 1
        today = snapshots.latest_revision(session, region_id, asof)
        if today is not None and today.status == "published":
            snapshots.new_revision(session, today, reason=reason, created_at=ctx.iso_now())
        else:
            # 오늘 스냅샷이 없거나 미발행(리비전 1 building — R3 4차 M-5): 직전 발행 스냅샷을 비교 기준으로 달아 §12
            # '지역 추가' 장이 빠지지 않게(이전에는 최신이 building 이면 비교 기준 없음)
            row = today or snapshots.get_or_create(session, region_id, asof, created_at=ctx.iso_now())
            snapshots.mark_compare_base(session, row, reason)
        session.commit()
    daily = collect(ctx, region_id, [*DAILY_SOURCES, "notice_pdf"], asof_date=asof, detect_list=False)
    weekly = collect(ctx, region_id, list(WEEKLY_SOURCES), asof_date=asof, detect_list=False)
    result = run_pipeline(ctx, daily.snapshot_id, complex_ids=None, reason=reason)
    stats: dict[str, Any] = {
        "region_id": region_id,
        "snapshot_id": result.snapshot_id,
        "complexes_reassigned": moved,
        "daily": daily.stats(),
        "weekly": weekly.stats(),
        "pipeline": result.stats(),
        "degraded": result.degraded,
    }
    if result.degraded:
        raise JobError("judge_unavailable: 판정기 연결 실패 — degraded 모드", stats)
    with ctx.session_factory() as session:
        stats.update(publish_or_retry(ctx, session, result.snapshot_id, job_id=job.id))
    return stats


HANDLERS: Final[dict[str, Handler]] = {
    "collect.daily": handle_collect_daily,
    "collect.weekly": handle_collect_weekly,
    "rejudge": handle_rejudge,
    "snapshot.publish": handle_snapshot_publish,
    "reference.refresh": handle_reference_refresh,
    "region.bootstrap": handle_region_bootstrap,
    "report": handle_report,
    "claim.reverify": handle_claim_reverify,  # 계약 2026-10-09.4 (R3 M8, reverify.py)
    "backup": handle_backup,  # 계약 2026-10-09.8 (D11-8, backup.py)
    "region.expand": handle_region_expand,  # 계약 2026-10-09.8 (D11-7)
}

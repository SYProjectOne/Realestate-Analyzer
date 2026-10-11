"""스냅샷 행 다루기 (RA §3 스냅샷 규칙, ADR-8): 만들기·이전 찾기·publish·DTO 변환.

publish 는 남은 contradicted 0 검사 — 보고서 생성 거부와 같은 정의(``judge.claims.remaining_contradicted``).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.contracts_gen import Region as RegionDTO
from app.core.contracts_gen import Snapshot as SnapshotDTO
from app.judge.claims import remaining_contradicted
from app.models import JobRun, Region, Snapshot

__all__ = [
    "contradicted_count",
    "get_or_create",
    "latest_for_region",
    "mark_compare_base",
    "previous",
    "publish",
    "publish_with_stats",
    "region_dto",
    "republish",
    "snapshot_dto",
]


def latest_revision(session: Session, region_id: int, asof_date: str) -> Snapshot | None:
    """(지역, 기준일)의 가장 큰 리비전."""
    return session.scalars(
        select(Snapshot)
        .where(Snapshot.region_id == region_id, Snapshot.asof_date == asof_date)
        .order_by(Snapshot.revision.desc(), Snapshot.id.desc())
        .limit(1)
    ).first()


def get_or_create(session: Session, region_id: int, asof_date: str, *, created_at: str) -> Snapshot:
    """수집이 쓸 (지역, 기준일) 스냅샷: 가장 큰 리비전, 없으면 리비전 1(building). 가장 큰 리비전이 발행됐으면
    새 리비전(D11-1 — 발행 스냅샷의 접수 행·벤치마크·변경 이벤트를 고치지 않는다)."""
    row = latest_revision(session, region_id, asof_date)
    if row is not None:
        if row.status == "published":
            return new_revision(session, row, reason="같은 기준일 재수집", created_at=created_at)
        return row
    row = Snapshot(
        region_id=region_id, asof_date=asof_date, status="building", degraded=False, created_at=created_at,
        revision=1,
    )  # fmt: skip
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError:  # 다른 worker 가 먼저 만들었다
        found = latest_revision(session, region_id, asof_date)
        if found is None:
            raise
        return found
    return row


def new_revision(session: Session, base: Snapshot, *, reason: str, created_at: str) -> Snapshot:
    """발행 스냅샷 ``base`` 와 같은 기준일의 새 리비전(building)을 만든다(D11-1). 이미 그 기준일에 미발행 리비전이 있으면 그것.

    입력 행만 옮긴다: 접수 상태 행(``persist.copy_intake`` — 같은 확인 시각). 파생 행(사다리·주장·점수·비교군)은
    파이프라인이
    바탕 리비전(``previous``)에서 재판정 대상이 아닌 단지만 복사하고 대상은 새로 판정한다 — 발행 리비전은 건드리지
    않는다.
    벤치마크는 ``api.benchmarks.benchmarks_for`` 가 리비전 자기 행이 없으면 앞선 조립분을 쓴다."""
    latest = latest_revision(session, base.region_id, base.asof_date) or base
    if latest.status != "published":
        return latest
    row = Snapshot(
        region_id=base.region_id,
        asof_date=base.asof_date,
        status="building",
        degraded=False,
        created_at=created_at,
        revision=int(latest.revision or 1) + 1,
        revision_of=latest.id,
        revision_reason=(reason or "재판정")[:200],
    )
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError:  # 다른 worker 가 먼저 만들었다
        found = latest_revision(session, base.region_id, base.asof_date)
        if found is None or found.status == "published":
            raise
        return found
    from app.scheduler.persist import copy_intake

    copy_intake(session, latest.id, row.id)
    session.flush()
    return row


def writable(session: Session, snapshot_id: int, *, reason: str, created_at: str) -> Snapshot:
    """재판정이 쓸 스냅샷: 그 기준일의 가장 큰 리비전이 발행 전이면 그것, 발행됐으면 새 리비전(D11-1·M-2)."""
    snap = session.get(Snapshot, snapshot_id)
    if snap is None:
        raise LookupError(f"snapshot {snapshot_id} 없음")
    latest = latest_revision(session, snap.region_id, snap.asof_date) or snap
    if latest.status != "published":
        return latest
    return new_revision(session, latest, reason=reason, created_at=created_at)


def _order_key(s: Snapshot) -> tuple[str, int, int]:
    return (s.asof_date, int(s.revision or 1), s.id)


def previous(session: Session, snap: Snapshot, *, published_only: bool = False) -> Snapshot | None:
    """같은 지역에서 (기준일, 리비전)이 더 앞선 스냅샷 중 가장 최근 — 같은 기준일의 앞 리비전도 포함(D11-1)."""
    stmt = select(Snapshot).where(Snapshot.region_id == snap.region_id, Snapshot.asof_date <= snap.asof_date)
    if published_only:
        stmt = stmt.where(Snapshot.status == "published")
    me = _order_key(snap)
    cands = [s for s in session.scalars(stmt) if s.id != snap.id and _order_key(s) < me]
    return max(cands, key=_order_key, default=None)


def mark_compare_base(session: Session, snap: Snapshot, reason: str) -> Snapshot | None:
    """판정 전(미발행) 스냅샷에 비교 기준이 없으면 직전 발행 스냅샷을 ``revision_of`` 로 단다(R3 4차 M-5·M-6).

    지역 확장·판정기 버전 변경이 **미발행 리비전 1**(새 리비전을 만들 필요가 없는 경우)에 걸려도 보고서 기본 비교
    (``reports.export.default_compare`` — revision_of)가 생겨 §12 '지역 추가' 장·delta 표가 빠지지 않는다. 이미
    비교 기준이 있거나 발행됐으면 그대로. 반환 = 비교 기준(없으면 None)."""
    if snap.status == "published":
        return None
    if snap.revision_of is None:
        prev = previous(session, snap, published_only=True)
        if prev is None:
            return None
        snap.revision_of = prev.id
    if not snap.revision_reason:
        snap.revision_reason = reason[:200]
    session.flush()
    return session.get(Snapshot, snap.revision_of) if snap.revision_of is not None else None


def republish(session: Session, region_id: int, *, reason: str, created_at: str) -> JobRun | None:
    """판정·점수에 쓰지 않는 리비전 값(호재 연결 — D12-4)만 바뀌었을 때: 판정기 호출·점수 재계산 없이 가장 새 발행
    리비전의 새 리비전(building)을 만들고 ``snapshot.publish`` 잡(``carry_from_snapshot_id``)을 등록한다 — worker 가 파생 행을
    복사하고 발행한다(D14-5: API 요청 안에서 발행하지 않는다, 계약 .11). 반환 = 그 잡(API 202 + job_id).

    D15-6(R3 7차 M5): 가장 새 리비전이 발행 전(판정 중·발행 계산 중)이면 **후속 발행 잡**(``follow_up``)을 늘 등록한다 —
    그 리비전의 발행 계산이 이 쓰기를 읽었으면(계산이 읽은 시점에 이 잡이 보였으면) 전환 트랜잭션이 잡을 '포함됨'으로
    닫고, 못 읽었으면 잡이 남아 새 리비전으로 이어 발행한다. 그래서 응답은 늘 job_id 를 준다. 후속 잡은 합치지 않는다
    (합치면 계산이 이미 본 잡에 나중 쓰기가 실려 빠질 수 있다)."""
    newest = latest_for_region(session, region_id)
    if newest is None:
        return None
    from app.scheduler.jobs import enqueue

    if newest.status != "published":
        return enqueue(
            session,
            "snapshot.publish",
            {"snapshot_id": newest.id, "follow_up": True},
            kind="manual",
            dedupe=False,
        )
    rev = new_revision(session, newest, reason=reason, created_at=created_at)
    if rev.id == newest.id:  # pragma: no cover - new_revision 은 발행 리비전이면 늘 새 행
        return None
    return enqueue(
        session,
        "snapshot.publish",
        {"snapshot_id": rev.id, "carry_from_snapshot_id": newest.id},
        kind="manual",
    )


def latest_for_region(session: Session, region_id: int) -> Snapshot | None:
    stmt = (
        select(Snapshot)
        .where(Snapshot.region_id == region_id)
        .order_by(Snapshot.asof_date.desc(), Snapshot.revision.desc(), Snapshot.id.desc())
        .limit(1)
    )
    return session.scalars(stmt).first()


def contradicted_count(session: Session, snapshot_id: int) -> int:
    """남은 contradicted 수 — 분할 자식 없는 contradicted(``judge.claims.remaining_contradicted``)."""
    return len(remaining_contradicted(session, snapshot_id))


def publish(session: Session, snapshot_id: int, *, now: str, holder: str | None = None) -> tuple[bool, int]:
    """contradicted claim 이 0개면 발행. 반환 (published 여부, contradicted 수). ``publish_with_stats`` 참고."""
    ok, n, _stats = publish_with_stats(session, snapshot_id, now=now, holder=holder)
    return ok, n


def publish_with_stats(
    session: Session, snapshot_id: int, *, now: str, holder: str | None = None
) -> tuple[bool, int, dict[str, Any]]:
    """**worker 전용**(D14-5). degraded(점수 미계산)·building(판정 전)·contradicted 남음이면 발행하지 않는다.

    발행 = ``app.snapshot_view.publish_revision``: 호출자 세션의 변경을 먼저 commit 하고(저장본 계산은 다른 연결의 읽기),
    계산(쓰기 잠금 없음) → 저장본 나눠 쓰기 → 짧은 published 전환. 끝날 때까지 이전 발행 리비전이 기본 화면이다.
    반환 stats = 저장본 잡 통계(행·바이트·출처 누락 건수·쓰기 잠금 최대 시간 등, D14-8). 같은 리비전을 다른 발행이 하고
    있으면(single-flight, D15-6) 아무것도 쓰지 않고 stats ``publish_in_progress`` = 그 보유자."""
    snap = session.get(Snapshot, snapshot_id)
    if snap is None:
        raise LookupError(f"snapshot {snapshot_id} 없음")
    n = contradicted_count(session, snapshot_id)
    if n > 0 or snap.degraded or snap.status == "building":
        return False, n, {}
    if snap.status == "published":
        return True, 0, {}
    session.commit()
    from app.snapshot_view import publish_revision

    res = publish_revision(session.get_bind(), snapshot_id, now=now, holder=holder)
    session.expire_all()
    stats = dict(res.stats)
    if res.busy:
        stats["publish_in_progress"] = stats.pop("holder", None) or "?"
    return res.published, res.contradicted, stats


def _plain(value: Any) -> Any:
    return value if value is not None else []


_AREA_KEYS = ("id", "name", "legal_dong_codes", "legal_dongs", "households", "supply_ref_units")


def _areas(value: Any) -> list[dict[str, Any]]:
    """저장 json 의 생활권 → LivingArea 모양(households 는 필수 키, 없으면 null)."""
    out: list[dict[str, Any]] = []
    for a in value or []:
        item = {k: a.get(k) for k in _AREA_KEYS if k in a}
        item.setdefault("households", None)
        out.append(item)
    return out


def region_dto(row: Region) -> RegionDTO:
    return RegionDTO.model_validate(
        {
            "id": row.id,
            "name": row.name,
            "query_text": row.query_text,
            "selections": _plain(row.selections),
            "sido_codes": _plain(row.sido_codes),
            "sigungu_codes": _plain(row.sigungu_codes),
            "legal_dong_codes": _plain(row.legal_dong_codes),
            "living_areas": _areas(row.living_areas),
            "age_premium_coef": row.age_premium_coef
            or {"c_per_year": 0.015, "cap_years": 8, "label": "추정"},
            "supply_ref_pct": float(row.supply_ref_pct) if row.supply_ref_pct is not None else 0.08,
            "applyhome_query": row.applyhome_query or {},
            "status": row.status,
            "created_at": row.created_at,
        }
    )


def snapshot_dto(row: Snapshot) -> SnapshotDTO:
    return SnapshotDTO(
        id=row.id,
        region_id=row.region_id,
        asof_date=row.asof_date,
        revision=int(row.revision or 1),
        revision_of=row.revision_of,
        revision_reason=row.revision_reason,
        status=row.status,
        degraded=bool(row.degraded),
        created_at=row.created_at,
        published_at=row.published_at,
    )

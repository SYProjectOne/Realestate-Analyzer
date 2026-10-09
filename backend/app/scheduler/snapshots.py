"""스냅샷 행 다루기 (RA §3 스냅샷 규칙, ADR-8): 만들기·이전 찾기·publish(contradicted 0 검사)·DTO 변환."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.contracts_gen import Region as RegionDTO
from app.core.contracts_gen import Snapshot as SnapshotDTO
from app.models import Claim, Region, Snapshot

__all__ = [
    "contradicted_count",
    "get_or_create",
    "latest_for_region",
    "previous",
    "publish",
    "region_dto",
    "snapshot_dto",
]


def get_or_create(session: Session, region_id: int, asof_date: str, *, created_at: str) -> Snapshot:
    """(region_id, asof_date) 하루 1개. 없으면 building 으로 만든다."""
    stmt = select(Snapshot).where(Snapshot.region_id == region_id, Snapshot.asof_date == asof_date)
    row = session.scalars(stmt).first()
    if row is not None:
        return row
    row = Snapshot(
        region_id=region_id, asof_date=asof_date, status="building", degraded=False, created_at=created_at
    )
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError:  # 다른 worker 가 먼저 만들었다
        found = session.scalars(stmt).first()
        if found is None:
            raise
        return found
    return row


def previous(session: Session, snap: Snapshot, *, published_only: bool = False) -> Snapshot | None:
    """같은 지역에서 기준일이 더 이른 스냅샷 중 가장 최근."""
    stmt = select(Snapshot).where(Snapshot.region_id == snap.region_id, Snapshot.asof_date < snap.asof_date)
    if published_only:
        stmt = stmt.where(Snapshot.status == "published")
    return session.scalars(stmt.order_by(Snapshot.asof_date.desc()).limit(1)).first()


def latest_for_region(session: Session, region_id: int) -> Snapshot | None:
    stmt = (
        select(Snapshot).where(Snapshot.region_id == region_id).order_by(Snapshot.asof_date.desc()).limit(1)
    )
    return session.scalars(stmt).first()


def contradicted_count(session: Session, snapshot_id: int) -> int:
    stmt = (
        select(func.count())
        .select_from(Claim)
        .where(Claim.snapshot_id == snapshot_id, Claim.verify_status == "contradicted")
    )
    return int(session.scalar(stmt) or 0)


def publish(session: Session, snapshot_id: int, *, now: str) -> tuple[bool, int]:
    """contradicted claim 이 0개면 status=published. 반환 (published 여부, contradicted 수). commit 은 호출자.

    degraded 스냅샷(점수 미계산)·building(판정 전)은 publish 하지 않는다.
    """
    snap = session.get(Snapshot, snapshot_id)
    if snap is None:
        raise LookupError(f"snapshot {snapshot_id} 없음")
    n = contradicted_count(session, snapshot_id)
    if n > 0 or snap.degraded or snap.status == "building":
        return False, n
    if snap.status != "published":
        snap.status = "published"
        snap.published_at = now
        session.flush()
    return True, 0


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
        status=row.status,
        degraded=bool(row.degraded),
        created_at=row.created_at,
        published_at=row.published_at,
    )

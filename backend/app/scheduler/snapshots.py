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
from app.models import Region, Snapshot

__all__ = [
    "contradicted_count",
    "get_or_create",
    "latest_for_region",
    "mark_compare_base",
    "previous",
    "publish",
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


def republish(session: Session, region_id: int, *, reason: str, created_at: str) -> Snapshot | None:
    """판정·점수에 쓰지 않는 리비전 값(호재 연결 — D12-4)만 바뀌었을 때: 판정기 호출·점수 재계산 없이 가장 새 발행
    리비전의 새 리비전을 만들어 파생 행을 그대로 복사하고 바로 발행한다(발행 순간 새 값이 얼려진다).

    R3 4차 minor: 예전에는 연결이 바뀔 때마다 rejudge 잡(판정 파이프라인)을 등록했다. 판정 중인(미발행) 리비전이 있으면
    그 리비전이 발행될 때 새 값으로 얼려지므로 아무것도 하지 않는다(None)."""
    newest = latest_for_region(session, region_id)
    if newest is None or newest.status != "published":
        return None
    from app.scheduler.persist import carry_forward

    rev = new_revision(session, newest, reason=reason, created_at=created_at)
    if rev.id == newest.id:  # pragma: no cover - new_revision 은 발행 리비전이면 늘 새 행
        return None
    carry_forward(session, newest.id, rev.id, created_at=created_at)
    rev.status = "ready"
    publish(session, rev.id, now=created_at)
    return rev


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
        from app.snapshot_view import materialize

        # D13-1: 같은 트랜잭션에서 그 리비전의 화면 응답 전부·보고서 입력을 저장한다(이후 GET 은 저장본만 읽는다).
        # 실패하면 발행도 함께 되돌아간다(호출자의 rollback) — 저장본 없는 발행 리비전은 생기지 않는다
        materialize(session, snapshot_id)
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
        revision=int(row.revision or 1),
        revision_of=row.revision_of,
        revision_reason=row.revision_reason,
        status=row.status,
        degraded=bool(row.degraded),
        created_at=row.created_at,
        published_at=row.published_at,
    )

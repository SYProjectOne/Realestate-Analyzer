"""참조 테이블 적재: legal_dong · admin_dong · admin_legal_map (DECISIONS D2-1).

- legal_dong·admin_dong: 코드 기준 upsert. 파일에서 빠진 코드는 지우지 않고 active=false.
- admin_legal_map: 현재 매핑으로 맞춘다(새 쌍 추가, 파일에서 빠진 쌍 삭제 — 폐지 매핑은 세대수 분할에 쓰면
  안 된다).
- 같은 파일을 두 번 적재해도 행 수·값이 같다(멱등).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, insert, select, tuple_, update
from sqlalchemy.orm import Session

from app.collectors.reference.jscode import AdminDongRecord
from app.collectors.reference.legal_dong import LegalDongRecord
from app.models import AdminDong, AdminLegalMap, LegalDong

__all__ = [
    "LoadStats",
    "find_sigungu",
    "replace_admin_legal_map",
    "sigungu_label",
    "upsert_admin_dongs",
    "upsert_legal_dongs",
]

_CHUNK = 2000


@dataclass(slots=True)
class LoadStats:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    deactivated: int = 0
    deleted: int = 0

    @property
    def total_changes(self) -> int:
        return self.inserted + self.updated + self.deactivated + self.deleted


def _chunks(items: Sequence[dict[str, Any]]) -> Iterable[Sequence[dict[str, Any]]]:
    for i in range(0, len(items), _CHUNK):
        yield items[i : i + _CHUNK]


def _upsert(
    session: Session,
    model: type[LegalDong] | type[AdminDong],
    rows: dict[str, dict[str, Any]],
    fields: tuple[str, ...],
) -> LoadStats:
    stats = LoadStats()
    existing: dict[str, tuple[Any, ...]] = {}
    cols = [getattr(model, f) for f in ("code", *fields)]
    for rec in session.execute(select(*cols)):
        existing[rec[0]] = tuple(rec[1:])
    new_rows = [r for code, r in rows.items() if code not in existing]
    changed: list[dict[str, Any]] = []
    for code, r in rows.items():
        old = existing.get(code)
        if old is None:
            continue
        if old != tuple(r[f] for f in fields):
            changed.append(r)
        else:
            stats.unchanged += 1
    gone = [code for code, old in existing.items() if code not in rows and old[fields.index("active")]]
    for chunk in _chunks(new_rows):
        session.execute(insert(model), list(chunk))
    for chunk in _chunks(changed):
        session.execute(update(model), list(chunk))
    for i in range(0, len(gone), _CHUNK):
        session.execute(update(model).where(model.code.in_(gone[i : i + _CHUNK])).values(active=False))
    stats.inserted, stats.updated, stats.deactivated = len(new_rows), len(changed), len(gone)
    session.flush()
    return stats


def upsert_legal_dongs(
    session: Session, records: Iterable[LegalDongRecord], *, source_date: str
) -> LoadStats:
    fields = (
        "sido_name",
        "sigungu_name",
        "eupmyeondong_name",
        "ri_name",
        "full_name",
        "sigungu_code",
        "active",
        "source_date",
    )
    rows = {
        r.code: {
            "code": r.code,
            "sido_name": r.sido_name,
            "sigungu_name": r.sigungu_name,
            "eupmyeondong_name": r.eupmyeondong_name,
            "ri_name": r.ri_name,
            "full_name": r.full_name,
            "sigungu_code": r.sigungu_code,
            "active": r.active,
            "source_date": source_date,
        }
        for r in records
    }
    return _upsert(session, LegalDong, rows, fields)


def upsert_admin_dongs(
    session: Session, records: Iterable[AdminDongRecord], *, source_date: str
) -> LoadStats:
    fields = ("full_name", "name", "sigungu_code", "active", "source_date")
    rows = {
        r.code: {
            "code": r.code,
            "full_name": r.full_name,
            "name": r.name,
            "sigungu_code": r.sigungu_code,
            "active": r.active,
            "source_date": source_date,
        }
        for r in records
    }
    return _upsert(session, AdminDong, rows, fields)


def replace_admin_legal_map(session: Session, pairs: Iterable[tuple[str, str]]) -> LoadStats:
    wanted = set(pairs)
    existing = {
        (a, b) for a, b in session.execute(select(AdminLegalMap.admin_code, AdminLegalMap.legal_code))
    }
    add = sorted(wanted - existing)
    drop = sorted(existing - wanted)
    for i in range(0, len(drop), _CHUNK):
        part = drop[i : i + _CHUNK]
        session.execute(
            delete(AdminLegalMap).where(tuple_(AdminLegalMap.admin_code, AdminLegalMap.legal_code).in_(part))
        )
    rows = [{"admin_code": a, "legal_code": b} for a, b in add]
    for chunk in _chunks(rows):
        session.execute(insert(AdminLegalMap), list(chunk))
    session.flush()
    return LoadStats(inserted=len(add), deleted=len(drop), unchanged=len(wanted & existing))


def find_sigungu(session: Session, name: str, *, include_inactive: bool = True) -> list[LegalDong]:
    """시군구 이름(공백 무시)으로 시군구 행(코드 끝 5자리 00000)을 찾는다. 활성 코드가 먼저."""
    key = "".join(name.split())
    stmt = select(LegalDong).where(LegalDong.code.like("_____00000"), LegalDong.sigungu_name.is_not(None))
    if not include_inactive:
        stmt = stmt.where(LegalDong.active.is_(True))
    hits = [r for r in session.scalars(stmt) if "".join((r.sigungu_name or "").split()) == key]
    return sorted(hits, key=lambda r: (not r.active, r.code))


def sigungu_label(row: LegalDong) -> str:
    return f"{row.full_name} ({row.sigungu_code}{'' if row.active else ', 폐지'})"

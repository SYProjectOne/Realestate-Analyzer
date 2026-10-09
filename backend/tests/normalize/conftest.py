"""WP2 테스트 fixture: 픽스처 원문을 RAW_DIR에 두고 raw_document 행을 만든다, 참조표·지역 행을 만든다."""

from __future__ import annotations

import csv
import hashlib
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.core.contracts_gen import RawDocument as RawDocumentDTO
from app.core.snapshot import store_raw
from app.models import AdminDong, AdminLegalMap, HouseholdStat, LegalDong, RawDocument, Region
from app.normalize.region_resolve import ReferenceData, load_reference_csv

from ._support import REFERENCE, AddRaw, dto, make_region


@pytest.fixture
def add_raw(db_session: Session, raw_dir: Path) -> AddRaw:
    """원문 텍스트를 RAW_DIR에 멱등 저장하고 raw_document 행을 넣는다 → DTO(id 포함)."""

    def _add(
        content: str,
        *,
        source_kind: str,
        url: str,
        region_id: int | None = None,
        complex_id: int | None = None,
        fetched_at: str = "2026-10-09T06:00:00+09:00",
        ext: str = "txt",
    ) -> RawDocumentDTO:
        data = content.encode("utf-8")
        day = date.fromisoformat(fetched_at[:10])
        stored = store_raw(data, source=source_kind, day=day, ext=ext, raw_dir=raw_dir)
        row = RawDocument(
            source_kind=source_kind,
            url=url,
            fetched_at=fetched_at,
            http_status=200,
            sha256=stored.sha256,
            path=stored.relpath,
            content_type="text/plain",
            text_path=stored.relpath,
            complex_id=complex_id,
            region_id=region_id,
        )
        db_session.add(row)
        db_session.flush()
        return dto(
            source_kind=source_kind,
            url=url,
            fetched_at=fetched_at,
            raw_id=row.id,
            complex_id=complex_id,
            region_id=region_id,
            path=stored.relpath,
            text_path=stored.relpath,
            sha=stored.sha256,
        )

    return _add


@pytest.fixture
def ref() -> ReferenceData:
    return load_reference_csv(REFERENCE)


@pytest.fixture
def reference_db(db_session: Session, ref: ReferenceData) -> ReferenceData:
    """참조표 CSV → legal_dong·admin_dong·admin_legal_map·household_stat."""
    for r in ref.legal:
        db_session.add(
            LegalDong(
                code=r.code,
                sido_name=r.sido_name,
                sigungu_name=r.sigungu_name,
                eupmyeondong_name=r.eupmyeondong_name,
                ri_name=r.ri_name,
                full_name=r.full_name,
                sigungu_code=r.sigungu_code,
                active=r.active,
                source_date="2026-09-01",
            )
        )
    for a in ref.admin:
        db_session.add(
            AdminDong(
                code=a.code,
                full_name=a.full_name,
                name=a.name,
                sigungu_code=a.sigungu_code,
                active=a.active,
                source_date="2026-09-01",
            )
        )
    for ac, lc in ref.admin_legal:
        db_session.add(AdminLegalMap(admin_code=ac, legal_code=lc))
    raw = RawDocument(
        source_kind="reference",
        url="https://jumin.mois.go.kr/",
        fetched_at="2026-09-05T05:00:00+09:00",
        http_status=200,
        sha256=hashlib.sha256(b"household").hexdigest(),
        path="reference/2026-09-05/household.csv",
    )
    db_session.add(raw)
    db_session.flush()
    with (REFERENCE / "household_stat.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            db_session.add(
                HouseholdStat(
                    scope_kind=r["scope_kind"],
                    scope_code=r["scope_code"],
                    ym=r["ym"],
                    households=int(r["households"]),
                    raw_document_id=raw.id,
                    label="추정",
                    reason="주민등록 세대",
                )
            )
    db_session.flush()
    return ref


@pytest.fixture
def region(db_session: Session, reference_db: ReferenceData) -> Region:
    """회귀 픽스처 지역(테스트 데이터): 연수구·서구·계양구·김포시."""
    return make_region(db_session, reference_db, ["28185", "28260", "28245", "41570"])

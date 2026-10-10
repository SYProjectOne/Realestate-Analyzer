"""기준: region (RA §3 + DECISIONS D2-2), snapshot."""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import REGION_STATUS, SNAPSHOT_STATUS, SNAPSHOT_VIEW_KIND, in_check

__all__ = ["Region", "Snapshot", "SnapshotView"]


class Region(Base):
    """사용자가 입력한 지역. 지역 추가 = 행 1개(코드에 지역명 없음).

    json 컬럼 모양은 contracts/schemas/region.json: selections=[{kind, code, full_name}],
    living_areas=[{id, name, legal_dong_codes, households}], age_premium_coef={c_per_year, cap_years, label}.
    """

    __tablename__ = "region"
    __table_args__ = (CheckConstraint(in_check("status", REGION_STATUS), name="status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    query_text: Mapped[str] = mapped_column(Text)
    selections: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    sido_codes: Mapped[list[str]] = mapped_column(JSON)
    sigungu_codes: Mapped[list[str]] = mapped_column(JSON)
    legal_dong_codes: Mapped[list[str]] = mapped_column(JSON)
    living_areas: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    age_premium_coef: Mapped[dict[str, Any]] = mapped_column(JSON)
    supply_ref_pct: Mapped[Decimal] = mapped_column(Numeric(5, 4), server_default="0.08")
    applyhome_query: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[str] = mapped_column(String(32))


class Snapshot(Base):
    """기준일 스냅샷 리비전. (region_id, asof_date, revision) 유일 — 0008(계약 .8, D11-1).

    발행(published) 리비전은 불변이다. 발행 후 재판정(사람 확인·생활권 편집·판정기 버전 변경·시나리오 실행·지역
    확장)은
    같은 기준일의 새 리비전(revision+1, ``revision_of`` = 바탕 리비전, ``revision_reason``)에 쓰고, 완성된 뒤 한
    번에
    published 가 된다(``scheduler.snapshots.writable``)."""

    __tablename__ = "snapshot"
    __table_args__ = (
        UniqueConstraint("region_id", "asof_date", "revision"),
        CheckConstraint(in_check("status", SNAPSHOT_STATUS), name="status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("region.id"), index=True)
    asof_date: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(16))
    degraded: Mapped[bool] = mapped_column(Boolean, server_default=false())
    created_at: Mapped[str] = mapped_column(String(32))
    published_at: Mapped[str | None] = mapped_column(String(32))
    # 0008 (계약 2026-10-09.8, D11-1): 같은 기준일 리비전(1부터)·바탕 리비전·사유
    revision: Mapped[int] = mapped_column(Integer, server_default="1")
    revision_of: Mapped[int | None] = mapped_column(ForeignKey("snapshot.id"))
    revision_reason: Mapped[str | None] = mapped_column(String(200))


class SnapshotView(Base):
    """발행 리비전의 저장된 읽기 모델 1행 — 0010(계약 2026-10-09.10, DECISIONS D13-1).

    리비전을 published 로 바꾸는 트랜잭션(``scheduler.snapshots.publish`` → ``app.snapshot_view.materialize``)에서 그
    리비전의 화면 응답 전부(대시보드·단지 목록·단지 상세·비교 입력·시장·변경 목록·민감도)와 보고서 입력 데이터를
    시나리오별로 만든다. 발행 리비전의 GET 은 이 행만 읽는다(현재 사실·오버레이 재계산 없음).

    - ``kind`` = ``SNAPSHOT_VIEW_KIND``, ``key`` = 단지 id 문자열(단지 상세)·생활권 id(시장) 또는 '',
      ``scenario`` = 시나리오 id 문자열(시나리오 무관 종류는 '').
    - ``body`` = UTF-8 JSON 의 zlib 압축(용량 — 단지 상세 수백 개 × 시나리오), ``sha256`` = 압축 전 JSON 의 sha256.
    - (snapshot_id, kind, key, scenario) 유일. 발행 리비전은 불변이라 고치지 않는다(devseed·합성 도구만 다시 만든다)."""

    __tablename__ = "snapshot_view"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "kind", "key", "scenario"),
        CheckConstraint(in_check("kind", SNAPSHOT_VIEW_KIND), name="kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshot.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    key: Mapped[str] = mapped_column(String(64), server_default="")
    scenario: Mapped[str] = mapped_column(String(16), server_default="")
    body: Mapped[bytes] = mapped_column(LargeBinary)
    sha256: Mapped[str] = mapped_column(String(64))

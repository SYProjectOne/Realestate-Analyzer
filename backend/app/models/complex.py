"""단지 사실 테이블(현재값만, 변경은 change_event) + 접수 상태(스냅샷별) — RA §3."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import (
    HOUSING_TYPE,
    INCLUSION_CLASS,
    INTAKE_PATH,
    INTAKE_STATUS,
    JUDGE_DECISION,
    LAND_TYPE,
    PRICE_CAP,
    REGULATED,
    SUPPLY_KIND,
    TRACK,
    in_check,
)

__all__ = ["Competition", "Complex", "ComplexType", "IntakeStatus", "PaymentTerms", "RemainingEvent"]


class Complex(Base):
    """한 행 = 한 공고 단지. (region_id, applyhome_id) 유일(공고 전이면 NULL).

    개명은 former_names에 추가하고 행은 유지."""

    __tablename__ = "complex"
    __table_args__ = (
        CheckConstraint(in_check("housing_type", HOUSING_TYPE), name="housing_type"),
        CheckConstraint(in_check("land_type", LAND_TYPE), name="land_type"),
        CheckConstraint(in_check("price_cap", PRICE_CAP), name="price_cap"),
        CheckConstraint(in_check("regulated", REGULATED), name="regulated"),
        CheckConstraint(in_check("inclusion_class", INCLUSION_CLASS), name="inclusion_class"),
        CheckConstraint(in_check("inclusion_decision", JUDGE_DECISION), name="inclusion_decision"),
        CheckConstraint(in_check("track", TRACK), name="track"),
        # 0004(W4): 같은 공고 단지가 지역마다 따로 있을 수 있다 — 유일은 (지역, 공고 id)
        UniqueConstraint("region_id", "applyhome_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("region.id"), index=True)
    applyhome_id: Mapped[str | None] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    former_names: Mapped[list[str]] = mapped_column(JSON)
    address: Mapped[str | None] = mapped_column(Text)
    legal_dong_code: Mapped[str | None] = mapped_column(String(10), index=True)
    living_area: Mapped[str | None] = mapped_column(String(64))
    official_site_url: Mapped[str | None] = mapped_column(Text)
    developer: Mapped[str | None] = mapped_column(String(200))
    trustee: Mapped[str | None] = mapped_column(String(200))
    builder: Mapped[str | None] = mapped_column(String(200))
    housing_type: Mapped[str | None] = mapped_column(String(8))
    land_type: Mapped[str | None] = mapped_column(String(8))
    price_cap: Mapped[str | None] = mapped_column(String(8))
    regulated: Mapped[str | None] = mapped_column(String(8))
    units_total: Mapped[int | None] = mapped_column(Integer)
    units_general: Mapped[int | None] = mapped_column(Integer)
    units_special: Mapped[int | None] = mapped_column(Integer)
    officetel_units: Mapped[int | None] = mapped_column(Integer)
    notice_date: Mapped[str | None] = mapped_column(String(10))
    apply_dates: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    winner_date: Mapped[str | None] = mapped_column(String(10))
    contract_dates: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    move_in_ym: Mapped[str | None] = mapped_column(String(7))
    resale_months: Mapped[int | None] = mapped_column(Integer)
    resale_release_on_registration: Mapped[bool | None] = mapped_column(Boolean)
    residency_months: Mapped[int | None] = mapped_column(Integer)
    rewin_restriction_years: Mapped[int | None] = mapped_column(Integer)
    inclusion_class: Mapped[str] = mapped_column(String(32), server_default="미분류")
    inclusion_decision: Mapped[str | None] = mapped_column(String(16))
    inclusion_prob: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    inclusion_judgment_seq: Mapped[int | None] = mapped_column(Integer)
    track: Mapped[str | None] = mapped_column(String(1))


class ComplexType(Base):
    """타입(평형). (complex_id, type_code) 유일. 판정 기준 타입은 84㎡에 가장 가까운 것."""

    __tablename__ = "complex_type"
    __table_args__ = (UniqueConstraint("complex_id", "type_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complex_id: Mapped[int] = mapped_column(ForeignKey("complex.id"), index=True)
    type_code: Mapped[str] = mapped_column(String(16))
    area_m2: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    units: Mapped[int | None] = mapped_column(Integer)
    max_price_won: Mapped[int | None] = mapped_column(BigInteger)
    floor_sample_price_won: Mapped[int | None] = mapped_column(BigInteger)
    floor_sample_text: Mapped[str | None] = mapped_column(Text)
    balcony_won: Mapped[int | None] = mapped_column(BigInteger)
    options_required_won: Mapped[int | None] = mapped_column(BigInteger)
    options_text: Mapped[str | None] = mapped_column(Text)
    # 0002 (계약 2026-10-09.2): 공고상 주택형 원문('084.9582A')
    notice_type_code: Mapped[str | None] = mapped_column(String(32))


class PaymentTerms(Base):
    """공고별 납부 조건. (complex_id, notice_no) 유일. 최신 effective_from이 현재 조건."""

    __tablename__ = "payment_terms"
    __table_args__ = (
        UniqueConstraint("complex_id", "notice_no"),
        CheckConstraint(in_check("notice_kind", SUPPLY_KIND), name="notice_kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complex_id: Mapped[int] = mapped_column(ForeignKey("complex.id"), index=True)
    notice_no: Mapped[str] = mapped_column(String(32))
    notice_kind: Mapped[str | None] = mapped_column(String(8))
    effective_from: Mapped[str] = mapped_column(String(10))
    down_payment_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    down_payment_first_won: Mapped[int | None] = mapped_column(BigInteger)
    interim_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    interim_terms_text: Mapped[str | None] = mapped_column(Text)
    balance_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    interim_schedule: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    # 0002 (계약 2026-10-09.2): 이 공고의 타입별 공급가
    # {type_code: {max_price_won, floor_sample_price_won, floor_sample_text, units, notice_type_code}}
    price_by_type: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class Competition(Base):
    """청약홈 경쟁률 페이지 원문 그대로."""

    __tablename__ = "competition"
    __table_args__ = (
        UniqueConstraint("complex_id", "kind", "round", "type_code"),
        CheckConstraint(in_check("kind", SUPPLY_KIND), name="kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complex_id: Mapped[int] = mapped_column(ForeignKey("complex.id"), index=True)
    round: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(8))
    type_code: Mapped[str] = mapped_column(String(16))
    supply: Mapped[int | None] = mapped_column(Integer)
    applied: Mapped[int | None] = mapped_column(Integer)
    ratio_or_shortfall_text: Mapped[str | None] = mapped_column(String(64))
    raw_document_id: Mapped[int | None] = mapped_column(ForeignKey("raw_document.id"))


class RemainingEvent(Base):
    """잔여 경로 이력 = 타임라인 C8의 원천."""

    __tablename__ = "remaining_event"
    __table_args__ = (CheckConstraint(in_check("kind", SUPPLY_KIND), name="kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complex_id: Mapped[int] = mapped_column(ForeignKey("complex.id"), index=True)
    kind: Mapped[str] = mapped_column(String(8))
    notice_no: Mapped[str | None] = mapped_column(String(32))
    notice_date: Mapped[str | None] = mapped_column(String(10))
    apply_dates: Mapped[list[str]] = mapped_column(JSON)
    units_by_type: Mapped[dict[str, int]] = mapped_column(JSON)
    ratio_text: Mapped[str | None] = mapped_column(Text)
    result_text: Mapped[str | None] = mapped_column(Text)
    raw_document_id: Mapped[int | None] = mapped_column(ForeignKey("raw_document.id"))


class IntakeStatus(Base):
    """접수 상태(스냅샷별, path별 여러 행). 표시값 우선순위 human_check > official_popup > headless_shot;
    unofficial_ref는 판정 미사용이고 '가능'이 될 수 없다(CHECK)."""

    __tablename__ = "intake_status"
    __table_args__ = (
        Index("ix_intake_status_snapshot_id_complex_id", "snapshot_id", "complex_id"),
        CheckConstraint(in_check("status", INTAKE_STATUS), name="status"),
        CheckConstraint(in_check("path", INTAKE_PATH), name="path"),
        CheckConstraint("path <> 'unofficial_ref' OR status <> '가능'", name="unofficial_not_open"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complex_id: Mapped[int] = mapped_column(ForeignKey("complex.id"))
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshot.id"))
    status: Mapped[str] = mapped_column(String(8))
    path: Mapped[str] = mapped_column(String(16))
    evidence_url: Mapped[str | None] = mapped_column(Text)
    screenshot_path: Mapped[str | None] = mapped_column(Text)
    raw_document_id: Mapped[int | None] = mapped_column(ForeignKey("raw_document.id"))
    http_status: Mapped[int | None] = mapped_column(Integer)
    checked_at: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(String(120))
    note: Mapped[str | None] = mapped_column(Text)
    entered_by: Mapped[str | None] = mapped_column(String(32))

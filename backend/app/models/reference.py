"""참조 데이터 (DECISIONS D2-1): 법정동·행정동·매핑·세대 현황. reference.refresh 잡(WP1)이 적재한다."""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import HOUSEHOLD_SCOPE, LABELS, in_check

__all__ = ["AdminDong", "AdminLegalMap", "HouseholdStat", "LegalDong"]


class LegalDong(Base):
    """법정동 코드(10자리). 폐지 코드는 지우지 않고 active=false."""

    __tablename__ = "legal_dong"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    sido_name: Mapped[str] = mapped_column(String(40))
    sigungu_name: Mapped[str | None] = mapped_column(String(40))
    eupmyeondong_name: Mapped[str | None] = mapped_column(String(40))
    ri_name: Mapped[str | None] = mapped_column(String(40))
    full_name: Mapped[str] = mapped_column(String(200))
    sigungu_code: Mapped[str] = mapped_column(String(5), index=True)
    active: Mapped[bool] = mapped_column(Boolean, server_default=true())
    source_date: Mapped[str] = mapped_column(String(10))


class AdminDong(Base):
    """행정동 코드(10자리)."""

    __tablename__ = "admin_dong"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(60))
    sigungu_code: Mapped[str] = mapped_column(String(5), index=True)
    active: Mapped[bool] = mapped_column(Boolean, server_default=true())
    source_date: Mapped[str] = mapped_column(String(10))


class AdminLegalMap(Base):
    """행정동 ↔ 법정동 매핑(N:M). 폐지 코드도 남기므로 FK를 걸지 않는다."""

    __tablename__ = "admin_legal_map"
    __table_args__ = (UniqueConstraint("admin_code", "legal_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_code: Mapped[str] = mapped_column(String(10), index=True)
    legal_code: Mapped[str] = mapped_column(String(10), index=True)


class HouseholdStat(Base):
    """주민등록 세대 현황. 라벨은 '추정', reason '주민등록 세대' 고정(D2-1)."""

    __tablename__ = "household_stat"
    __table_args__ = (
        UniqueConstraint("scope_kind", "scope_code", "ym"),
        CheckConstraint(in_check("scope_kind", HOUSEHOLD_SCOPE), name="scope_kind"),
        CheckConstraint(in_check("label", LABELS), name="label"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope_kind: Mapped[str] = mapped_column(String(16))
    scope_code: Mapped[str] = mapped_column(String(10))
    ym: Mapped[str] = mapped_column(String(7))
    households: Mapped[int] = mapped_column(Integer)
    raw_document_id: Mapped[int | None] = mapped_column(ForeignKey("raw_document.id"))
    label: Mapped[str] = mapped_column(String(8), server_default="추정")
    reason: Mapped[str | None] = mapped_column(String(120))

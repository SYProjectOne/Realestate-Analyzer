"""시세·호재·시장: benchmark, rtms_trade, comparable_set, catalyst, catalyst_link, supply, unsold — RA §3."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
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
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import (
    CATALYST_KIND,
    CATALYST_STAGE,
    JUDGE_DECISION,
    LABELS,
    SALE_PERIOD,
    TRADE_SOURCE,
    in_check,
)

__all__ = ["Benchmark", "Catalyst", "CatalystLink", "ComparableSet", "RtmsTrade", "Supply", "Unsold"]


class Benchmark(Base):
    """분양가 → 입주 후 실거래. 분양가는 자체 아카이브 공고 우선, 언론 역산은 추정. is_presale은 점수 제외."""

    __tablename__ = "benchmark"
    __table_args__ = (
        CheckConstraint(in_check("sale_period", SALE_PERIOD), name="sale_period"),
        CheckConstraint(in_check("sale_price_label", LABELS), name="sale_price_label"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("region.id"), index=True)
    living_area: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    completed_year: Mapped[int | None] = mapped_column(Integer)
    sale_year: Mapped[int | None] = mapped_column(Integer)
    sale_period: Mapped[str | None] = mapped_column(String(16))
    sale_price_84_won: Mapped[int | None] = mapped_column(BigInteger)
    sale_price_label: Mapped[str | None] = mapped_column(String(8))
    trade_low_won: Mapped[int | None] = mapped_column(BigInteger)
    trade_median_won: Mapped[int | None] = mapped_column(BigInteger)
    trade_high_won: Mapped[int | None] = mapped_column(BigInteger)
    trade_window: Mapped[str | None] = mapped_column(String(32))
    n_trades: Mapped[int | None] = mapped_column(Integer)
    peak_won: Mapped[int | None] = mapped_column(BigInteger)
    peak_ym: Mapped[str | None] = mapped_column(String(7))
    is_presale: Mapped[bool] = mapped_column(Boolean, server_default=false())
    note: Mapped[str | None] = mapped_column(Text)
    # 0006 (계약 2026-10-09.6, G1 요청): 이 행을 조립한 스냅샷 — 재조립이 발행 스냅샷이 인용한 행을
    # 지우지 않게. NULL = 이전 행·사람 입력
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("snapshot.id"), index=True)
    # 0007 (계약 2026-10-09.7): 지역 전체 대체 행(D9-2, 라벨 추정) — note 문자열 대신 이 컬럼으로 판별한다
    substitute: Mapped[bool] = mapped_column(Boolean, server_default=false())


class RtmsTrade(Base):
    """실거래 1건. Open API 행이 있으면 reprocessed 행은 점수에 미사용, cancelled=true 제외."""

    __tablename__ = "rtms_trade"
    __table_args__ = (
        Index("ix_rtms_trade_region_id_apt_name", "region_id", "apt_name"),
        CheckConstraint(in_check("source", TRADE_SOURCE), name="source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("region.id"))
    apt_name: Mapped[str] = mapped_column(String(200))
    dong: Mapped[str | None] = mapped_column(String(64))
    legal_dong_code: Mapped[str | None] = mapped_column(String(10))
    completed_year: Mapped[int | None] = mapped_column(Integer)
    area_m2: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    floor: Mapped[int | None] = mapped_column(Integer)
    price_won: Mapped[int] = mapped_column(BigInteger)
    deal_date: Mapped[str] = mapped_column(String(10))
    cancelled: Mapped[bool] = mapped_column(Boolean, server_default=false())
    is_presale: Mapped[bool] = mapped_column(Boolean, server_default=false())
    source: Mapped[str] = mapped_column(String(16))
    raw_document_id: Mapped[int | None] = mapped_column(ForeignKey("raw_document.id"))


class ComparableSet(Base):
    """가격 갭 비교군 구성 기록(스냅샷별) — '대체' 배지·'이상치 제외'(T4)의 근거. Fact.prov = 'cs_<id>'."""

    __tablename__ = "comparable_set"
    __table_args__ = (Index("ix_comparable_set_snapshot_id_complex_id", "snapshot_id", "complex_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complex_id: Mapped[int] = mapped_column(ForeignKey("complex.id"))
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshot.id"))
    member_apt_name: Mapped[str] = mapped_column(String(200))
    completed_year: Mapped[int | None] = mapped_column(Integer)
    substitute: Mapped[bool] = mapped_column(Boolean, server_default=false())
    adjusted: Mapped[bool] = mapped_column(Boolean, server_default=false())
    coef_used: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    n_trades: Mapped[int | None] = mapped_column(Integer)
    low_won: Mapped[int | None] = mapped_column(BigInteger)
    median_won: Mapped[int | None] = mapped_column(BigInteger)
    adjusted_median_won: Mapped[int | None] = mapped_column(BigInteger)
    high_won: Mapped[int | None] = mapped_column(BigInteger)
    outliers_excluded: Mapped[int | None] = mapped_column(Integer)
    excluded_reason: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text)


class Catalyst(Base):
    """호재. stage는 classify 결과(review면 미확정)."""

    __tablename__ = "catalyst"
    __table_args__ = (
        CheckConstraint(in_check("kind", CATALYST_KIND), name="kind"),
        CheckConstraint(in_check("stage", CATALYST_STAGE), name="stage"),
        CheckConstraint(in_check("decision", JUDGE_DECISION), name="decision"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("region.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(8))
    stage: Mapped[str] = mapped_column(String(8))
    stage_prob: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    decision: Mapped[str | None] = mapped_column(String(16))
    expected_ym: Mapped[str | None] = mapped_column(String(7))
    location_confirmed: Mapped[bool] = mapped_column(Boolean, server_default=false())
    lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    lon: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    raw_document_id: Mapped[int | None] = mapped_column(ForeignKey("raw_document.id"))
    judgment_seq: Mapped[int | None] = mapped_column(Integer)
    source_url: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)


class CatalystLink(Base):
    """호재 ↔ 단지. location_confirmed=false면 행 없음(연결 금지). 0008(D11-5): 사람이 위치를 확인할 때
    (PATCH /catalysts/{id}) 만든다 — 단지 좌표가 없으면 distance_m NULL, weight 1, label 추정."""

    __tablename__ = "catalyst_link"
    __table_args__ = (
        UniqueConstraint("catalyst_id", "complex_id"),
        CheckConstraint(in_check("label", LABELS), name="label"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    catalyst_id: Mapped[int] = mapped_column(ForeignKey("catalyst.id"))
    complex_id: Mapped[int] = mapped_column(ForeignKey("complex.id"), index=True)
    distance_m: Mapped[int | None] = mapped_column(Integer)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    label: Mapped[str | None] = mapped_column(String(8))  # 0008
    reason: Mapped[str | None] = mapped_column(
        String(120)
    )  # 0008: 연결 근거(같은 생활권·단지 지정·좌표 거리)


class Supply(Base):
    """입주 물량. 공고문 입주예정월 합산이면 label 추정, reason '추정 집계'."""

    __tablename__ = "supply"
    __table_args__ = (CheckConstraint(in_check("label", LABELS), name="label"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("region.id"), index=True)
    living_area: Mapped[str | None] = mapped_column(String(64))
    year: Mapped[int] = mapped_column(Integer)
    ym: Mapped[str | None] = mapped_column(String(7))
    units: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(8))
    reason: Mapped[str | None] = mapped_column(String(120))
    complex_id: Mapped[int | None] = mapped_column(ForeignKey("complex.id"))
    raw_document_id: Mapped[int | None] = mapped_column(ForeignKey("raw_document.id"))


class Unsold(Base):
    """미분양(월말 기준). scope = 통계 단위(시군구 코드). 단지별 귀속 금지."""

    __tablename__ = "unsold"
    __table_args__ = (
        UniqueConstraint("region_id", "scope_code", "ym"),
        CheckConstraint(in_check("source_label", LABELS), name="source_label"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("region.id"))
    scope_code: Mapped[str | None] = mapped_column(String(10))
    scope_name: Mapped[str | None] = mapped_column(String(60))
    ym: Mapped[str] = mapped_column(String(7))
    total: Mapped[int | None] = mapped_column(Integer)
    post_completion: Mapped[int | None] = mapped_column(Integer)
    source_label: Mapped[str] = mapped_column(String(8))
    raw_document_id: Mapped[int | None] = mapped_column(ForeignKey("raw_document.id"))

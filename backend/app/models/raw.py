"""원문: raw_document(실패도 행), field_provenance(모든 수치의 출처) — RA §3."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import LABELS, SOURCE_KIND, in_check

__all__ = ["FieldProvenance", "RawDocument"]


class RawDocument(Base):
    """원문 1건. sha256 유일 = 같은 파일 중복 저장 없음.

    실패 행의 sha256 규칙은 contracts/schemas/raw_document.json.
    """

    __tablename__ = "raw_document"
    __table_args__ = (CheckConstraint(in_check("source_kind", SOURCE_KIND), name="source_kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_kind: Mapped[str] = mapped_column(String(24))
    url: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[str] = mapped_column(String(32))
    http_status: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    path: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(String(128))
    text_path: Mapped[str | None] = mapped_column(Text)
    complex_id: Mapped[int | None] = mapped_column(ForeignKey("complex.id"), index=True)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("region.id"))
    error_text: Mapped[str | None] = mapped_column(Text)
    image_hash: Mapped[str | None] = mapped_column(String(64))
    # 0002 (계약 2026-10-09.2)
    table_path: Mapped[str | None] = mapped_column(Text)  # 공고문 표 JSON 상대 경로
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # 수집기 부가 정보


class FieldProvenance(Base):
    """필드 출처 1행. 한 필드에 출처가 여럿이면 행 여러 개, chosen 하나. 상충은 conflict_group으로 묶는다.
    Fact.prov = 'fp_<id>'."""

    __tablename__ = "field_provenance"
    __table_args__ = (
        Index("ix_field_provenance_entity_entity_id_field", "entity", "entity_id", "field"),
        CheckConstraint(in_check("label", LABELS), name="label"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    entity_key: Mapped[str | None] = mapped_column(String(64))
    field: Mapped[str] = mapped_column(String(64))
    value_text: Mapped[str | None] = mapped_column(Text)
    raw_document_id: Mapped[int | None] = mapped_column(ForeignKey("raw_document.id"))
    url: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[str | None] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(8))
    reason: Mapped[str | None] = mapped_column(String(120))
    source_rank: Mapped[int] = mapped_column(Integer)
    chosen: Mapped[bool] = mapped_column(Boolean, server_default=false())
    conflict_group: Mapped[str | None] = mapped_column(String(128), index=True)
    excerpt: Mapped[str | None] = mapped_column(Text)
    excerpt_start: Mapped[int | None] = mapped_column(Integer)
    excerpt_end: Mapped[int | None] = mapped_column(Integer)
    compare_judgment_seq: Mapped[int | None] = mapped_column(Integer)
    # 0002 (계약 2026-10-09.2)
    value_norm: Mapped[str | None] = mapped_column(Text)  # 정규화 값의 정준 문자열
    observed_on: Mapped[str | None] = mapped_column(String(10))  # 원문 시점(공고일 등)

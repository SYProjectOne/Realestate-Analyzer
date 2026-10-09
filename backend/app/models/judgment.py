"""판정: judgment_log(모든 호출 1행, input_hash 유일), claim(원자 주장) — RA §3."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import JUDGE_TOOL, JUDGMENT_STATUS, VERIFY_STATUS, in_check

__all__ = ["Claim", "JudgmentLog"]


class JudgmentLog(Base):
    """판정기 호출 1건 = 1행(성공·실패 불문). input_hash UNIQUE = 같은 입력 재호출 금지가 DB 제약.

    status='error' 행(판정기 오류·미수신)은 같은 input_hash로 다시 부르면
    새 행을 넣지 않고 이 행을 UPDATE한다.
    ok·review·escaped·blocked는 최종 — 다시 부르지 않고 cached 봉투를 돌려준다(WP3 cache.py).
    input_json에는 guard를 통과한 공개 텍스트만 들어간다. 로그(logging)에는 input_hash·길이만.
    """

    __tablename__ = "judgment_log"
    __table_args__ = (
        CheckConstraint(in_check("tool", JUDGE_TOOL), name="tool"),
        CheckConstraint(in_check("status", JUDGMENT_STATUS), name="status"),
    )

    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("snapshot.id"), index=True)
    tool: Mapped[str] = mapped_column(String(16))
    purpose: Mapped[str] = mapped_column(String(128))
    complex_id: Mapped[int | None] = mapped_column(ForeignKey("complex.id"), index=True)
    input_hash: Mapped[str] = mapped_column(String(71), unique=True)
    input_len: Mapped[int | None] = mapped_column(Integer)
    input_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    output_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(32))
    adapter_version: Mapped[str] = mapped_column(String(64))
    error_text: Mapped[str | None] = mapped_column(Text)
    # 0003 (계약 2026-10-09.3): 정규화 결과(봉투 result). 옛 행은 NULL — 읽는 쪽이 output_json 을 다시 정규화
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class Claim(Base):
    """원자 주장 1건. contradicted가 남으면 그 스냅샷은 published 불가."""

    __tablename__ = "claim"
    __table_args__ = (CheckConstraint(in_check("verify_status", VERIFY_STATUS), name="verify_status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshot.id"), index=True)
    section: Mapped[str] = mapped_column(String(32))
    complex_id: Mapped[int | None] = mapped_column(ForeignKey("complex.id"))
    text: Mapped[str] = mapped_column(Text)
    evidence_text: Mapped[str | None] = mapped_column(Text)
    verify_status: Mapped[str | None] = mapped_column(String(16))
    judgment_seq: Mapped[int | None] = mapped_column(ForeignKey("judgment_log.seq"))
    parent_claim_id: Mapped[int | None] = mapped_column(ForeignKey("claim.id"))
    ordinal: Mapped[int | None] = mapped_column(Integer)

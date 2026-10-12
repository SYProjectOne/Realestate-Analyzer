"""판정: judgment_log(모든 호출 1행, input_hash 유일), claim(원자 주장) — RA §3."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import DEMOTION_RESTORED_BY, JUDGE_TOOL, JUDGMENT_STATUS, VERIFY_STATUS, in_check

__all__ = ["Claim", "FactDemotion", "JudgmentLog"]


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
    # 0015 (계약 .15, D18-1·D20-1): 그 응답의 실제 model·provider(원응답에서). 캐시 키의 고정 모델과
    # 다를 수 있다 — provider 'none' = 판정기가 모델을 부르지 않은 로컬 처리. blocked·error·옛 행은 NULL
    model: Mapped[str | None] = mapped_column(String(64))
    provider: Mapped[str | None] = mapped_column(String(32))


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
    # 0006 (계약 2026-10-09.6, D10-3): 주장이 생성된 DB 사실(field_provenance 의 entity·entity_id·field).
    # 사실 문장이 아니면 NULL
    entity: Mapped[str | None] = mapped_column(String(32))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    field: Mapped[str | None] = mapped_column(String(64))


class FactDemotion(Base):
    """D10-3 사실 강등 1건 (0006, 계약 2026-10-09.6 — R3 재리뷰 N-C3).

    contradicted 주장(DB 사실에서 생성)의 문장을 사람이 고치면(PATCH /claims/{id}) 그 사실 필드를
    강등한다: 사실 테이블 값을 비우고, ``demotion_fp_id`` 행(라벨 '확인 불가', reason '검증 모순')을
    chosen 으로, 원래 chosen 행(``original_fp_id``)은 chosen=false 로 보관한다.
    복원(``restored_at``·``restored_by``)은 사람 확인(human_check) 또는 새 원문(정규화가 다른 원문
    출처를 chosen 으로 올림 — ``new_source``).
    """

    __tablename__ = "fact_demotion"
    __table_args__ = (
        Index("ix_fact_demotion_entity_entity_id_field", "entity", "entity_id", "field"),
        CheckConstraint(in_check("restored_by", DEMOTION_RESTORED_BY), name="restored_by"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claim.id"), index=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshot.id"))
    complex_id: Mapped[int | None] = mapped_column(ForeignKey("complex.id"))
    entity: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[int] = mapped_column(Integer)
    field: Mapped[str] = mapped_column(String(64))
    original_fp_id: Mapped[int | None] = mapped_column(ForeignKey("field_provenance.id"))
    demotion_fp_id: Mapped[int | None] = mapped_column(ForeignKey("field_provenance.id"))
    original_value_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(32))
    restored_at: Mapped[str | None] = mapped_column(String(32))
    restored_by: Mapped[str | None] = mapped_column(String(16))
    human_check_id: Mapped[int | None] = mapped_column(ForeignKey("human_check.id"))
    checklist_item_id: Mapped[int | None] = mapped_column(ForeignKey("checklist_item.id"))
    rejudge_job_id: Mapped[int | None] = mapped_column(Integer)
    # 0008 (계약 2026-10-09.8, D11-3): 강등한 모순 값(field_provenance.value_norm 정준 문자열). chosen 값이 이
    # 값과 같은 동안 읽기 시점 오버레이(``app.facts_view``)로 '확인 불가(검증 모순)'. NULL = 0006 시절 행(값을
    # 비운 강등)
    value_norm: Mapped[str | None] = mapped_column(Text)

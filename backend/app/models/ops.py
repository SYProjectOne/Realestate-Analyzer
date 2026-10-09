"""운영: human_check, checklist_item, change_event, job_run — RA §3.

share_link — 계약 2026-10-09.4 (RA §10 보안 5).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import (
    CHANGE_ENTITY,
    CHECKLIST_CLOSED_BY,
    CHECKLIST_KIND,
    CHECKLIST_STATUS,
    HUMAN_CHECK_KIND,
    JOB_KIND,
    JOB_NAME,
    JOB_STATUS,
    SEVERITY,
    in_check,
)

__all__ = ["ChangeEvent", "ChecklistItem", "HumanCheck", "JobRun", "ShareLink"]


class HumanCheck(Base):
    """사람 확인(전화·방문·이메일). entered_by는 역할 문자열('운영자')만 — 사람 이름 금지."""

    __tablename__ = "human_check"
    __table_args__ = (CheckConstraint(in_check("kind", HUMAN_CHECK_KIND), name="kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complex_id: Mapped[int] = mapped_column(ForeignKey("complex.id"), index=True)
    field: Mapped[str] = mapped_column(String(64))
    value_text: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(8))
    checked_at: Mapped[str] = mapped_column(String(32))
    entered_by: Mapped[str] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(String(32))
    # 0008 (계약 2026-10-09.8, D11-3): 확인한 사실 행(field_provenance 의 entity·entity_id). 사람 확인 값은
    # resolver 0순위 후보(source_rank 0)로 들어가 재정규화에도 유지된다. NULL = 접수 상태·옛 행
    entity: Mapped[str | None] = mapped_column(String(32))
    entity_id: Mapped[int | None] = mapped_column(Integer)


class ChecklistItem(Base):
    """체크리스트·캘린더 항목(상태 있음)."""

    __tablename__ = "checklist_item"
    __table_args__ = (
        CheckConstraint(in_check("kind", CHECKLIST_KIND), name="kind"),
        CheckConstraint(in_check("status", CHECKLIST_STATUS), name="status"),
        CheckConstraint(in_check("closed_by", CHECKLIST_CLOSED_BY), name="closed_by"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complex_id: Mapped[int | None] = mapped_column(ForeignKey("complex.id"))
    kind: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(Text)
    due_date: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(8), server_default="open")
    note: Mapped[str | None] = mapped_column(Text)
    # 0008 (계약 2026-10-09.8, M-9): 'auto' = 동기화가 닫음(근거 사실이 사라짐·강등·단지 제외 — 근거가
    # 돌아오면 다시 연다), 'human' = 사람이 PATCH 로 처리, NULL = 열림·옛 행
    closed_by: Mapped[str | None] = mapped_column(String(8))


class ChangeEvent(Base):
    """변경 감지 1건. 새 공고·팝업 변경·중도금일·가격 변경·생활권 편집·판정기 버전 변경은 critical."""

    __tablename__ = "change_event"
    __table_args__ = (
        CheckConstraint(in_check("entity", CHANGE_ENTITY), name="entity"),
        CheckConstraint(in_check("severity", SEVERITY), name="severity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("snapshot.id"), index=True)
    entity: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    field: Mapped[str] = mapped_column(String(64))
    old_text: Mapped[str | None] = mapped_column(Text)
    new_text: Mapped[str | None] = mapped_column(Text)
    detected_at: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(8))
    triggers_rejudge: Mapped[bool] = mapped_column(Boolean, server_default=false())
    complex_id: Mapped[int | None] = mapped_column(ForeignKey("complex.id"))


class JobRun(Base):
    """잡 큐(ADR-3). api가 queued 행을 넣고 worker가 polling.

    잠금 = status='queued'인 행만 running으로 UPDATE.
    """

    __tablename__ = "job_run"
    __table_args__ = (
        Index("ix_job_run_status_scheduled_at", "status", "scheduled_at"),
        CheckConstraint(in_check("job_name", JOB_NAME), name="job_name"),
        CheckConstraint(in_check("kind", JOB_KIND), name="kind"),
        CheckConstraint(in_check("status", JOB_STATUS), name="status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_name: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    scheduled_at: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[str | None] = mapped_column(String(32))
    finished_at: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), server_default="queued")
    stats: Mapped[dict[str, Any]] = mapped_column(JSON)
    error_text: Mapped[str | None] = mapped_column(Text)
    locked_by: Mapped[str | None] = mapped_column(String(64))
    progress: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class ShareLink(Base):
    """읽기 전용 공유 링크(RA §10 보안 5, ADR-9, 계약 2026-10-09.4 — 0004).

    토큰 원문은 저장하지 않는다: ``token_sha256`` = sha256(토큰) hex.
    만료 = ``expires_at``(발급 + SHARE_TOKEN_TTL_DAYS), 회수 = ``revoked_at``.
    상태(active/expired/revoked)는 조회 시각으로 계산한다(컬럼 아님).
    """

    __tablename__ = "share_link"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    label: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(32))
    expires_at: Mapped[str] = mapped_column(String(32))
    revoked_at: Mapped[str | None] = mapped_column(String(32))

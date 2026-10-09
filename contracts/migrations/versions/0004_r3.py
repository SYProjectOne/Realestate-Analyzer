"""0004 r3 — 계약 2026-10-09.4 (R3 수정 F3)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-09

계약 마이그레이션 — 계약 .4 소유자(R3 F3)가 추가한다. contracts/CHANGELOG.md 2026-10-09.4 항목에 요청별 출처·영향.
backend/app/models 를 같은 커밋에서 맞추고 tests/contracts 의 autogenerate diff 0·CHECK 일치 테스트를 통과시킨다.

| 변경 | 내용 | 리뷰 항목 |
| --- | --- | --- |
| share_link 테이블 | 읽기 전용 공유 링크(token_sha256 유일, label, created_at, expires_at, revoked_at) | M9 (RA §10 보안 5) |
| job_run.job_name CHECK | 값 'claim.reverify' 추가(contradicted 주장 문장 수정 → 원자 분할 재검증 잡) | M8 |
| score_component.raw_value_unadjusted | Numeric(18,6) NULL — gap 성분의 미보정 원값(미보정 중앙값 기준 gap%) | W7 |

score_total.judge_scope 의 새 값 '미해결'(D9-1)은 CHECK 가 없는 String(8) 이라 DDL 변경이 없다.

SQLite 는 CHECK 를 ALTER 로 못 바꾸므로 batch 모드(테이블 재생성)로 바꾼다 — 재생성 정의를 ``_job_run_table()`` 로 고정해
반사(reflection) 결과에 기대지 않는다. Postgres 는 같은 batch 블록이 ALTER TABLE … DROP/ADD CONSTRAINT 로 돈다.

downgrade: share_link 를 지우고 CHECK 를 되돌린다. 옛 CHECK 를 통과할 수 없는 claim.reverify 잡 행은 먼저 지운다(잡 큐의
일시 행 — 결과인 claim 행은 남는다).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JOB_NAMES_0001 = (
    "collect.daily",
    "collect.weekly",
    "rejudge",
    "report",
    "snapshot.publish",
    "reference.refresh",
    "region.bootstrap",
)
JOB_NAMES_0004 = (*JOB_NAMES_0001, "claim.reverify")


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _job_run_table(job_names: Sequence[str]) -> sa.Table:
    """SQLite 재생성용 job_run 정의(0001 과 같고 job_name CHECK 값만 인자)."""
    return sa.Table(
        "job_run",
        sa.MetaData(),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_name", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("scheduled_at", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.String(length=32), nullable=True),
        sa.Column("finished_at", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="queued", nullable=False),
        sa.Column("stats", sa.JSON(), nullable=False),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("locked_by", sa.String(length=64), nullable=True),
        sa.Column("progress", sa.JSON(), nullable=True),
        sa.CheckConstraint(_in("job_name", job_names), name="ck_job_run_job_name"),
        sa.CheckConstraint("kind IN ('scheduled', 'manual', 'rejudge')", name="ck_job_run_kind"),
        sa.CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="ck_job_run_status"),
        sa.PrimaryKeyConstraint("id", name="pk_job_run"),
        sa.Index("ix_job_run_status_scheduled_at", "status", "scheduled_at"),
    )


def _set_job_names(old: Sequence[str], new: Sequence[str]) -> None:
    with op.batch_alter_table("job_run", copy_from=_job_run_table(old)) as batch:
        batch.drop_constraint(op.f("ck_job_run_job_name"), type_="check")
        batch.create_check_constraint(op.f("ck_job_run_job_name"), sa.text(_in("job_name", new)))


def upgrade() -> None:
    op.create_table(
        "share_link",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_sha256", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.String(length=32), nullable=False),
        sa.Column("revoked_at", sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_share_link")),
        sa.UniqueConstraint("token_sha256", name=op.f("uq_share_link_token_sha256")),
    )
    _set_job_names(JOB_NAMES_0001, JOB_NAMES_0004)
    op.add_column("score_component", sa.Column("raw_value_unadjusted", sa.Numeric(18, 6), nullable=True))


def downgrade() -> None:
    op.drop_column("score_component", "raw_value_unadjusted")
    op.execute(sa.text("DELETE FROM job_run WHERE job_name = 'claim.reverify'"))
    _set_job_names(JOB_NAMES_0004, JOB_NAMES_0001)
    op.drop_table("share_link")

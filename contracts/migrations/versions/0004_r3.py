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
| score_component.unadjusted_gap_pct · unadjusted_median_won | Numeric(18,6) · BigInteger NULL — gap 성분의 미보정 갭%·미보정 중앙값 | W7 (F2 요청) |
| score_component.score_0_10 | Numeric(6,3) → Numeric(7,4) (점수 엔진 정밀도 4자리) | W12b (F2 요청) |
| complex 유일 제약 | applyhome_id → (region_id, applyhome_id) — 같은 공고 단지가 지역마다 따로 있을 수 있다 | W4 (F1b 요청) |
| checklist_item.kind CHECK | 값 '계약' 추가(계약일 항목) | M7 (F1a 요청) |

score_total.judge_scope 의 새 값 '미해결'(D9-1)은 CHECK 가 없는 String(8) 이라 DDL 변경이 없다.

SQLite 는 CHECK 를 ALTER 로 못 바꾸므로 batch 모드(테이블 재생성)로 바꾼다 — 재생성 정의를 ``_job_run_table()`` 로 고정해
반사(reflection) 결과에 기대지 않는다. Postgres 는 같은 batch 블록이 ALTER TABLE … DROP/ADD CONSTRAINT 로 돈다.

downgrade: share_link 를 지우고 CHECK·컬럼·유일 제약을 되돌린다. 옛 CHECK 를 통과할 수 없는 claim.reverify 잡 행은 먼저
지운다(잡 큐의 일시 행 — 결과인 claim 행은 남는다). checklist_item '계약' 은 '만료'로 바꾼다. 다른 지역의 같은
applyhome_id 행이 있으면 옛 전역 유일 제약을 만들 수 없다(downgrade 실패 — 먼저 정리).
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


CHECKLIST_KINDS_0001 = ("법적 확인", "중도금", "만료", "공고 예상")
CHECKLIST_KINDS_0004 = (*CHECKLIST_KINDS_0001, "계약")


def _checklist_table(kinds: Sequence[str]) -> sa.Table:
    """SQLite 재생성용 checklist_item 정의(0001 과 같고 kind CHECK 값만 인자)."""
    meta = sa.MetaData()
    sa.Table("complex", meta, sa.Column("id", sa.Integer(), primary_key=True))
    return sa.Table(
        "checklist_item",
        meta,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("complex_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("due_date", sa.String(length=10), nullable=True),
        sa.Column("status", sa.String(length=8), server_default="open", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(_in("kind", kinds), name="ck_checklist_item_kind"),
        sa.CheckConstraint("status IN ('open', 'done', 'na')", name="ck_checklist_item_status"),
        sa.ForeignKeyConstraint(["complex_id"], ["complex.id"], name="fk_checklist_item_complex_id_complex"),
        sa.PrimaryKeyConstraint("id", name="pk_checklist_item"),
    )


def _set_checklist_kinds(old: Sequence[str], new: Sequence[str]) -> None:
    with op.batch_alter_table("checklist_item", copy_from=_checklist_table(old)) as batch:
        batch.drop_constraint(op.f("ck_checklist_item_kind"), type_="check")
        batch.create_check_constraint(op.f("ck_checklist_item_kind"), sa.text(_in("kind", new)))


def _score_component_up() -> None:
    with op.batch_alter_table("score_component") as batch:
        batch.alter_column(
            "score_0_10",
            existing_type=sa.Numeric(precision=6, scale=3),
            type_=sa.Numeric(precision=7, scale=4),
            existing_nullable=True,
        )
        batch.add_column(sa.Column("unadjusted_gap_pct", sa.Numeric(18, 6), nullable=True))
        batch.add_column(sa.Column("unadjusted_median_won", sa.BigInteger(), nullable=True))


def _score_component_down() -> None:
    with op.batch_alter_table("score_component") as batch:
        batch.drop_column("unadjusted_median_won")
        batch.drop_column("unadjusted_gap_pct")
        batch.alter_column(
            "score_0_10",
            existing_type=sa.Numeric(precision=7, scale=4),
            type_=sa.Numeric(precision=6, scale=3),
            existing_nullable=True,
        )


def _complex_unique_up() -> None:
    with op.batch_alter_table("complex") as batch:
        batch.drop_constraint(op.f("uq_complex_applyhome_id"), type_="unique")
        batch.create_unique_constraint(
            op.f("uq_complex_region_id_applyhome_id"), ["region_id", "applyhome_id"]
        )


def _complex_unique_down() -> None:
    with op.batch_alter_table("complex") as batch:
        batch.drop_constraint(op.f("uq_complex_region_id_applyhome_id"), type_="unique")
        batch.create_unique_constraint(op.f("uq_complex_applyhome_id"), ["applyhome_id"])


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
    _score_component_up()
    _complex_unique_up()
    _set_checklist_kinds(CHECKLIST_KINDS_0001, CHECKLIST_KINDS_0004)


def downgrade() -> None:
    # '계약' 항목은 옛 CHECK 를 통과하지 못한다 → '만료'(F1a 가 .4 전에 쓰던 값)로 되돌린다
    op.execute(sa.text("UPDATE checklist_item SET kind = '만료' WHERE kind = '계약'"))
    _set_checklist_kinds(CHECKLIST_KINDS_0004, CHECKLIST_KINDS_0001)
    _complex_unique_down()
    _score_component_down()
    op.execute(sa.text("DELETE FROM job_run WHERE job_name = 'claim.reverify'"))
    _set_job_names(JOB_NAMES_0004, JOB_NAMES_0001)
    op.drop_table("share_link")

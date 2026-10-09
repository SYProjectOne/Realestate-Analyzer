"""0006 r3b — 계약 2026-10-09.6 (R3b 수정 라운드 G3)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-09

계약 마이그레이션 — 계약 .6 소유자(R3b G3)가 추가한다. contracts/CHANGELOG.md 2026-10-09.6 항목에 요청별 출처·영향.
backend/app/models 를 같은 커밋에서 맞추고 tests/contracts 의 autogenerate diff 0·CHECK 일치 테스트를 통과시킨다.

| 변경 | 내용 | 리뷰 항목 |
| --- | --- | --- |
| claim.entity · entity_id · field | 주장이 생성된 DB 사실(field_provenance 의 entity·entity_id·field), NULL 허용 | N-C3 · D10-3 |
| fact_demotion 테이블 | 사실 강등 1건(claim·사실·원래/강등 출처 행·체크리스트·rejudge 잡·복원 시각/경로) | N-C3 · D10-3 |
| checklist_item.kind CHECK | 값 '사실 재확인' 추가 | N-C3 · D10-3 |
| benchmark.snapshot_id | 이 행을 조립한 스냅샷(FK snapshot.id, NULL 허용, 색인) — 발행 스냅샷이 인용한 행 보존 | 재리뷰 F1a minor(G1 요청) |

SQLite 는 CHECK 를 ALTER 로 못 바꾸므로 checklist_item 은 batch 모드(재생성 정의 고정, 0004 와 같은 방식)로 바꾼다.

downgrade: fact_demotion 을 지우고, '사실 재확인' 항목은 '법적 확인'(옛 CHECK 안의 값)으로 바꾼 뒤 CHECK·컬럼을 되돌린다.
강등으로 비운 사실 값은 되돌리지 않는다(강등 출처 행·원래 출처 행은 field_provenance 에 남는다).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECKLIST_KINDS_0004 = ("법적 확인", "중도금", "만료", "공고 예상", "계약")
CHECKLIST_KINDS_0006 = (*CHECKLIST_KINDS_0004, "사실 재확인")
RESTORED_BY = ("human_check", "new_source")


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


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


def upgrade() -> None:
    with op.batch_alter_table("claim") as batch:
        batch.add_column(sa.Column("entity", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("entity_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("field", sa.String(length=64), nullable=True))
    with op.batch_alter_table("benchmark") as batch:
        batch.add_column(sa.Column("snapshot_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            op.f("fk_benchmark_snapshot_id_snapshot"), "snapshot", ["snapshot_id"], ["id"]
        )
        batch.create_index(op.f("ix_benchmark_snapshot_id"), ["snapshot_id"], unique=False)
    _set_checklist_kinds(CHECKLIST_KINDS_0004, CHECKLIST_KINDS_0006)
    op.create_table(
        "fact_demotion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("claim_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("complex_id", sa.Integer(), nullable=True),
        sa.Column("entity", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("field", sa.String(length=64), nullable=False),
        sa.Column("original_fp_id", sa.Integer(), nullable=True),
        sa.Column("demotion_fp_id", sa.Integer(), nullable=True),
        sa.Column("original_value_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("restored_at", sa.String(length=32), nullable=True),
        sa.Column("restored_by", sa.String(length=16), nullable=True),
        sa.Column("human_check_id", sa.Integer(), nullable=True),
        sa.Column("checklist_item_id", sa.Integer(), nullable=True),
        sa.Column("rejudge_job_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(_in("restored_by", RESTORED_BY), name=op.f("ck_fact_demotion_restored_by")),
        sa.ForeignKeyConstraint(["claim_id"], ["claim.id"], name=op.f("fk_fact_demotion_claim_id_claim")),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["snapshot.id"], name=op.f("fk_fact_demotion_snapshot_id_snapshot")
        ),
        sa.ForeignKeyConstraint(
            ["complex_id"], ["complex.id"], name=op.f("fk_fact_demotion_complex_id_complex")
        ),
        sa.ForeignKeyConstraint(
            ["original_fp_id"],
            ["field_provenance.id"],
            name=op.f("fk_fact_demotion_original_fp_id_field_provenance"),
        ),
        sa.ForeignKeyConstraint(
            ["demotion_fp_id"],
            ["field_provenance.id"],
            name=op.f("fk_fact_demotion_demotion_fp_id_field_provenance"),
        ),
        sa.ForeignKeyConstraint(
            ["human_check_id"], ["human_check.id"], name=op.f("fk_fact_demotion_human_check_id_human_check")
        ),
        sa.ForeignKeyConstraint(
            ["checklist_item_id"],
            ["checklist_item.id"],
            name=op.f("fk_fact_demotion_checklist_item_id_checklist_item"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fact_demotion")),
    )
    op.create_index(op.f("ix_fact_demotion_claim_id"), "fact_demotion", ["claim_id"], unique=False)
    op.create_index(
        "ix_fact_demotion_entity_entity_id_field",
        "fact_demotion",
        ["entity", "entity_id", "field"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_fact_demotion_entity_entity_id_field", table_name="fact_demotion")
    op.drop_index(op.f("ix_fact_demotion_claim_id"), table_name="fact_demotion")
    op.drop_table("fact_demotion")
    # '사실 재확인' 항목은 옛 CHECK 를 통과하지 못한다 → '법적 확인'(사람이 확인할 항목)으로 되돌린다
    op.execute(sa.text("UPDATE checklist_item SET kind = '법적 확인' WHERE kind = '사실 재확인'"))
    _set_checklist_kinds(CHECKLIST_KINDS_0006, CHECKLIST_KINDS_0004)
    with op.batch_alter_table("benchmark") as batch:
        batch.drop_index(op.f("ix_benchmark_snapshot_id"))
        batch.drop_constraint(op.f("fk_benchmark_snapshot_id_snapshot"), type_="foreignkey")
        batch.drop_column("snapshot_id")
    with op.batch_alter_table("claim") as batch:
        batch.drop_column("field")
        batch.drop_column("entity_id")
        batch.drop_column("entity")

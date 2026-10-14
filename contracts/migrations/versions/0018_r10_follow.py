"""0018 r10 follow — 체크리스트 kind '청약 접수'·'당첨자 발표'(D29-3) · 중복 단지 행 병합 표식(D29-2)

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-14

R10-FOLLOW(계약 2026-10-09.21)가 추가한다. **앱 코드를 import 하지 않는다**(D14-9).

| 변경 | 내용 | 결정 |
| --- | --- | --- |
| checklist_item.kind CHECK | 값 '청약 접수'·'당첨자 발표' 추가(``complex.apply_dates``·``winner_date`` 에서 만드는 자동 항목) | D29-3 |
| complex.merged_into_id (새 열, NULL 가능, FK complex.id) | 같은 사업의 중복 단지 행(잔여·임의 공고 번호로 따로 생긴 행)이 병합된 원 단지. NULL = 현재 단지 | D29-2 |

데이터 채움 없음 — 병합은 정규화(``normalize.store`` — 공고문이 원 공고 번호를 인용할 때, 다음 ``collect.daily``)가 change_event 와
함께 한다(인천 도화 단지 99 → 39). 병합된 행은 지우지 않는다(발행 리비전의 점수·사다리·접수 행이 그 id 를 가리킨다 — D11-1).

downgrade: '청약 접수'·'당첨자 발표' 항목은 옛 CHECK 를 통과하지 못하므로 지운다(자동 항목 — 다시 올리면 다음 동기화가 다시
만든다; 사람이 남긴 메모는 사라진다). merged_into_id 열 삭제(병합된 행이 다시 목록·점수 대상이 된다 — 0017 의 동작).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECKLIST_KINDS_0008 = ("법적 확인", "중도금", "만료", "공고 예상", "계약", "사실 재확인")
CHECKLIST_KINDS_0018 = (*CHECKLIST_KINDS_0008, "청약 접수", "당첨자 발표")
CLOSED_BY = ("auto", "human")


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _checklist_table(kinds: Sequence[str]) -> sa.Table:
    """SQLite 재생성용 checklist_item 정의(0008 과 같고 kind CHECK 값만 인자)."""
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
        sa.Column("closed_by", sa.String(length=8), nullable=True),
        sa.CheckConstraint(_in("kind", kinds), name="ck_checklist_item_kind"),
        sa.CheckConstraint("status IN ('open', 'done', 'na')", name="ck_checklist_item_status"),
        sa.CheckConstraint(_in("closed_by", CLOSED_BY), name="ck_checklist_item_closed_by"),
        sa.ForeignKeyConstraint(["complex_id"], ["complex.id"], name="fk_checklist_item_complex_id_complex"),
        sa.PrimaryKeyConstraint("id", name="pk_checklist_item"),
    )


def _set_checklist_kinds(old: Sequence[str], new: Sequence[str]) -> None:
    with op.batch_alter_table("checklist_item", copy_from=_checklist_table(old)) as batch:
        batch.drop_constraint(op.f("ck_checklist_item_kind"), type_="check")
        batch.create_check_constraint(op.f("ck_checklist_item_kind"), sa.text(_in("kind", new)))


def upgrade() -> None:
    _set_checklist_kinds(CHECKLIST_KINDS_0008, CHECKLIST_KINDS_0018)
    with op.batch_alter_table("complex") as batch:
        batch.add_column(sa.Column("merged_into_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            op.f("fk_complex_merged_into_id_complex"), "complex", ["merged_into_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("complex") as batch:
        batch.drop_constraint(op.f("fk_complex_merged_into_id_complex"), type_="foreignkey")
        batch.drop_column("merged_into_id")
    op.execute(sa.text("DELETE FROM checklist_item WHERE kind IN ('청약 접수', '당첨자 발표')"))
    _set_checklist_kinds(CHECKLIST_KINDS_0018, CHECKLIST_KINDS_0008)

"""0009 r3d — 계약 2026-10-09.9 (R3 4차 리뷰 · DECISIONS D12-4)

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-10

계약 마이그레이션 — 계약 .9 소유자(R3d CORE2)가 추가한다. contracts/CHANGELOG.md 2026-10-09.9 항목.

| 변경 | 내용 | 결정·리뷰 |
| --- | --- | --- |
| snapshot_state (새 테이블) | 발행 순간의 리비전 시점 값: entity = region(생활권) · complex(분류·생활권·법정동) · catalyst(단계·종류·위치·연결). (snapshot_id, entity, entity_id) 유일, entity CHECK. 발행 스냅샷을 읽는 화면·보고서가 이 값을 쓴다(app.snapshot_state) | D12-4 · M-7 |

upgrade: 테이블 생성(기존 발행 스냅샷은 행이 없다 — 지금 값으로 읽는다, 0008 과 같은 동작).
downgrade: 테이블 삭제(얼린 값 손실 — 옛 리비전 상세·보고서가 지금 값으로 읽힌다. 재upgrade 로 되살릴 수 없다).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENTITIES = ("region", "complex", "catalyst")


def upgrade() -> None:
    op.create_table(
        "snapshot_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("snapshot.id", name=op.f("fk_snapshot_state_snapshot_id_snapshot")), nullable=False),
        sa.Column("entity", sa.String(length=16), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.CheckConstraint("entity IN (" + ", ".join(f"'{e}'" for e in ENTITIES) + ")", name=op.f("ck_snapshot_state_entity")),
        sa.UniqueConstraint("snapshot_id", "entity", "entity_id", name=op.f("uq_snapshot_state_snapshot_id_entity_entity_id")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_snapshot_state")),
    )
    op.create_index(op.f("ix_snapshot_state_snapshot_id"), "snapshot_state", ["snapshot_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_snapshot_state_snapshot_id"), table_name="snapshot_state")
    op.drop_table("snapshot_state")

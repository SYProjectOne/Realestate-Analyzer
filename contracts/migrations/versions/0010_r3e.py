"""0010 r3e — 계약 2026-10-09.10 (R3 5차 리뷰 · DECISIONS D13-1)

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-10

계약 마이그레이션 — 계약 .10 소유자(R3e CORE3)가 추가한다. contracts/CHANGELOG.md 2026-10-09.10 항목.

| 변경 | 내용 | 결정·리뷰 |
| --- | --- | --- |
| snapshot_view (새 테이블) | 발행 리비전의 저장된 읽기 모델: (snapshot_id, kind, key, scenario) 유일, kind CHECK, body = zlib 압축 JSON, sha256 = 압축 전 JSON. 발행 리비전 GET·보고서는 이 행만 읽는다(app.snapshot_view) | D13-1 · K2 · M6 |
| snapshot_state (삭제) | 0009 값별 동결(분류·생활권·호재 단계/연결)은 저장본으로 대체 | D13-1 |
| 데이터 | (계약 .11 D14-9 로 옮김) 0010 이전 발행 스냅샷 저장본은 마이그레이션이 만들지 않는다 — worker 시작·``python -m app.snapshot_view backfill`` 이 멱등으로 채운다(그 사이 GET = 503 materialize_pending) | D13-1 · D14-9 |

upgrade: snapshot_view 생성 → snapshot_state 삭제. **앱 코드를 import 하지 않는다**(R3 6차 m2·D14-9 — 마이그레이션이 최신 ORM 을 읽으면
이후 열 추가 때 0009→head 가 깨진다). 0009 얼린 값은 옮기지 않는다(backfill 이 지금 값으로 materialize — 0009 발행분은 개발 DB 뿐이었다).
downgrade: snapshot_view 삭제(저장본 손실 — 0009 코드는 발행 리비전을 지금 값으로 읽는다) + 빈 snapshot_state 재생성.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = (
    "dashboard",
    "complexes",
    "complex",
    "compare",
    "market",
    "changes",
    "sensitivity",
    "report",
    "report_diff",
)
STATE_ENTITIES = ("region", "complex", "catalyst")


def upgrade() -> None:
    op.create_table(
        "snapshot_view",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.Integer(),
            sa.ForeignKey("snapshot.id", name=op.f("fk_snapshot_view_snapshot_id_snapshot")),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("key", sa.String(length=64), server_default="", nullable=False),
        sa.Column("scenario", sa.String(length=16), server_default="", nullable=False),
        sa.Column("body", sa.LargeBinary(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "kind IN (" + ", ".join(f"'{k}'" for k in KINDS) + ")", name=op.f("ck_snapshot_view_kind")
        ),
        sa.UniqueConstraint(
            "snapshot_id",
            "kind",
            "key",
            "scenario",
            name=op.f("uq_snapshot_view_snapshot_id_kind_key_scenario"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_snapshot_view")),
    )
    op.create_index(op.f("ix_snapshot_view_snapshot_id"), "snapshot_view", ["snapshot_id"])
    op.drop_index(op.f("ix_snapshot_state_snapshot_id"), table_name="snapshot_state")
    op.drop_table("snapshot_state")


def downgrade() -> None:
    op.create_table(
        "snapshot_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.Integer(),
            sa.ForeignKey("snapshot.id", name=op.f("fk_snapshot_state_snapshot_id_snapshot")),
            nullable=False,
        ),
        sa.Column("entity", sa.String(length=16), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "entity IN (" + ", ".join(f"'{e}'" for e in STATE_ENTITIES) + ")",
            name=op.f("ck_snapshot_state_entity"),
        ),
        sa.UniqueConstraint(
            "snapshot_id", "entity", "entity_id", name=op.f("uq_snapshot_state_snapshot_id_entity_entity_id")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_snapshot_state")),
    )
    op.create_index(op.f("ix_snapshot_state_snapshot_id"), "snapshot_state", ["snapshot_id"])
    op.drop_index(op.f("ix_snapshot_view_snapshot_id"), table_name="snapshot_view")
    op.drop_table("snapshot_view")

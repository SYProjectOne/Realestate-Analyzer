"""0011 r3f — 계약 2026-10-09.11 (R3 6차 리뷰 · DECISIONS D14-1·D14-4·D14-9)

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-10

계약 마이그레이션 — 계약 .11 소유자(R3f CORE4)가 추가한다. contracts/CHANGELOG.md 2026-10-09.11 항목.
**앱 코드를 import 하지 않는다**(D14-9 — 이후 ORM 열이 늘어도 이 파일은 그대로 돈다).

| 변경 | 내용 | 결정·리뷰 |
| --- | --- | --- |
| snapshot_view.contract_version (새 열) | 행을 만든 계약 버전. 읽을 때 현재 계약 버전·sha256 을 검증(다르면 500 stored_view_mismatch) | D14-4 · N-M2 |
| snapshot_view.kind CHECK | provenance(출처 서랍)·claims(주장 목록) 추가 | D14-1 · C2 · m1 |
| 데이터(저장본 변환 .10 → .11) | 기존 행의 모양은 .11 과 같다(식별 변환) — contract_version = '2026-10-09.11'. 새 종류(provenance·claims)는 만들지 않는다: worker 시작·``python -m app.snapshot_view backfill`` 이 멱등으로 채운다(그 사이 그 종류 GET = 503 materialize_pending) | D14-4 · D14-9 |

downgrade: provenance·claims 행 삭제(backfill 로 다시 만들 수 있다) → kind CHECK 되돌림 → contract_version 열 삭제.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS_0010 = (
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
KINDS_0011 = (*KINDS_0010, "provenance", "claims")
CONTRACT_0011 = "2026-10-09.11"
"""이 마이그레이션이 변환해 넣는 계약 버전(.10 행 = .11 모양 — 식별 변환)."""


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN (" + ", ".join("'" + v + "'" for v in values) + ")"


def _table(kinds: Sequence[str], *, version: bool) -> sa.Table:
    meta = sa.MetaData()
    sa.Table("snapshot", meta, sa.Column("id", sa.Integer(), primary_key=True))
    cols: list[sa.schema.SchemaItem] = [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("key", sa.String(length=64), server_default="", nullable=False),
        sa.Column("scenario", sa.String(length=16), server_default="", nullable=False),
        sa.Column("body", sa.LargeBinary(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.CheckConstraint(_in("kind", kinds), name="ck_snapshot_view_kind"),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["snapshot.id"], name="fk_snapshot_view_snapshot_id_snapshot"
        ),
        sa.UniqueConstraint(
            "snapshot_id", "kind", "key", "scenario", name="uq_snapshot_view_snapshot_id_kind_key_scenario"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_snapshot_view"),
        sa.Index("ix_snapshot_view_snapshot_id", "snapshot_id"),
    ]
    if version:
        cols.append(sa.Column("contract_version", sa.String(length=32), server_default="", nullable=False))
    return sa.Table("snapshot_view", meta, *cols)


def upgrade() -> None:
    with op.batch_alter_table("snapshot_view", copy_from=_table(KINDS_0010, version=False)) as batch:
        batch.add_column(
            sa.Column("contract_version", sa.String(length=32), server_default="", nullable=False)
        )
        batch.drop_constraint(op.f("ck_snapshot_view_kind"), type_="check")
        batch.create_check_constraint(op.f("ck_snapshot_view_kind"), sa.text(_in("kind", KINDS_0011)))
    # 저장본 변환(.10 → .11): 기존 kind 의 모양은 바뀌지 않았다 — 버전만 올린다(D14-4)
    op.execute(sa.text("UPDATE snapshot_view SET contract_version = :v").bindparams(v=CONTRACT_0011))


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM snapshot_view WHERE kind IN ('provenance', 'claims')"))
    with op.batch_alter_table("snapshot_view", copy_from=_table(KINDS_0011, version=True)) as batch:
        batch.drop_constraint(op.f("ck_snapshot_view_kind"), type_="check")
        batch.create_check_constraint(op.f("ck_snapshot_view_kind"), sa.text(_in("kind", KINDS_0010)))
        batch.drop_column("contract_version")

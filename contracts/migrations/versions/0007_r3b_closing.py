"""0007 r3b closing — 계약 2026-10-09.7 (R3b 마무리)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-10

계약 마이그레이션 — 계약 .7 소유자(R3b 마무리)가 추가한다. contracts/CHANGELOG.md 2026-10-09.7 항목.

| 변경 | 내용 |
| --- | --- |
| benchmark.substitute | 지역 전체 대체 행(D9-2: 생활권 자체 표본 0 → 지역 전체 표본 복사, 라벨 추정). Boolean NOT NULL, 기본 false. 대체 판별을 note 문자열(`추정(대체: 지역 전체)`) 대신 이 컬럼으로 한다(정규화·점수·API·보고서). |

upgrade: 컬럼 추가 후 기존 행은 note 에 대체 표식이 있으면 true 로 채운다(그 밖은 false).
downgrade: 컬럼 삭제(note 는 그대로 남는다 — 0006 코드의 note 판별이 계속 동작한다).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUBSTITUTE_NOTE = (
    "추정(대체: 지역 전체)"  # 0006 까지의 대체 행 note 표식(app.normalize.benchmark.SUBSTITUTE_NOTE)
)


def upgrade() -> None:
    with op.batch_alter_table("benchmark") as batch:
        batch.add_column(sa.Column("substitute", sa.Boolean(), server_default=sa.false(), nullable=False))
    # 판별은 파이썬에서(DB 별 LIKE·인코딩 차이 없이 — pgserver 의 SQL_ASCII 등) 같은 부분 문자열 규칙으로
    bind = op.get_bind()
    ids = [
        int(row_id)
        for row_id, note in bind.execute(sa.text("SELECT id, note FROM benchmark WHERE note IS NOT NULL"))
        if SUBSTITUTE_NOTE in str(note)
    ]
    for row_id in ids:
        bind.execute(sa.text("UPDATE benchmark SET substitute = :t WHERE id = :i"), {"t": True, "i": row_id})


def downgrade() -> None:
    with op.batch_alter_table("benchmark") as batch:
        batch.drop_column("substitute")

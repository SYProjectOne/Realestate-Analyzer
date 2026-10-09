"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

계약 마이그레이션 — 오케스트레이터(WP0)만 추가한다. contracts/CHANGELOG.md 에 버전 항목을 함께 적는다.
backend/app/models 를 같은 커밋에서 맞추고 tests/contracts 의 autogenerate diff 0 테스트를 통과시킨다.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}

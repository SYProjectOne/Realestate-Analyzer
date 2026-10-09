"""0003 r2 — 계약 2026-10-09.3 (R2 WP5·WP7 요청 반영)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-09

계약 마이그레이션 — 오케스트레이터(WP0)만 추가한다. contracts/CHANGELOG.md 2026-10-09.3 항목에 요청별 출처·영향 WP.
backend/app/models 를 같은 커밋에서 맞추고 tests/contracts 의 autogenerate diff 0 테스트를 통과시킨다.

컬럼 추가만 한다(모두 NULL 허용, 인덱스·제약 없음 — SQLite 3.35+ DROP COLUMN 으로 되돌린다).

| 테이블.컬럼 | 형 | 요청 |
| --- | --- | --- |
| judgment_log.result_json | JSON | WP5-3 — 정규화 결과(봉투 result). output_json(판정기 원응답)과 따로 둔다. 옛 행은 NULL(읽는 쪽이 원응답을 다시 정규화) |
| score_total.judge_scope | String(8) | WP5-4 — 이 점수 실행이 쓴 판정 범위(판정 대상/보류/참고/제외). 옛 행은 NULL |
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns() -> list[tuple[str, sa.Column[object]]]:
    """(테이블, 컬럼). Column 객체는 테이블 하나에만 붙으므로 호출마다 새로 만든다."""
    return [
        ("judgment_log", sa.Column("result_json", sa.JSON(), nullable=True)),
        ("score_total", sa.Column("judge_scope", sa.String(length=8), nullable=True)),
    ]


def upgrade() -> None:
    for table, column in _columns():
        op.add_column(table, column)


def downgrade() -> None:
    for table, column in reversed(_columns()):
        op.drop_column(table, column.name)

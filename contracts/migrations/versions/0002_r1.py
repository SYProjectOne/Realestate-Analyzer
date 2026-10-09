"""0002 r1 — 계약 2026-10-09.2 (R1 계약 변경 요청 일괄 반영)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-09

계약 마이그레이션 — 오케스트레이터(WP0)만 추가한다. contracts/CHANGELOG.md 2026-10-09.2 항목에 요청별 출처·영향 WP.
backend/app/models 를 같은 커밋에서 맞추고 tests/contracts 의 autogenerate diff 0 테스트를 통과시킨다.

컬럼 추가만 한다(모두 NULL 허용, 기존 행 값 없음). SQLite·Postgres 16 둘 다 ALTER TABLE ADD/DROP COLUMN 으로 돈다
(새 컬럼은 인덱스·제약이 없어 SQLite 3.35+ DROP COLUMN 이 된다 — 배치 재생성 불필요).

| 테이블.컬럼 | 형 | 요청 |
| --- | --- | --- |
| field_provenance.value_norm | Text | WP2 #3 — 정규화 값 정준 문자열(옛 출처 재파싱 없이 비교) |
| field_provenance.observed_on | String(10) | WP2 #2 — 원문 시점(공고일). 저장된 출처끼리 '공고문 최신' 비교 |
| complex_type.notice_type_code | String(32) | WP2 #4 — 공고상 주택형 원문('084.9582A') |
| payment_terms.price_by_type | JSON | WP2 #5 — 공고별 타입 공급가 {type_code: {max_price_won, floor_sample_price_won, floor_sample_text, units}} |
| raw_document.table_path | Text | WP1a #2 — 공고문 표 JSON 상대 경로 |
| raw_document.meta | JSON | WP1b #1 — 수집기 부가 정보 |
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns() -> list[tuple[str, sa.Column[object]]]:
    """(테이블, 컬럼). Column 객체는 테이블 하나에만 붙으므로 호출마다 새로 만든다."""
    return [
        ("field_provenance", sa.Column("value_norm", sa.Text(), nullable=True)),
        ("field_provenance", sa.Column("observed_on", sa.String(length=10), nullable=True)),
        ("complex_type", sa.Column("notice_type_code", sa.String(length=32), nullable=True)),
        ("payment_terms", sa.Column("price_by_type", sa.JSON(), nullable=True)),
        ("raw_document", sa.Column("table_path", sa.Text(), nullable=True)),
        ("raw_document", sa.Column("meta", sa.JSON(), nullable=True)),
    ]


def upgrade() -> None:
    for table, column in _columns():
        op.add_column(table, column)


def downgrade() -> None:
    for table, column in reversed(_columns()):
        op.drop_column(table, column.name)

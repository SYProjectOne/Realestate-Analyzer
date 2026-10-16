"""0019 r11 be — 가격 갭 비교군 전체 중앙값(gap% 기준) 열 (D30-5)

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-16

R11-BE(계약 2026-10-09.22)가 추가한다. **앱 코드를 import 하지 않는다**(D14-9).

| 변경 | 내용 | 결정 |
| --- | --- | --- |
| score_component.median_won (새 열, NULL 가능) | gap 성분만: gap% 의 기준인 비교군 전체 중앙값(원, 대체 단지는 연식 보정값 — ``analysis.gap`` 의 median(T_adj)). 단지 상세·비교의 ``gap.comps_median`` | D30-5 |

데이터 채움 없음 — 다음 점수 실행(재판정)이 채운다. 옛 실행 행은 NULL 이고, 대체 단지가 없던 실행이면 API 가 같은 값인
``unadjusted_median_won``(0004)을 쓴다(대체가 없으면 보정·미보정 거래 목록이 같다). 대체 단지가 있던 옛 실행은 '확인 불가'.

downgrade: 열 삭제(``gap.comps_median`` 은 위 규칙의 옛 실행처럼 보인다).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("score_component") as batch:
        batch.add_column(sa.Column("median_won", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("score_component") as batch:
        batch.drop_column("median_won")

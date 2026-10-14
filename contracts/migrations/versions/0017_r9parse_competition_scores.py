"""0017 r9parse competition scores — 당첨가점 열 (R9-PARSE Q4 · DECISIONS D28-5)

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-14

R9-PARSE(저장·파싱 담당)가 추가한다. **API·계약(openapi·schemas) 노출은 R9-API 의 계약 .20 몫** — 이 마이그레이션은 저장 열만
만든다. R9-API 도 마이그레이션을 내면 CEO 가 순서를 정한다(이 파일은 0016 바로 다음, 스키마 추가만이라 순서를 바꿔도 된다).
**앱 코드를 import 하지 않는다**(D14-9).

| 변경 | 내용 | 결정 |
| --- | --- | --- |
| competition.winning_score_min (새 열, NULL 가능, Numeric(5,2)) | 청약홈 경쟁률 팝업 '당첨가점' 최저(가점제 당첨자만). 회차 '1순위 <거주지역>' 행에 단다 | D28-5 Q4 |
| competition.winning_score_max (새 열) | 같은 묶음의 최고 | D28-5 Q4 |
| competition.winning_score_avg (새 열) | 같은 묶음의 평균(원문 소수 2자리까지) | D28-5 Q4 |

데이터 채움 없음 — 값은 수집(웹 경쟁률 팝업, ``collectors.applyhome``)과 정규화(``normalize.applyhome_parser``)가 출처 행(field_provenance,
entity 'competition', field 'winning_score_*')과 함께 쓴다. 원문 '-'(발표 전·가점 당첨자 없음)는 NULL.

downgrade: 세 열 삭제(출처 행은 남는다 — 다시 올리면 다음 수집·재정규화가 채운다).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = ("winning_score_min", "winning_score_max", "winning_score_avg")


def upgrade() -> None:
    with op.batch_alter_table("competition") as batch:
        for name in _COLUMNS:
            batch.add_column(sa.Column(name, sa.Numeric(precision=5, scale=2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("competition") as batch:
        for name in reversed(_COLUMNS):
            batch.drop_column(name)

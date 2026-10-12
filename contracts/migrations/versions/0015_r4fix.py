"""0015 r4fix — 계약 2026-10-09.15 (R4 실데이터 · DECISIONS D18-1 · D20-1)

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-12

계약 마이그레이션 — 계약 .15 소유자(R4-FIX, D20-1 위임)가 추가한다. contracts/CHANGELOG.md 2026-10-09.15 항목.
**앱 코드를 import 하지 않는다**(D14-9).

| 변경 | 내용 | 결정 |
| --- | --- | --- |
| judgment_log.model (새 열, NULL 가능) | 그 응답의 실제 ``model``(JEV 원응답 ``output_json.model``) — 캐시 키의 고정 모델과 다를 수 있다(로컬 단락 ``jev-latest``) | D18-1 |
| judgment_log.provider (새 열, NULL 가능) | 그 응답의 ``provider``(``typesafe``·``none`` …). ``none`` = 판정기가 모델을 부르지 않은 로컬 처리 | D18-1 |
| 데이터 | 기존 행은 ``output_json`` 에서 채운다(없으면 NULL — blocked·error 행 등) | — |

downgrade: 두 열 삭제(값은 output_json 에 그대로 남는다).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BATCH = 500


def _text(value: Any) -> str | None:
    return value.strip()[:64] if isinstance(value, str) and value.strip() else None


def upgrade() -> None:
    with op.batch_alter_table("judgment_log") as batch:
        batch.add_column(sa.Column("model", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("provider", sa.String(length=32), nullable=True))
    bind = op.get_bind()
    jl = sa.table(
        "judgment_log",
        sa.column("seq", sa.Integer),
        sa.column("output_json", sa.JSON),
        sa.column("model", sa.String),
        sa.column("provider", sa.String),
    )
    last = 0
    while True:
        rows = list(
            bind.execute(sa.select(jl.c.seq, jl.c.output_json).where(jl.c.seq > last).order_by(jl.c.seq).limit(_BATCH))
        )
        if not rows:
            break
        for seq, out in rows:
            last = seq
            if isinstance(out, str):
                try:
                    out = json.loads(out)
                except ValueError:
                    out = None
            if not isinstance(out, dict):
                continue
            model, provider = _text(out.get("model")), _text(out.get("provider"))
            if model is None and provider is None:
                continue
            bind.execute(sa.update(jl).where(jl.c.seq == seq).values(model=model, provider=provider))


def downgrade() -> None:
    with op.batch_alter_table("judgment_log") as batch:
        batch.drop_column("provider")
        batch.drop_column("model")

"""0005 wait_new — 계약 2026-10-09.5 (R3 마무리)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-09

계약 마이그레이션 — 계약 .5 소유자(R3 마무리)가 추가한다. contracts/CHANGELOG.md 2026-10-09.5 항목.

| 변경 | 내용 | 근거 |
| --- | --- | --- |
| scenario.policy(JSON) 데이터 | 내장 시나리오 5개에 ``include_wait_new`` 를 명시 — A(가점 높음·실거주)만 true | 보고서 §8-2·§12-5-2(#126): decide 후보 = TOP 5 + '모집공고 대기' |

DDL 변경 없음(policy 는 JSON 컬럼). 사용자 시나리오(is_builtin=false)는 건드리지 않는다 — 키가 없으면 false(계약 기본값).

downgrade: 모든 시나리오 행의 policy 에서 ``include_wait_new`` 를 뺀다(옛 계약 ScenarioPolicy 는 additionalProperties=false).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BUILTIN_WAIT_NEW: dict[str, bool] = {"base": False, "A": True, "B": False, "C": False, "D": False}
"""내장 시나리오 code → policy.include_wait_new (0001 시드 + 이 값 = 현재 내장 시나리오)."""

_scenario = sa.table(
    "scenario",
    sa.column("id", sa.Integer),
    sa.column("code", sa.String),
    sa.column("is_builtin", sa.Boolean),
    sa.column("policy", sa.JSON),
)


def _rows(*, builtin_only: bool) -> list[Any]:
    stmt = sa.select(_scenario.c.id, _scenario.c.code, _scenario.c.policy)
    if builtin_only:
        stmt = stmt.where(_scenario.c.is_builtin.is_(True))
    return list(op.get_bind().execute(stmt))


def upgrade() -> None:
    bind = op.get_bind()
    for row in _rows(builtin_only=True):
        if row.code not in BUILTIN_WAIT_NEW:
            continue
        policy = dict(row.policy or {})
        policy["include_wait_new"] = BUILTIN_WAIT_NEW[row.code]
        bind.execute(_scenario.update().where(_scenario.c.id == row.id).values(policy=policy))


def downgrade() -> None:
    bind = op.get_bind()
    for row in _rows(builtin_only=False):
        policy = dict(row.policy or {})
        if "include_wait_new" in policy:
            policy.pop("include_wait_new")
            bind.execute(_scenario.update().where(_scenario.c.id == row.id).values(policy=policy))

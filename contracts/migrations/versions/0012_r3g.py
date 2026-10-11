"""0012 r3g — 계약 2026-10-09.12 (R3 7차 리뷰 · DECISIONS D15-3·D15-6)

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-11

계약 마이그레이션 — 계약 .12 소유자(R3g CORE5)가 추가한다. contracts/CHANGELOG.md 2026-10-09.12 항목.
**앱 코드를 import 하지 않는다**(D14-9).

| 변경 | 내용 | 결정·리뷰 |
| --- | --- | --- |
| snapshot_view_unit (새 테이블) | 저장본 완료 표식 = (snapshot_id, kind, scenario) 유일 + shape_version·rows·done. 표식은 그 단위의 마지막 쓰기와 같은 트랜잭션에 쓴다. 표식 없는(또는 done=false·행 수 모자란) 단위 = 미완(GET 503 + backfill 이 다시) | D15-3 · M2 |
| snapshot_view.shape_version (새 열) | 저장 모양 버전(정수, 기본 1). 읽기 호환은 계약 문자열이 아니라 이 값으로 비교(계약 버전만 바뀐 변경에 발행 GET 500 이 나지 않는다) | D15-3 · m9 |
| snapshot.publish_lease (새 열) | 발행 single-flight 임대 '<보유자>\\|<epoch>' — 조건부 UPDATE 로 하나만 발행 | D15-6 · m1 |
| 데이터 | **D16-2(R3h)**: 발행 리비전마다 (이미 있는 행 묶음 ∪ 그 리비전 시나리오(행·점수 실행에 나온 것) × kind) 단위 → **전부 done=false** 표식(rows = 지금 행 수, shape 1). 행 수 추정 없음 — backfill 이 단위마다 빠진 키만 채우고 완료로 닫는다(이미 있는 행 바이트 그대로, 출처 서랍은 D15-2 범위로 빠진 id). 행이 전혀 없는 발행 리비전은 표식 없음(backfill 이 지금 시나리오 전부로 만든다) | D15-3 · D16-2 |

downgrade: snapshot_view_unit 삭제, shape_version·publish_lease 열 삭제(0011 은 표식 없이 '종류 행 하나라도 있으면 완료'로 읽는다).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
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
    "provenance",
    "claims",
)
NO_SCENARIO_KINDS = ("changes", "claims", "provenance")
SCENARIO_KINDS = tuple(k for k in KINDS if k not in NO_SCENARIO_KINDS)
SHAPE_0012 = 1
"""이 마이그레이션이 기존 행에 붙이는 저장 모양 버전(.11 행 = 모양 1 — 식별 변환)."""


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN (" + ", ".join("'" + v + "'" for v in values) + ")"


def upgrade() -> None:
    op.create_table(
        "snapshot_view_unit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.Integer(),
            sa.ForeignKey("snapshot.id", name=op.f("fk_snapshot_view_unit_snapshot_id_snapshot")),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("scenario", sa.String(length=16), server_default="", nullable=False),
        sa.Column("shape_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("done", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.CheckConstraint(_in("kind", KINDS), name=op.f("ck_snapshot_view_unit_kind")),
        sa.UniqueConstraint(
            "snapshot_id", "kind", "scenario", name=op.f("uq_snapshot_view_unit_snapshot_id_kind_scenario")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_snapshot_view_unit")),
    )
    op.create_index(op.f("ix_snapshot_view_unit_snapshot_id"), "snapshot_view_unit", ["snapshot_id"])
    op.add_column(
        "snapshot_view", sa.Column("shape_version", sa.Integer(), server_default="1", nullable=False)
    )
    op.add_column("snapshot", sa.Column("publish_lease", sa.String(length=80), nullable=True))

    # 데이터: 발행 리비전의 단위(기존 행 묶음 ∪ 그 리비전 시나리오 × kind) = 전부 미완 표식(backfill 몫, D16-2)
    conn = op.get_bind()
    groups: dict[int, dict[tuple[str, str], int]] = {}
    for sid, kind, scen, n in conn.execute(
        sa.text(
            "SELECT v.snapshot_id, v.kind, v.scenario, COUNT(*) FROM snapshot_view v "
            "JOIN snapshot s ON s.id = v.snapshot_id WHERE s.status = 'published' "
            "GROUP BY v.snapshot_id, v.kind, v.scenario"
        )
    ):
        groups.setdefault(int(sid), {})[(str(kind), str(scen or ""))] = int(n)
    unit = sa.table(
        "snapshot_view_unit",
        sa.column("snapshot_id", sa.Integer()),
        sa.column("kind", sa.String()),
        sa.column("scenario", sa.String()),
        sa.column("shape_version", sa.Integer()),
        sa.column("rows", sa.Integer()),
        sa.column("done", sa.Boolean()),
    )
    rows: list[dict[str, object]] = []
    for sid, present in sorted(groups.items()):
        # D16-2(R3h, R3 8차 N-M1·N-M2): 0012 이전에 만든 단위는 **전부 미완**(done=false)으로 표시한다 — 행 수를 추정하지
        # 않는다(예전: 시나리오 사이 최대 행 수·서랍 색인 묶음 수로 done 을 정해 일부만 쓴 기본 시나리오 단위·.11 범위 서랍이
        # 완료로 남았다). backfill 이 단위마다 빠진 키만 채우고(이미 있는 행 바이트 그대로) 완료로 닫는다
        scenarios = {s for (_k, s) in present if s}
        scenarios |= {
            str(i)
            for i in conn.execute(
                sa.text("SELECT DISTINCT scenario_id FROM score_run WHERE snapshot_id = :sid").bindparams(
                    sid=sid
                )
            ).scalars()
            if i is not None
        }
        expected = {(k, "") for k in NO_SCENARIO_KINDS} | {(k, s) for k in SCENARIO_KINDS for s in scenarios}
        for kind, scen in sorted(expected | set(present)):
            rows.append(
                {
                    "snapshot_id": sid,
                    "kind": kind,
                    "scenario": scen,
                    "shape_version": SHAPE_0012,
                    "rows": present.get((kind, scen), 0),
                    "done": False,
                }
            )
    if rows:
        op.bulk_insert(unit, rows)


def downgrade() -> None:
    op.drop_column("snapshot", "publish_lease")
    op.drop_column("snapshot_view", "shape_version")
    op.drop_index(op.f("ix_snapshot_view_unit_snapshot_id"), table_name="snapshot_view_unit")
    op.drop_table("snapshot_view_unit")

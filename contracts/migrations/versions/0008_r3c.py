"""0008 r3c — 계약 2026-10-09.8 (R3c CORE, DECISIONS D11)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-10

계약 마이그레이션 — 계약 .8 소유자(R3c CORE)가 추가한다. contracts/CHANGELOG.md 2026-10-09.8 항목.

| 변경 | 내용 | 결정·리뷰 |
| --- | --- | --- |
| snapshot.revision · revision_of · revision_reason | 같은 기준일 스냅샷 리비전(1부터). 유일 (region_id, asof_date) → (region_id, asof_date, revision). 발행 스냅샷은 불변 — 발행 후 재판정은 새 리비전 | D11-1 · M-2 |
| fact_demotion.value_norm | 강등한 모순 값의 정준 문자열(field_provenance.value_norm). chosen 값이 이 값과 같은 동안 읽기 시점 오버레이로 강등 | D11-3 · C-3 · C-4 |
| human_check.entity · entity_id | 사람 확인이 가리키는 사실 행(resolver 0순위 후보) | D11-3 · minor 10 |
| checklist_item.closed_by | 'auto'(동기화가 닫음 — 근거가 돌아오면 다시 연다) / 'human'(사람 처리) / NULL | M-9 |
| payment_terms.discount_by_type | 공고에 명시된 할인(타입별 {type_code: 원}, 금액 정수). 이름은 컬럼 형 정책(*_won = BigInteger) 때문에 초안의 discount_won 대신 | D11-6 |
| catalyst_link.label · reason | 연결 라벨(추정)·근거(같은 생활권·단지 지정·좌표 거리) | D11-5 |
| catalyst.stage CHECK | '호재 아님' 추가(판정 결과 보존 — 삭제하지 않는다) | D11-2 · M-10 |
| job_run.job_name CHECK | 'backup'·'region.expand' 추가 | D11-8 · D11-7 |

SQLite 는 CHECK·유일 제약을 ALTER 로 못 바꾸므로 batch 모드(재생성 정의 고정 — 0004·0006 과 같은 방식).

downgrade: 리비전 2 이상 스냅샷이 있으면 (region_id, asof_date) 유일을 되돌릴 수 없다 → 그 리비전 행과 파생 행을 지우지 않고
**실패**시킨다(데이터 손실 방지). '호재 아님' catalyst 는 '미확정'으로, 새 잡 이름 행은 지운다(대기 잡). 나머지는 컬럼 삭제.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JOB_NAMES_0004 = (
    "collect.daily",
    "collect.weekly",
    "rejudge",
    "report",
    "snapshot.publish",
    "reference.refresh",
    "region.bootstrap",
    "claim.reverify",
)
JOB_NAMES_0008 = (*JOB_NAMES_0004, "backup", "region.expand")
STAGES_0001 = ("확정", "계획", "추진", "언론", "미확정")
STAGES_0008 = (*STAGES_0001, "호재 아님")
CLOSED_BY = ("auto", "human")
LABELS = ("확인됨", "추정", "비공식", "재가공", "확인 불가")


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _job_run_table(job_names: Sequence[str]) -> sa.Table:
    """SQLite 재생성용 job_run 정의(0004 와 같고 job_name CHECK 값만 인자)."""
    return sa.Table(
        "job_run",
        sa.MetaData(),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_name", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("scheduled_at", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.String(length=32), nullable=True),
        sa.Column("finished_at", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="queued", nullable=False),
        sa.Column("stats", sa.JSON(), nullable=False),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("locked_by", sa.String(length=64), nullable=True),
        sa.Column("progress", sa.JSON(), nullable=True),
        sa.CheckConstraint(_in("job_name", job_names), name="ck_job_run_job_name"),
        sa.CheckConstraint("kind IN ('scheduled', 'manual', 'rejudge')", name="ck_job_run_kind"),
        sa.CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="ck_job_run_status"),
        sa.PrimaryKeyConstraint("id", name="pk_job_run"),
        sa.Index("ix_job_run_status_scheduled_at", "status", "scheduled_at"),
    )


def _catalyst_table(stages: Sequence[str]) -> sa.Table:
    """SQLite 재생성용 catalyst 정의(0001 과 같고 stage CHECK 값만 인자)."""
    meta = sa.MetaData()
    sa.Table("region", meta, sa.Column("id", sa.Integer(), primary_key=True))
    sa.Table("raw_document", meta, sa.Column("id", sa.Integer(), primary_key=True))
    return sa.Table(
        "catalyst",
        meta,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("stage", sa.String(length=8), nullable=False),
        sa.Column("stage_prob", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("decision", sa.String(length=16), nullable=True),
        sa.Column("expected_ym", sa.String(length=7), nullable=True),
        sa.Column("location_confirmed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("lat", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("lon", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("raw_document_id", sa.Integer(), nullable=True),
        sa.Column("judgment_seq", sa.Integer(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint("decision IN ('auto', 'review', 'manual_review')", name="ck_catalyst_decision"),
        sa.CheckConstraint("kind IN ('교통', '개발', '학교', '상업', '생활인프라', '기타')", name="ck_catalyst_kind"),
        sa.CheckConstraint(_in("stage", stages), name="ck_catalyst_stage"),
        sa.ForeignKeyConstraint(
            ["raw_document_id"], ["raw_document.id"], name="fk_catalyst_raw_document_id_raw_document"
        ),
        sa.ForeignKeyConstraint(["region_id"], ["region.id"], name="fk_catalyst_region_id_region"),
        sa.PrimaryKeyConstraint("id", name="pk_catalyst"),
        sa.Index("ix_catalyst_region_id", "region_id"),
    )


def _snapshot_table(*, revision: bool) -> sa.Table:
    """SQLite 재생성용 snapshot 정의(0001 + 리비전 컬럼 유무)."""
    meta = sa.MetaData()
    sa.Table("region", meta, sa.Column("id", sa.Integer(), primary_key=True))
    cols: list[sa.schema.SchemaItem] = [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("asof_date", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("degraded", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("published_at", sa.String(length=32), nullable=True),
        sa.CheckConstraint("status IN ('building', 'ready', 'published')", name="ck_snapshot_status"),
        sa.ForeignKeyConstraint(["region_id"], ["region.id"], name="fk_snapshot_region_id_region"),
        sa.PrimaryKeyConstraint("id", name="pk_snapshot"),
        sa.Index("ix_snapshot_region_id", "region_id"),
    ]
    if revision:
        cols += [
            sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
            sa.Column("revision_of", sa.Integer(), nullable=True),
            sa.Column("revision_reason", sa.String(length=200), nullable=True),
            sa.ForeignKeyConstraint(["revision_of"], ["snapshot.id"], name="fk_snapshot_revision_of_snapshot"),
            sa.UniqueConstraint(
                "region_id", "asof_date", "revision", name="uq_snapshot_region_id_asof_date_revision"
            ),
        ]
    else:
        cols.append(sa.UniqueConstraint("region_id", "asof_date", name="uq_snapshot_region_id_asof_date"))
    return sa.Table("snapshot", meta, *cols)


def _checklist_table(*, closed_by: bool) -> sa.Table:
    meta = sa.MetaData()
    sa.Table("complex", meta, sa.Column("id", sa.Integer(), primary_key=True))
    kinds = ("법적 확인", "중도금", "만료", "공고 예상", "계약", "사실 재확인")
    cols: list[sa.schema.SchemaItem] = [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("complex_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("due_date", sa.String(length=10), nullable=True),
        sa.Column("status", sa.String(length=8), server_default="open", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(_in("kind", kinds), name="ck_checklist_item_kind"),
        sa.CheckConstraint("status IN ('open', 'done', 'na')", name="ck_checklist_item_status"),
        sa.ForeignKeyConstraint(["complex_id"], ["complex.id"], name="fk_checklist_item_complex_id_complex"),
        sa.PrimaryKeyConstraint("id", name="pk_checklist_item"),
    ]
    if closed_by:
        cols += [
            sa.Column("closed_by", sa.String(length=8), nullable=True),
            sa.CheckConstraint(_in("closed_by", CLOSED_BY), name="ck_checklist_item_closed_by"),
        ]
    return sa.Table("checklist_item", meta, *cols)


def upgrade() -> None:
    # D11-1 스냅샷 리비전: 기존 행은 리비전 1
    with op.batch_alter_table("snapshot", copy_from=_snapshot_table(revision=False)) as batch:
        batch.add_column(sa.Column("revision", sa.Integer(), server_default="1", nullable=False))
        batch.add_column(sa.Column("revision_of", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("revision_reason", sa.String(length=200), nullable=True))
        batch.drop_constraint(op.f("uq_snapshot_region_id_asof_date"), type_="unique")
        batch.create_unique_constraint(
            "uq_snapshot_region_id_asof_date_revision", ["region_id", "asof_date", "revision"]
        )
        batch.create_foreign_key(op.f("fk_snapshot_revision_of_snapshot"), "snapshot", ["revision_of"], ["id"])
    # D11-3 강등 오버레이: 모순 값. 기존 행은 원래 chosen 출처 행의 value_norm 으로 채운다
    with op.batch_alter_table("fact_demotion") as batch:
        batch.add_column(sa.Column("value_norm", sa.Text(), nullable=True))
    bind = op.get_bind()
    rows = list(
        bind.execute(
            sa.text(
                "SELECT d.id, fp.value_norm FROM fact_demotion d "
                "JOIN field_provenance fp ON fp.id = d.original_fp_id WHERE fp.value_norm IS NOT NULL"
            )
        )
    )
    for did, vn in rows:
        bind.execute(sa.text("UPDATE fact_demotion SET value_norm = :v WHERE id = :i"), {"v": vn, "i": did})
    with op.batch_alter_table("human_check") as batch:
        batch.add_column(sa.Column("entity", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("entity_id", sa.Integer(), nullable=True))
    with op.batch_alter_table("checklist_item", copy_from=_checklist_table(closed_by=False)) as batch:
        batch.add_column(sa.Column("closed_by", sa.String(length=8), nullable=True))
        batch.create_check_constraint(op.f("ck_checklist_item_closed_by"), sa.text(_in("closed_by", CLOSED_BY)))
    with op.batch_alter_table("payment_terms") as batch:
        batch.add_column(sa.Column("discount_by_type", sa.JSON(), nullable=True))
    with op.batch_alter_table("catalyst_link") as batch:
        batch.add_column(sa.Column("label", sa.String(length=8), nullable=True))
        batch.add_column(sa.Column("reason", sa.String(length=120), nullable=True))
        batch.create_check_constraint(op.f("ck_catalyst_link_label"), sa.text(_in("label", LABELS)))
    with op.batch_alter_table("catalyst", copy_from=_catalyst_table(STAGES_0001)) as batch:
        batch.drop_constraint(op.f("ck_catalyst_stage"), type_="check")
        batch.create_check_constraint(op.f("ck_catalyst_stage"), sa.text(_in("stage", STAGES_0008)))
    with op.batch_alter_table("job_run", copy_from=_job_run_table(JOB_NAMES_0004)) as batch:
        batch.drop_constraint(op.f("ck_job_run_job_name"), type_="check")
        batch.create_check_constraint(op.f("ck_job_run_job_name"), sa.text(_in("job_name", JOB_NAMES_0008)))


def downgrade() -> None:
    bind = op.get_bind()
    n = bind.execute(sa.text("SELECT COUNT(*) FROM snapshot WHERE revision > 1")).scalar() or 0
    if n:
        raise RuntimeError(
            f"리비전 2 이상 스냅샷 {n}개 — (region_id, asof_date) 유일로 되돌리면 발행 리비전이 사라진다. "
            "0008 downgrade 를 거부한다(데이터 손실 방지)"
        )
    op.execute(sa.text("DELETE FROM job_run WHERE job_name IN ('backup', 'region.expand')"))
    with op.batch_alter_table("job_run", copy_from=_job_run_table(JOB_NAMES_0008)) as batch:
        batch.drop_constraint(op.f("ck_job_run_job_name"), type_="check")
        batch.create_check_constraint(op.f("ck_job_run_job_name"), sa.text(_in("job_name", JOB_NAMES_0004)))
    op.execute(sa.text("UPDATE catalyst SET stage = '미확정' WHERE stage = '호재 아님'"))
    with op.batch_alter_table("catalyst", copy_from=_catalyst_table(STAGES_0008)) as batch:
        batch.drop_constraint(op.f("ck_catalyst_stage"), type_="check")
        batch.create_check_constraint(op.f("ck_catalyst_stage"), sa.text(_in("stage", STAGES_0001)))
    with op.batch_alter_table("catalyst_link") as batch:
        batch.drop_constraint(op.f("ck_catalyst_link_label"), type_="check")
        batch.drop_column("reason")
        batch.drop_column("label")
    with op.batch_alter_table("payment_terms") as batch:
        batch.drop_column("discount_by_type")
    with op.batch_alter_table("checklist_item", copy_from=_checklist_table(closed_by=True)) as batch:
        batch.drop_constraint(op.f("ck_checklist_item_closed_by"), type_="check")
        batch.drop_column("closed_by")
    with op.batch_alter_table("human_check") as batch:
        batch.drop_column("entity_id")
        batch.drop_column("entity")
    with op.batch_alter_table("fact_demotion") as batch:
        batch.drop_column("value_norm")
    with op.batch_alter_table("snapshot", copy_from=_snapshot_table(revision=True)) as batch:
        batch.drop_constraint(op.f("fk_snapshot_revision_of_snapshot"), type_="foreignkey")
        batch.drop_constraint(op.f("uq_snapshot_region_id_asof_date_revision"), type_="unique")
        batch.create_unique_constraint(op.f("uq_snapshot_region_id_asof_date"), ["region_id", "asof_date"])
        batch.drop_column("revision_reason")
        batch.drop_column("revision_of")
        batch.drop_column("revision")

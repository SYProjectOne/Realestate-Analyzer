"""0001 init — 계약 2026-10-09.1 초기 스키마 (RA §3 전부 + DECISIONS D2-1 참조 테이블 4개 + D2-2 region 컬럼).

Revision ID: 0001
Revises:
Create Date: 2026-10-09

원칙(RA §3): 금액 *_won = BigInteger(원), 면적 = Numeric(8,2)(㎡), 날짜 = ISO 문자열(String(10) 날짜 / String(7) 연월 /
String(32) 시각), json = sa.JSON, 열거 = 문자열 + CHECK. 유일 제약: judgment_log.input_hash(같은 입력 재호출 금지),
raw_document.sha256(같은 파일 중복 저장 금지), snapshot(region_id, asof_date)(하루 1개), complex.applyhome_id 등.
RA §3 밖에 더한 컬럼은 contracts/CHANGELOG.md 2026-10-09.1 항목에 적었다.

SQLite·Postgres 16 둘 다에서 upgrade/downgrade가 돈다(CREATE/DROP만, 불리언 기본값은 sa.true()/sa.false()).
backend/app/models 와 1:1 — tests/contracts/test_migrations.py 가 autogenerate diff 0을 강제한다.
이 파일은 계약이다: 고치지 말고 새 리비전을 추가한다(오케스트레이터만).
"""

# ruff: noqa: E501  (CHECK 식의 열거 문자열은 한 줄로 둔다)
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 내장 시나리오 5개(RA §6-4 가중치 표 그대로, A·D는 liquidity → move_in). id는 삽입 순서대로 1~5.
BUILTIN_SCENARIOS: list[dict[str, Any]] = [
    {
        "code": "base",
        "name": "기본",
        "is_builtin": True,
        "params": {
            "residence": None,
            "homeless": True,
            "household_size": None,
            "subscription": None,
            "equity_won": None,
            "loan_limit_won": None,
            "purpose": "병행",
            "holding_years": None,
            "preferred_area_m2": 84,
            "move_in_by": None,
            "rewin_restricted": None,
            "accepts_residency_obligation": None,
        },
        "weights": {
            "p10": 0.35,
            "rerank": 0.2,
            "gap": 0.15,
            "benchmark": 0.1,
            "supply": 0.1,
            "liquidity": 0.1,
        },
        "requirements": {
            "access": {"code": "intake_open", "text": "공식 경로로 지금 접수 가능"},
            "regulation": {
                "code": "no_conflict",
                "text": "거주의무·재당첨 제한·규제지역 요건과 충돌 없음(입주 후 2년 내 매도 가능)",
            },
            "funds": {
                "code": "equity_and_loan",
                "text": "자기자본·대출한도로 계약금·잔금 충당(미입력이면 '미입력')",
            },
        },
        "policy": {"p10_horizon": "move_in_plus_1y", "exclude_intake_not_open": False},
        "created_at": "2026-10-09T00:00:00+09:00",
    },
    {
        "code": "A",
        "name": "A 가점 높음(실거주)",
        "is_builtin": True,
        "params": {
            "residence": None,
            "homeless": True,
            "household_size": None,
            "subscription": {"has_account": True, "score": 60},
            "equity_won": 300000000,
            "loan_limit_won": 600000000,
            "purpose": "실거주",
            "holding_years": None,
            "preferred_area_m2": 84,
            "move_in_by": None,
            "rewin_restricted": False,
            "accepts_residency_obligation": True,
        },
        "weights": {"p10": 0.35, "rerank": 0.2, "gap": 0.15, "benchmark": 0.1, "supply": 0.1, "move_in": 0.1},
        "requirements": {
            "access": {
                "code": "priority_supply",
                "text": "가점제 1순위 공급(본청약·예정 공고)으로 접근 가능",
            },
            "regulation": {"code": "no_conflict", "text": "거주의무·전매제한이 실거주 계획과 충돌 없음"},
            "funds": {
                "code": "equity_and_loan",
                "text": "자기자본 3억 이하로 계약금·잔금 충당",
                "params": {"equity_won": 300000000, "loan_limit_won": 600000000},
            },
        },
        "policy": {"p10_horizon": "move_in_plus_1y", "exclude_intake_not_open": False},
        "created_at": "2026-10-09T00:00:00+09:00",
    },
    {
        "code": "B",
        "name": "B 가점 낮음·소액 자기자본",
        "is_builtin": True,
        "params": {
            "residence": None,
            "homeless": True,
            "household_size": None,
            "subscription": {"has_account": None, "score": 20},
            "equity_won": 200000000,
            "loan_limit_won": 600000000,
            "purpose": "병행",
            "holding_years": 2,
            "preferred_area_m2": 84,
            "move_in_by": None,
            "rewin_restricted": None,
            "accepts_residency_obligation": False,
        },
        "weights": {
            "p10": 0.3,
            "rerank": 0.15,
            "gap": 0.2,
            "benchmark": 0.1,
            "supply": 0.1,
            "liquidity": 0.15,
        },
        "requirements": {
            "access": {
                "code": "official_path_no_account",
                "text": "통장 없이 공식 접수 경로(무순위·임의·선착순)로 접근 가능",
            },
            "regulation": {"code": "no_residency_obligation", "text": "거주의무 없음"},
            "funds": {
                "code": "equity_and_loan",
                "text": "자기자본 2억 이하로 계약금·잔금 충당",
                "params": {"equity_won": 200000000, "loan_limit_won": 600000000},
            },
        },
        "policy": {"p10_horizon": "move_in_plus_1y", "exclude_intake_not_open": False},
        "created_at": "2026-10-09T00:00:00+09:00",
    },
    {
        "code": "C",
        "name": "C 시세차익 우선",
        "is_builtin": True,
        "params": {
            "residence": None,
            "homeless": True,
            "household_size": None,
            "subscription": None,
            "equity_won": 400000000,
            "loan_limit_won": 600000000,
            "purpose": "시세차익",
            "holding_years": 5,
            "preferred_area_m2": 84,
            "move_in_by": None,
            "rewin_restricted": None,
            "accepts_residency_obligation": False,
        },
        "weights": {
            "p10": 0.45,
            "rerank": 0.15,
            "gap": 0.15,
            "benchmark": 0.05,
            "supply": 0.05,
            "liquidity": 0.15,
        },
        "requirements": {
            "access": {
                "code": "resale_before_exit",
                "text": "전매 종료 ≤ 목표 매도 시점(기준일 + 보유 5년)",
                "params": {"holding_years": 5},
            },
            "regulation": {"code": "no_residency_obligation", "text": "거주의무 없음"},
            "funds": {
                "code": "equity_and_loan",
                "text": "자기자본 4억 이하로 계약금·잔금 충당",
                "params": {"equity_won": 400000000, "loan_limit_won": 600000000},
            },
        },
        "policy": {"p10_horizon": "asof_plus_5y", "exclude_intake_not_open": False},
        "created_at": "2026-10-09T00:00:00+09:00",
    },
    {
        "code": "D",
        "name": "D 즉시 구매",
        "is_builtin": True,
        "params": {
            "residence": None,
            "homeless": True,
            "household_size": None,
            "subscription": None,
            "equity_won": 300000000,
            "loan_limit_won": 600000000,
            "purpose": "병행",
            "holding_years": None,
            "preferred_area_m2": 84,
            "move_in_by": None,
            "rewin_restricted": None,
            "accepts_residency_obligation": False,
        },
        "weights": {"p10": 0.35, "rerank": 0.2, "gap": 0.15, "benchmark": 0.1, "supply": 0.1, "move_in": 0.1},
        "requirements": {
            "access": {"code": "official_path", "text": "공식 접수 경로로 지금 계약 가능"},
            "regulation": {"code": "no_residency_obligation", "text": "거주의무 없음"},
            "funds": {
                "code": "equity_and_loan",
                "text": "자기자본 3억 이하로 계약금·잔금 충당",
                "params": {"equity_won": 300000000, "loan_limit_won": 600000000},
            },
        },
        "policy": {"p10_horizon": "move_in_plus_1y", "exclude_intake_not_open": True},
        "created_at": "2026-10-09T00:00:00+09:00",
    },
]


def upgrade() -> None:
    op.create_table(
        "admin_dong",
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("sigungu_code", sa.String(length=5), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("source_date", sa.String(length=10), nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_admin_dong")),
    )
    op.create_index(op.f("ix_admin_dong_sigungu_code"), "admin_dong", ["sigungu_code"], unique=False)

    op.create_table(
        "admin_legal_map",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("admin_code", sa.String(length=10), nullable=False),
        sa.Column("legal_code", sa.String(length=10), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_legal_map")),
        sa.UniqueConstraint(
            "admin_code", "legal_code", name=op.f("uq_admin_legal_map_admin_code_legal_code")
        ),
    )
    op.create_index(op.f("ix_admin_legal_map_admin_code"), "admin_legal_map", ["admin_code"], unique=False)
    op.create_index(op.f("ix_admin_legal_map_legal_code"), "admin_legal_map", ["legal_code"], unique=False)

    op.create_table(
        "job_run",
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
        sa.CheckConstraint(
            "job_name IN ('collect.daily', 'collect.weekly', 'rejudge', 'report', 'snapshot.publish', 'reference.refresh', 'region.bootstrap')",
            name=op.f("ck_job_run_job_name"),
        ),
        sa.CheckConstraint("kind IN ('scheduled', 'manual', 'rejudge')", name=op.f("ck_job_run_kind")),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')", name=op.f("ck_job_run_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_run")),
    )
    op.create_index(
        op.f("ix_job_run_status_scheduled_at"), "job_run", ["status", "scheduled_at"], unique=False
    )

    op.create_table(
        "legal_dong",
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("sido_name", sa.String(length=40), nullable=False),
        sa.Column("sigungu_name", sa.String(length=40), nullable=True),
        sa.Column("eupmyeondong_name", sa.String(length=40), nullable=True),
        sa.Column("ri_name", sa.String(length=40), nullable=True),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("sigungu_code", sa.String(length=5), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("source_date", sa.String(length=10), nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_legal_dong")),
    )
    op.create_index(op.f("ix_legal_dong_sigungu_code"), "legal_dong", ["sigungu_code"], unique=False)

    op.create_table(
        "region",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("selections", sa.JSON(), nullable=False),
        sa.Column("sido_codes", sa.JSON(), nullable=False),
        sa.Column("sigungu_codes", sa.JSON(), nullable=False),
        sa.Column("legal_dong_codes", sa.JSON(), nullable=False),
        sa.Column("living_areas", sa.JSON(), nullable=False),
        sa.Column("age_premium_coef", sa.JSON(), nullable=False),
        sa.Column("supply_ref_pct", sa.Numeric(precision=5, scale=4), server_default="0.08", nullable=False),
        sa.Column("applyhome_query", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "status IN ('resolving', 'bootstrapping', 'ready', 'failed')", name=op.f("ck_region_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_region")),
    )
    op.create_table(
        "scenario",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=8), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_builtin", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("weights", sa.JSON(), nullable=False),
        sa.Column("requirements", sa.JSON(), nullable=False),
        sa.Column("policy", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.CheckConstraint("code IN ('base', 'A', 'B', 'C', 'D')", name=op.f("ck_scenario_code")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scenario")),
        sa.UniqueConstraint("code", name=op.f("uq_scenario_code")),
    )
    op.create_table(
        "benchmark",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("living_area", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("completed_year", sa.Integer(), nullable=True),
        sa.Column("sale_year", sa.Integer(), nullable=True),
        sa.Column("sale_period", sa.String(length=16), nullable=True),
        sa.Column("sale_price_84_won", sa.BigInteger(), nullable=True),
        sa.Column("sale_price_label", sa.String(length=8), nullable=True),
        sa.Column("trade_low_won", sa.BigInteger(), nullable=True),
        sa.Column("trade_median_won", sa.BigInteger(), nullable=True),
        sa.Column("trade_high_won", sa.BigInteger(), nullable=True),
        sa.Column("trade_window", sa.String(length=32), nullable=True),
        sa.Column("n_trades", sa.Integer(), nullable=True),
        sa.Column("peak_won", sa.BigInteger(), nullable=True),
        sa.Column("peak_ym", sa.String(length=7), nullable=True),
        sa.Column("is_presale", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "sale_period IN ('저가 분양기', '고가 분양기')", name=op.f("ck_benchmark_sale_period")
        ),
        sa.CheckConstraint(
            "sale_price_label IN ('확인됨', '추정', '비공식', '재가공', '확인 불가')",
            name=op.f("ck_benchmark_sale_price_label"),
        ),
        sa.ForeignKeyConstraint(["region_id"], ["region.id"], name=op.f("fk_benchmark_region_id_region")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_benchmark")),
    )
    op.create_index(op.f("ix_benchmark_region_id"), "benchmark", ["region_id"], unique=False)

    op.create_table(
        "complex",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("applyhome_id", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("former_names", sa.JSON(), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("legal_dong_code", sa.String(length=10), nullable=True),
        sa.Column("living_area", sa.String(length=64), nullable=True),
        sa.Column("official_site_url", sa.Text(), nullable=True),
        sa.Column("developer", sa.String(length=200), nullable=True),
        sa.Column("trustee", sa.String(length=200), nullable=True),
        sa.Column("builder", sa.String(length=200), nullable=True),
        sa.Column("housing_type", sa.String(length=8), nullable=True),
        sa.Column("land_type", sa.String(length=8), nullable=True),
        sa.Column("price_cap", sa.String(length=8), nullable=True),
        sa.Column("regulated", sa.String(length=8), nullable=True),
        sa.Column("units_total", sa.Integer(), nullable=True),
        sa.Column("units_general", sa.Integer(), nullable=True),
        sa.Column("units_special", sa.Integer(), nullable=True),
        sa.Column("officetel_units", sa.Integer(), nullable=True),
        sa.Column("notice_date", sa.String(length=10), nullable=True),
        sa.Column("apply_dates", sa.JSON(), nullable=False),
        sa.Column("winner_date", sa.String(length=10), nullable=True),
        sa.Column("contract_dates", sa.JSON(), nullable=False),
        sa.Column("move_in_ym", sa.String(length=7), nullable=True),
        sa.Column("resale_months", sa.Integer(), nullable=True),
        sa.Column("resale_release_on_registration", sa.Boolean(), nullable=True),
        sa.Column("residency_months", sa.Integer(), nullable=True),
        sa.Column("rewin_restriction_years", sa.Integer(), nullable=True),
        sa.Column("inclusion_class", sa.String(length=32), server_default="미분류", nullable=False),
        sa.Column("inclusion_decision", sa.String(length=16), nullable=True),
        sa.Column("inclusion_prob", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("inclusion_judgment_seq", sa.Integer(), nullable=True),
        sa.Column("track", sa.String(length=1), nullable=True),
        sa.CheckConstraint("housing_type IN ('민영', '국민')", name=op.f("ck_complex_housing_type")),
        sa.CheckConstraint(
            "inclusion_class IN ('private_sale_apt', 'public_sale', 'public_rental', 'private_rental', 'non_apartment', 'out_of_scope', 'manual_review', '범위 경계', '미분류')",
            name=op.f("ck_complex_inclusion_class"),
        ),
        sa.CheckConstraint(
            "inclusion_decision IN ('auto', 'review', 'manual_review')",
            name=op.f("ck_complex_inclusion_decision"),
        ),
        sa.CheckConstraint("land_type IN ('공공택지', '민간택지')", name=op.f("ck_complex_land_type")),
        sa.CheckConstraint("price_cap IN ('적용', '미적용')", name=op.f("ck_complex_price_cap")),
        sa.CheckConstraint("regulated IN ('규제', '비규제')", name=op.f("ck_complex_regulated")),
        sa.CheckConstraint("track IN ('A', 'B')", name=op.f("ck_complex_track")),
        sa.ForeignKeyConstraint(["region_id"], ["region.id"], name=op.f("fk_complex_region_id_region")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_complex")),
        sa.UniqueConstraint("applyhome_id", name=op.f("uq_complex_applyhome_id")),
    )
    op.create_index(op.f("ix_complex_legal_dong_code"), "complex", ["legal_dong_code"], unique=False)
    op.create_index(op.f("ix_complex_region_id"), "complex", ["region_id"], unique=False)

    op.create_table(
        "snapshot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("asof_date", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("degraded", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("published_at", sa.String(length=32), nullable=True),
        sa.CheckConstraint("status IN ('building', 'ready', 'published')", name=op.f("ck_snapshot_status")),
        sa.ForeignKeyConstraint(["region_id"], ["region.id"], name=op.f("fk_snapshot_region_id_region")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_snapshot")),
        sa.UniqueConstraint("region_id", "asof_date", name=op.f("uq_snapshot_region_id_asof_date")),
    )
    op.create_index(op.f("ix_snapshot_region_id"), "snapshot", ["region_id"], unique=False)

    op.create_table(
        "change_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=True),
        sa.Column("entity", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("field", sa.String(length=64), nullable=False),
        sa.Column("old_text", sa.Text(), nullable=True),
        sa.Column("new_text", sa.Text(), nullable=True),
        sa.Column("detected_at", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=8), nullable=False),
        sa.Column("triggers_rejudge", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("complex_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "entity IN ('complex', 'complex_type', 'payment_terms', 'competition', 'remaining_event', 'intake_status', 'region', 'judge', 'catalyst', 'benchmark', 'supply', 'unsold', 'rtms_trade', 'checklist_item', 'notice')",
            name=op.f("ck_change_event_entity"),
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'notice', 'critical')", name=op.f("ck_change_event_severity")
        ),
        sa.ForeignKeyConstraint(
            ["complex_id"], ["complex.id"], name=op.f("fk_change_event_complex_id_complex")
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["snapshot.id"], name=op.f("fk_change_event_snapshot_id_snapshot")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change_event")),
    )
    op.create_index(op.f("ix_change_event_snapshot_id"), "change_event", ["snapshot_id"], unique=False)

    op.create_table(
        "checklist_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("complex_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("due_date", sa.String(length=10), nullable=True),
        sa.Column("status", sa.String(length=8), server_default="open", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('법적 확인', '중도금', '만료', '공고 예상')", name=op.f("ck_checklist_item_kind")
        ),
        sa.CheckConstraint("status IN ('open', 'done', 'na')", name=op.f("ck_checklist_item_status")),
        sa.ForeignKeyConstraint(
            ["complex_id"], ["complex.id"], name=op.f("fk_checklist_item_complex_id_complex")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_checklist_item")),
    )
    op.create_table(
        "comparable_set",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("complex_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("member_apt_name", sa.String(length=200), nullable=False),
        sa.Column("completed_year", sa.Integer(), nullable=True),
        sa.Column("substitute", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("adjusted", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("coef_used", sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column("n_trades", sa.Integer(), nullable=True),
        sa.Column("low_won", sa.BigInteger(), nullable=True),
        sa.Column("median_won", sa.BigInteger(), nullable=True),
        sa.Column("adjusted_median_won", sa.BigInteger(), nullable=True),
        sa.Column("high_won", sa.BigInteger(), nullable=True),
        sa.Column("outliers_excluded", sa.Integer(), nullable=True),
        sa.Column("excluded_reason", sa.String(length=64), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["complex_id"], ["complex.id"], name=op.f("fk_comparable_set_complex_id_complex")
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["snapshot.id"], name=op.f("fk_comparable_set_snapshot_id_snapshot")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comparable_set")),
    )
    op.create_index(
        op.f("ix_comparable_set_snapshot_id_complex_id"),
        "comparable_set",
        ["snapshot_id", "complex_id"],
        unique=False,
    )

    op.create_table(
        "complex_type",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("complex_id", sa.Integer(), nullable=False),
        sa.Column("type_code", sa.String(length=16), nullable=False),
        sa.Column("area_m2", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("units", sa.Integer(), nullable=True),
        sa.Column("max_price_won", sa.BigInteger(), nullable=True),
        sa.Column("floor_sample_price_won", sa.BigInteger(), nullable=True),
        sa.Column("floor_sample_text", sa.Text(), nullable=True),
        sa.Column("balcony_won", sa.BigInteger(), nullable=True),
        sa.Column("options_required_won", sa.BigInteger(), nullable=True),
        sa.Column("options_text", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["complex_id"], ["complex.id"], name=op.f("fk_complex_type_complex_id_complex")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_complex_type")),
        sa.UniqueConstraint("complex_id", "type_code", name=op.f("uq_complex_type_complex_id_type_code")),
    )
    op.create_index(op.f("ix_complex_type_complex_id"), "complex_type", ["complex_id"], unique=False)

    op.create_table(
        "human_check",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("complex_id", sa.Integer(), nullable=False),
        sa.Column("field", sa.String(length=64), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("checked_at", sa.String(length=32), nullable=False),
        sa.Column("entered_by", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=True),
        sa.CheckConstraint("kind IN ('phone', 'visit', 'email')", name=op.f("ck_human_check_kind")),
        sa.ForeignKeyConstraint(
            ["complex_id"], ["complex.id"], name=op.f("fk_human_check_complex_id_complex")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_human_check")),
    )
    op.create_index(op.f("ix_human_check_complex_id"), "human_check", ["complex_id"], unique=False)

    op.create_table(
        "judgment_log",
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=True),
        sa.Column("tool", sa.String(length=16), nullable=False),
        sa.Column("purpose", sa.String(length=128), nullable=False),
        sa.Column("complex_id", sa.Integer(), nullable=True),
        sa.Column("input_hash", sa.String(length=71), nullable=False),
        sa.Column("input_len", sa.Integer(), nullable=True),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("output_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("adapter_version", sa.String(length=64), nullable=False),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('ok', 'review', 'escaped', 'blocked', 'error')", name=op.f("ck_judgment_log_status")
        ),
        sa.CheckConstraint(
            "tool IN ('screen', 'extract', 'audit', 'classify', 'compare', 'noul', 'rerank', 'decide', 'verify')",
            name=op.f("ck_judgment_log_tool"),
        ),
        sa.ForeignKeyConstraint(
            ["complex_id"], ["complex.id"], name=op.f("fk_judgment_log_complex_id_complex")
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["snapshot.id"], name=op.f("fk_judgment_log_snapshot_id_snapshot")
        ),
        sa.PrimaryKeyConstraint("seq", name=op.f("pk_judgment_log")),
        sa.UniqueConstraint("input_hash", name=op.f("uq_judgment_log_input_hash")),
    )
    op.create_index(op.f("ix_judgment_log_complex_id"), "judgment_log", ["complex_id"], unique=False)
    op.create_index(op.f("ix_judgment_log_snapshot_id"), "judgment_log", ["snapshot_id"], unique=False)

    op.create_table(
        "payment_terms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("complex_id", sa.Integer(), nullable=False),
        sa.Column("notice_no", sa.String(length=32), nullable=False),
        sa.Column("notice_kind", sa.String(length=8), nullable=True),
        sa.Column("effective_from", sa.String(length=10), nullable=False),
        sa.Column("down_payment_pct", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("down_payment_first_won", sa.BigInteger(), nullable=True),
        sa.Column("interim_pct", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("interim_terms_text", sa.Text(), nullable=True),
        sa.Column("balance_pct", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("interim_schedule", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "notice_kind IN ('본청약', '무순위', '임의', '선착순')", name=op.f("ck_payment_terms_notice_kind")
        ),
        sa.ForeignKeyConstraint(
            ["complex_id"], ["complex.id"], name=op.f("fk_payment_terms_complex_id_complex")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_terms")),
        sa.UniqueConstraint("complex_id", "notice_no", name=op.f("uq_payment_terms_complex_id_notice_no")),
    )
    op.create_index(op.f("ix_payment_terms_complex_id"), "payment_terms", ["complex_id"], unique=False)

    op.create_table(
        "raw_document",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_kind", sa.String(length=24), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.String(length=32), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("text_path", sa.Text(), nullable=True),
        sa.Column("complex_id", sa.Integer(), nullable=True),
        sa.Column("region_id", sa.Integer(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("image_hash", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "source_kind IN ('applyhome_list', 'applyhome_detail', 'notice_pdf', 'official_site', 'rtms', 'stats', 'news', 'reference')",
            name=op.f("ck_raw_document_source_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["complex_id"], ["complex.id"], name=op.f("fk_raw_document_complex_id_complex")
        ),
        sa.ForeignKeyConstraint(["region_id"], ["region.id"], name=op.f("fk_raw_document_region_id_region")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_raw_document")),
        sa.UniqueConstraint("sha256", name=op.f("uq_raw_document_sha256")),
    )
    op.create_index(op.f("ix_raw_document_complex_id"), "raw_document", ["complex_id"], unique=False)

    op.create_table(
        "catalyst",
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
        sa.CheckConstraint(
            "decision IN ('auto', 'review', 'manual_review')", name=op.f("ck_catalyst_decision")
        ),
        sa.CheckConstraint(
            "kind IN ('교통', '개발', '학교', '상업', '생활인프라', '기타')", name=op.f("ck_catalyst_kind")
        ),
        sa.CheckConstraint(
            "stage IN ('확정', '계획', '추진', '언론', '미확정')", name=op.f("ck_catalyst_stage")
        ),
        sa.ForeignKeyConstraint(
            ["raw_document_id"], ["raw_document.id"], name=op.f("fk_catalyst_raw_document_id_raw_document")
        ),
        sa.ForeignKeyConstraint(["region_id"], ["region.id"], name=op.f("fk_catalyst_region_id_region")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalyst")),
    )
    op.create_index(op.f("ix_catalyst_region_id"), "catalyst", ["region_id"], unique=False)

    op.create_table(
        "claim",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(length=32), nullable=False),
        sa.Column("complex_id", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("verify_status", sa.String(length=16), nullable=True),
        sa.Column("judgment_seq", sa.Integer(), nullable=True),
        sa.Column("parent_claim_id", sa.Integer(), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "verify_status IN ('verified', 'contradicted', 'unsupported', 'review')",
            name=op.f("ck_claim_verify_status"),
        ),
        sa.ForeignKeyConstraint(["complex_id"], ["complex.id"], name=op.f("fk_claim_complex_id_complex")),
        sa.ForeignKeyConstraint(
            ["judgment_seq"], ["judgment_log.seq"], name=op.f("fk_claim_judgment_seq_judgment_log")
        ),
        sa.ForeignKeyConstraint(
            ["parent_claim_id"], ["claim.id"], name=op.f("fk_claim_parent_claim_id_claim")
        ),
        sa.ForeignKeyConstraint(["snapshot_id"], ["snapshot.id"], name=op.f("fk_claim_snapshot_id_snapshot")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_claim")),
    )
    op.create_index(op.f("ix_claim_snapshot_id"), "claim", ["snapshot_id"], unique=False)

    op.create_table(
        "competition",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("complex_id", sa.Integer(), nullable=False),
        sa.Column("round", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("type_code", sa.String(length=16), nullable=False),
        sa.Column("supply", sa.Integer(), nullable=True),
        sa.Column("applied", sa.Integer(), nullable=True),
        sa.Column("ratio_or_shortfall_text", sa.String(length=64), nullable=True),
        sa.Column("raw_document_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('본청약', '무순위', '임의', '선착순')", name=op.f("ck_competition_kind")
        ),
        sa.ForeignKeyConstraint(
            ["complex_id"], ["complex.id"], name=op.f("fk_competition_complex_id_complex")
        ),
        sa.ForeignKeyConstraint(
            ["raw_document_id"], ["raw_document.id"], name=op.f("fk_competition_raw_document_id_raw_document")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_competition")),
        sa.UniqueConstraint(
            "complex_id",
            "kind",
            "round",
            "type_code",
            name=op.f("uq_competition_complex_id_kind_round_type_code"),
        ),
    )
    op.create_index(op.f("ix_competition_complex_id"), "competition", ["complex_id"], unique=False)

    op.create_table(
        "field_provenance",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entity", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("entity_key", sa.String(length=64), nullable=True),
        sa.Column("field", sa.String(length=64), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("raw_document_id", sa.Integer(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.String(length=32), nullable=True),
        sa.Column("label", sa.String(length=8), nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=True),
        sa.Column("source_rank", sa.Integer(), nullable=False),
        sa.Column("chosen", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("conflict_group", sa.String(length=128), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("excerpt_start", sa.Integer(), nullable=True),
        sa.Column("excerpt_end", sa.Integer(), nullable=True),
        sa.Column("compare_judgment_seq", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "label IN ('확인됨', '추정', '비공식', '재가공', '확인 불가')",
            name=op.f("ck_field_provenance_label"),
        ),
        sa.ForeignKeyConstraint(
            ["raw_document_id"],
            ["raw_document.id"],
            name=op.f("fk_field_provenance_raw_document_id_raw_document"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_field_provenance")),
    )
    op.create_index(
        op.f("ix_field_provenance_conflict_group"), "field_provenance", ["conflict_group"], unique=False
    )
    op.create_index(
        op.f("ix_field_provenance_entity_entity_id_field"),
        "field_provenance",
        ["entity", "entity_id", "field"],
        unique=False,
    )

    op.create_table(
        "household_stat",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scope_kind", sa.String(length=16), nullable=False),
        sa.Column("scope_code", sa.String(length=10), nullable=False),
        sa.Column("ym", sa.String(length=7), nullable=False),
        sa.Column("households", sa.Integer(), nullable=False),
        sa.Column("raw_document_id", sa.Integer(), nullable=True),
        sa.Column("label", sa.String(length=8), server_default="추정", nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=True),
        sa.CheckConstraint(
            "label IN ('확인됨', '추정', '비공식', '재가공', '확인 불가')",
            name=op.f("ck_household_stat_label"),
        ),
        sa.CheckConstraint(
            "scope_kind IN ('admin_dong', 'sigungu')", name=op.f("ck_household_stat_scope_kind")
        ),
        sa.ForeignKeyConstraint(
            ["raw_document_id"],
            ["raw_document.id"],
            name=op.f("fk_household_stat_raw_document_id_raw_document"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_household_stat")),
        sa.UniqueConstraint(
            "scope_kind", "scope_code", "ym", name=op.f("uq_household_stat_scope_kind_scope_code_ym")
        ),
    )
    op.create_table(
        "intake_status",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("complex_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("path", sa.String(length=16), nullable=False),
        sa.Column("evidence_url", sa.Text(), nullable=True),
        sa.Column("screenshot_path", sa.Text(), nullable=True),
        sa.Column("raw_document_id", sa.Integer(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("checked_at", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("entered_by", sa.String(length=32), nullable=True),
        sa.CheckConstraint(
            "path <> 'unofficial_ref' OR status <> '가능'", name=op.f("ck_intake_status_unofficial_not_open")
        ),
        sa.CheckConstraint(
            "path IN ('human_check', 'official_popup', 'headless_shot', 'unofficial_ref')",
            name=op.f("ck_intake_status_path"),
        ),
        sa.CheckConstraint(
            "status IN ('가능', '미정', '확인 불가', '불가')", name=op.f("ck_intake_status_status")
        ),
        sa.ForeignKeyConstraint(
            ["complex_id"], ["complex.id"], name=op.f("fk_intake_status_complex_id_complex")
        ),
        sa.ForeignKeyConstraint(
            ["raw_document_id"],
            ["raw_document.id"],
            name=op.f("fk_intake_status_raw_document_id_raw_document"),
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["snapshot.id"], name=op.f("fk_intake_status_snapshot_id_snapshot")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_intake_status")),
    )
    op.create_index(
        op.f("ix_intake_status_snapshot_id_complex_id"),
        "intake_status",
        ["snapshot_id", "complex_id"],
        unique=False,
    )

    op.create_table(
        "ladder",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("complex_id", sa.Integer(), nullable=False),
        sa.Column("horizon", sa.String(length=16), nullable=False),
        sa.Column("target_ym", sa.String(length=7), nullable=False),
        sa.Column("months_from_asof", sa.Integer(), nullable=True),
        sa.Column("p5", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("p10", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("p20", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("p_flat", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("verdicts", sa.JSON(), nullable=False),
        sa.Column("annualized", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("judgment_seq", sa.Integer(), nullable=True),
        sa.Column("proposition_text", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "horizon IN ('move_in_plus_1y', 'asof_plus_3y', 'asof_plus_5y')", name=op.f("ck_ladder_horizon")
        ),
        sa.CheckConstraint(
            "status IN ('ok', 'review', 'escaped', 'blocked', 'error')", name=op.f("ck_ladder_status")
        ),
        sa.ForeignKeyConstraint(["complex_id"], ["complex.id"], name=op.f("fk_ladder_complex_id_complex")),
        sa.ForeignKeyConstraint(
            ["judgment_seq"], ["judgment_log.seq"], name=op.f("fk_ladder_judgment_seq_judgment_log")
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["snapshot.id"], name=op.f("fk_ladder_snapshot_id_snapshot")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ladder")),
        sa.UniqueConstraint(
            "snapshot_id", "complex_id", "horizon", name=op.f("uq_ladder_snapshot_id_complex_id_horizon")
        ),
    )
    op.create_table(
        "remaining_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("complex_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("notice_no", sa.String(length=32), nullable=True),
        sa.Column("notice_date", sa.String(length=10), nullable=True),
        sa.Column("apply_dates", sa.JSON(), nullable=False),
        sa.Column("units_by_type", sa.JSON(), nullable=False),
        sa.Column("ratio_text", sa.Text(), nullable=True),
        sa.Column("result_text", sa.Text(), nullable=True),
        sa.Column("raw_document_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('본청약', '무순위', '임의', '선착순')", name=op.f("ck_remaining_event_kind")
        ),
        sa.ForeignKeyConstraint(
            ["complex_id"], ["complex.id"], name=op.f("fk_remaining_event_complex_id_complex")
        ),
        sa.ForeignKeyConstraint(
            ["raw_document_id"],
            ["raw_document.id"],
            name=op.f("fk_remaining_event_raw_document_id_raw_document"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_remaining_event")),
    )
    op.create_index(op.f("ix_remaining_event_complex_id"), "remaining_event", ["complex_id"], unique=False)

    op.create_table(
        "rtms_trade",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("apt_name", sa.String(length=200), nullable=False),
        sa.Column("dong", sa.String(length=64), nullable=True),
        sa.Column("legal_dong_code", sa.String(length=10), nullable=True),
        sa.Column("completed_year", sa.Integer(), nullable=True),
        sa.Column("area_m2", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("floor", sa.Integer(), nullable=True),
        sa.Column("price_won", sa.BigInteger(), nullable=False),
        sa.Column("deal_date", sa.String(length=10), nullable=False),
        sa.Column("cancelled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_presale", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("raw_document_id", sa.Integer(), nullable=True),
        sa.CheckConstraint("source IN ('openapi', 'reprocessed')", name=op.f("ck_rtms_trade_source")),
        sa.ForeignKeyConstraint(
            ["raw_document_id"], ["raw_document.id"], name=op.f("fk_rtms_trade_raw_document_id_raw_document")
        ),
        sa.ForeignKeyConstraint(["region_id"], ["region.id"], name=op.f("fk_rtms_trade_region_id_region")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rtms_trade")),
    )
    op.create_index(
        op.f("ix_rtms_trade_region_id_apt_name"), "rtms_trade", ["region_id", "apt_name"], unique=False
    )

    op.create_table(
        "score_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("scenario_id", sa.Integer(), nullable=False),
        sa.Column("weights", sa.JSON(), nullable=False),
        sa.Column("rerank_judgment_seq", sa.Integer(), nullable=True),
        sa.Column("prev_score_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["prev_score_run_id"], ["score_run.id"], name=op.f("fk_score_run_prev_score_run_id_score_run")
        ),
        sa.ForeignKeyConstraint(
            ["rerank_judgment_seq"],
            ["judgment_log.seq"],
            name=op.f("fk_score_run_rerank_judgment_seq_judgment_log"),
        ),
        sa.ForeignKeyConstraint(
            ["scenario_id"], ["scenario.id"], name=op.f("fk_score_run_scenario_id_scenario")
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["snapshot.id"], name=op.f("fk_score_run_snapshot_id_snapshot")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_score_run")),
    )
    op.create_index(op.f("ix_score_run_snapshot_id"), "score_run", ["snapshot_id"], unique=False)

    op.create_table(
        "supply",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("living_area", sa.String(length=64), nullable=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("ym", sa.String(length=7), nullable=True),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=8), nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=True),
        sa.Column("complex_id", sa.Integer(), nullable=True),
        sa.Column("raw_document_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "label IN ('확인됨', '추정', '비공식', '재가공', '확인 불가')", name=op.f("ck_supply_label")
        ),
        sa.ForeignKeyConstraint(["complex_id"], ["complex.id"], name=op.f("fk_supply_complex_id_complex")),
        sa.ForeignKeyConstraint(
            ["raw_document_id"], ["raw_document.id"], name=op.f("fk_supply_raw_document_id_raw_document")
        ),
        sa.ForeignKeyConstraint(["region_id"], ["region.id"], name=op.f("fk_supply_region_id_region")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_supply")),
    )
    op.create_index(op.f("ix_supply_region_id"), "supply", ["region_id"], unique=False)

    op.create_table(
        "unsold",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("scope_code", sa.String(length=10), nullable=True),
        sa.Column("scope_name", sa.String(length=60), nullable=True),
        sa.Column("ym", sa.String(length=7), nullable=False),
        sa.Column("total", sa.Integer(), nullable=True),
        sa.Column("post_completion", sa.Integer(), nullable=True),
        sa.Column("source_label", sa.String(length=8), nullable=False),
        sa.Column("raw_document_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "source_label IN ('확인됨', '추정', '비공식', '재가공', '확인 불가')",
            name=op.f("ck_unsold_source_label"),
        ),
        sa.ForeignKeyConstraint(
            ["raw_document_id"], ["raw_document.id"], name=op.f("fk_unsold_raw_document_id_raw_document")
        ),
        sa.ForeignKeyConstraint(["region_id"], ["region.id"], name=op.f("fk_unsold_region_id_region")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_unsold")),
        sa.UniqueConstraint("region_id", "scope_code", "ym", name=op.f("uq_unsold_region_id_scope_code_ym")),
    )
    op.create_table(
        "catalyst_link",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("catalyst_id", sa.Integer(), nullable=False),
        sa.Column("complex_id", sa.Integer(), nullable=False),
        sa.Column("distance_m", sa.Integer(), nullable=True),
        sa.Column("weight", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.ForeignKeyConstraint(
            ["catalyst_id"], ["catalyst.id"], name=op.f("fk_catalyst_link_catalyst_id_catalyst")
        ),
        sa.ForeignKeyConstraint(
            ["complex_id"], ["complex.id"], name=op.f("fk_catalyst_link_complex_id_complex")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalyst_link")),
        sa.UniqueConstraint(
            "catalyst_id", "complex_id", name=op.f("uq_catalyst_link_catalyst_id_complex_id")
        ),
    )
    op.create_index(op.f("ix_catalyst_link_complex_id"), "catalyst_link", ["complex_id"], unique=False)

    op.create_table(
        "decision",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("score_run_id", sa.Integer(), nullable=False),
        sa.Column("scenario_id", sa.Integer(), nullable=False),
        sa.Column("complex_id", sa.Integer(), nullable=True),
        sa.Column("option_key", sa.String(length=16), nullable=False),
        sa.Column("prob", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("chosen", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("tie", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("req_access_pre", sa.JSON(), nullable=True),
        sa.Column("req_regulation_pre", sa.JSON(), nullable=True),
        sa.Column("req_funds_pre", sa.JSON(), nullable=True),
        sa.Column("req_access_judge", sa.String(length=16), nullable=True),
        sa.Column("req_regulation_judge", sa.String(length=16), nullable=True),
        sa.Column("req_funds_judge", sa.String(length=16), nullable=True),
        sa.Column("mismatch", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("judgment_seq", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "option_key IN ('complex', 'wait_new', 'ask_user', 'investigate', 'none')",
            name=op.f("ck_decision_option_key"),
        ),
        sa.CheckConstraint(
            "req_access_judge IN ('supported', 'contradicted', 'unknown')",
            name=op.f("ck_decision_req_access_judge"),
        ),
        sa.CheckConstraint(
            "req_funds_judge IN ('supported', 'contradicted', 'unknown')",
            name=op.f("ck_decision_req_funds_judge"),
        ),
        sa.CheckConstraint(
            "req_regulation_judge IN ('supported', 'contradicted', 'unknown')",
            name=op.f("ck_decision_req_regulation_judge"),
        ),
        sa.ForeignKeyConstraint(["complex_id"], ["complex.id"], name=op.f("fk_decision_complex_id_complex")),
        sa.ForeignKeyConstraint(
            ["judgment_seq"], ["judgment_log.seq"], name=op.f("fk_decision_judgment_seq_judgment_log")
        ),
        sa.ForeignKeyConstraint(
            ["scenario_id"], ["scenario.id"], name=op.f("fk_decision_scenario_id_scenario")
        ),
        sa.ForeignKeyConstraint(
            ["score_run_id"], ["score_run.id"], name=op.f("fk_decision_score_run_id_score_run")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_decision")),
        sa.UniqueConstraint(
            "score_run_id",
            "scenario_id",
            "option_key",
            "complex_id",
            name=op.f("uq_decision_score_run_id_scenario_id_option_key_complex_id"),
        ),
    )
    op.create_index(op.f("ix_decision_score_run_id"), "decision", ["score_run_id"], unique=False)

    op.create_table(
        "score_component",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("score_run_id", sa.Integer(), nullable=False),
        sa.Column("complex_id", sa.Integer(), nullable=False),
        sa.Column("component", sa.String(length=16), nullable=False),
        sa.Column("raw_value", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("score_0_10", sa.Numeric(precision=6, scale=3), nullable=True),
        sa.Column("formula_text", sa.Text(), nullable=False),
        sa.Column("label", sa.String(length=8), nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=True),
        sa.Column("delta", sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column("flags", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "component IN ('p10', 'rerank', 'gap', 'benchmark', 'supply', 'liquidity', 'move_in')",
            name=op.f("ck_score_component_component"),
        ),
        sa.CheckConstraint("formula_text <> ''", name=op.f("ck_score_component_formula_text_not_empty")),
        sa.CheckConstraint(
            "label IN ('확인됨', '추정', '비공식', '재가공', '확인 불가')",
            name=op.f("ck_score_component_label"),
        ),
        sa.ForeignKeyConstraint(
            ["complex_id"], ["complex.id"], name=op.f("fk_score_component_complex_id_complex")
        ),
        sa.ForeignKeyConstraint(
            ["score_run_id"], ["score_run.id"], name=op.f("fk_score_component_score_run_id_score_run")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_score_component")),
        sa.UniqueConstraint(
            "score_run_id",
            "complex_id",
            "component",
            name=op.f("uq_score_component_score_run_id_complex_id_component"),
        ),
    )
    op.create_table(
        "score_total",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("score_run_id", sa.Integer(), nullable=False),
        sa.Column("complex_id", sa.Integer(), nullable=False),
        sa.Column("total", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("tie_group", sa.Integer(), nullable=True),
        sa.Column("unstable", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.ForeignKeyConstraint(
            ["complex_id"], ["complex.id"], name=op.f("fk_score_total_complex_id_complex")
        ),
        sa.ForeignKeyConstraint(
            ["score_run_id"], ["score_run.id"], name=op.f("fk_score_total_score_run_id_score_run")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_score_total")),
        sa.UniqueConstraint(
            "score_run_id", "complex_id", name=op.f("uq_score_total_score_run_id_complex_id")
        ),
    )

    scenario = sa.table(
        "scenario",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("is_builtin", sa.Boolean),
        sa.column("params", sa.JSON),
        sa.column("weights", sa.JSON),
        sa.column("requirements", sa.JSON),
        sa.column("policy", sa.JSON),
        sa.column("created_at", sa.String),
    )
    op.bulk_insert(scenario, BUILTIN_SCENARIOS)


def downgrade() -> None:
    op.drop_table("score_total")
    op.drop_table("score_component")
    op.drop_table("decision")
    op.drop_table("catalyst_link")
    op.drop_table("unsold")
    op.drop_table("supply")
    op.drop_table("score_run")
    op.drop_table("rtms_trade")
    op.drop_table("remaining_event")
    op.drop_table("ladder")
    op.drop_table("intake_status")
    op.drop_table("household_stat")
    op.drop_table("field_provenance")
    op.drop_table("competition")
    op.drop_table("claim")
    op.drop_table("catalyst")
    op.drop_table("raw_document")
    op.drop_table("payment_terms")
    op.drop_table("judgment_log")
    op.drop_table("human_check")
    op.drop_table("complex_type")
    op.drop_table("comparable_set")
    op.drop_table("checklist_item")
    op.drop_table("change_event")
    op.drop_table("snapshot")
    op.drop_table("complex")
    op.drop_table("benchmark")
    op.drop_table("scenario")
    op.drop_table("region")
    op.drop_table("legal_dong")
    op.drop_table("job_run")
    op.drop_table("admin_legal_map")
    op.drop_table("admin_dong")

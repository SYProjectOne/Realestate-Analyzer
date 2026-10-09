"""R3b G1 — 출처 전수 검사(M16 부분)·호재 출처 행(M6 부분).

M16: 검사 대상 테이블 목록을 손으로 쓰지 않고 모델 메타데이터에서 — supply·household_stat·remaining_event·catalyst
     포함. 모든 매핑 테이블은 '사실 테이블' 또는 사유가 적힌 '사실 아님' 둘 중 하나여야 한다(새 테이블 = 결정 강제).
M6: 호재 후보(뉴스·사람 URL)를 만들 때 field_provenance 출처 행을 남긴다(라벨·URL·확인일).
"""

# ruff: noqa: E501

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Base, Catalyst, FieldProvenance, HouseholdStat, Region
from app.normalize.catalyst import catalyst_candidate
from app.normalize.provenance import (
    FACT_TABLES,
    NON_FACT_TABLES,
    POINTER_PROVENANCE,
    missing_provenance,
    numeric_columns,
)

from ._support import AddRaw


def test_m16_fact_tables_come_from_metadata_and_cover_every_table() -> None:
    assert {"supply", "household_stat", "remaining_event", "catalyst"} <= set(FACT_TABLES)
    assert {"complex", "complex_type", "payment_terms", "competition", "rtms_trade", "unsold", "benchmark"} <= set(FACT_TABLES)
    tables = {m.class_.__tablename__ for m in Base.registry.mappers}
    assert set(FACT_TABLES) | set(NON_FACT_TABLES) == tables  # 새 테이블은 둘 중 하나로 분류해야 한다
    assert not set(FACT_TABLES) & set(NON_FACT_TABLES)
    assert all(reason.strip() for reason in NON_FACT_TABLES.values())


def test_m16_catalyst_columns_and_pointer() -> None:
    cols = set(numeric_columns(Catalyst))
    assert {"stage_prob", "expected_ym", "lat", "lon"} <= cols and "judgment_seq" not in cols
    assert POINTER_PROVENANCE[("catalyst", "stage_prob")] == "judgment_seq"


def test_m16_household_stat_row_level_source(db_session: Session, add_raw: AddRaw) -> None:
    """household_stat 은 행 자체가 출처(raw_document_id + label) — 없으면 검사에 걸린다."""
    doc = add_raw("세대 현황", source_kind="stats", url="https://jumin.mois.go.kr/x.csv")
    db_session.add_all([
        HouseholdStat(scope_kind="sigungu", scope_code="28185", ym="2026-09", households=1000, raw_document_id=doc.id, label="추정", reason="주민등록 세대"),
        HouseholdStat(scope_kind="sigungu", scope_code="28245", ym="2026-09", households=900, raw_document_id=None, label="추정"),
    ])  # fmt: skip
    db_session.flush()
    probs = [(p.entity, p.field, p.problem) for p in missing_provenance(db_session, ("household_stat",))]
    assert probs == [("household_stat", "households", "no_row"), ("household_stat", "ym", "no_row")]


def test_m6_catalyst_candidate_writes_provenance(db_session: Session, region: Region, add_raw: AddRaw) -> None:
    doc = add_raw("{}", source_kind="news", url="https://naverapihub.apigw.ntruss.com/search/v1/news?query=x", region_id=region.id)
    out = catalyst_candidate(db_session, region.id, url="https://news.example.com/a/1", title="GTX-B 착공",
                             excerpt="국토부 발표", raw_document_id=doc.id)  # fmt: skip
    fps = list(db_session.scalars(select(FieldProvenance).where(FieldProvenance.entity == "catalyst", FieldProvenance.entity_id == out.catalyst.id)))
    by_field = {fp.field: fp for fp in fps}
    assert set(by_field) >= {"name", "source_url"}
    name = by_field["name"]
    assert name.chosen and name.label == "비공식" and name.url == "https://news.example.com/a/1"
    assert name.checked_at and name.raw_document_id == doc.id and name.value_text == "GTX-B 착공"
    # 사람 URL 입력(원문 행 없음)도 출처 행이 남는다
    human = catalyst_candidate(db_session, region.id, url="https://www.example.go.kr/notice/9", title="공원 조성 고시")
    fp = db_session.scalars(select(FieldProvenance).where(FieldProvenance.entity == "catalyst", FieldProvenance.entity_id == human.catalyst.id, FieldProvenance.field == "name")).one()
    assert fp.url == "https://www.example.go.kr/notice/9" and fp.label and fp.checked_at
    assert missing_provenance(db_session, ("catalyst",)) == []
    # 판정 확률은 judgment_seq 포인터가 출처 — 없으면 걸린다
    out.catalyst.stage_prob = 0.9  # type: ignore[assignment]
    db_session.flush()
    assert [(p.field, p.problem) for p in missing_provenance(db_session, ("catalyst",))] == [("stage_prob", "no_row")]
    out.catalyst.judgment_seq = 1
    db_session.flush()
    assert missing_provenance(db_session, ("catalyst",)) == []

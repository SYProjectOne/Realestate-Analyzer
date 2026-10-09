"""backend/app/models — 열거 값이 JSON Schema enum과 같다, 모든 모델이 마이그레이션 테이블과 1:1."""

from __future__ import annotations

from typing import Any

import pytest

from app.models import Base, enums

from ._support import SCHEMAS, load_json


def schema_enum(file: str, *pointer: str) -> list[Any]:
    node: Any = load_json(SCHEMAS / file)
    for key in pointer:
        node = node[key]
    values = node["enum"]
    return [v for v in values if v is not None]


PAIRS = [
    (enums.LABELS, ("label.json",)),
    (enums.INTAKE_STATUS, ("intake.json", "properties", "status")),
    (enums.INTAKE_PATH, ("intake.json", "properties", "path")),
    (enums.REGION_STATUS, ("region.json", "properties", "status")),
    (enums.SNAPSHOT_STATUS, ("snapshot.json", "properties", "status")),
    (enums.INCLUSION_CLASS, ("complex.json", "$defs", "InclusionClass")),
    (enums.JUDGE_DECISION, ("complex.json", "properties", "inclusion_decision")),
    (enums.TRACK, ("complex.json", "properties", "track")),
    (enums.SUPPLY_KIND, ("remaining_event.json", "properties", "kind")),
    (enums.SUPPLY_KIND, ("competition.json", "properties", "kind")),
    (enums.SOURCE_KIND, ("raw_document.json", "$defs", "SourceKind")),
    (enums.SALE_PERIOD, ("market.json", "$defs", "BenchmarkView", "properties", "sale_period")),
    (enums.CATALYST_KIND, ("catalyst.json", "properties", "kind")),
    (enums.CATALYST_STAGE, ("catalyst.json", "properties", "stage")),
    (enums.JUDGE_TOOL, ("judgment_envelope.json", "$defs", "JudgeTool")),
    (enums.JUDGMENT_STATUS, ("judgment_envelope.json", "properties", "status")),
    (enums.VERIFY_STATUS, ("claim.json", "properties", "verify_status")),
    (enums.COMPONENT, ("scenario.json", "$defs", "ComponentKey")),
    (enums.HORIZON, ("ladder.json", "properties", "horizon")),
    (enums.OPTION_KEY, ("decision.json", "properties", "option_key")),
    (enums.REQ_JUDGE, ("decision.json", "$defs", "RequirementCheck", "properties", "judge")),
    (enums.HUMAN_CHECK_KIND, ("human_check.json", "properties", "kind")),
    (enums.CHECKLIST_KIND, ("checklist_item.json", "properties", "kind")),
    (enums.CHECKLIST_STATUS, ("checklist_item.json", "properties", "status")),
    (enums.CHANGE_ENTITY, ("change_event.json", "properties", "entity")),
    (enums.SEVERITY, ("change_event.json", "properties", "severity")),
    (enums.JOB_NAME, ("job_run.json", "$defs", "JobName")),
    (enums.JOB_KIND, ("job_run.json", "properties", "kind")),
    (enums.JOB_STATUS, ("job_run.json", "properties", "status")),
    (enums.SCENARIO_CODE, ("scenario.json", "properties", "code")),
    (enums.JUDGE_SCOPE, ("score_row.json", "$defs", "JudgeScope")),
    (enums.ENTERED_BY_ROLE, ("human_check.json", "$defs", "EnteredByRole")),
    (enums.SHARE_LINK_STATUS, ("share_link.json", "properties", "status")),
]


@pytest.mark.parametrize(("values", "where"), PAIRS, ids=["/".join(w) for _, w in PAIRS])
def test_enum_matches_schema(values: tuple[str, ...], where: tuple[str, ...]) -> None:
    assert list(values) == schema_enum(*where)


def test_every_table_has_a_model_and_primary_key() -> None:
    tables = Base.metadata.tables
    assert len(tables) == 34  # + share_link (0004)
    for name, table in tables.items():
        assert table.primary_key.columns, name


def test_derived_tables_have_snapshot_id() -> None:
    """RA §3: 파생 테이블은 snapshot_id(또는 score_run → snapshot)를 가진다."""
    tables = Base.metadata.tables
    for name in (
        "intake_status",
        "judgment_log",
        "claim",
        "score_run",
        "ladder",
        "comparable_set",
        "change_event",
    ):
        assert "snapshot_id" in tables[name].columns, name
    for name in ("score_component", "score_total", "decision"):
        assert "score_run_id" in tables[name].columns, name

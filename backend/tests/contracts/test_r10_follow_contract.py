"""계약 2026-10-09.21 (R10-FOLLOW, DECISIONS D29-2·D29-3) — 체크리스트 kind 2 · ReasonCode no_winner · 마이그레이션 0018.

버전 표시 4곳·CHANGELOG `.21` FE 차이 표, 스키마 enum = 서버(models·reason_codes), MSW 예시의 새 종류, 0018 왕복(새 kind CHECK ·
complex.merged_into_id — downgrade 가 새 kind 항목을 지우고 열을 뺀다).
"""

# ruff: noqa: E501

from __future__ import annotations

import re
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command

from ._support import CONTRACTS, EXAMPLES, SCHEMAS, alembic_config, load_json, load_yaml

VERSION = "2026-10-09.21"


def test_contract_version_is_21_everywhere() -> None:
    from app.core.protocols import CONTRACT_VERSION

    assert CONTRACT_VERSION == VERSION
    assert load_yaml(CONTRACTS / "openapi.yaml")["info"]["version"] == VERSION
    assert load_yaml(CONTRACTS / "openapi.bundled.yaml")["info"]["version"] == VERSION
    decisions = (CONTRACTS.parent / "docs" / "design" / "DECISIONS.md").read_text(encoding="utf-8")
    assert f"계약 버전: `{VERSION}`" in decisions
    changelog = (CONTRACTS / "CHANGELOG.md").read_text(encoding="utf-8")
    top = re.search(r"^## (\d{4}-\d{2}-\d{2}\.\d+)\b", changelog, re.M)
    assert top is not None and top.group(1) == VERSION


def test_changelog_21_has_fe_difference_table() -> None:
    changelog = (CONTRACTS / "CHANGELOG.md").read_text(encoding="utf-8")
    entry = changelog.split(f"## {VERSION}", 1)[1].split("\n## ", 1)[0]
    assert "D29-3" in entry and "D29-2" in entry and "R10_TESTS_FOLLOW.md" in entry
    assert "### FE 차이(화면이 맞출 것)" in entry
    assert "| # | 대상 | .20 | .21 | 결정 |" in entry
    for f in ("F1", "F2", "F3", "F4", "F5"):
        assert f"| {f} |" in entry, f
    assert "SHAPE_VERSION" in entry and "0018" in entry


def test_checklist_kind_enum_has_apply_and_winner() -> None:
    from app.models.enums import CHECKLIST_KIND

    enum = load_json(SCHEMAS / "checklist_item.json")["properties"]["kind"]["enum"]
    assert enum[-2:] == ["청약 접수", "당첨자 발표"]
    assert tuple(enum) == CHECKLIST_KIND
    bundled = load_yaml(CONTRACTS / "openapi.bundled.yaml")["components"]["schemas"]
    assert bundled["ChecklistItem"]["properties"]["kind"]["enum"] == enum


def test_reason_code_no_winner_matches_server() -> None:
    from app.api.reason_codes import REASON_CODES, reason_code

    enum = load_json(SCHEMAS / "fact.json")["$defs"]["ReasonCode"]["enum"]
    assert tuple(enum) == REASON_CODES and "no_winner" in enum
    assert enum.index("no_winner") == enum.index("human_check") + 1  # 서버 규칙 순서
    desc = load_json(SCHEMAS / "fact.json")["$defs"]["ReasonCode"]["description"]
    assert "no_winner" in desc and "발표 전" in desc
    assert reason_code("가점 당첨자 없음(미달)") == "no_winner"


def test_checklist_example_carries_new_kinds() -> None:
    """MSW 데이터(contracts/examples) — 새 종류 항목이 서버 제목 규칙(``normalize.checklist``) 그대로."""
    from app.normalize.checklist import item_key

    items = load_json(EXAMPLES / "checklist.json")["value"]
    new = [i for i in items if i["kind"] in ("청약 접수", "당첨자 발표")]
    assert {(i["kind"], i["title"]) for i in new} == {
        ("청약 접수", "1순위 청약 접수(해당지역·기타지역)"),
        ("당첨자 발표", "당첨자 발표"),
    }
    assert {item_key(i["kind"], i["title"]) for i in new} == {"apply:1순위(해당지역·기타지역)", "winner"}
    assert all(i["due_date"] and i["note"].startswith("자동: 청약홈") for i in new)


def test_sqlite_0017_0018_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """0018: 새 kind 는 0017 CHECK 가 거부 → head 에서 받는다, merged_into_id 열(FK) → downgrade 0017 이 새 kind 항목을 지우고 열을
    뺀다(다른 항목 그대로) → head 다시."""
    url = f"sqlite:///{(tmp_path / 'r10.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = alembic_config(url)
    command.upgrade(cfg, "0017")
    engine = sa.create_engine(url)
    region = (
        "INSERT INTO region (id, name, query_text, selections, sido_codes, sigungu_codes, legal_dong_codes, "
        "living_areas, age_premium_coef, applyhome_query, status, created_at) VALUES "
        "(1, 'r', 'q', '[]', '[]', '[]', '[]', '[]', '{}', '{}', 'ready', '2026-10-14')"
    )
    cx = (
        "INSERT INTO complex (id, region_id, applyhome_id, name, former_names, apply_dates, contract_dates, "
        "inclusion_class) VALUES ({id}, 1, '{no}', '도화', '[]', '[]', '[]', '미분류')"
    )
    item = (
        "INSERT INTO checklist_item (complex_id, kind, title, due_date, status) VALUES "
        "(1, '{kind}', '{title}', '2026-10-20', 'open')"
    )
    try:
        with engine.begin() as conn:
            conn.execute(sa.text(region))
            conn.execute(sa.text(cx.format(id=1, no="2025000397")))
            conn.execute(sa.text(cx.format(id=2, no="2025940268")))
            conn.execute(sa.text(item.format(kind="중도금", title="중도금 1회차 납부일")))
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
            conn.execute(sa.text(item.format(kind="청약 접수", title="1순위 청약 접수")))
        engine.dispose()
        command.upgrade(cfg, "head")
        engine = sa.create_engine(url)
        with engine.begin() as conn:
            conn.execute(sa.text(item.format(kind="청약 접수", title="1순위 청약 접수")))
            conn.execute(sa.text(item.format(kind="당첨자 발표", title="당첨자 발표")))
            conn.execute(sa.text("UPDATE complex SET merged_into_id = 1 WHERE id = 2"))
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
            conn.execute(sa.text(item.format(kind="모르는 종류", title="x")))
        cols = {c["name"] for c in sa.inspect(engine).get_columns("complex")}
        assert "merged_into_id" in cols
        fks = sa.inspect(engine).get_foreign_keys("complex")
        assert any(
            fk["constrained_columns"] == ["merged_into_id"] and fk["referred_table"] == "complex"
            for fk in fks
        )
        engine.dispose()
        command.downgrade(cfg, "0017")
        engine = sa.create_engine(url)
        with engine.connect() as conn:
            kinds = [k for (k,) in conn.execute(sa.text("SELECT kind FROM checklist_item ORDER BY id"))]
        assert kinds == ["중도금"]
        assert "merged_into_id" not in {c["name"] for c in sa.inspect(engine).get_columns("complex")}
        engine.dispose()
        command.upgrade(cfg, "head")
    finally:
        engine.dispose()

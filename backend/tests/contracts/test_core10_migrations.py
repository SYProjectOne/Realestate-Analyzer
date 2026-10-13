"""R4-CORE10 계약 .18 (DECISIONS D23-2) — 마이그레이션 ``0016``(경쟁률 원 면적 코드 + R4 4차 N13 중복 정리, 데이터만) 왕복.

| 결정 | 테스트 |
| --- | --- |
| D23-2 경쟁률 행 = (단지, 구분, 회차, 원 면적 코드), 이미 생긴 중복 정리(앱 import 금지) | ``test_*_0016_merges_n13_duplicates_and_roundtrips`` — 0015 에 R4 4차 모양(bootstrap 행 '84.9939' + (b) 중복 '84' · '확인 불가(타입 모호)' 중복, 다른 원문만 가진 중복, change_event 가 가리키는 중복)을 넣고 0016: 중복 행 삭제·출처 행 정리(같은 출처 삭제, 다른 출처는 남는 행으로 + 상충 묶음 이름), 값은 가장 늦은 행, type_code = 원 코드, 이벤트는 남는 행으로. 0015 로 내려도(데이터 그대로)·다시 올려도 같고 autogenerate diff 0 |
"""

# ruff: noqa: E501

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.models import Base

from ._support import alembic_config

H = "2026000073"
URL = f"https://api.odcloud.kr/api/ApplyhomeInfoCmpetRtSvc/v1/getAPTLttotPblancCmpet?cond%5BHOUSE_MANAGE_NO%3A%3AEQ%5D={H}"
R1 = "1순위 해당지역"


def _exec(c: sa.Connection, sql: str, **kw: Any) -> None:
    c.execute(sa.text(sql), kw)


def _fp(
    c: sa.Connection,
    fid: int,
    eid: int,
    code: str,
    field: str,
    value: str,
    raw: int,
    *,
    chosen: bool,
    group: str | None = None,
    rnd: str = R1,
) -> None:
    _exec(
        c,
        "INSERT INTO field_provenance (id, entity, entity_id, entity_key, field, value_text, raw_document_id, url, checked_at, "
        "label, source_rank, chosen, conflict_group, excerpt, excerpt_start, value_norm) VALUES (:id, 'competition', :eid, :key, "
        ":f, :v, :raw, :url, '2026-10-13', '확인됨', 1, :ch, :g, :ex, :st, :v)",
        id=fid, eid=eid, key=f"{H}:본청약:{rnd}:{code}", f=field, v=value, raw=raw, url=URL, ch=chosen, g=group,
        ex=f'"{field}":{value}', st=len(rnd) * 1000 + raw + len(value),  # 같은 원문·회차·값 = 같은 발췌 위치
    )  # fmt: skip


def _insert_0015_rows(engine: sa.Engine) -> None:
    with engine.begin() as c:
        _exec(
            c,
            "INSERT INTO region (id, name, query_text, selections, sido_codes, sigungu_codes, legal_dong_codes, living_areas, "
            "age_premium_coef, applyhome_query, status, created_at) VALUES (1, 't', 't', '[]', '[]', '[]', '[]', '[]', '{}', '{}', "
            "'ready', '2026-10-13T01:00:00+09:00')",
        )
        _exec(
            c,
            "INSERT INTO complex (id, region_id, applyhome_id, name, former_names, apply_dates, contract_dates) "
            "VALUES (28, 1, :h, '테스트', '[]', '[]', '[]')",
            h=H,
        )
        for rid in (388, 1326):
            _exec(
                c,
                "INSERT INTO raw_document (id, source_kind, url, fetched_at, http_status, sha256) "
                "VALUES (:id, 'applyhome_detail', :u, '2026-10-13T01:05:00+09:00', 200, :sha)",
                id=rid, u=f"{URL}&r={rid}", sha=f"{rid:064d}",
            )  # fmt: skip
        comp = "INSERT INTO competition (id, complex_id, round, kind, type_code, supply, applied, ratio_or_shortfall_text) VALUES (:id, 28, :r, '본청약', :t, :s, :a, :x)"
        # R4 4차 N13: bootstrap 행(원 코드) + (b) 가 같은 원문으로 만든 중복(대조 코드)
        _exec(c, comp, id=657, r=R1, t="84.9939", s=337, a=210, x="(△127)")
        _exec(c, comp, id=1915, r=R1, t="84", s=337, a=210, x="(△127)")
        # 모호 코드로 만든 중복 + (b) 뒤에 바뀐 원문(1326)만 가진 값
        _exec(c, comp, id=660, r="2순위 해당지역", t="120.5868", s=8, a=1, x="(△1)")
        _exec(c, comp, id=1909, r="2순위 해당지역", t="확인 불가(타입 모호)", s=8, a=2, x="(△0)")
        # 중복 아님 — 대조 코드로만 저장된 행(원 코드로 되돌린다), 출처 행 없는 행(그대로)
        _exec(c, comp, id=700, r="1순위 기타지역", t="84", s=337, a=309, x="2.43")
        _exec(c, comp, id=701, r="특별공급", t="59A", s=10, a=20, x="2.00")
        _fp(c, 1, 657, "84.9939", "applied", "210", 388, chosen=True)
        _fp(c, 2, 1915, "84.9939", "applied", "210", 388, chosen=True)  # 같은 출처 → 지운다
        _fp(
            c,
            3,
            660,
            "120.5868",
            "applied",
            "1",
            388,
            chosen=True,
            group="competition:660:applied",
            rnd="2순위 해당지역",
        )
        _fp(
            c,
            4,
            1909,
            "120.5868",
            "applied",
            "1",
            388,
            chosen=False,
            group="competition:1909:applied",
            rnd="2순위 해당지역",
        )
        _fp(
            c,
            5,
            1909,
            "120.5868",
            "applied",
            "2",
            1326,
            chosen=True,
            group="competition:1909:applied",
            rnd="2순위 해당지역",
        )
        _fp(c, 6, 700, "84.9939", "applied", "309", 388, chosen=True, rnd="1순위 기타지역")
        _exec(
            c,
            "INSERT INTO change_event (id, entity, entity_id, field, old_text, new_text, detected_at, severity, triggers_rejudge) "
            "VALUES (1, 'competition', 1909, 'applied', '1', '2', '2026-10-13T02:00:00+09:00', 'notice', false)",
        )


def _state(engine: sa.Engine) -> dict[str, Any]:
    with engine.connect() as c:
        return {
            "competition": [tuple(r) for r in c.execute(sa.text(
                "SELECT id, round, type_code, supply, applied, ratio_or_shortfall_text FROM competition ORDER BY id"))],
            "fp": [tuple(r) for r in c.execute(sa.text(
                "SELECT id, entity_id, value_text, raw_document_id, chosen, conflict_group FROM field_provenance ORDER BY id"))],
            "events": [tuple(r) for r in c.execute(sa.text("SELECT id, entity_id FROM change_event ORDER BY id"))],
        }  # fmt: skip


def check_0016(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENV_FILE", raising=False)
    cfg = alembic_config(url)
    command.upgrade(cfg, "0015")
    engine = sa.create_engine(url)
    try:
        _insert_0015_rows(engine)
        command.upgrade(cfg, "head")
        got = _state(engine)
        assert got["competition"] == [
            (657, R1, "84.9939", 337, 210, "(△127)"),
            (660, "2순위 해당지역", "120.5868", 8, 2, "(△0)"),  # 값 = 가장 늦게 쓴 행(1909)
            (700, "1순위 기타지역", "84.9939", 337, 309, "2.43"),  # 원 코드로
            (701, "특별공급", "59A", 10, 20, "2.00"),  # 출처 없음 — 그대로
        ], got["competition"]
        assert got["fp"] == [
            (1, 657, "210", 388, True, None),
            (3, 660, "1", 388, False, "competition:660:applied"),
            (
                5,
                660,
                "2",
                1326,
                True,
                "competition:660:applied",
            ),  # 다른 출처 → 남는 행으로, 채택은 가장 늦은 것 하나
            (6, 700, "309", 388, True, None),
        ], got["fp"]
        assert got["events"] == [(1, 660)]
        with engine.connect() as c:
            ctx = MigrationContext.configure(c, opts={"compare_type": True})
            assert compare_metadata(ctx, Base.metadata) == []
        command.downgrade(cfg, "0015")
        assert _state(engine) == got, "downgrade 는 데이터를 되돌리지 않는다"
        command.upgrade(cfg, "head")
        assert _state(engine) == got, "다시 올려도 같다(멱등)"
        with engine.connect() as c:
            ctx = MigrationContext.configure(c, opts={"compare_type": True})
            assert compare_metadata(ctx, Base.metadata) == []
    finally:
        command.downgrade(cfg, "base")
        engine.dispose()


def test_sqlite_0016_merges_n13_duplicates_and_roundtrips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    check_0016(f"sqlite:///{(tmp_path / 'core10.db').as_posix()}", monkeypatch)


@pytest.mark.postgres
def test_postgres_0016_merges_n13_duplicates_and_roundtrips(postgres_url: str) -> None:
    mp = pytest.MonkeyPatch()
    try:
        check_0016(postgres_url, mp)
    finally:
        mp.undo()


def test_contract_version_is_18() -> None:
    """계약 .18(R4-CORE10): ``CONTRACT_VERSION`` = openapi ``info.version`` = DECISIONS 5행(버전 3곳 — CHANGELOG 맨 위는
    ``test_protocols``·``test_openapi`` 가 맞춘다). .19(R7-QUEUE) 이후에도 .18 항목은 CHANGELOG 에 남고 버전은 .18 이상이다
    (현재 버전 단언은 ``test_r7_queue_contract``)."""
    from app.core.protocols import CONTRACT_VERSION

    from ._support import CONTRACTS, load_yaml

    assert "## 2026-10-09.18" in (CONTRACTS / "CHANGELOG.md").read_text(encoding="utf-8")
    assert CONTRACT_VERSION.startswith("2026-10-09.") and int(CONTRACT_VERSION.rsplit(".", 1)[1]) >= 18
    assert load_yaml(CONTRACTS / "openapi.yaml")["info"]["version"] == CONTRACT_VERSION
    decisions = (CONTRACTS.parent / "docs" / "design" / "DECISIONS.md").read_text(encoding="utf-8")
    assert f"계약 버전: `{CONTRACT_VERSION}`" in decisions

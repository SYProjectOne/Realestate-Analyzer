"""R3c SEC — minor 33: 0006 downgrade 가 잃는 것과 재upgrade 후 복원 경로(문서 + 고정 테스트).

0006 downgrade(→ 0005)는 다음을 **되돌릴 수 없게** 잃는다(마이그레이션은 CORE 소유 — 여기서는 고정만 한다):

| 잃는 것 | 재upgrade 후 상태 |
| --- | --- |
| ``fact_demotion`` 행 전부(강등 기록·원래 값 ``original_value_text``·복원 시각/경로·체크리스트·rejudge 잡 연결) | 빈 테이블 |
| ``claim.entity``·``entity_id``·``field``(주장이 가리킨 DB 사실) | NULL |
| ``checklist_item.kind='사실 재확인'`` | '법적 확인'으로 바뀐 채 남는다(되돌리지 않음) |
| ``benchmark.snapshot_id``(발행 스냅샷이 인용한 행 표시) | NULL |

복원 경로: 강등의 **근거 행은 0006 밖 테이블에 남는다** — ``field_provenance`` 의 원래 출처 행(값·라벨·
chosen)과 강등 출처 행, ``claim`` 의 본문·verify_status('contradicted')·judgment_seq. 재upgrade 뒤에는
모순 주장(verify_status='contradicted')을 다시 검증(reverify)하면 그 주장의 대상 사실을 다시 찾아
강등을 새로 만든다(D11-3 읽기 시점 오버레이 — 값 자체는 field_provenance 에 그대로라 값 손실은 없다).
즉 운영에서 0006 아래로 내리는 것은 '강등 기록을 버리고 재검증으로 다시 쌓는' 조작이다.

이 테스트는 그 계약을 고정한다: 잃는 것은 위 표와 정확히 같고, 복원에 필요한 근거 행은 하나도 잃지 않는다.
"""

# ruff: noqa: E501

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command

from ._support import alembic_config

NOW = "2026-10-10T00:00:00+09:00"


def _seed(conn: sa.Connection) -> dict[str, int]:
    def ins(sql: str, **params: object) -> int:
        row = conn.execute(sa.text(sql + " RETURNING id"), params).first()
        assert row is not None
        return int(row[0])

    region = ins(
        "INSERT INTO region (name, query_text, selections, sido_codes, sigungu_codes, legal_dong_codes, living_areas,"
        " age_premium_coef, applyhome_query, status, created_at)"
        " VALUES ('시험', '시험', '[]', '[]', '[]', '[]', '[]', '{}', '{}', 'ready', :now)",
        now=NOW,
    )
    snap = ins(
        "INSERT INTO snapshot (region_id, asof_date, status, created_at) VALUES (:r, '2026-10-10', 'published', :now)",
        r=region,
        now=NOW,
    )
    cx = ins(
        "INSERT INTO complex (region_id, name, former_names, apply_dates, contract_dates)"
        " VALUES (:r, '시험단지', '[]', '{}', '{}')",
        r=region,
    )
    original = ins(
        "INSERT INTO field_provenance (entity, entity_id, field, value_text, label, source_rank, chosen, value_norm)"
        " VALUES ('complex', :cx, 'households', '1573', '확인됨', 1, true, '1573')",
        cx=cx,
    )
    demotion = ins(
        "INSERT INTO field_provenance (entity, entity_id, field, value_text, label, reason, source_rank, chosen)"
        " VALUES ('complex', :cx, 'households', NULL, '확인 불가', '검증 모순', 0, false)",
        cx=cx,
    )
    claim = ins(
        "INSERT INTO claim (snapshot_id, section, complex_id, text, verify_status, entity, entity_id, field)"
        " VALUES (:s, 'summary', :cx, '총 1,573세대', 'contradicted', 'complex', :cx, 'households')",
        s=snap,
        cx=cx,
    )
    item = ins(
        "INSERT INTO checklist_item (complex_id, kind, title, status) VALUES (:cx, '사실 재확인', '세대수 재확인', 'open')",
        cx=cx,
    )
    ins(
        "INSERT INTO fact_demotion (claim_id, snapshot_id, complex_id, entity, entity_id, field, original_fp_id,"
        " demotion_fp_id, original_value_text, created_at, checklist_item_id)"
        " VALUES (:c, :s, :cx, 'complex', :cx, 'households', :o, :d, '1573', :now, :i)",
        c=claim,
        s=snap,
        cx=cx,
        o=original,
        d=demotion,
        now=NOW,
        i=item,
    )
    return {"complex": cx, "original": original, "demotion": demotion, "claim": claim, "item": item}


def test_minor33_0006_downgrade_loses_only_documented_rows_and_keeps_restore_basis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = f"sqlite:///{(tmp_path / 'm33.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = alembic_config(url)
    command.upgrade(cfg, "head")
    engine = sa.create_engine(url)
    try:
        with engine.begin() as conn:
            ids = _seed(conn)
            fp_before = conn.execute(
                sa.text("SELECT id, value_text, label, chosen, reason FROM field_provenance ORDER BY id")
            ).all()
        command.downgrade(cfg, "0005")
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            # 잃는 것(문서 표와 같다)
            assert conn.execute(sa.text("SELECT COUNT(*) FROM fact_demotion")).scalar_one() == 0
            claim = conn.execute(
                sa.text("SELECT text, verify_status, entity, entity_id, field FROM claim WHERE id = :i"),
                {"i": ids["claim"]},
            ).one()
            assert (claim.entity, claim.entity_id, claim.field) == (None, None, None)
            kind = conn.execute(
                sa.text("SELECT kind FROM checklist_item WHERE id = :i"), {"i": ids["item"]}
            ).scalar_one()
            assert kind == "법적 확인"
            # 복원 근거는 남는다: 원래·강등 출처 행(값·라벨·chosen 그대로), 모순 주장 본문·상태
            fp_after = conn.execute(
                sa.text("SELECT id, value_text, label, chosen, reason FROM field_provenance ORDER BY id")
            ).all()
            assert fp_after == fp_before
            assert {r.id for r in fp_after} == {ids["original"], ids["demotion"]}
            assert (claim.text, claim.verify_status) == ("총 1,573세대", "contradicted")
            # 재upgrade 한 스키마는 강등을 다시 쓸 수 있다(복원 경로가 열려 있다)
        with engine.begin() as conn:
            conn.execute(
                sa.text("UPDATE claim SET entity='complex', entity_id=:cx, field='households' WHERE id=:c"),
                {"cx": ids["complex"], "c": ids["claim"]},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO fact_demotion (claim_id, snapshot_id, complex_id, entity, entity_id, field,"
                    " original_fp_id, demotion_fp_id, original_value_text, created_at)"
                    " SELECT c.id, c.snapshot_id, c.complex_id, c.entity, c.entity_id, c.field, :o, :d, fp.value_text, :now"
                    " FROM claim c JOIN field_provenance fp ON fp.id = :o WHERE c.id = :c"
                ),
                {"o": ids["original"], "d": ids["demotion"], "now": NOW, "c": ids["claim"]},
            )
            assert (
                conn.execute(sa.text("SELECT original_value_text FROM fact_demotion")).scalar_one() == "1573"
            )
    finally:
        engine.dispose()

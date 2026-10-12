"""R4 재시험 N2(D21-2) — NUL 문자가 든 잔여 공고문을 **Postgres** 에 저장한다(임베디드 Postgres 16).

R4: SQLite 에서는 드러나지 않고 Postgres 에서만 ``field_provenance.excerpt`` INSERT 가 ``DataError: PostgreSQL text fields
cannot contain NUL (0x00) bytes`` 로 실패해 그 공고문의 정규화 값이 매 실행 롤백됐다(stats ``store_errors``).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.orm import Session

from app.core.settings import Settings
from app.models import Complex, FieldProvenance, RawDocument, Region
from app.normalize.store import raw_dto, store_raw_document

from ._support import alembic_config

FIX = Path(__file__).resolve().parents[1] / "normalize" / "fixtures" / "r4b_core8"


@pytest.mark.postgres
def test_postgres_stores_nul_notice(
    postgres_url: str, test_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    monkeypatch.delenv("ENV_FILE", raising=False)
    shutil.copytree(FIX / "raw", test_settings.raw_dir, dirs_exist_ok=True)
    docs = json.loads((FIX / "docs.json").read_text(encoding="utf-8"))["docs"]["n2"]
    cfg = alembic_config(postgres_url)
    command.upgrade(cfg, "head")
    engine = sa.create_engine(postgres_url)
    try:
        with Session(engine) as s:
            region = Region(
                name="테스트", query_text="테스트", selections=[], sido_codes=["28"], sigungu_codes=["28185"],
                legal_dong_codes=[], living_areas=[], age_premium_coef={}, applyhome_query={}, status="ready",
                created_at="2026-10-12T06:00:00+09:00",
            )  # fmt: skip
            s.add(region)
            s.flush()
            for raw_id in (613, 616):
                r = next(d for d in docs if d["id"] == raw_id)
                row = RawDocument(
                    **{k: v for k, v in r.items() if k != "id"}, region_id=region.id, complex_id=None
                )
                s.add(row)
                s.flush()
                res = store_raw_document(s, raw_dto(row), raw_dir=test_settings.raw_dir)
                assert res.provenance_ids, f"rd{raw_id}: Postgres 에 정규화 값이 저장된다"
            s.commit()
            n = s.scalar(sa.select(sa.func.count()).select_from(FieldProvenance))
            assert (
                n and n >= 2
            )  # 인용한 원 단지(자리표시)에는 입주 예정월만 — 잔여 공고의 단지 단위 값은 쓰지 않는다(D11-4)
            ids = set(s.scalars(sa.select(Complex.applyhome_id)))
            assert {"2020000611", "2019000711"} <= ids and not {"2025910104", "2025930032"} & ids
    finally:
        engine.dispose()
        command.downgrade(cfg, "base")

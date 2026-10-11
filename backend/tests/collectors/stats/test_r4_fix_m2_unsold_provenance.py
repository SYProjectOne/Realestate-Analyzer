"""R4-FIX M2 (D18-7) — 미분양 사실은 출처 행을 갖는다.

R4: 미분양 35행이 저장됐지만 field_provenance 가 없어 사실 뷰가 '확인 불가(출처 누락)'로 가리고, 대시보드 KPI 는
'미분양 자료 없음'(틀린 사유)을 보였다(발행 stats missing_provenance 560~605 의 대부분).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from pathlib import Path

import pytest
import respx
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.collectors.stats.unsold import MOLIT_DATA_URL, UnsoldCollector
from app.core.contracts_gen import Region, Snapshot
from app.core.http import HttpClient
from app.models import FieldProvenance, RawDocument, Unsold

from .test_unsold import _route, legal_dongs  # noqa: F401  (fixture)


@pytest.mark.usefixtures("legal_dongs")
def test_unsold_values_have_provenance_rows(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], fixtures_dir: Path, http: HttpClient
) -> None:
    region, snapshot = region_ctx
    sept = snapshot.model_copy(update={"asof_date": "2026-09-15"})
    with respx.mock(assert_all_called=False) as router:
        router.get("https://stat.molit.go.kr/robots.txt").respond(200, text="User-agent: *\n")
        router.get(MOLIT_DATA_URL).mock(side_effect=_route(fixtures_dir))
        UnsoldCollector(http=http, months=1).fetch(region, sept, None)
        UnsoldCollector(http=http, months=1).fetch(
            region, sept, None
        )  # 멱등 — 같은 값이면 출처 행이 늘지 않는다
    with Session(db_engine) as s:
        rows = list(s.scalars(select(Unsold)))
        fps = list(s.scalars(select(FieldProvenance).where(FieldProvenance.entity == "unsold")))
        urls = {d.id: d.url for d in s.scalars(select(RawDocument))}
    assert rows
    chosen = {(fp.entity_id, fp.field): fp for fp in fps if fp.chosen}
    for u in rows:
        for name in ("total", "post_completion"):
            if getattr(u, name) is None:
                continue
            fp = chosen.get((u.id, name))
            assert fp is not None, f"unsold {u.id} {name} 출처 행 없음"
            assert fp.label == "확인됨" and fp.value_text == str(getattr(u, name))
            assert fp.raw_document_id is not None and fp.url == urls[fp.raw_document_id] and fp.checked_at
            form = "2082" if name == "total" else "5328"
            assert f"formId={form}" in (fp.url or "")
    assert len(fps) == len(chosen), "다시 받아도 출처 행이 늘지 않는다"

"""R4-FIX D18-5 — 공고문 조각 단위 screen·extract 는 유지하되 같은 조각(같은 정규화 본문)은 한 번만 판정한다.

R4: 판정 purpose 가 원문 id(``extract:rd<id>:<조각>``)라 같은 공고문을 다른 원문(첨부 번호가 바뀐 재다운로드·같은 본문 다른
공고)으로 받으면 같은 조각을 다시 판정했다(R4 1회차 screen 190·extract 190 — 원자 분할 + 중복).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.snapshot import store_raw
from app.models import RawDocument
from app.scheduler.context import SchedulerContext
from app.scheduler.pipeline import run_pipeline

from .conftest import SynthJev
from .test_r25 import NOTICE_FIXTURES, _seed_notice


def _same_text_second_doc(factory: sessionmaker[Session], cid: int) -> None:
    """같은 공고문 본문(공백만 다름 — 정규화하면 같다)을 다른 원문(다른 첨부 URL)으로 하나 더."""
    fname = "2025000435_centreville.txt"
    data = (NOTICE_FIXTURES / fname).read_bytes().replace(b"\n", b" \n") + b"\n\n"
    manifest = json.loads((NOTICE_FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    url = next(m["url"] for m in manifest if m["file"] == fname) + "&atchmnflSn=99"
    stored = store_raw(data, source="notice_pdf", day=date(2026, 10, 8), ext="txt")
    with factory() as s:
        s.add(
            RawDocument(
                source_kind="notice_pdf", url=url, fetched_at="2026-10-08T06:00:00+09:00", http_status=200,
                sha256=stored.sha256, path=stored.relpath, content_type="text/plain", text_path=stored.relpath,
                region_id=1, complex_id=cid,
            )
        )  # fmt: skip
        s.commit()
        assert len(s.scalars(select(RawDocument).where(RawDocument.complex_id == cid)).all()) == 2


def test_same_chunk_in_two_documents_is_judged_once(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    cid, _ = _seed_notice(factory)
    _same_text_second_doc(factory, cid)
    jev.extract_values = {"max_price_won": "699,400,000원"}
    out = run_pipeline(make_ctx(), seeded, complex_ids=[cid])
    n_extract = jev.calls.count("jev_extract")
    assert n_extract >= 1
    requests = out.carried.get("extract_requests", 0)
    assert requests == 2 * n_extract, (
        f"요청 {requests}건(원문 2개) 중 판정기 extract 는 조각마다 1번: {n_extract}"
    )
    assert out.cached_by_tool.get("extract", 0) == n_extract, "두 번째 원문의 같은 조각은 캐시"
    assert out.extract_applied >= 1

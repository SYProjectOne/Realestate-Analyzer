"""R5-PIPE 3(D25, minor — AGENTS 규칙 7 "실패도 데이터다"): 원문 저장(정규화)·파싱 실패를 상태와 함께 **행으로** 남긴다.

수정 전: 수집의 원문 저장 실패는 잡 stats ``store_errors`` 문자열에만, 판정 파이프라인의 공고문 파싱 실패는 잡 stats
``skipped['parse:rd<id>']`` 에만 남았다 — 원문 행(raw_document, G7 ``/ops/sources`` 가 읽는 행)에는 흔적이 없었다.

| 테스트 | 확인 |
| --- | --- |
| ``test_store_failure_is_marked_on_raw_document_and_cleared_on_success`` | 저장 실패 → 그 원문 행 ``error_text`` = ``store_failed: <예외 종류>…``(+ stats 그대로) · 같은 원문 저장이 다음에 성공하면 표식이 지워진다 · 수집기가 쓴 실패 사유(403 등)는 덮어쓰지 않는다 |
| ``test_parse_failure_is_marked_on_raw_document`` | 판정 파이프라인 P1~P3 의 공고문 파서 예외 → 원문 행 ``error_text`` = ``parse_failed: <예외 종류>…`` + stats ``skipped`` · 다음 파싱 성공 때 표식 지움 |

``/ops/sources`` 의 실패 목록(``failing_targets``)은 지금 ``path``·``http_status`` 로만 실패를 가른다(api 소유) — ``last_error_text`` 에는 바로
보인다. 실패 목록에도 넣으려면 api 의 성공 판정에 ``error_text`` 의 ``store_failed:``·``parse_failed:`` 를 더하는 변경이 필요하다(보고 요청).
"""

# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import RawDocument
from app.scheduler import collect as collect_mod
from app.scheduler.collect import PROCESS_FAILURE_PREFIXES, collect, mark_process_failure
from app.scheduler.context import SchedulerContext
from app.scheduler.pipeline import run_pipeline

from .conftest import RowsCollector, popup_row


def _doc(factory: sessionmaker[Session], sha: str) -> RawDocument:
    with factory() as s:
        d = s.scalars(select(RawDocument).where(RawDocument.sha256 == sha)).one()
        s.expunge(d)
        return d


def test_store_failure_is_marked_on_raw_document_and_cleared_on_success(
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    seeded: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = popup_row("yesterday")
    site = RowsCollector(factory, [row])
    ctx = make_ctx(collectors={"official_site": lambda c: site})
    real = collect_mod.store_raw_document

    def boom(*a: Any, **k: Any) -> Any:
        raise RuntimeError("정규화 실패(테스트)")

    monkeypatch.setattr(collect_mod, "store_raw_document", boom)
    res = collect(ctx, 1, ["official_site"], asof_date="2026-10-07")
    assert res.store_errors, res.stats()
    d = _doc(factory, row["sha256"])
    assert d.error_text is not None and d.error_text.startswith("store_failed: RuntimeError"), d.error_text

    monkeypatch.setattr(collect_mod, "store_raw_document", real)
    res2 = collect(ctx, 1, ["official_site"], asof_date="2026-10-07")
    assert not res2.store_errors, res2.store_errors
    assert _doc(factory, row["sha256"]).error_text is None  # 저장 성공 → 표식 지움

    # 수집기가 쓴 실패 사유(접근 거부 등)는 처리 실패 표식으로 덮지 않는다
    with factory() as s:
        doc = s.scalars(select(RawDocument).where(RawDocument.sha256 == row["sha256"])).one()
        doc.error_text = "403 Forbidden"
        mark_process_failure(s, doc.id, "store", RuntimeError("x"))
        assert doc.error_text == "403 Forbidden"
        s.rollback()
    assert PROCESS_FAILURE_PREFIXES == ("store_failed:", "parse_failed:")


class _Broken:
    source_kind = "notice_pdf"

    def parse(self, raw: Any) -> list[Any]:
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "깨진 공고문 텍스트(테스트)")


def test_parse_failure_is_marked_on_raw_document(
    make_ctx: Callable[..., SchedulerContext],
    factory: sessionmaker[Session],
    seeded: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.scheduler.pipeline as pipeline_mod

    monkeypatch.setattr(pipeline_mod, "parser_for", lambda kind, **k: _Broken())
    with factory() as s:
        doc = RawDocument(
            source_kind="notice_pdf", url="https://www.applyhome.co.kr/missing.pdf",
            fetched_at="2026-10-07T05:00:00+09:00", http_status=200, sha256="f" * 64,
            path="notice_pdf/2026-10-07/없는파일.pdf", text_path="notice_pdf/2026-10-07/없는파일.txt",
            content_type="application/pdf", complex_id=2, region_id=1,
        )  # fmt: skip
        s.add(doc)
        s.commit()
        rd = doc.id
    res = run_pipeline(make_ctx(), seeded, complex_ids=[2])
    assert not res.degraded, res.error
    assert f"parse:rd{rd}" in res.skipped, res.skipped
    with factory() as s:
        row = s.get(RawDocument, rd)
        assert row is not None and row.error_text is not None
        assert row.error_text.startswith("parse_failed: UnicodeDecodeError"), row.error_text
    # 파싱이 다음에 성공하면 표식을 지운다(같은 원문 — 파일이 없으면 파서는 예외 없이 '실패 후보'를 낸다)
    monkeypatch.undo()
    run_pipeline(make_ctx(), seeded, complex_ids=[2])
    with factory() as s:
        row = s.get(RawDocument, rd)
        assert row is not None and row.error_text is None, row.error_text

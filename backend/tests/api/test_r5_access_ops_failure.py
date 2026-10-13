"""R5-ACCESS 4 (R5-PIPE 요청, 계약 변경 없음): ``/ops/sources`` 의 성공 판정(``ops._ok``)이 원문 처리 실패 표식을 실패로 본다.

R5-PIPE 가 원문 행 ``error_text`` 에 ``store_failed: …``(원문 저장·정규화 실패)·``parse_failed: …``(공고문 파서 예외)를 남기게 했다
(``app.scheduler.collect.PROCESS_FAILURE_PREFIXES``, AGENTS 규칙 7). 수정 전 ``_ok`` 는 ``path``·``http_status`` 만 봐서 이 행이
'성공'으로 세어지고 ``failing_targets`` 에 나오지 않았다(``last_error_text`` 에만 보임).

| 테스트 | 확인 |
| --- | --- |
| ``test_process_failure_marks_are_failing_targets`` | 표식 행 → ``failing_targets``(reason = 표식 문구)·``failures_7d`` 에 들어가고 ``last_success_at`` 이 되지 않는다 |
| ``test_collector_markers_without_failure_prefix_stay_success`` | 수집기 표식(OCR ``scan``·``scan_partial``)은 원문이 있으면 그대로 성공(가드) |
"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_session
from app.core.time import now_kst
from app.models import RawDocument
from app.scheduler.collect import PROCESS_FAILURE_PREFIXES

from ._support import WRITE, validate


def _add(source_kind: str, url: str, error_text: str | None, *, sha: str) -> int:
    now = now_kst().isoformat(timespec="seconds")
    with get_session() as s:
        d = RawDocument(
            source_kind=source_kind, url=url, fetched_at=now, http_status=200, sha256=sha,
            path=f"{source_kind}/r5_access_{sha[:8]}.html", content_type="text/html", error_text=error_text,
        )  # fmt: skip
        s.add(d)
        s.commit()
        return d.id


def _source(client: TestClient, kind: str) -> dict[str, Any]:
    body = client.get("/api/ops/sources", headers=WRITE).json()
    validate("listSourceStatus", 200, body)
    return next(s for s in body if s["source_kind"] == kind)


def test_process_failure_marks_are_failing_targets(client: TestClient) -> None:
    assert PROCESS_FAILURE_PREFIXES == ("store_failed:", "parse_failed:")
    before_site = _source(client, "official_site")
    before_pdf = _source(client, "notice_pdf")
    store = "store_failed: RuntimeError: 정규화 실패(테스트)"
    parse = "parse_failed: ValueError: 표 해석 실패(테스트)"
    site_url = "https://example.invalid/r5-access/site"
    pdf_url = "https://example.invalid/r5-access/notice.pdf"
    site_id = _add("official_site", site_url, store, sha="a" * 64)
    pdf_id = _add("notice_pdf", pdf_url, parse, sha="b" * 64)

    for kind, url, rid, text, before in (
        ("official_site", site_url, site_id, store, before_site),
        ("notice_pdf", pdf_url, pdf_id, parse, before_pdf),
    ):
        src = _source(client, kind)
        hit = [t for t in src["failing_targets"] if t["url"] == url]
        assert hit, f"{kind}: {text!r} 행이 failing_targets 에 없음 — {src['failing_targets']}"
        assert hit[0]["raw_document_id"] == rid and hit[0]["reason"] == text and hit[0]["http_status"] == 200
        assert src["failures_7d"] == before["failures_7d"] + 1, kind
        assert src["successes_7d"] == before["successes_7d"], kind
        assert src["attempts_7d"] == before["attempts_7d"] + 1, kind
        assert src["last_error_text"] == text, kind
        assert src["last_success_at"] == before["last_success_at"], f"{kind}: 처리 실패 행이 최종 성공이 됨"


def test_collector_markers_without_failure_prefix_stay_success(client: TestClient) -> None:
    before = _source(client, "notice_pdf")
    urls = {}
    for i, marker in enumerate(("scan", "scan_partial:2")):
        url = f"https://example.invalid/r5-access/scan{i}.pdf"
        urls[url] = _add("notice_pdf", url, marker, sha=f"{i}" * 64)
    src = _source(client, "notice_pdf")
    assert not [t for t in src["failing_targets"] if t["url"] in urls], src["failing_targets"]
    assert src["successes_7d"] == before["successes_7d"] + 2
    assert src["failures_7d"] == before["failures_7d"]
    with get_session() as s:
        assert len(list(s.scalars(select(RawDocument).where(RawDocument.url.in_(urls))))) == 2

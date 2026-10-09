"""R3b G1 — 잔여 공고 (F1a minor): 첫 수집 과거 잔여 공고 이벤트 폭주 방지 · N+1 없음.

- 지역 최초 적재(region.status 가 ready 가 아님 = bootstrap — 어차피 전체 판정) 또는 접수가 이미 끝난 과거 공고의 새 행은
  info(재판정 없음). 지금·앞으로 접수하는 새 잔여 공고만 critical.
- 공고마다 주택형·경쟁률 원문을 따로 조회하지 않는다(URL 일괄 조회).
"""

# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models import Region
from app.normalize.remaining import sync_remaining_events

from ._assemble_support import add_complex
from ._support import AddRaw
from .test_remaining_f1a import SONGDO, _api_notice

DETECTED = "2026-10-09T06:00:00+09:00"


def test_past_notice_new_row_is_info_not_critical(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    """배포 후 첫 수집: 접수가 끝난 과거 잔여 공고 전부 → info(재판정 폭주 없음)."""
    add_complex(
        db_session, region.id, "2024000777", "더샵 송도마리나베이", address="송도동", legal_dong_code=SONGDO
    )
    _api_notice(
        db_session,
        add_raw,
        region,
        "2025910001",
        "더샵 송도마리나베이(1회차)",
        notice="2025-03-01",
        rcpt=("2025-03-05", "2025-03-05"),
    )
    _api_notice(
        db_session,
        add_raw,
        region,
        "2025910002",
        "더샵 송도마리나베이(2회차)",
        notice="2025-06-01",
        rcpt=("2025-06-05", "2025-06-05"),
        comp=False,
    )
    res = sync_remaining_events(db_session, region.id, snapshot_id=None, detected_at=DETECTED)
    assert res.inserted == 2
    assert {(e.severity, e.triggers_rejudge) for e in res.events} == {("info", False)}


def test_current_notice_new_row_is_critical(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    add_complex(
        db_session, region.id, "2024000777", "더샵 송도마리나베이", address="송도동", legal_dong_code=SONGDO
    )
    _api_notice(
        db_session,
        add_raw,
        region,
        "2026910242",
        "더샵 송도마리나베이(3회차)",
        notice="2026-10-01",
        rcpt=("2026-10-12", "2026-10-12"),
    )
    res = sync_remaining_events(db_session, region.id, snapshot_id=None, detected_at=DETECTED)
    assert [(e.severity, e.triggers_rejudge) for e in res.events] == [("critical", True)]


def test_bootstrap_initial_load_is_info(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    """지역 최초 적재(bootstrap)는 진행 중 공고도 info — bootstrap 이 전체 판정을 돌린다."""
    region.status = "bootstrapping"
    add_complex(
        db_session, region.id, "2024000777", "더샵 송도마리나베이", address="송도동", legal_dong_code=SONGDO
    )
    _api_notice(
        db_session,
        add_raw,
        region,
        "2026910242",
        "더샵 송도마리나베이(3회차)",
        notice="2026-10-01",
        rcpt=("2026-10-12", "2026-10-12"),
    )
    res = sync_remaining_events(db_session, region.id, snapshot_id=None, detected_at=DETECTED)
    assert [e.severity for e in res.events] == ["info"]


@contextmanager
def _count_raw_selects(db_session: Session) -> Iterator[list[str]]:
    seen: list[str] = []
    engine = db_session.get_bind()

    def on(conn: Any, cursor: Any, statement: str, *a: Any) -> None:
        low = statement.lower()
        if low.lstrip().startswith("select") and "from raw_document" in low:
            seen.append(statement)

    event.listen(engine, "before_cursor_execute", on)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", on)


def test_no_n_plus_one_raw_queries(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    for i in range(2):
        _api_notice(db_session, add_raw, region, f"20259100{i:02d}", f"단지{i}(1회차)", comp=False)
    with _count_raw_selects(db_session) as few:
        sync_remaining_events(db_session, region.id, snapshot_id=None, detected_at=DETECTED)
    for i in range(2, 10):
        _api_notice(db_session, add_raw, region, f"20259100{i:02d}", f"단지{i}(1회차)", comp=False)
    with _count_raw_selects(db_session) as many:
        res = sync_remaining_events(db_session, region.id, snapshot_id=None, detected_at=DETECTED)
    assert res.inserted == 8
    assert len(many) == len(few), (len(few), len(many))

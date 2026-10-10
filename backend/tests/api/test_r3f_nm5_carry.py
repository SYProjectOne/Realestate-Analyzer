"""R3f CORE4 — R3 6차 N-M5 / DECISIONS D14-7 (계약 2026-10-09.11): 이월·재판정 판단은 단지 단위.

리뷰 재현(scratchpad b/test_probe_m2.py): 단지 A rejudge 실패 뒤 다른 단지만 재판정한 실행이 같은 리비전에서 성공하면 리비전의
마지막 점수 실행 시각이 늦어져 A 의 이벤트·실패가 가려졌다(``before_partial=True after_partial=False``).
"""

# ruff: noqa: E501

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_session
from app.models import ChangeEvent, JobRun, ScoreRun, Snapshot

from .test_r3b_g3 import CX, SNAP

OTHER = 5


def _event(
    s: object, cid: int | None, at: str, *, entity: str = "complex", entity_id: int | None = None
) -> None:
    s.add(  # type: ignore[attr-defined]
        ChangeEvent(snapshot_id=SNAP, entity=entity, entity_id=entity_id if entity_id is not None else cid, field="move_in_ym",
                    old_text="a", new_text="b", detected_at=at, severity="critical", triggers_rejudge=True, complex_id=cid)
    )  # fmt: skip


def _job(s: object, status: str, ids: list[int] | None, finished: str, name: str = "rejudge") -> None:
    payload = (
        {"snapshot_id": SNAP, "scenario_id": None, "complex_ids": ids, "reason": "시험"}
        if name == "rejudge"
        else {"region_id": 1}
    )
    s.add(
        JobRun(
            job_name=name,
            kind="rejudge",
            status=status,
            payload=payload,
            scheduled_at=finished,
            finished_at=finished,
            stats={},
        )
    )  # type: ignore[attr-defined]


def test_nm5_partial_success_does_not_hide_failed_complex(client: TestClient) -> None:
    from app.scheduler.handlers import changed_after_runs

    with get_session() as s:
        base = s.scalars(select(ScoreRun).where(ScoreRun.snapshot_id == SNAP)).first()
        assert base is not None
        _event(s, CX, "2099-01-01T10:00:00+09:00")
        _job(s, "failed", [CX], "2099-01-01T10:05:00+09:00")  # A 재판정 실패(판정기 장애)
        s.flush()
        assert CX in changed_after_runs(s, s.get(Snapshot, SNAP))  # type: ignore[arg-type]
        # 다른 단지만 재판정한 실행이 같은 리비전에서 성공(10:30) — 리비전의 마지막 실행 시각이 늦어진다
        _job(s, "done", [OTHER], "2099-01-01T10:30:00+09:00")
        s.add(
            ScoreRun(
                snapshot_id=SNAP,
                scenario_id=base.scenario_id,
                weights=base.weights,
                created_at="2099-01-01T10:30:00+09:00",
            )
        )
        s.flush()
        stale = changed_after_runs(s, s.get(Snapshot, SNAP))  # type: ignore[arg-type]
        assert CX in stale, "A 의 이벤트·실패가 다른 단지 성공 실행에 가려지면 안 된다(D14-7)"
        assert OTHER not in stale, "방금 판정한 단지는 이월 가능"
        s.rollback()


def test_nm5_later_success_for_that_complex_clears_it(client: TestClient) -> None:
    from app.scheduler.handlers import changed_after_runs

    with get_session() as s:
        _event(s, CX, "2099-01-01T10:00:00+09:00")
        _job(s, "failed", [CX], "2099-01-01T10:05:00+09:00")
        _job(s, "done", [CX], "2099-01-01T10:40:00+09:00")  # 복구 뒤 그 단지 재판정 성공
        s.flush()
        assert CX not in changed_after_runs(s, s.get(Snapshot, SNAP))  # type: ignore[arg-type]
        s.rollback()


def test_nm5_region_level_event_after_complex_judgment(client: TestClient) -> None:
    """지역 단위 변경(생활권 편집 — complex_id 없음)은 그 뒤에 판정하지 않은 단지 전부. 그 뒤 판정한 단지는 빠진다."""
    from app.scheduler.handlers import changed_after_runs

    with get_session() as s:
        _job(s, "done", None, "2099-01-01T09:00:00+09:00")  # 전체 재판정
        _event(s, None, "2099-01-01T10:00:00+09:00", entity="region", entity_id=1)
        _job(s, "done", [CX], "2099-01-01T11:00:00+09:00")
        s.flush()
        stale = changed_after_runs(s, s.get(Snapshot, SNAP))  # type: ignore[arg-type]
        assert CX not in stale and OTHER in stale
        s.rollback()


def test_nm5_bootstrap_job_counts_as_judgment(client: TestClient) -> None:
    from app.scheduler.handlers import changed_after_runs

    with get_session() as s:
        _event(s, CX, "2099-01-01T10:00:00+09:00")
        _job(s, "done", None, "2099-01-01T12:00:00+09:00", name="region.bootstrap")
        s.flush()
        assert CX not in changed_after_runs(s, s.get(Snapshot, SNAP))  # type: ignore[arg-type]
        s.rollback()

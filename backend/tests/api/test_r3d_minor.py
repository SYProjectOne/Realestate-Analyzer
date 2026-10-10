"""R3d CORE2 — API·스케줄러 쪽 4차 리뷰 minor(`R3_REVIEW4.md`). 실제 경로만(spy 없음).

| minor | 테스트 |
| --- | --- |
| 출처 서랍 | 강등된 사실의 출처(GET /provenance/fp_N)가 '확인 불가(검증 모순)'를 보인다 |
| change_event | 강등 change_event·재판정은 발행 스냅샷이 아니라 쓰기 가능 리비전에 붙는다 |
| M-9(3차) | 단지가 제외돼도 사람이 만든 체크리스트 항목은 auto 로 닫히지 않는다 |
| 리비전 | 변경 없는 주간 수집 뒤 building 리비전이 남지 않는다(이월·발행) |
| §12 | 사람 확인 리비전 요약은 'rerank 다시 실행' 이라고 쓰지 않는다 |
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_session
from app.models import ChangeEvent, ChecklistItem, Complex, FactDemotion, JobRun, Snapshot

from ._support import READ, WRITE
from .test_r3b_g3 import CX, SNAP
from .test_r3c_core import _demote_resale


def test_provenance_drawer_shows_demotion(client: TestClient) -> None:
    from ._support import as_live

    as_live()  # 계약 .11(D14-1): 발행 리비전 서랍은 저장본 — 실시간 강등 표시는 발행 전 리비전에서 본다
    _demote_resale(client)
    with get_session() as s:
        d = s.scalars(select(FactDemotion)).one()
        fp_id = d.original_fp_id
    assert fp_id is not None
    body = client.get(f"/api/provenance/fp_{fp_id}", headers=READ).json()
    assert body["label"] == "확인 불가" and "검증 모순" in (body["reason"] or ""), body
    assert body["value_text"], "모순 값(원문)은 근거로 그대로 보인다"


def test_demotion_change_event_goes_to_writable_revision_not_published(client: TestClient) -> None:
    _demote_resale(client)
    with get_session() as s:
        ce = s.scalars(
            select(ChangeEvent).where(ChangeEvent.complex_id == CX, ChangeEvent.new_text.like("확인 불가%"))
        ).one()
        assert ce.snapshot_id != SNAP, "발행 스냅샷 12 는 불변(D11-1)"
        rev = s.get(Snapshot, ce.snapshot_id)
        assert rev is not None and rev.revision_of == SNAP and rev.status == "building"
        job = s.scalars(select(JobRun).where(JobRun.job_name == "rejudge")).one()
        assert job.payload["snapshot_id"] == rev.id


def test_excluded_complex_keeps_human_checklist_items(client: TestClient) -> None:
    from app.normalize.checklist import sync_checklist

    with get_session() as s:
        s.add(
            ChecklistItem(
                complex_id=CX, kind="법적 확인", title="사람이 만든 메모: 분양사무소 재방문", status="open"
            )
        )
        cx = s.get(Complex, CX)
        assert cx is not None
        cx.inclusion_class = "범위 경계"  # 단지 제외
    with get_session() as s:
        sync_checklist(s, 1, asof_date="2026-10-08")
        item = s.scalars(
            select(ChecklistItem).where(ChecklistItem.title == "사람이 만든 메모: 분양사무소 재방문")
        ).one()
        assert item.status == "open" and item.closed_by is None, "사람 항목은 사람이 닫는다"


def test_unchanged_weekly_collect_does_not_leave_building_revision(client: TestClient) -> None:
    from app.core.db import get_sessionmaker
    from app.scheduler.context import SchedulerContext
    from app.scheduler.handlers import _finish_unchanged_revision
    from app.scheduler.snapshots import get_or_create

    with get_session() as s:
        base = s.get(Snapshot, SNAP)
        assert base is not None and base.status == "published"
        rev = get_or_create(s, base.region_id, base.asof_date, created_at="2026-10-09T07:00:00+09:00")
        assert rev.id != SNAP and rev.status == "building"
        rid = rev.id

    def no_judge() -> Any:
        raise AssertionError("판정기를 부르면 안 된다")

    ctx = SchedulerContext(session_factory=get_sessionmaker(), adapter_factory=no_judge, collectors={})
    out = _finish_unchanged_revision(ctx, rid)
    # 계약 .10(D13-4): 변경 없는 주간 수집은 새 리비전을 만들지 않는다 — 빈 리비전을 지우고 직전 발행 리비전 유지
    # (예전 .9: 같은 내용 리비전을 복사·발행)
    assert out == {"discarded_revision": rid, "kept": SNAP}, out
    with get_session() as s:
        assert s.get(Snapshot, rid) is None


def test_section12_summary_does_not_claim_rerank_rerun_for_human_check_revision(client: TestClient) -> None:
    from app.reports.data import load_report

    from ._support import publish_revision

    rid = publish_revision(1, "사람 확인 리비전(테스트)")  # 계약 .11(D14-5): 발행은 snapshot.publish 잡
    with get_session() as s:
        data = load_report(s, rid, scenario_id=None, compare_snapshot_id=SNAP)
    assert data.extra is not None
    assert "다시 실행하지 않았다" in data.extra.summary and "다시 실행했다" not in data.extra.summary, (
        data.extra.summary
    )
    _ = WRITE

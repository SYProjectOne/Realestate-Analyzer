"""T3 후반: 공식 홈페이지 403 → '확인 불가' → 사람 확인 '가능' 입력 → rejudge → 상황 후보 포함.

사람 확인 입력(human_check + intake_status(path=human_check) + change_event + rejudge 잡)은 API(WP5)가 한다 —
여기서는 그 행들을 같은 모양으로 넣고 WP7 이 처리하는 부분(재판정 후 D 상황 후보 포함)을 검사한다.
"""

# ruff: noqa: E501  (한국어 docstring·픽스처 행)

from __future__ import annotations

import json
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import ChangeEvent, Decision, HumanCheck, IntakeStatus, ScoreRun, ScoreTotal
from app.scheduler import runner
from app.scheduler.context import SchedulerContext
from app.scheduler.rejudge import enqueue_rejudge
from app.scheduler.snapshots import writable

from .conftest import FIXTURE

SCENARIO_D = 5  # 내장 시나리오 D 즉시 구매(접수 '가능'이 아니면 후보 제외)


def _d_total(s: Session, snapshot_id: int, complex_id: int) -> ScoreTotal:
    run = s.scalars(
        select(ScoreRun)
        .where(ScoreRun.snapshot_id == snapshot_id, ScoreRun.scenario_id == SCENARIO_D)
        .order_by(ScoreRun.id.desc())
    ).first()
    assert run is not None
    row = s.scalars(
        select(ScoreTotal).where(ScoreTotal.score_run_id == run.id, ScoreTotal.complex_id == complex_id)
    ).one()
    return row


def test_human_check_then_rejudge_includes_complex(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int
) -> None:
    hc = json.loads(
        (FIXTURE / "raw" / "human_check" / "t3_switzen_possible.json").read_text(encoding="utf-8")
    )
    cid = int(hc["complex_id"])
    ctx = make_ctx()
    with factory() as s:
        before = s.scalars(
            select(IntakeStatus).where(IntakeStatus.complex_id == cid, IntakeStatus.path != "unofficial_ref")
        ).all()
        assert before and all(
            i.status == "확인 불가" and i.http_status == 403 for i in before
        )  # 공식 경로 403
        enqueue_rejudge(s, seeded, None, "최초 판정")
        s.commit()
    runner.run_until_idle(ctx)
    with factory() as s:
        t = _d_total(s, seeded, cid)
        assert t.rank is None  # D: 접수 확인 불가 → 후보 제외

        # --- API(WP5)가 하는 일: human_check + intake(human_check) + change_event + rejudge.
        # 발행 스냅샷은 바꾸지 않는다 — 사람 확인은 같은 기준일 새 리비전에 쓴다(D11-1)
        target = writable(s, seeded, reason="사람 확인", created_at=hc["checked_at"]).id
        assert target != seeded
        h = HumanCheck(
            complex_id=cid,
            field="intake_status",
            value_text=hc["value_text"],
            kind=hc["kind"],
            checked_at=hc["checked_at"],
            entered_by=hc["entered_by"],
        )
        s.add(h)
        s.flush()
        s.add(
            IntakeStatus(
                complex_id=cid,
                snapshot_id=target,
                status="가능",
                path="human_check",
                checked_at=hc["checked_at"],
                entered_by=hc["entered_by"],
                note=f"hc_{h.id}",
            )
        )
        ev = ChangeEvent(
            snapshot_id=target, entity="intake_status", entity_id=None, field="status", old_text="확인 불가",
            new_text="가능", detected_at="2026-10-09T10:00:00+09:00", severity="critical", triggers_rejudge=True,
            complex_id=cid,
        )  # fmt: skip
        s.add(ev)
        s.flush()
        job = enqueue_rejudge(s, target, [cid], "사람 확인 입력", change_event_ids=[ev.id])
        s.commit()
        assert job.payload["complex_ids"] == [cid]
    runner.run_until_idle(ctx)
    with factory() as s:
        assert _d_total(s, seeded, cid).rank is None  # 발행 리비전은 그대로
        t = _d_total(s, target, cid)
        assert t.rank is not None and t.total is not None  # 후보 포함
        run = s.scalars(
            select(ScoreRun).where(ScoreRun.snapshot_id == target, ScoreRun.scenario_id == SCENARIO_D)
            .order_by(ScoreRun.id.desc())
        ).first()  # fmt: skip
        assert run is not None
        mine = s.scalars(
            select(Decision).where(Decision.score_run_id == run.id, Decision.complex_id == cid)
        ).first()
        if (
            mine is not None
        ):  # D 의 접근 요건은 공급 경로(무순위·임의·선착순)로 본다(RA §6-7 — R3 3차 RA 부분)
            assert mine.req_access_pre and "공고" in mine.req_access_pre["evidence"]

"""claim.reverify 잡 (계약 2026-10-09.4, R3 M8): contradicted 주장 문장 수정 → 원자 분할 → verify → 자식 행.

PATCH /claims/{id}(API, tests/api/test_r3_f3.py)가 등록하는 잡을 worker 가 처리하는 부분. 판정기는 SynthJev.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.judge.claims import remaining_contradicted
from app.models import Claim, Complex, JobRun
from app.scheduler import runner
from app.scheduler.context import SchedulerContext
from app.scheduler.reverify import parse_evidence

from .conftest import SynthJev


def _setup(factory: sessionmaker[Session], snapshot_id: int, text: str) -> tuple[int, int]:
    with factory() as s:
        cx = s.scalars(select(Complex).order_by(Complex.id)).first()
        assert cx is not None
        parent = Claim(
            snapshot_id=snapshot_id,
            section=f"complex:{cx.id}",
            complex_id=cx.id,
            text="틀린 문장이다",
            evidence_text="fp_1: 공고문 발췌",
            verify_status="contradicted",
            ordinal=0,
        )
        s.add(parent)
        s.flush()
        job = JobRun(
            job_name="claim.reverify",
            kind="manual",
            payload={"snapshot_id": snapshot_id, "claim_id": parent.id, "text": text},
            scheduled_at="2026-10-08T09:00:00+09:00",
            status="queued",
            stats={},
        )
        s.add(job)
        s.commit()
        return parent.id, job.id


def _children(factory: sessionmaker[Session], parent_id: int) -> list[Claim]:
    with factory() as s:
        return list(s.scalars(select(Claim).where(Claim.parent_claim_id == parent_id).order_by(Claim.id)))


def test_reverify_splits_and_verifies(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    text = "단지 A의 +10% 명제는 unlikely이고 +20% 명제는 uncertain이다"
    parent_id, job_id = _setup(factory, seeded, text)
    ctx = make_ctx()
    assert runner.claim(ctx, job_id)
    assert runner.execute(ctx, job_id) == "done"
    kids = _children(factory, parent_id)
    assert len(kids) >= 2, "복합 문장은 원자 주장 2개 이상으로 나눠 verify(T6)"
    assert all(k.verify_status == "verified" and k.judgment_seq is not None for k in kids)
    assert "verify" in " ".join(jev.calls)
    with factory() as s:
        parent = s.get(Claim, parent_id)
        assert parent is not None and parent.text == "틀린 문장이다"
        assert parent.verify_status == "contradicted"
        assert remaining_contradicted(s, seeded) == []
        job = s.get(JobRun, job_id)
        assert job is not None and job.stats["children"] == len(kids)
        pub = s.scalars(select(JobRun).where(JobRun.job_name == "snapshot.publish")).all()
        assert pub, "남은 contradicted 0 → publish 등록"
    # 다시 돌려도 자식이 늘지 않는다(멱등)
    with factory() as s:
        again = JobRun(
            job_name="claim.reverify", kind="manual",
            payload={"snapshot_id": seeded, "claim_id": parent_id, "text": text},
            scheduled_at="2026-10-08T09:01:00+09:00", status="queued", stats={},
        )  # fmt: skip
        s.add(again)
        s.commit()
        again_id = again.id
    assert runner.claim(ctx, again_id) and runner.execute(ctx, again_id) == "done"
    assert len(_children(factory, parent_id)) == len(kids)


def test_reverify_contradicted_child_still_blocks(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    jev.verdict = "contradicted"
    parent_id, job_id = _setup(factory, seeded, "단지 A의 입주 예정 시기는 2030-01이다")
    ctx = make_ctx()
    assert runner.claim(ctx, job_id) and runner.execute(ctx, job_id) == "done"
    kids = _children(factory, parent_id)
    assert kids and all(k.verify_status == "contradicted" for k in kids)
    with factory() as s:
        left = remaining_contradicted(s, seeded)
        assert {c.id for c in left} == {k.id for k in kids}, "자식이 contradicted 면 그것이 publish 를 막는다"


def test_reverify_judge_down_fails_without_children(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int, jev: SynthJev
) -> None:
    jev.down = True
    parent_id, job_id = _setup(factory, seeded, "단지 A의 입주 예정 시기는 2030-01이다")
    ctx = make_ctx()
    assert runner.claim(ctx, job_id)
    assert runner.execute(ctx, job_id) == "failed"
    assert _children(factory, parent_id) == []
    with factory() as s:
        job = s.get(JobRun, job_id)
        assert job is not None and (job.error_text or "").startswith("judge_unavailable")


def test_copy_claims_keeps_split_links(factory: sessionmaker[Session], seeded: int) -> None:
    """이전 스냅샷 주장 복사(carry_forward·P9 미대상)에서 분할 연결이 끊기면 contradicted 가 다시 남는다."""
    from app.models import Snapshot
    from app.scheduler.persist import copy_claims

    with factory() as s:
        snap = s.get(Snapshot, seeded)
        assert snap is not None
        dst = Snapshot(
            region_id=snap.region_id, asof_date="2026-10-09", status="building", created_at="2026-10-09"
        )
        s.add(dst)
        parent = Claim(snapshot_id=seeded, section="x", text="복합", verify_status="contradicted", ordinal=0)
        s.add(parent)
        s.flush()
        child = Claim(
            snapshot_id=seeded, section="x", text="원자", verify_status="verified", parent_claim_id=parent.id
        )
        s.add(child)
        s.flush()
        assert copy_claims(s, seeded, dst.id, None) >= 2
        assert remaining_contradicted(s, dst.id) == []
        s.rollback()


def test_parse_evidence() -> None:
    assert parse_evidence("fp_1: 가; fp_2: 나") == [("fp_1", "가"), ("fp_2", "나")]
    assert parse_evidence("근거 문장") == [("claim", "근거 문장")]
    assert parse_evidence(None) == []

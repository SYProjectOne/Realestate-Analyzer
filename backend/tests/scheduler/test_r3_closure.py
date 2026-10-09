"""R3 마무리 — P8 가상 후보 '모집공고 대기'(wait_new, 계약 2026-10-09.5) + D9-1 참여 규칙(남은 사다리 행).

보고서 §8-2·§12-5-2: decide 후보 = TOP 5 + "모집공고 대기"(+ escape hatch). 시나리오 policy.include_wait_new(내장 A 만
true) 이면 단지 후보 ≤5 + 가상 후보 1(합 ≤6), 근거 = 지역 (A) 트랙 공고 예정 목록 요약. 지역명은 픽스처에만 있다.
"""

# ruff: noqa: E501  (한국어 docstring·픽스처 행)

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.views import load_bundles, score_input
from app.judge.jev_mcp import JevMcpAdapter
from app.judge.payloads import DECIDE_MAX, WAIT_NEW_DESCRIPTION, WAIT_NEW_OPTION
from app.models import Complex, Decision, Ladder, Region, ScoreRun, ScoreTotal, Snapshot
from app.scheduler.context import SchedulerContext
from app.scheduler.inputs import load_facts
from app.scheduler.payloads import scenario_payloads, wait_new_evidence
from app.scheduler.pipeline import load_scenarios, run_pipeline

from .conftest import SynthJev


@dataclass
class DecideSpy(SynthJev):
    """decide payload 를 purpose 없이 순서대로 기록(시나리오 base·A·B·C·D 순으로 불린다)."""

    decides: list[dict[str, Any]] = field(default_factory=list)

    def _decide(self, a: dict[str, Any]) -> dict[str, Any]:
        self.decides.append(a)
        out = super()._decide(a)
        if any(c["id"] == WAIT_NEW_OPTION for c in a["candidates"]):  # 보고서 #126: A 는 wait_new 선택
            out["recommendation"]["selected"] = WAIT_NEW_OPTION
            out["recommendation"]["probabilities"][WAIT_NEW_OPTION] = 0.94
        return out


def _ctx(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], jev: SynthJev
) -> SchedulerContext:
    return make_ctx(adapter_factory=lambda: JevMcpAdapter(transport=jev, session_factory=factory, secrets=[]))


def test_wait_new_virtual_candidate_only_for_policy_scenarios(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int
) -> None:
    jev = DecideSpy()
    res = run_pipeline(_ctx(make_ctx, factory, jev), seeded)
    assert not res.degraded, res.error
    with_wait = [d for d in jev.decides if any(c["id"] == WAIT_NEW_OPTION for c in d["candidates"])]
    assert len(with_wait) == 1 and len(jev.decides) == 5  # 내장 A 만(policy.include_wait_new)
    a = with_wait[0]
    ids = [c["id"] for c in a["candidates"]]
    assert ids[-1] == WAIT_NEW_OPTION and len(ids) <= DECIDE_MAX
    assert sum(1 for i in ids if i.startswith("complex_")) == DECIDE_MAX - 1  # TOP 5 + 모집공고 대기
    assert (
        next(c for c in a["candidates"] if c["id"] == WAIT_NEW_OPTION)["description"] == WAIT_NEW_DESCRIPTION
    )
    # 근거 = 지역 (A) 트랙 공고 예정 목록 요약(픽스처 15·16 = track A, 공고 전)
    with factory() as s:
        names = {c.id: c.name for c in s.scalars(select(Complex).where(Complex.track == "A"))}
    assert set(names) == {15, 16}
    block = a["evidence"].split(f"[{WAIT_NEW_OPTION}]", 1)[1]
    assert "지역 (A) 트랙 공고 예정 2곳" in block and all(n in block for n in names.values())
    for other in jev.decides:
        if other is not a:
            assert len(other["candidates"]) <= DECIDE_MAX and WAIT_NEW_OPTION not in other["evidence"]
    # decision 행: 가상 후보 = option_key wait_new · complex_id null · 선택(보고서 #126)
    with factory() as s:
        run_a = s.scalars(
            select(ScoreRun).where(ScoreRun.snapshot_id == seeded, ScoreRun.scenario_id == 2)
        ).one()
        rows = list(s.scalars(select(Decision).where(Decision.score_run_id == run_a.id)))
        wait = [r for r in rows if r.option_key == WAIT_NEW_OPTION]
        assert len(wait) == 1 and wait[0].complex_id is None and wait[0].chosen
        assert float(wait[0].prob or 0) == 0.94
        assert wait[0].req_access_judge == "supported" and wait[0].req_access_pre is None  # 판정기 판정만
        assert sum(1 for r in rows if r.option_key == "complex") == DECIDE_MAX - 1
        other_runs = list(
            s.scalars(select(ScoreRun.id).where(ScoreRun.snapshot_id == seeded, ScoreRun.scenario_id != 2))
        )
        assert not list(
            s.scalars(
                select(Decision).where(
                    Decision.score_run_id.in_(other_runs), Decision.option_key == WAIT_NEW_OPTION
                )
            )
        )


def test_wait_new_preview_payload_matches_pipeline(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int
) -> None:
    """G5 미리보기(scenario_payloads)도 같은 가상 후보를 넣는다 — 실행 뒤 decide hash 가 캐시에 있다."""
    jev = DecideSpy()
    run_pipeline(_ctx(make_ctx, factory, jev), seeded)
    with factory() as s:
        (a,) = load_scenarios(s, 2)
        assert a.code == "A" and a.policy.include_wait_new is True
        plan = scenario_payloads(s, seeded, a)
        decide = next(c for c in plan.calls if c.tool == "decide")
        assert decide.payload is not None
        assert decide.payload["candidates"][-1]["id"] == WAIT_NEW_OPTION
        assert decide.payload == jev.decides[1]  # 파이프라인이 보낸 A payload 와 같다


def test_wait_new_evidence_lists_only_upcoming_track_a(factory: sessionmaker[Session], seeded: int) -> None:
    with factory() as s:
        snap = s.get(Snapshot, seeded)
        assert snap is not None
        region = s.get(Region, snap.region_id)
        assert region is not None
        # R3b F2: 포함 분류 전(미해결)은 넣지 않는다 — 시드 직후는 전부 '미분류'
        assert wait_new_evidence(load_facts(s, snap, region), snap.asof_date).startswith(
            "지역 (A) 트랙 공고 예정 0곳"
        )
        for cx in s.scalars(select(Complex).where(Complex.region_id == region.id)):
            cx.inclusion_class, cx.inclusion_decision = "private_sale_apt", "auto"
        s.flush()
        facts = load_facts(s, snap, region)
        text = wait_new_evidence(facts, snap.asof_date)
        assert text.startswith("지역 (A) 트랙 공고 예정 2곳")
        assert "모집공고일 미정(공고 전)" in text and "분양가 미공개" in text
        for f in facts:  # (B) 트랙(잔여물건)·이미 공고된 단지는 넣지 않는다
            if f.row.track != "A":
                assert f.row.name not in text
        assert wait_new_evidence([], snap.asof_date).endswith("기다릴 공고 예정 단지가 확인되지 않음")


def test_reference_scope_leftover_ladder_not_used_for_score_or_api(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int
) -> None:
    """D9-1: '참고' 단지(13, 접수 확인 불가)에 같은 스냅샷 사다리 행이 남아 있어도(이전 범위의 판정·이월 재현)
    점수 입력·API 표시에 쓰지 않는다 → p10 null → 종합 미판정·순위 없음."""
    jev = SynthJev()
    run_pipeline(_ctx(make_ctx, factory, jev), seeded)
    with factory() as s:
        for lad in list(
            s.scalars(select(Ladder).where(Ladder.snapshot_id == seeded, Ladder.complex_id == 2))
        ):
            s.add(Ladder(snapshot_id=seeded, complex_id=13, horizon=lad.horizon, target_ym=lad.target_ym,
                         months_from_asof=lad.months_from_asof, p5=lad.p5, p10=lad.p10, p20=lad.p20, p_flat=lad.p_flat,
                         verdicts=lad.verdicts, annualized=lad.annualized, status=lad.status,
                         judgment_seq=lad.judgment_seq, proposition_text=lad.proposition_text))  # fmt: skip
        s.commit()
    run_pipeline(_ctx(make_ctx, factory, jev), seeded)
    with factory() as s:
        last = max(
            s.scalars(select(ScoreRun.id).where(ScoreRun.snapshot_id == seeded, ScoreRun.scenario_id == 1))
        )
        t13 = s.scalars(
            select(ScoreTotal).where(ScoreTotal.score_run_id == last, ScoreTotal.complex_id == 13)
        ).one()
        assert t13.judge_scope == "참고" and t13.total is None and t13.rank is None
        cx = s.get(Complex, 13)
        assert cx is not None
        b = load_bundles(s, [cx], seeded)[13]
        assert b.ladders == []  # API 표시(p10·C1·비교)도 남은 행을 쓰지 않는다
        assert score_input(b).ladders == []

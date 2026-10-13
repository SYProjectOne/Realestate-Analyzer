"""R5-PIPE 1(D25, major): P6 사다리(noul) 입력에 지역 벤치마크·제도 맥락·가격 갭, 증거 카드의 벤치마크·공급·호재 줄.

meta §2-1 P6: "단지 증거 카드(≤2,000자) + 지역 벤치마크 + 제도 컨텍스트". 수정 전 파이프라인은 P6 에 갭 없는 카드만 넘기고
(``evidence_card(f)``) ``benchmark_text``·``policy_text`` 를 넘기지 않았으며, 카드의 벤치마크·공급·호재 줄은 어디서도 채워지지
않았다(``scheduler.inputs.evidence_card``).

| 테스트 | 확인 |
| --- | --- |
| ``test_noul_rerank_decide_payloads_carry_regional_context`` | 파이프라인 1회: 모든 noul payload context = card(가격 갭·벤치마크·공급 줄) + benchmark(지역 벤치마크) + policy(제도: 규제지역 등) · 연결된 auto 호재는 카드 '호재' 줄, review 호재·연결 없는 단지는 없음 · rerank 후보 카드·decide evidence 에도 같은 줄 · 벤치마크 텍스트는 P1 screen 을 거친다(noul 보다 먼저) |
| ``test_preview_noul_payloads_match_pipeline`` | 시나리오 미리보기(``scheduler.payloads.scenario_payloads``)가 만든 noul·rerank 입력이 파이프라인이 실제로 보낸 것과 같은 input_hash(캐시 미스 0) |
| ``test_benchmark_screen_not_usable_drops_benchmark_context`` | 벤치마크 텍스트가 P1 screen 에서 block 이면 noul context 에 넣지 않는다(카드·제도는 그대로) |

픽스처 지역(회귀 16단지 + v2 시장 입력)·가짜 판정기. 외부 호출 없음.
"""

# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.judge.jev_mcp import JevMcpAdapter, ToolResponse
from app.judge.payloads import CATALYST_CLASSES
from app.models import Catalyst, CatalystLink, Scenario, Snapshot
from app.scheduler.context import SchedulerContext
from app.scheduler.payloads import cache_status, scenario_payloads
from app.scheduler.pipeline import load_scenarios, run_pipeline

from .conftest import SynthJev

CATALYST_IDS = [c["id"] for c in CATALYST_CLASSES]
LINKED_AUTO = "테스트 철도 연장선"
LINKED_REVIEW = "미해결 테스트 호재"


@dataclass
class CaptureJev(SynthJev):
    """보낸 payload 를 모은다. 호재 단계 classify 는 이름에 '미해결'이 있으면 review. ``block_benchmark`` 면 벤치마크 screen block."""

    sent: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    block_benchmark: bool = False

    def call(self, tool_name: str, arguments: dict[str, Any]) -> ToolResponse:
        self.sent.append((tool_name.removeprefix("jev_"), arguments))
        return super().call(tool_name, arguments)

    def _screen(self, a: dict[str, Any]) -> dict[str, Any]:
        if self.block_benchmark and "벤치마크" in str(a.get("purpose", "")):
            return {"probabilities": {"injection": 0.9}, "recommendation": {"action": "block"}}
        return super()._screen(a)

    def _classify(self, a: dict[str, Any]) -> dict[str, Any]:
        out = super()._classify(a)
        if [c["id"] for c in a["classes"]] == CATALYST_IDS:
            for r, it in zip(out["results"], a["items"], strict=True):
                if "미해결" in str(it.get("text", "")):
                    r.update(decision="review", confidence=0.4)
        return out

    def payloads(self, tool: str) -> list[dict[str, Any]]:
        return [p for t, p in self.sent if t == tool]


def _ctx(make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], jev: SynthJev) -> SchedulerContext:
    return make_ctx(adapter_factory=lambda: JevMcpAdapter(transport=jev, session_factory=factory, secrets=[]))


def _link_catalysts(factory: sessionmaker[Session], cid: int) -> None:
    with factory() as s:
        for name in (LINKED_AUTO, LINKED_REVIEW):
            cat = Catalyst(region_id=1, name=name, kind="교통", stage="계획", location_confirmed=True,
                           expected_ym="2029-06", source_url="https://example.go.kr/notice")  # fmt: skip
            s.add(cat)
            s.flush()
            s.add(CatalystLink(catalyst_id=cat.id, complex_id=cid))
        s.commit()


def _ctx_of(payload: dict[str, Any]) -> dict[str, str]:
    return {str(c.get("id")): str(c["text"]) for c in payload.get("context") or []}


LINKED_CID = 2  # 판정 대상(픽스처 '엘리프 검단 포레듀')


def test_noul_rerank_decide_payloads_carry_regional_context(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int
) -> None:
    _link_catalysts(factory, LINKED_CID)
    jev = CaptureJev()
    res = run_pipeline(_ctx(make_ctx, factory, jev), seeded)
    assert not res.degraded, res.error

    nouls = jev.payloads("noul")
    assert nouls, "noul 호출 없음"
    problems: list[str] = []
    by_complex: dict[int, list[dict[str, str]]] = {}
    for p in nouls:
        ctx = _ctx_of(p)
        if set(ctx) != {"card", "benchmark", "policy"}:
            problems.append(f"noul context id {sorted(ctx)} (card·benchmark·policy 필요)")
            continue
        name = ctx["card"].splitlines()[0].removeprefix("단지: ")
        by_complex.setdefault(hash(name), []).append(ctx)
        if "규제지역" not in ctx["policy"]:
            problems.append(f"policy 에 규제지역 없음: {ctx['policy'][:120]}")
        if "벤치마크" not in ctx["benchmark"]:
            problems.append(f"benchmark 텍스트 머리 없음: {ctx['benchmark'][:120]}")
    cards = [c["card"] for cs in by_complex.values() for c in cs]
    if cards and not any("\n가격 갭: " in c for c in cards):
        problems.append("noul 카드에 '가격 갭' 줄이 하나도 없음(P6 카드에 갭 미반영)")
    if cards and not any("\n벤치마크: " in c for c in cards):
        problems.append("noul 카드에 '벤치마크' 줄이 하나도 없음")
    if cards and not any("\n공급: " in c for c in cards):
        problems.append("noul 카드에 '공급' 줄이 하나도 없음")
    linked = [c for c in cards if "\n호재: " in c]
    if not any(LINKED_AUTO in c for c in linked):
        problems.append(f"연결된 auto 호재 '{LINKED_AUTO}'가 카드 '호재' 줄에 없음")
    if any(LINKED_REVIEW in c for c in cards):
        problems.append("review(미해결) 호재가 카드에 들어감 — 상승 근거로 쓰면 안 된다(meta P4)")

    # 벤치마크 텍스트는 P1 screen 을 거친다 — noul 보다 먼저
    order = [t for t, _ in jev.sent]
    bench_screens = [i for i, (t, p) in enumerate(jev.sent) if t == "screen" and "벤치마크" in str(p.get("purpose", ""))]
    if not bench_screens or bench_screens[0] > order.index("noul"):
        problems.append("벤치마크 텍스트 P1 screen 이 noul 전에 없음")

    reranks = jev.payloads("rerank")
    if not reranks:
        problems.append("rerank 호출 없음")
    else:
        texts = [c["text"] for c in reranks[-1]["candidates"]]
        if not any("\n벤치마크: " in t for t in texts) or not any("\n공급: " in t for t in texts):
            problems.append("rerank 후보 카드에 벤치마크·공급 줄 없음")
        if not any(LINKED_AUTO in t for t in texts):
            problems.append("rerank 후보 카드에 연결 호재 없음")
    decides = jev.payloads("decide")
    if not decides:
        problems.append("decide 호출 없음")
    elif not all("벤치마크: " in d["evidence"] and "가격 갭: " in d["evidence"] for d in decides):
        problems.append("decide evidence 에 벤치마크·가격 갭 줄 없음")
    elif not all("규제지역" in d["evidence"] for d in decides):
        problems.append("decide evidence 에 제도(규제지역) 맥락 없음")
    assert not problems, "\n".join(problems)


def test_preview_noul_payloads_match_pipeline(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int
) -> None:
    _link_catalysts(factory, LINKED_CID)
    jev = CaptureJev()
    res = run_pipeline(_ctx(make_ctx, factory, jev), seeded)
    assert not res.degraded, res.error
    with factory() as s:
        snap = s.get(Snapshot, res.snapshot_id)
        assert snap is not None
        base = s.scalars(select(Scenario).where(Scenario.code == "base")).one()
        sc = next(x for x in load_scenarios(s, base.id))
        plan = scenario_payloads(s, snap.id, sc)
        st = cache_status(s, plan)
    noul_calls = [c for c in plan.calls if c.tool == "noul"]
    assert noul_calls and all(c.payload is not None for c in noul_calls)
    assert st.calls_by_tool.get("noul", 0) == 0 and st.calls_by_tool.get("rerank", 0) == 0, st
    assert st.misses == 0, st


def test_benchmark_screen_not_usable_drops_benchmark_context(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], seeded: int
) -> None:
    jev = CaptureJev(block_benchmark=True)
    res = run_pipeline(_ctx(make_ctx, factory, jev), seeded)
    assert not res.degraded, res.error
    nouls = jev.payloads("noul")
    assert nouls
    for p in nouls:
        ctx = _ctx_of(p)
        assert set(ctx) == {"card", "policy"}, sorted(ctx)
    assert any(k.startswith("screen:benchmark") for k in res.skipped), res.skipped

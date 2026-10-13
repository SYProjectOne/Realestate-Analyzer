"""R5-PIPE(D25, ``docs/design/wp/R5_FINAL.md`` PIPE) 판정기 단계 단위 테스트.

| 테스트 | 확인 |
| --- | --- |
| ``test_p1_skip_rescreens_with_other_purpose_and_input`` | meta §2-1 P1: skip 이면 purpose 를 바꿔 다른 입력으로 재screen(호출 2회, 두 payload 다름), 재screen pass 면 usable |
| ``test_p1_block_is_not_rescreened`` | block 은 사용 금지 — 재screen 하지 않는다(호출 1회) |
| ``test_p1_pass_is_screened_once`` | pass 면 1회 |
| ``test_p7_rerank_over_cap_is_failure_not_crash`` | rerank 후보 > 250(JEV 상한) → ValueError 로 잡이 죽지 않고 판정기 호출 없이 status error 앵커(실패를 숨기지 않는다) |
| ``test_noul_payload_carries_benchmark_and_policy_context`` | P6 noul payload context = 증거 카드 + 지역 벤치마크 + 제도(meta §2-1 P6) |
| ``test_card_lines_benchmark_supply_catalysts`` | 증거 카드 '벤치마크'·'공급'·'호재' 줄이 순서대로 나온다 |
"""

# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.judge import payloads as P
from app.judge import pipeline
from app.judge.jev_mcp import ToolResponse

from .conftest import FakeTransport

FIRST_TASK = "첫 검사 목적"
RETRY_TASK = "다른 단계 목적"


@dataclass
class ScreenTransport(FakeTransport):
    """screen 응답을 payload 의 purpose(검사 목적)로 정한다."""

    by_task: dict[str, str] | None = None

    def call(self, tool_name: str, arguments: dict[str, Any]) -> ToolResponse:
        self.calls.append((tool_name, arguments))
        action = (self.by_task or {}).get(str(arguments.get("purpose")), "pass")
        raw = {
            "tool": tool_name,
            "probabilities": {"injection": 0.01, "substance": 0.9, "relevance": 0.1 if action == "skip" else 0.9},
            "recommendation": {"action": action},
        }
        return ToolResponse(raw=raw, is_error=False, duration_ms=3)


def _screen(adapter: Any) -> pipeline.ScreenOutcome:
    return pipeline.p1_screen_retry(
        adapter,
        "청약 공고문 발췌 본문",
        task=FIRST_TASK,
        purpose="screen:test:c1",
        retry_text="추출 대상: 계약금 비율\n청약 공고문 발췌 본문",
        retry_task=RETRY_TASK,
    )


def test_p1_skip_rescreens_with_other_purpose_and_input(make_adapter: Callable[..., Any]) -> None:
    t = ScreenTransport(by_task={FIRST_TASK: "skip", RETRY_TASK: "pass"})
    out = _screen(make_adapter(t))
    assert [c[0] for c in t.calls] == ["jev_screen", "jev_screen"]
    first, second = t.calls[0][1], t.calls[1][1]
    assert first != second and first["text"] != second["text"] and second["purpose"] == RETRY_TASK
    assert out.usable and out.verdict == "pass"
    assert out.envelope.purpose != "screen:test:c1" and out.envelope.purpose.startswith("screen:test:c1")


def test_p1_block_is_not_rescreened(make_adapter: Callable[..., Any]) -> None:
    t = ScreenTransport(by_task={FIRST_TASK: "block"})
    out = _screen(make_adapter(t))
    assert len(t.calls) == 1 and not out.usable and out.verdict == "block"


def test_p1_pass_is_screened_once(make_adapter: Callable[..., Any]) -> None:
    t = ScreenTransport()
    out = _screen(make_adapter(t))
    assert len(t.calls) == 1 and out.usable


def test_p7_rerank_over_cap_is_failure_not_crash(make_adapter: Callable[..., Any]) -> None:
    t = FakeTransport()
    cards = [P.EvidenceCard(complex_id=i, name=f"단지{i}") for i in range(1, 252)]
    anchor = pipeline.p7_rerank(make_adapter(t), cards, region_id=1, snapshot_id=None)
    assert t.calls == []  # 판정기에 보내지 않는다(JEV 상한 250 — 나누면 §6-5 고정 앵커가 깨진다)
    assert anchor.status == "error" and anchor.items == [] and anchor.judgment_seq is None


def test_noul_payload_carries_benchmark_and_policy_context() -> None:
    card = P.EvidenceCard(complex_id=2, name="단지", basis_type="84A", price_range="5.78~6.08억",
                          move_in_ym="2028-03", gap="+3.0% (추정)", benchmark="생활권 분양 사례 3건")  # fmt: skip
    spec = P.ladder_specs(card, asof_date="2026-10-08")[0]
    payload = P.noul_payload(
        spec,
        card_text=P.evidence_card_text(card),
        benchmark_text="지역 벤치마크: 사례",
        policy_text="제도: 규제지역 비규제",
    )
    ctx = {c["id"]: c["text"] for c in payload["context"]}
    assert set(ctx) == {"card", "benchmark", "policy"}
    assert "가격 갭: +3.0%" in ctx["card"] and "벤치마크: 생활권" in ctx["card"]
    assert ctx["benchmark"].startswith("지역 벤치마크") and "비규제" in ctx["policy"]


def test_card_lines_benchmark_supply_catalysts() -> None:
    card = P.EvidenceCard(complex_id=1, name="단지", benchmark="B", supply="S", catalysts=("C1", "C2"), notes="N")
    lines = P.evidence_card_text(card).splitlines()
    assert lines == ["단지: 단지", "벤치마크: B", "공급: S", "호재: C1; C2", "비고: N"]

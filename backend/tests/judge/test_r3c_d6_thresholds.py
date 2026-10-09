"""R3c CORE — D6 '어댑터는 임계값을 넘기지 않는다' 9개 도구 전부 (R3 3차 RA 부분: 검사가 2개 도구뿐이던 것).

판정기에 실제로 가는 인자(어댑터 → transport.call)를 9개 도구 모두 기록해, 어느 깊이에도 임계값 키가 없음을 본다.
"""

# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from app.core.protocols import JudgePayload
from app.judge import payloads as P
from app.judge.base import TOOL_NAMES, ToolResponse
from app.judge.jev_mcp import JevMcpAdapter

THRESHOLD_KEYS = {
    "threshold", "thresholds", "auto_accept", "minimum_margin", "min_margin", "abstain_below", "flag_above",
    "review_below", "min_confidence", "confidence_threshold", "auto_threshold", "escalate_above",
}  # fmt: skip


def _keys(obj: Any) -> Iterator[str]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def server_version(self) -> str:
        return "0.14.1"

    def close(self) -> None:
        return None

    def call(self, tool_name: str, arguments: JudgePayload) -> ToolResponse:
        self.calls.append((tool_name, dict(arguments)))
        return ToolResponse(raw={"tool": tool_name, "model": "jev-1.13.0"}, is_error=False, duration_ms=1)


def _payloads() -> dict[str, JudgePayload]:
    card = P.EvidenceCard(
        complex_id=1, name="테스트 단지", basis_type="84A", price_range="5.78~6.08억", move_in_ym="2028-12"
    )
    cand = [
        P.DecideCandidate(card=card),
        P.DecideCandidate(card=P.EvidenceCard(complex_id=2, name="두 번째 단지")),
    ]
    spec = P.ladder_specs(card, asof_date="2026-10-08")[0]
    return {
        "screen": P.screen_payload("공고문 본문", task="청약 공고문 수치 추출 전 입력 검사"),
        "extract": P.extract_payload(
            "공급금액 600,000,000원", [P.ExtractField("max_price_won", r"[0-9,]+원", "최고가")]
        ),
        "audit": P.audit_payload(
            "공급금액 600,000,000원", [P.AuditRecord("max_price_won", "최고가", "600,000,000")]
        ),
        "classify": P.classify_inclusion_batch_payload([("complex:1", "사업주체: 민간")]),
        "compare": P.compare_payload("총 1,573세대", "총 1,769세대"),
        "noul": P.noul_payload(spec, card_text="카드"),
        "rerank": P.rerank_payload([card, cand[1].card]),
        "decide": P.decide_payload(
            scenario_name="기본",
            requirements=("접근", "규제", "자금"),
            candidates=cand,
            priorities="p10 0.35",
        ),
        "verify": P.verify_payload(
            ["테스트 단지 입주 예정 시기는 2028-12이다"], [("fp_1", "입주 2028년 12월")]
        ),
    }


def test_d6_no_threshold_keys_reach_the_judge_for_all_nine_tools(tmp_path: Any) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models import Base

    engine = create_engine(f"sqlite:///{(tmp_path / 'j.db').as_posix()}")
    Base.metadata.create_all(engine)
    rec = Recorder()
    adapter = JevMcpAdapter(transport=rec, session_factory=sessionmaker(bind=engine), secrets=[])
    payloads = _payloads()
    assert set(payloads) == set(TOOL_NAMES), "9개 도구 전부"
    for tool, payload in payloads.items():
        adapter.call(tool, payload, f"d6:{tool}")  # type: ignore[arg-type]
    sent = {name for name, _ in rec.calls}
    assert sent == {TOOL_NAMES[t] for t in payloads}, sent
    for name, args in rec.calls:
        found = {k for k in _keys(args) if k.lower() in THRESHOLD_KEYS or "threshold" in k.lower()}
        assert not found, f"{name}: 임계값 키 {found} — JEV 기본값을 쓴다(D6)"

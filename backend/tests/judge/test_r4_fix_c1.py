"""R4-FIX C1 (D18-1·D18-2) — 고정 모델 캐시 키, 실행 중 키 불변, tools/call 전송 계층 계수.

R4 실데이터: JEV 0.14.1 은 extract 가 모델을 부르지 않으면(provider none) ``model: "jev-latest"``, 그 밖에는
``"jev-1.13.0"`` 을 준다. 옛 어댑터는 응답 모델마다 버전을 바꿔 2회차에 실제 ``tools/call`` 298건을 '캐시'로 기록했다.

| 테스트 | 확인 |
| --- | --- |
| ``test_stdio_provider_none_mixed_second_run_sends_no_tools_call`` | 실제 stdio MCP 서버(가짜)에서 provider none·모델 응답이 섞여도 2회차 서버 측 tools/call 0 |
| ``test_provider_none_mixed_one_version_and_no_replay`` | 1회차 버전 1개, 2회차 전송 0 |
| ``test_first_run_learns_model_after_local_responses`` | 첫 실행에서 모델을 늦게 알아도(앞 응답이 provider none) 2회차 전송 0 |
| ``test_model_change_keeps_key_in_run_then_next_run_rejudges`` | 모델이 바뀌면 그 실행은 키 그대로, 다음 실행(새 어댑터)에서 재판정 |
| ``test_meter_counts_transport_calls_only`` | 계수기 = 전송 계층 tools/call 수, 캐시 적중은 0 |
| ``test_counting_caller_counts_hidden_calls`` | 봉투가 cached 여도 전송이 있었으면 실제 호출로 센다 |
"""

# ruff: noqa: E501  (한국어 docstring·주석)

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.contracts_gen import JudgmentEnvelope
from app.judge.base import ADAPTER_CODE_VERSION, ToolResponse
from app.judge.jev_mcp import JevMcpAdapter
from app.models import JudgmentLog

from .conftest import FakeServer, FakeTransport, load_samples

V = f"{ADAPTER_CODE_VERSION}+jev-mcp@0.14.1"


def _raw(tool: str, *, model: str = "jev-1.13.0", provider: str = "typesafe") -> dict[str, Any]:
    raw: dict[str, Any] = dict(load_samples()["calls"][f"jev_{tool}"]["response"])
    return raw | {"model": model, "provider": provider}


class MixedTransport(FakeTransport):
    """R4 모양: extract 는 provider none(jev-latest), 나머지는 모델 호출(jev-1.13.0)."""

    def __init__(self, model: str = "jev-1.13.0") -> None:
        super().__init__()
        self.model = model

    def call(self, tool_name: str, arguments: dict[str, Any]) -> ToolResponse:
        self.calls.append((tool_name, arguments))
        tool = tool_name.removeprefix("jev_")
        if tool == "extract":
            raw = _raw(tool, model="jev-latest", provider="none")
        else:
            raw = _raw(tool, model=self.model)
        return ToolResponse(raw=raw, is_error=False, duration_ms=1)


def _seq(i: int) -> list[tuple[str, dict[str, Any], str]]:
    """screen → extract 를 번갈아(R4 P1·P2 순서) i 조각."""
    out: list[tuple[str, dict[str, Any], str]] = []
    for k in range(i):
        out.append(
            ("screen", {"text": f"공고문 조각 {k}", "purpose": "공고 발췌 검사"}, f"screen:extract:rd1:{k}")
        )
        out.append(("extract", {"text": f"공고문 조각 {k}", "fields": [{"id": "f"}]}, f"extract:rd1:{k}"))
    return out


def _run(adapter: Any, calls: list[tuple[str, dict[str, Any], str]]) -> list[JudgmentEnvelope]:
    return [adapter.call(tool, payload, purpose) for tool, payload, purpose in calls]


def _rows(sf: sessionmaker[Session]) -> list[JudgmentLog]:
    with sf() as s:
        return list(s.scalars(select(JudgmentLog).order_by(JudgmentLog.seq)))


def test_stdio_provider_none_mixed_second_run_sends_no_tools_call(
    fake_server: FakeServer, session_factory: sessionmaker[Session]
) -> None:
    """서버 쪽 계수(R4 의 tools/call 프록시와 같은 자리): 2회차는 새 프로세스·새 어댑터에서 tools/call 0."""
    fake_server.configure(local_tools=["jev_extract"])
    calls = _seq(3)
    first = JevMcpAdapter(cmd=fake_server.cmd, session_factory=session_factory, timeout_s=20)
    try:
        _run(first, calls)
        first_meter = first.meter.total() if hasattr(first, "meter") else None
    finally:
        first.close()
    sent = len(fake_server.calls())
    assert sent == len(calls)

    second = JevMcpAdapter(cmd=fake_server.cmd, session_factory=session_factory, timeout_s=20)
    try:
        envs = _run(second, calls)
        second_meter = second.meter.total() if hasattr(second, "meter") else None
    finally:
        second.close()
    assert len(fake_server.calls()) == sent, "2회차 실제 tools/call 이 0 이어야 한다(D18-5 게이트)"
    assert all(e.cached for e in envs)
    assert (first_meter, second_meter) == (len(calls), 0), "어댑터 계수기 = 서버 쪽 tools/call 수"


def test_provider_none_mixed_one_version_and_no_replay(
    make_adapter: Callable[..., Any], session_factory: sessionmaker[Session]
) -> None:
    t1 = MixedTransport()
    _run(make_adapter(t1), _seq(4))
    rows = _rows(session_factory)
    assert len(rows) == 8
    assert {r.adapter_version for r in rows} == {V + "+jev-1.13.0"}, (
        "고정 모델 하나(provider none 의 model 무시)"
    )
    # 행에는 응답의 실제 model·provider 가 그대로 남는다(D18-1)
    assert {(r.output_json["model"], r.output_json["provider"]) for r in rows if r.tool == "extract"} == {
        ("jev-latest", "none")
    }

    t2 = MixedTransport()
    a2 = make_adapter(t2)
    envs = _run(a2, _seq(4))
    assert t2.calls == []
    assert all(e.cached for e in envs)
    assert len(_rows(session_factory)) == 8


def test_first_run_learns_model_after_local_responses(
    make_adapter: Callable[..., Any], session_factory: sessionmaker[Session]
) -> None:
    """빈 DB: 첫 응답들이 provider none(모델 모름)이어도, 모델을 알게 된 뒤 같은 실행·다음 실행 모두 재호출 없음."""
    t1 = MixedTransport()
    a1 = make_adapter(t1)
    extracts = [c for c in _seq(3) if c[0] == "extract"]
    screens = [c for c in _seq(3) if c[0] == "screen"]
    _run(a1, extracts)  # 모델 모름(접미 없음)
    assert a1.adapter_version == V
    _run(a1, screens)  # 모델 호출 → 고정 모델 jev-1.13.0
    assert a1.adapter_version == V + "+jev-1.13.0"
    again = _run(a1, extracts)  # 같은 실행 안 — 이미 판정한 입력
    assert all(e.cached for e in again) and len(t1.calls) == 6
    assert {r.adapter_version for r in _rows(session_factory)} == {V + "+jev-1.13.0"}

    t2 = MixedTransport()
    a2 = make_adapter(t2)
    _run(a2, extracts + screens)
    assert t2.calls == []


def test_model_change_keeps_key_in_run_then_next_run_rejudges(
    make_adapter: Callable[..., Any], session_factory: sessionmaker[Session]
) -> None:
    old = ("screen", {"text": "옛 입력", "purpose": "공고 발췌 검사"}, "screen:t:1")
    new = ("screen", {"text": "새 입력", "purpose": "공고 발췌 검사"}, "screen:t:2")
    _run(make_adapter(MixedTransport("jev-1.13.0")), [old])

    t2 = MixedTransport("jev-1.14.0")
    a2 = make_adapter(t2)
    (fresh,) = _run(a2, [new])  # 새 입력에서 새 모델을 본다
    assert fresh.cached is False and fresh.adapter_version == V + "+jev-1.13.0", "실행 중 키는 그대로"
    (redo,) = _run(a2, [old])
    assert redo.cached is True and len(t2.calls) == 1, "실행 중 키를 바꾸거나 replay 하지 않는다"
    assert a2.observed_version == V + "+jev-1.14.0" and a2.model_change_pending

    t3 = MixedTransport("jev-1.14.0")
    a3 = make_adapter(t3)  # 다음 실행: 모델 호출 응답이 알려 준 새 모델로 고정
    assert a3.adapter_version == V + "+jev-1.14.0"
    envs = _run(a3, [old, new])
    assert [e.cached for e in envs] == [False, False] and len(t3.calls) == 2
    assert not a3.model_change_pending


def test_meter_counts_transport_calls_only(make_adapter: Callable[..., Any]) -> None:
    from app.judge.base import CallMeter

    meter = CallMeter()
    t = MixedTransport()
    a = make_adapter(t)
    a.meter = meter
    _run(a, _seq(2))
    _run(a, _seq(2))
    assert meter.total() == 4 == len(t.calls)
    assert meter.by_tool() == {"screen": 2, "extract": 2}


def test_counting_caller_counts_hidden_calls() -> None:
    """옛 어댑터처럼 전송 뒤 cached 봉투를 돌려줘도 실제 호출은 전송 계층 수로 센다(D18-2)."""
    from app.judge.base import CallMeter
    from app.scheduler.pipeline import CountingCaller

    class Hidden:
        adapter_version = V + "+jev-1.13.0"

        def __init__(self) -> None:
            self.meter = CallMeter()

        def call(self, tool: Any, payload: Any, purpose: str, **_: Any) -> JudgmentEnvelope:
            self.meter.add(tool)  # 판정기로 나갔다
            return JudgmentEnvelope(
                tool=tool, purpose=purpose, input_hash="sha256:" + "a" * 64, input_len=1, status="ok",
                confidence=None, cached=True, result={}, raw={}, duration_ms=1, judgment_seq=1,
                created_at="2026-10-12T00:00:00+09:00", adapter_version=self.adapter_version,
            )  # fmt: skip

    cc = CountingCaller(Hidden())  # type: ignore[arg-type]
    cc.call("screen", {"text": "x"}, "screen:x")
    assert cc.calls == 1 and cc.cached == 0 and cc.by_tool == {"screen": 1}

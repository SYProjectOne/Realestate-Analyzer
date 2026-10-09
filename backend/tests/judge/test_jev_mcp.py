"""jev_mcp.py — 실제 JEV 응답(녹화) → 봉투 status·result 매핑,
stdio MCP 전송(가짜 서버 프로세스), JudgeUnavailable(T18)."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.contracts_gen import (
    AuditResult,
    ClassifyResult,
    CompareResult,
    DecideResult,
    ExtractResult,
    NoulResult,
    RerankResult,
    ScreenResult,
    VerifyResult,
)
from app.core.protocols import JUDGE_TOOLS, JudgeAdapter, JudgeUnavailable
from app.judge.jev_mcp import JevMcpAdapter, McpStdioTransport, normalize, subprocess_env
from app.models import JudgmentLog

from .conftest import FakeServer, FakeTransport

RESULT_MODELS = {
    "screen": ScreenResult,
    "extract": ExtractResult,
    "audit": AuditResult,
    "classify": ClassifyResult,
    "compare": CompareResult,
    "noul": NoulResult,
    "rerank": RerankResult,
    "decide": DecideResult,
    "verify": VerifyResult,
}
PURPOSE = {t: f"{t}:t" for t in JUDGE_TOOLS} | {"noul": "noul:ladder:asof_plus_3y:2029-10:c1"}


def norm(tool: str, raw: dict[str, Any], payload: dict[str, Any] | None = None) -> Any:
    return normalize(tool, raw, payload or {}, PURPOSE[tool])  # type: ignore[arg-type]


def test_protocol(fake_transport: FakeTransport, session_factory: sessionmaker[Session]) -> None:
    assert isinstance(JevMcpAdapter(transport=fake_transport, session_factory=session_factory), JudgeAdapter)


@pytest.mark.parametrize("tool", JUDGE_TOOLS)
def test_real_samples_normalize_to_contract_result(tool: str, samples: dict[str, Any]) -> None:
    s = copy.deepcopy(samples[f"jev_{tool}"])
    if tool == "noul":  # 녹화는 명제 2개 — 계약 NoulResult 는 사다리 명제 4개
        s["response"]["results"] = [
            s["response"]["results"][i % 2] | {"id": f"proposition{i}"} for i in range(4)
        ]
    n = norm(tool, s["response"], s["arguments"])
    assert n.status == "ok"
    RESULT_MODELS[tool].model_validate(n.result)
    if n.confidence is not None:
        assert 0 <= n.confidence <= 1


def test_tool_names_are_mapped(make_adapter: Callable[..., Any], samples: dict[str, Any]) -> None:
    transport = FakeTransport()
    adapter = make_adapter(transport)
    for tool in JUDGE_TOOLS:
        getattr(adapter, tool)(samples[f"jev_{tool}"]["arguments"], PURPOSE[tool])
    assert [name for name, _ in transport.calls] == [f"jev_{t}" for t in JUDGE_TOOLS]


# ---------------------------------------------------------------- 도구별 값 매핑


def test_screen_mapping(samples: dict[str, Any]) -> None:
    raw = samples["jev_screen"]["response"]
    n = norm("screen", raw)
    assert n.result == {"verdict": "pass", "injection": 0.02, "substance": 0.98, "relevance": 0.98}
    block = copy.deepcopy(raw) | {"recommendation": {"action": "block", "reason": "x"}}
    assert norm("screen", block).status == "blocked"
    assert norm("screen", block).result["verdict"] == "block"
    skip = copy.deepcopy(raw) | {"recommendation": {"action": "skip", "reason": "x"}}
    assert (norm("screen", skip).status, norm("screen", skip).result["verdict"]) == ("ok", "skip")
    review = copy.deepcopy(raw) | {"recommendation": {"action": "review", "reason": "x"}}
    assert norm("screen", review).status == "review"
    invalid = copy.deepcopy(raw) | {"status": "invalid_response", "recommendation": {"action": "review"}}
    assert norm("screen", invalid).status == "review"


def test_noul_mapping_keys_and_horizon(samples: dict[str, Any]) -> None:
    raw = copy.deepcopy(samples["jev_noul"]["response"])
    raw["results"] = [raw["results"][i % 2] | {"id": f"proposition{i}"} for i in range(4)]
    n = norm("noul", raw)
    r = NoulResult.model_validate(n.result)
    assert (r.horizon, r.target_ym) == ("asof_plus_3y", "2029-10")
    assert [p.key for p in r.propositions] == ["p5", "p10", "p20", "p_flat"]
    assert r.propositions[0].prob == 0.98 and r.propositions[0].verdict == "likely"
    assert r.propositions[0].decision == "auto"
    raw["results"][1] = raw["results"][1] | {"label": "uncertain", "auto": False, "probability": 0.5}
    assert NoulResult.model_validate(norm("noul", raw).result).propositions[1].decision == "review"
    raw["status"] = "invalid_response"
    assert norm("noul", raw).status == "review"


def test_decide_mapping_ids_checks_escape(samples: dict[str, Any]) -> None:
    s = samples["jev_decide"]
    n = norm("decide", s["response"], s["arguments"])
    r = DecideResult.model_validate(n.result)
    assert r.selected == "complex:1"
    assert set(r.probs) == {"complex:1", "complex:2", "ask_user", "investigate", "none"}
    assert r.checks is not None
    assert r.checks["complex:1"].access == "supported"
    assert r.checks["complex:2"].access == "contradicted"
    assert n.confidence == 1
    esc = copy.deepcopy(s["response"])
    esc["recommendation"] |= {"selected": "ask_user", "escaped": True}
    ne = norm("decide", esc, s["arguments"])
    assert ne.status == "escaped"
    assert ne.result["escaped"] is True and ne.result["question"]
    bad = copy.deepcopy(s["response"])
    bad["checks"][0]["answer"] = "invalid_response"
    assert norm("decide", bad, s["arguments"]).status == "review"


def test_decide_requirement_order_maps_to_access_regulation_funds(samples: dict[str, Any]) -> None:
    s = copy.deepcopy(samples["jev_decide"])
    s["arguments"]["requirements"] = ["접근", "규제", "자금"]
    s["response"]["checks"] = [
        {"candidate": "complex_1", "requirement": j, "answer": a}
        for j, a in enumerate(["supported", "unknown", "contradicted"])
    ]
    r = DecideResult.model_validate(norm("decide", s["response"], s["arguments"]).result)
    assert r.checks is not None
    c = r.checks["complex:1"]
    assert (c.access, c.regulation, c.funds) == ("supported", "unknown", "contradicted")


def test_verify_mapping(samples: dict[str, Any]) -> None:
    raw = copy.deepcopy(samples["jev_verify"]["response"])
    r = VerifyResult.model_validate(norm("verify", raw).result)
    assert [(c.claim_id, c.verdict) for c in r.claims] == [("0", "verified"), ("1", "contradicted")]
    raw["results"][0] |= {"action": "review", "confidence": 0.6}
    r = VerifyResult.model_validate(norm("verify", raw).result)
    assert r.claims[0].verdict == "review"
    raw["results"][1] |= {"status": "invalid_response", "verdict": "unknown"}
    assert norm("verify", raw).status == "review"


def test_classify_batch_is_summary_plus_items(samples: dict[str, Any]) -> None:
    """계약 2026-10-09.2 ClassifyResult.items: 최상위 = 요약(label 'batch', prob = auto 비율),
    항목별 decision."""
    c = copy.deepcopy(samples["jev_classify"]["response"])
    first = c["results"][0]
    c["results"] = [
        first | {"id": "complex:1"},
        first | {"id": "complex:2", "decision": "review", "top_probability": 0.6},
        first | {"id": "complex:3", "classification": "public_rental"},
    ]
    n = norm("classify", c)
    r = ClassifyResult.model_validate(n.result)
    assert (n.status, r.label, r.prob, r.decision) == ("ok", "batch", 0.6667, "review")
    assert r.items is not None
    assert [(i.id, i.label, i.decision) for i in r.items] == [
        ("complex:1", "private_sale_apt", "auto"),
        ("complex:2", "private_sale_apt", "review"),
        ("complex:3", "public_rental", "auto"),
    ]
    c["results"][1] = c["results"][0] | {"id": "complex:2"}
    assert norm("classify", c).result["decision"] == "auto"
    c["results"][2] |= {"status": "invalid_response", "classification": None}
    assert norm("classify", c).status == "review"  # 항목 하나라도 무효 응답이면 봉투 review


def test_timeouts_default_from_settings(session_factory: sessionmaker[Session], test_settings: Any) -> None:
    """JUDGE_CALL_TIMEOUT_S·JUDGE_START_TIMEOUT_S(계약 2026-10-09.2)가 기본값이다."""
    from app.core.settings import set_settings

    set_settings(test_settings.model_copy(update={"judge_call_timeout_s": 7.0, "judge_start_timeout_s": 9.0}))
    try:
        adapter = JevMcpAdapter(cmd="jev-test-cmd", session_factory=session_factory)
        transport = adapter._transport
        assert isinstance(transport, McpStdioTransport)
        assert (transport._timeout_s, transport._startup_timeout_s) == (7.0, 9.0)  # 프로세스는 아직 안 띄움
    finally:
        set_settings(test_settings)


def test_audit_missing_p_wrong_is_null(samples: dict[str, Any]) -> None:
    a = copy.deepcopy(samples["jev_audit"]["response"])
    a["records"][0].pop("p_wrong", None)
    item = AuditResult.model_validate(norm("audit", a).result).items[0]
    assert item.p_wrong is None  # 지어내지 않는다(계약 2026-10-09.2)


def test_classify_extract_audit_compare_rerank_review_paths(samples: dict[str, Any]) -> None:
    c = copy.deepcopy(samples["jev_classify"]["response"])
    assert ClassifyResult.model_validate(norm("classify", c).result).label == "private_sale_apt"
    c["results"][0]["decision"] = "review"
    assert norm("classify", c).status == "review"
    c["results"][0] |= {"decision": "auto", "classification": "manual_review"}
    assert norm("classify", c).status == "review"
    assert norm("classify", c).result["decision"] == "manual_review"

    e = copy.deepcopy(samples["jev_extract"]["response"])
    f = ExtractResult.model_validate(norm("extract", e).result).fields[0]
    assert (f.name, f.value_text, f.decision) == ("max_price", "608,000,000원", "auto")
    e["results"][0] |= {"status": "review"}
    assert norm("extract", e).status == "ok"  # 필드 단위 review는 필드에 표기
    assert norm("extract", e).result["fields"][0]["decision"] == "review"
    e["results"][0] |= {"status": "invalid_response"}
    assert norm("extract", e).status == "review"

    a = copy.deepcopy(samples["jev_audit"]["response"])
    assert norm("audit", a).result["verdict"] == "pass"
    a |= {"action": "escalate"}
    a["records"][0] |= {"action": "wrong", "p_wrong": 0.9}
    na = norm("audit", a)
    assert (na.status, na.result["verdict"], na.result["items"][0]["flagged"]) == ("ok", "flagged", True)
    a["summary"] = {"records": 1, "flagged": 0, "invalid": 1}
    a["records"][0] |= {"action": "invalid_response", "p_wrong": None}
    assert norm("audit", a).status == "review"

    cmp_ = copy.deepcopy(samples["jev_compare"]["response"])
    rc = CompareResult.model_validate(norm("compare", cmp_).result)
    assert rc.overall == "contradicts" and rc.aspects and rc.aspects[0].aspect == "세대수"
    cmp_["overall"]["decision"] = "review"
    assert norm("compare", cmp_).status == "review"

    rr = copy.deepcopy(samples["jev_rerank"]["response"])
    items = RerankResult.model_validate(norm("rerank", rr).result).items
    assert [(i.candidate_id, i.complex_id, i.rank) for i in items] == [
        ("complex:1", 1, 1),
        ("complex:2", 2, 2),
    ]
    rr |= {"status": "invalid_response", "ranked": None}
    assert norm("rerank", rr).status == "review"


# ---------------------------------------------------------------- 실제 stdio 프로세스 (가짜 서버)


def test_subprocess_env_forwards_only_judge_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "tk")
    monkeypatch.setenv("JEV_MCP_MODEL", "jev-latest")
    monkeypatch.setenv("DATA_GO_KR_KEY", "should-not-pass")
    env = subprocess_env()
    assert env["TYPESAFE_API_KEY"] == "tk"
    assert env["JEV_MCP_MODEL"] == "jev-latest"
    assert "DATA_GO_KR_KEY" not in env
    assert "PATH" in env or "Path" in env


def test_stdio_transport_reads_server_version_and_calls(
    fake_server: FakeServer, session_factory: sessionmaker[Session]
) -> None:
    fake_server.configure(version="7.7.7")
    adapter = JevMcpAdapter(cmd=fake_server.cmd, session_factory=session_factory, timeout_s=20)
    try:
        assert adapter.adapter_version.endswith("+jev-mcp@7.7.7")
        a = adapter.noul({"propositions": ["서울은 수도다"]}, "noul:t")
        b = adapter.noul({"propositions": ["서울은 수도다"]}, "noul:t")
    finally:
        adapter.close()
    assert a.status == "ok" and a.cached is False
    assert b.cached is True
    assert fake_server.calls() == ["jev_noul"]  # 실제 호출 1회 (T17)


@pytest.mark.parametrize("mode", ["sleep", "die", "error"])
def test_stdio_failures_raise_judge_unavailable(
    mode: str, fake_server: FakeServer, session_factory: sessionmaker[Session]
) -> None:
    """T18: 타임아웃·프로세스 사망·도구 오류 → JudgeUnavailable + error 행."""
    fake_server.configure(mode=mode)
    adapter = JevMcpAdapter(cmd=fake_server.cmd, session_factory=session_factory, timeout_s=3)
    try:
        with pytest.raises(JudgeUnavailable):
            adapter.screen({"text": "공개 텍스트"}, "screen:t")
    finally:
        adapter.close()
    with session_factory() as s:
        (row,) = s.scalars(select(JudgmentLog))
    assert row.status == "error"
    assert row.error_text


def test_process_restarts_after_death(
    fake_server: FakeServer, session_factory: sessionmaker[Session]
) -> None:
    fake_server.configure(mode="die")
    adapter = JevMcpAdapter(cmd=fake_server.cmd, session_factory=session_factory, timeout_s=5)
    try:
        with pytest.raises(JudgeUnavailable):
            adapter.screen({"text": "공개 텍스트"}, "screen:t")
        fake_server.configure(mode="normal")
        env = adapter.screen({"text": "공개 텍스트"}, "screen:t")  # 새 프로세스로 재시도, error 행 갱신
        assert env.status == "ok"
    finally:
        adapter.close()
    with session_factory() as s:
        (row,) = s.scalars(select(JudgmentLog))
    assert row.status == "ok"


def test_bad_command_is_unavailable(session_factory: sessionmaker[Session]) -> None:
    transport = McpStdioTransport("definitely-not-a-real-command-xyz", startup_timeout_s=5)
    with pytest.raises(JudgeUnavailable):
        transport.server_version()
    transport.close()

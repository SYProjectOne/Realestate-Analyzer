"""cache.py · log.py — 같은 입력 재호출 금지(T17), adapter_version → input_hash, 실패도 행."""

# ruff: noqa: E501  (한국어 docstring·주석)

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.protocols import JudgeUnavailable, input_hash
from app.judge import cache
from app.judge.base import ADAPTER_CODE_VERSION, make_adapter_version
from app.models import JudgmentLog

from .conftest import FakeTransport

PAYLOAD: dict[str, Any] = {"text": "84㎡ 공급금액 최고가 608,000,000원", "purpose": "공고 발췌 검사"}


def rows(sf: sessionmaker[Session]) -> list[JudgmentLog]:
    with sf() as s:
        return list(s.scalars(select(JudgmentLog).order_by(JudgmentLog.seq)))


def test_same_payload_twice_calls_judge_once(
    make_adapter: Callable[..., Any], fake_transport: FakeTransport, session_factory: sessionmaker[Session]
) -> None:
    """T17: 같은 payload 2회 → 실제 호출 1회, 두 번째는 cached=true."""
    adapter = make_adapter(fake_transport)
    first = adapter.screen(PAYLOAD, "screen:notice:1")
    second = adapter.screen(PAYLOAD, "screen:notice:1")

    assert len(fake_transport.calls) == 1
    assert first.cached is False
    assert second.cached is True
    assert second.judgment_seq == first.judgment_seq
    assert second.input_hash == first.input_hash
    assert second.result == first.result
    assert second.raw == first.raw
    assert second.status == first.status == "ok"
    assert len(rows(session_factory)) == 1


def test_purpose_is_part_of_the_key(make_adapter: Callable[..., Any], fake_transport: FakeTransport) -> None:
    adapter = make_adapter(fake_transport)
    a = adapter.screen(PAYLOAD, "screen:notice:1")
    b = adapter.screen(PAYLOAD, "screen:benchmark:1")
    assert a.input_hash != b.input_hash
    assert len(fake_transport.calls) == 2


def test_input_hash_matches_contract_definition(
    make_adapter: Callable[..., Any], fake_transport: FakeTransport
) -> None:
    adapter = make_adapter(fake_transport)
    env = adapter.screen(PAYLOAD, "screen:notice:1")
    assert env.input_hash == input_hash("screen", "screen:notice:1", PAYLOAD, adapter.adapter_version)
    assert env.input_hash == cache.compute_hash("screen", "screen:notice:1", PAYLOAD, adapter.adapter_version)
    assert env.adapter_version == adapter.adapter_version


def test_adapter_version_from_server_info() -> None:
    assert make_adapter_version("0.14.1") == f"{ADAPTER_CODE_VERSION}+jev-mcp@0.14.1"
    assert make_adapter_version("0.14.1", "jev-1.13.0") == f"{ADAPTER_CODE_VERSION}+jev-mcp@0.14.1+jev-1.13.0"
    assert make_adapter_version("0.14.1", " ") == f"{ADAPTER_CODE_VERSION}+jev-mcp@0.14.1"
    assert len(make_adapter_version("1" * 80)) <= 64


def _with_model(model: str) -> dict[str, Any]:
    from .conftest import load_samples

    raw: dict[str, Any] = load_samples()["calls"]["jev_screen"]["response"]
    return raw | {"model": model}


def test_adapter_version_includes_response_model(
    make_adapter: Callable[..., Any], session_factory: sessionmaker[Session]
) -> None:
    """D6 보강(계약 2026-10-09.2): 응답의 model 이 adapter_version 에 들어가고, 그 버전의 hash 로 기록된다."""
    transport = FakeTransport(responses={"jev_screen": _with_model("jev-1.13.0")})
    adapter = make_adapter(transport)
    assert adapter.adapter_version == f"{ADAPTER_CODE_VERSION}+jev-mcp@0.14.1"  # 아직 모델 모름
    first = adapter.screen(PAYLOAD, "screen:notice:1")
    want = f"{ADAPTER_CODE_VERSION}+jev-mcp@0.14.1+jev-1.13.0"
    assert adapter.adapter_version == want == first.adapter_version
    assert first.input_hash == input_hash("screen", "screen:notice:1", PAYLOAD, want)
    again = adapter.screen(PAYLOAD, "screen:notice:1")
    assert again.cached is True and len(transport.calls) == 1

    # 재시작(새 어댑터): judgment_log 의 마지막 모델로 같은 버전 → 판정기 호출 없이 캐시
    restarted = make_adapter(FakeTransport(responses={"jev_screen": _with_model("jev-1.13.0")}))
    assert restarted.adapter_version == want
    assert restarted.screen(PAYLOAD, "screen:notice:1").cached is True
    assert len(rows(session_factory)) == 1


def test_model_change_rejudges(
    make_adapter: Callable[..., Any], session_factory: sessionmaker[Session]
) -> None:
    """모델이 바뀌면(서버 버전 그대로여도) 새 hash → 같은 입력도 재판정. D18-1(R4-FIX): 바뀐 것을 본 **그 실행 중에는
    키를 바꾸지 않고**(같은 입력 재호출·replay 없음) 다음 실행(새 어댑터)부터 새 키로 재판정한다."""
    t1 = FakeTransport(responses={"jev_screen": _with_model("jev-1.13.0")})
    make_adapter(t1).screen(PAYLOAD, "screen:notice:1")
    t2 = FakeTransport(responses={"jev_screen": _with_model("jev-1.14.0")})
    a2 = make_adapter(t2)
    other = {"text": "다른 공개 문장", "purpose": "공고 발췌 검사"}
    first_new = a2.screen(other, "screen:notice:2")  # 새 입력에서 새 모델을 알게 된다
    assert first_new.adapter_version is not None and first_new.adapter_version.endswith("+jev-1.13.0")
    assert (a2.observed_version or "").endswith("+jev-1.14.0") and a2.model_change_pending
    same_run = a2.screen(PAYLOAD, "screen:notice:1")  # 같은 실행: 옛 키 그대로 → 캐시
    assert same_run.cached is True and len(t2.calls) == 1
    t3 = FakeTransport(responses={"jev_screen": _with_model("jev-1.14.0")})
    a3 = make_adapter(t3)  # 다음 실행: 새 모델로 고정
    redo = a3.screen(PAYLOAD, "screen:notice:1")  # 옛 모델로 판정했던 입력 → 재판정
    assert redo.cached is False and (redo.adapter_version or "").endswith("+jev-1.14.0")
    assert len(t3.calls) == 1
    assert len(rows(session_factory)) == 3


def test_server_version_change_changes_input_hash(
    make_adapter: Callable[..., Any], session_factory: sessionmaker[Session]
) -> None:
    """serverInfo.version 변경 → adapter_version 변경 → input_hash 변경 → 재호출 1회."""
    t1 = FakeTransport(version="0.14.1")
    t2 = FakeTransport(version="0.15.0")
    e1 = make_adapter(t1).screen(PAYLOAD, "screen:notice:1")
    e2 = make_adapter(t2).screen(PAYLOAD, "screen:notice:1")
    assert e1.adapter_version != e2.adapter_version
    assert e1.input_hash != e2.input_hash
    assert len(t1.calls) == 1 and len(t2.calls) == 1
    assert e2.cached is False
    assert len(rows(session_factory)) == 2


def test_judge_unavailable_leaves_error_row_then_retry_updates_it(
    make_adapter: Callable[..., Any], session_factory: sessionmaker[Session]
) -> None:
    """T18 경로: 타임아웃·프로세스 사망 → JudgeUnavailable + status='error' 행. 재시도는 같은 행 UPDATE."""
    transport = FakeTransport(fail="unavailable")
    adapter = make_adapter(transport)
    with pytest.raises(JudgeUnavailable):
        adapter.noul({"propositions": ["x"]}, "noul:ladder:asof_plus_3y:2029-10:c1")
    (row,) = rows(session_factory)
    assert row.status == "error"
    assert row.error_text
    seq = row.seq

    transport.fail = None
    env = adapter.noul({"propositions": ["x"]}, "noul:ladder:asof_plus_3y:2029-10:c1")
    assert env.cached is False
    assert env.judgment_seq == seq  # 같은 행을 갱신
    (row,) = rows(session_factory)
    assert row.status == "ok"
    assert row.error_text is None


def test_tool_is_error_response_is_unavailable(
    make_adapter: Callable[..., Any], session_factory: sessionmaker[Session]
) -> None:
    adapter = make_adapter(FakeTransport(fail="is_error"))
    with pytest.raises(JudgeUnavailable):
        adapter.rerank({"query": "q", "candidates": [{"id": "complex:1", "text": "t"}]}, "rerank:region:1")
    (row,) = rows(session_factory)
    assert row.status == "error"


def test_every_call_has_a_row_and_output_json_is_raw(
    make_adapter: Callable[..., Any],
    fake_transport: FakeTransport,
    session_factory: sessionmaker[Session],
    samples: dict[str, Any],
) -> None:
    adapter = make_adapter(fake_transport)
    env = adapter.verify(samples["jev_verify"]["arguments"], "verify:section_8")
    with session_factory() as s:
        n = s.scalar(select(func.count()).select_from(JudgmentLog))
        row = s.get(JudgmentLog, env.judgment_seq)
    assert n == 1
    assert row is not None
    # 판정기 원응답(임계값·decision 포함)을 그대로 저장한다 (D6)
    assert row.output_json == samples["jev_verify"]["response"]
    assert row.output_json["auto_accept"] == 0.8
    assert row.input_json == samples["jev_verify"]["arguments"]
    assert row.input_len and row.input_len > 0
    assert row.adapter_version == adapter.adapter_version
    assert env.raw == samples["jev_verify"]["response"]


def test_cached_envelope_from_row_is_rebuilt_identically(
    make_adapter: Callable[..., Any], fake_transport: FakeTransport, samples: dict[str, Any]
) -> None:
    adapter = make_adapter(fake_transport)
    for tool in ("extract", "audit", "classify", "compare", "decide"):
        payload = samples[f"jev_{tool}"]["arguments"]
        first = getattr(adapter, tool)(payload, f"{tool}:t")
        again = getattr(adapter, tool)(payload, f"{tool}:t")
        assert again.cached is True
        assert again.model_dump(exclude={"cached"}) == first.model_dump(exclude={"cached"})

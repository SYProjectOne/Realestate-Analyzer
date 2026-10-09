"""cache.py · log.py — 같은 입력 재호출 금지(T17), adapter_version → input_hash, 실패도 행."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from app.judge.base import ADAPTER_CODE_VERSION, make_adapter_version
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.protocols import JudgeUnavailable, input_hash
from app.judge import cache
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
    assert len(make_adapter_version("1" * 80)) <= 64


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

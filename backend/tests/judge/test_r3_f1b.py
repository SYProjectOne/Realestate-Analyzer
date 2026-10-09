"""R3 수정 F1b — 판정기 어댑터: M12(error·blocked 행은 버전 근거 아님) · minor 11(판정기 다운 시 캐시 재생,
blocked 는 연결 없이, 모델 확정 전 동시 호출 1회)."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.protocols import JudgeUnavailable
from app.judge.base import ADAPTER_CODE_VERSION, ToolResponse, make_adapter_version
from app.models import JudgmentLog

from .conftest import FakeTransport

PAYLOAD: dict[str, Any] = {"text": "84㎡ 공급금액 최고가 608,000,000원", "purpose": "공고 발췌 검사"}
PHONE_PAYLOAD: dict[str, Any] = {"text": "분양문의 010-1234-5678", "purpose": "공고 발췌 검사"}


def _rows(sf: sessionmaker[Session]) -> list[JudgmentLog]:
    with sf() as s:
        return list(s.scalars(select(JudgmentLog).order_by(JudgmentLog.seq)))


def test_minor11_judge_down_replays_cache_instead_of_raising(
    make_adapter: Callable[..., Any], session_factory: sessionmaker[Session]
) -> None:
    first = make_adapter(FakeTransport()).screen(PAYLOAD, "screen:notice:1")
    down = FakeTransport(fail="down")
    again = make_adapter(down).screen(PAYLOAD, "screen:notice:1")
    assert again.cached and again.judgment_seq == first.judgment_seq and again.result == first.result
    assert down.calls == []
    with pytest.raises(JudgeUnavailable):  # 캐시에 없는 입력은 여전히 판정기가 필요하다
        make_adapter(down).screen({"text": "다른 입력"}, "screen:notice:2")
    errors = [r for r in _rows(session_factory) if r.status == "error"]
    assert len(errors) == 1 and errors[0].adapter_version == first.adapter_version


def test_minor11_guard_block_does_not_need_the_judge(
    make_adapter: Callable[..., Any], session_factory: sessionmaker[Session]
) -> None:
    down = FakeTransport(fail="down")
    env = make_adapter(down).screen(PHONE_PAYLOAD, "screen:notice:3")
    assert env.status == "blocked" and down.calls == []
    (row,) = _rows(session_factory)
    assert row.status == "blocked" and "010-1234-5678" not in str(row.input_json)


class SlowTransport(FakeTransport):
    """호출 사이에 끼어들 틈을 만든다(경합 재현)."""

    def call(self, tool_name: str, arguments: dict[str, Any]) -> ToolResponse:
        time.sleep(0.05)
        return super().call(tool_name, arguments)


def test_minor11_concurrent_first_calls_before_model_confirmed_call_judge_once(
    make_adapter: Callable[..., Any], session_factory: sessionmaker[Session]
) -> None:
    transport = SlowTransport()
    adapter = make_adapter(transport)
    envs: list[Any] = []
    errors: list[BaseException] = []

    def work() -> None:
        try:
            envs.append(adapter.screen(PAYLOAD, "screen:notice:9"))
        except BaseException as exc:  # pragma: no cover - 실패 보고용
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(transport.calls) == 1  # 모델 확정 전 경합에도 실제 호출 1회
    assert len({e.judgment_seq for e in envs}) == 1 and sum(not e.cached for e in envs) == 1
    assert len(_rows(session_factory)) == 1


def test_m12_error_rows_are_not_model_evidence(
    make_adapter: Callable[..., Any], session_factory: sessionmaker[Session]
) -> None:
    ok = make_adapter(FakeTransport()).screen(PAYLOAD, "screen:notice:1")
    assert ok.adapter_version and ok.adapter_version.endswith("+jev-1.13.0")
    stale = make_adapter_version("0.14.1", "jev-0.0.0-stale")
    with session_factory() as s:  # 응답 없이 쓰인 error 행(다른 모델 접미)
        s.add(JudgmentLog(tool="screen", purpose="x", input_hash="sha256:" + "e" * 64, input_len=1,
                          input_json={}, output_json={}, status="error", adapter_version=stale,
                          created_at="2026-10-09T00:00:00+09:00"))  # fmt: skip
        s.commit()
    fresh = make_adapter(FakeTransport())
    assert fresh.adapter_version == ok.adapter_version  # 마지막 '정상' 행의 모델
    assert fresh.adapter_version.startswith(f"{ADAPTER_CODE_VERSION}+jev-mcp@0.14.1")

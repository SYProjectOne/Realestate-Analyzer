"""guard.py — T14: 전화번호·주민번호·이메일·설정 비밀값 → 호출 거부 + status=blocked 행 + 로그에 원문 없음."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import Settings
from app.judge import guard
from app.models import JudgmentLog

from .conftest import FakeTransport

PHONE = "010-1234-5678"
EMAIL = "someone@example.com"
RRN = "900101-1234567"
SECRET = "sk-test-SECRET-value-123456"


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        (f"분양 문의 {PHONE}", "phone"),
        (f"담당자 메일 {EMAIL}", "email"),
        (f"주민번호 {RRN}", "rrn"),
        (f"키 {SECRET}", "secret"),
    ],
)
def test_check_payload_finds_sensitive_values(text: str, kind: str) -> None:
    result = guard.check_payload({"candidates": [{"id": "complex:1", "text": text}]}, secrets=[SECRET])
    assert not result.ok
    assert [f.kind for f in result.findings] == [kind]
    assert result.findings[0].path == "$.candidates[0].text"


def test_public_payload_passes() -> None:
    result = guard.check_payload(
        {"text": "전용 84A 공급금액 최고가 608,000,000원, 계약금 10%, 입주 2028-03", "purpose": "공고"},
        secrets=[SECRET],
    )
    assert result.ok
    assert result.findings == []


def test_keys_are_checked_too() -> None:
    assert not guard.check_payload({EMAIL: "x"}, secrets=[]).ok


def test_default_secrets_include_settings_secret_values(test_settings: Settings) -> None:
    test_settings.data_go_kr_key = SecretStr(SECRET)
    assert SECRET in guard.default_secrets(test_settings)


@pytest.mark.parametrize("bad", [PHONE, EMAIL, RRN, SECRET])
def test_blocked_call_is_refused_logged_and_never_leaks(
    bad: str,
    make_adapter: Callable[..., Any],
    fake_transport: FakeTransport,
    session_factory: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """T14: 거부 + blocked 행 + 로그·행·봉투 어디에도 원문 없음."""
    adapter = make_adapter(fake_transport, secrets=[SECRET])
    payload = {"claims": [f"문의처는 {bad} 이다."], "evidence": "공고문 발췌"}
    with caplog.at_level(logging.DEBUG):
        env = adapter.verify(payload, "verify:section_1")

    assert fake_transport.calls == []  # 판정기에 보내지 않았다
    assert env.status == "blocked"
    assert env.result == {}
    assert env.judgment_seq is not None
    assert env.cached is False

    with session_factory() as s:
        (row,) = s.scalars(select(JudgmentLog))
    assert row.status == "blocked"
    assert row.seq == env.judgment_seq
    dumped = json.dumps(
        {"in": row.input_json, "out": row.output_json, "err": row.error_text}, ensure_ascii=False
    )
    assert bad not in dumped
    assert bad not in env.model_dump_json()
    assert "$.claims[0]" in dumped  # 어디서 걸렸는지는 남긴다(경로·종류만)

    logged = "\n".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    assert bad not in logged
    assert "문의처" not in logged  # payload 원문 어떤 부분도 로그에 없다
    assert any(getattr(r, "input_hash", None) for r in caplog.records)  # hash·길이만


def test_blocked_is_final_and_cached(
    make_adapter: Callable[..., Any], fake_transport: FakeTransport, session_factory: sessionmaker[Session]
) -> None:
    adapter = make_adapter(fake_transport)
    payload = {"text": f"문의 {PHONE}"}
    a = adapter.screen(payload, "screen:notice:1")
    b = adapter.screen(payload, "screen:notice:1")
    assert a.status == b.status == "blocked"
    assert b.cached is True
    assert fake_transport.calls == []
    with session_factory() as s:
        assert len(list(s.scalars(select(JudgmentLog)))) == 1


def test_successful_call_logs_only_hash_and_length(
    make_adapter: Callable[..., Any], fake_transport: FakeTransport, caplog: pytest.LogCaptureFixture
) -> None:
    adapter = make_adapter(fake_transport)
    with caplog.at_level(logging.DEBUG):
        env = adapter.screen({"text": "고유문구XYZ 공급금액"}, "screen:notice:9")
    logged = "\n".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    assert "고유문구XYZ" not in logged
    rec = next(r for r in caplog.records if getattr(r, "input_hash", None))
    assert env.input_hash.endswith(rec.input_hash)
    assert rec.payload_length == env.input_len

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator

import pytest

from app.core.logging import JsonFormatter, configure_logging, get_logger, log_payload_meta
from app.core.settings import Settings

HASH = "a" * 64


@pytest.fixture
def stream(test_settings: Settings) -> Iterator[io.StringIO]:
    buf = io.StringIO()
    configure_logging(test_settings, stream=buf, level="DEBUG")
    yield buf
    configure_logging(test_settings, stream=io.StringIO(), level="WARNING")


def lines(buf: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in buf.getvalue().splitlines() if line.strip()]


def test_json_lines_with_standard_fields(stream: io.StringIO) -> None:
    get_logger("app.test").info("hello %s", "world", extra={"source": "applyhome", "n": 3})
    (rec,) = lines(stream)
    assert rec["msg"] == "hello world"
    assert rec["level"] == "INFO"
    assert rec["logger"] == "app.test"
    assert str(rec["ts"]).endswith("+09:00")
    assert rec["source"] == "applyhome"
    assert rec["n"] == 3


def test_pii_and_secrets_masked(test_settings: Settings) -> None:
    from pydantic import SecretStr

    s = test_settings.model_copy(update={"api_token": SecretStr("SUPERSECRET-TOKEN-123")})
    buf = io.StringIO()
    configure_logging(s, stream=buf, level="INFO")
    log = get_logger("app.test")
    log.info("token SUPERSECRET-TOKEN-123 phone 010-1234-5678", extra={"email": "a@b.com"})
    log.info("url", extra={"url": "https://x.test/?serviceKey=SUPERSECRET-TOKEN-123"})
    out = buf.getvalue()
    assert "SUPERSECRET-TOKEN-123" not in out
    assert "010-1234-5678" not in out
    assert "a@b.com" not in out
    assert "[REDACTED:secret]" in out
    configure_logging(test_settings, stream=io.StringIO(), level="WARNING")


def test_exception_is_logged_and_redacted(stream: io.StringIO) -> None:
    try:
        raise ValueError("bad 010-9999-8888")
    except ValueError:
        get_logger("app.test").exception("failed")
    (rec,) = lines(stream)
    assert "ValueError" in str(rec["exc"])
    assert "010-9999-8888" not in str(rec["exc"])


def test_configure_logging_idempotent(stream: io.StringIO, test_settings: Settings) -> None:
    buf2 = io.StringIO()
    configure_logging(test_settings, stream=buf2, level="INFO")
    configure_logging(test_settings, stream=buf2, level="INFO")
    get_logger("app.test").info("once")
    assert len(lines(buf2)) == 1
    json_handlers = [h for h in logging.getLogger().handlers if isinstance(h.formatter, JsonFormatter)]
    assert len(json_handlers) == 1


def test_log_payload_meta_only_hash_and_length(stream: io.StringIO) -> None:
    log_payload_meta(HASH, 1234, tool="jev_screen", cached=False)
    (rec,) = lines(stream)
    assert rec["input_hash"] == HASH
    assert rec["payload_length"] == 1234
    assert rec["tool"] == "jev_screen"
    assert rec["cached"] is False
    assert rec["msg"] == "judge.payload"


def test_log_payload_meta_rejects_payload_like_values(stream: io.StringIO) -> None:
    with pytest.raises(ValueError):
        log_payload_meta("not-a-hash", 10)
    with pytest.raises(ValueError):
        log_payload_meta(HASH, -1)
    with pytest.raises(ValueError):
        log_payload_meta(HASH, 10, payload="x" * 500)
    with pytest.raises(TypeError):
        log_payload_meta(HASH, 10, payload={"text": "원문"})  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        log_payload_meta(HASH, 10, msg="reserved")
    assert lines(stream) == []

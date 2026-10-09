"""JSON 구조 로그 + 마스킹 (AGENTS 규칙 6·13).

- 한 줄 = JSON 하나: ``ts``(Asia/Seoul ISO), ``level``, ``logger``, ``msg``, extra 필드, ``exc``.
- 출력 직전 ``redact_obj`` 로 설정의 비밀값 전부·전화번호·주민번호·이메일·URL 키 파라미터를 가린다.
- 판정기 payload 는 원문을 로그에 남기지 않는다 → ``log_payload_meta(input_hash, length)`` 만 쓴다.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Sequence
from datetime import datetime
from typing import IO, Any

from app.core.redact import redact_obj
from app.core.settings import Settings, get_settings
from app.core.time import KST

_RESERVED = frozenset(logging.LogRecord("x", logging.INFO, "x", 0, "x", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}
_HASH_RE = re.compile(r"^[0-9a-f]{16,128}$")
_MAX_META_STR = 80
_HANDLER_MARK = "_subscription_analyzer_json"


class JsonFormatter(logging.Formatter):
    def __init__(self, secrets: Sequence[str] = ()) -> None:
        super().__init__()
        self._secrets = list(secrets)

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, KST).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_") and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(redact_obj(payload, self._secrets), ensure_ascii=False, default=str)


def configure_logging(
    settings: Settings | None = None,
    *,
    stream: IO[str] | None = None,
    level: str | int | None = None,
) -> None:
    """루트 로거에 JSON 핸들러 하나를 단다. 여러 번 불러도 핸들러는 하나(이전 것을 교체)."""
    s = settings or get_settings()
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, _HANDLER_MARK, False):
            root.removeHandler(h)
            h.close()  # StreamHandler.close 는 스트림을 닫지 않는다
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    if s.log_json:
        handler.setFormatter(JsonFormatter(s.secret_values()))
    else:
        handler.setFormatter(_RedactingTextFormatter(s.secret_values()))
    setattr(handler, _HANDLER_MARK, True)
    root.addHandler(handler)
    root.setLevel(level if level is not None else s.log_level.upper())
    # httpx 는 INFO 에 전체 URL(쿼리 키 포함)을 남긴다 — 마스킹되지만 소음이 커서 WARNING 으로
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


class _RedactingTextFormatter(logging.Formatter):
    def __init__(self, secrets: Sequence[str] = ()) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s %(message)s")
        self._secrets = list(secrets)

    def format(self, record: logging.LogRecord) -> str:
        return str(redact_obj(super().format(record), self._secrets))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_payload_meta(
    input_hash: str,
    length: int,
    *,
    logger: logging.Logger | None = None,
    event: str = "judge.payload",
    level: int = logging.INFO,
    **fields: str | int | float | bool | None,
) -> None:
    """판정기 호출 기록: input_hash·길이·짧은 메타(도구 이름·cached 등)만. payload 원문은 받지 않는다."""
    if not isinstance(input_hash, str) or not _HASH_RE.fullmatch(input_hash):
        raise ValueError("input_hash 는 소문자 hex 문자열이어야 한다")
    if not isinstance(length, int) or isinstance(length, bool) or length < 0:
        raise ValueError("length 는 0 이상의 정수")
    extra: dict[str, Any] = {"input_hash": input_hash, "payload_length": length}
    for key, value in fields.items():
        if key in _RESERVED or key in extra:
            raise ValueError(f"예약된 로그 필드 이름: {key}")
        if value is not None and not isinstance(value, str | int | float | bool):
            raise TypeError(f"{key}: 스칼라 값만 허용 (payload 원문 금지)")
        if isinstance(value, str) and len(value) > _MAX_META_STR:
            raise ValueError(f"{key}: {_MAX_META_STR}자 초과 문자열 금지 (payload 원문 금지)")
        extra[key] = value
    (logger or logging.getLogger("app.judge")).log(level, event, extra=extra)

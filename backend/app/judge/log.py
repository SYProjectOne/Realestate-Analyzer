"""판정기 호출 기록 (RA §3 judgment_log, AGENTS 규칙 7·13).

- 모든 호출은 성공·실패·blocked 불문 judgment_log 1행(``record``).
  status='error' 행은 같은 hash 재시도 때 UPDATE.
- 정규화 결과(봉투 result)는 ``result_json`` 에 저장한다(계약 2026-10-09.3). blocked·error 행은 ``{}``.
- 파이썬 로그(``log_call``)에는 input_hash·길이·도구·상태·cached·소요만.
  payload 원문·purpose 는 남기지 않는다.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.contracts_gen import JudgmentEnvelope
from app.core.logging import get_logger, log_payload_meta
from app.models import JudgmentLog

__all__ = ["log_call", "record"]

_logger = get_logger("app.judge")


def record(
    session: Session,
    *,
    existing: JudgmentLog | None,
    tool: str,
    purpose: str,
    input_hash: str,
    input_len: int,
    input_json: dict[str, Any],
    output_json: dict[str, Any],
    status: str,
    confidence: float | None,
    duration_ms: int | None,
    adapter_version: str,
    snapshot_id: int | None,
    complex_id: int | None,
    error_text: str | None,
    created_at: str,
    result_json: dict[str, Any] | None = None,
) -> JudgmentLog:
    """행을 넣거나(새 hash) error 행을 갱신한다(같은 hash 재시도). commit 은 호출자가 한다."""
    if existing is not None and existing.status != "error":
        raise ValueError("최종 판정 행은 갱신하지 않는다 (같은 입력 재호출 금지)")
    row = existing if existing is not None else JudgmentLog(input_hash=input_hash)
    row.input_hash = input_hash  # error 행 재시도 중 모델을 알게 되면 새 버전의 hash 로 옮긴다(D6 보강)
    row.tool = tool
    row.purpose = purpose
    row.input_len = input_len
    row.input_json = input_json
    row.output_json = output_json
    row.result_json = result_json if result_json is not None else {}
    row.status = status
    row.confidence = Decimal(str(round(confidence, 4))) if confidence is not None else None
    row.duration_ms = duration_ms
    row.adapter_version = adapter_version
    row.snapshot_id = snapshot_id if snapshot_id is not None else row.snapshot_id
    row.complex_id = complex_id if complex_id is not None else row.complex_id
    row.error_text = error_text
    row.created_at = created_at
    row.model, row.provider = (
        _response_model(output_json) if status not in ("blocked", "error") else (None, None)
    )
    if existing is None:
        session.add(row)
    session.flush()
    return row


def _response_model(raw: dict[str, Any]) -> tuple[str | None, str | None]:
    """원응답의 (model, provider) — 계약 .15 judgment_log 열(D18-1: 행에 실제 응답 모델을 따로)."""

    def text(v: Any, n: int) -> str | None:
        return v.strip()[:n] if isinstance(v, str) and v.strip() else None

    raw = raw if isinstance(raw, dict) else {}
    return text(raw.get("model"), 64), text(raw.get("provider"), 32)


def log_call(env: JudgmentEnvelope, *, cached: bool) -> None:
    """input_hash(hex)·길이·짧은 메타만 남긴다."""
    log_payload_meta(
        env.input_hash.removeprefix("sha256:"),
        env.input_len or 0,
        logger=_logger,
        tool=env.tool,
        status=env.status,
        cached=cached,
        judgment_seq=env.judgment_seq,
        duration_ms=env.duration_ms,
    )

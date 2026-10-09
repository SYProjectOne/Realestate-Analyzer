"""같은 입력 재호출 금지 (AGENTS 규칙 4, RA §4-3, T17).

키 = ``input_hash = 'sha256:' + sha256(canonical JSON{tool, purpose, payload, adapter_version})`` —
정의는 ``app.core.protocols.input_hash`` 한 곳(WP5 시나리오 미리보기와 공용). 여기서는 그것을 쓰고
judgment_log 조회·행 → 봉투 변환만 한다.

- status 가 ok·review·escaped·blocked 인 행은 최종: 다시 부르지 않고 ``cached=True`` 봉투.
- status='error' 행은 최종이 아니다: 같은 hash 로 재시도하면 그 행을 갱신한다(``log.record``).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contracts_gen import JudgmentEnvelope
from app.core.protocols import JudgePayload, JudgeTool, canonical_hash_json, input_hash
from app.models import JudgmentLog

__all__ = [
    "NOT_VERSION_EVIDENCE",
    "compute_hash",
    "envelope_from_row",
    "find",
    "is_final",
    "last_adapter_version",
    "payload_length",
]


def compute_hash(tool: JudgeTool, purpose: str, payload: JudgePayload, adapter_version: str) -> str:
    return input_hash(tool, purpose, payload, adapter_version)


def payload_length(payload: JudgePayload) -> int:
    """canonical payload 길이(문자 수) = judgment_log.input_len, 로그용."""
    return len(canonical_hash_json(payload))


def find(session: Session, key: str) -> JudgmentLog | None:
    return session.scalars(select(JudgmentLog).where(JudgmentLog.input_hash == key)).one_or_none()


NOT_VERSION_EVIDENCE = ("error", "blocked")
"""버전 근거로 쓰지 않는 행 상태(R3 M12): 판정기 응답 없이(모델을 모른 채·연결 없이) 쓰인 버전일 수 있다."""


def last_adapter_version(session: Session, prefix: str, *, final_only: bool = False) -> str | None:
    """prefix 로 시작하는 adapter_version 중 가장 최근 행(seq 최대)의 값. 없으면 None.

    ``final_only`` 면 판정기 응답이 있는 행(ok·review·escaped)만 본다 — error·blocked 행 제외.
    """
    stmt = select(JudgmentLog.adapter_version).where(
        JudgmentLog.adapter_version.startswith(prefix, autoescape=True)
    )
    if final_only:
        stmt = stmt.where(JudgmentLog.status.not_in(NOT_VERSION_EVIDENCE))
    return session.scalars(stmt.order_by(JudgmentLog.seq.desc()).limit(1)).first()


def is_final(row: JudgmentLog) -> bool:
    return row.status != "error"


def envelope_from_row(row: JudgmentLog, *, cached: bool, result: dict[str, Any]) -> JudgmentEnvelope:
    """judgment_log 행 → 봉투. raw = output_json 그대로(임계값·decision 포함, D6)."""
    confidence = float(row.confidence) if row.confidence is not None else None
    return JudgmentEnvelope(
        tool=row.tool,
        purpose=row.purpose,
        input_hash=row.input_hash,
        input_len=row.input_len,
        status=row.status,
        confidence=confidence,
        cached=cached,
        result=result,
        raw=dict(row.output_json or {}),
        duration_ms=row.duration_ms,
        judgment_seq=row.seq,
        created_at=row.created_at,
        adapter_version=row.adapter_version,
        snapshot_id=row.snapshot_id,
        complex_id=row.complex_id,
        error_text=row.error_text,
    )

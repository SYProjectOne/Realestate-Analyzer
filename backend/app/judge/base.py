"""판정기 어댑터 공통 (RA §4-3 JudgeAdapter, DECISIONS D6).

흐름(모든 도구 공통, ``CachedJudgeAdapter.call``)::

    guard(payload) ─ 거부 → status='blocked' 행 + 봉투 (판정기에 보내지 않음)
         │ 통과
    input_hash(tool, purpose, payload, adapter_version) → judgment_log 조회
         │ 있고 error 가 아니면 → cached=True 봉투 (판정기 호출 없음, T17)
         │ 없거나 error
    transport.call(jev_<tool>, payload) ─ 실패 → status='error' 행 + JudgeUnavailable (T18)
         │
    normalize(tool, raw, payload, purpose) → status·result·confidence
         │
    judgment_log 행(insert, error 행이면 update) → cached=False 봉투

- 어댑터는 임계값을 넘기지 않는다. payload 는 JEV 입력 그대로(``payloads.py``)이고 임계 인자를 넣지 않는다.
- adapter_version = ``<ADAPTER_CODE_VERSION>+jev-mcp@<initialize.serverInfo.version>+<응답 model>``
  (DECISIONS D6 보강, 계약 2026-10-09.2). 모델은 응답에만 보이므로: 시작할 때 judgment_log 에서 같은 코드·서버
  버전의 마지막 모델을 읽고(없으면 접미 없이), 응답의 ``model`` 이 다르면 그 자리에서 버전을 바꾸고 이 호출을
  새 버전의 input_hash 로 기록한다 — 모델이 바뀌면 그 뒤 모든 hash 가 바뀌어 재판정된다.
- 로그에는 input_hash·길이·도구·상태만(``log.py``). payload 원문은 judgment_log.input_json 에만(guard 통과분).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal, Protocol, runtime_checkable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.contracts_gen import JudgmentEnvelope
from app.core.protocols import JUDGE_TOOLS, JudgePayload, JudgeTool, JudgeUnavailable
from app.core.redact import redact_text
from app.core.time import now_kst
from app.judge import cache, guard, log

__all__ = [
    "ADAPTER_CODE_VERSION",
    "TOOL_NAMES",
    "CachedJudgeAdapter",
    "JudgeCaller",
    "Normalized",
    "SessionFactory",
    "Status",
    "ToolResponse",
    "Transport",
    "make_adapter_version",
    "model_of",
]

ADAPTER_CODE_VERSION: Final = "0.1.0"
"""어댑터 코드 버전. 정규화·payload 규칙이 바뀌면 올린다 → 모든 input_hash가 바뀌어 전체 재판정 1회."""

SERVER_TAG: Final = "jev-mcp"
TOOL_NAMES: Final[dict[JudgeTool, str]] = {t: f"jev_{t}" for t in JUDGE_TOOLS}
"""계약 도구 이름 → JEV MCP 도구 이름 (DECISIONS D6). find·gate·review 는 쓰지 않는다."""

Status = Literal["ok", "review", "escaped", "blocked", "error"]
SessionFactory = Callable[[], Session]
_ERROR_TEXT_MAX = 300


def make_adapter_version(server_version: str, model: str | None = None) -> str:
    """``'<코드 버전>+jev-mcp@<서버 버전>[+<모델>]'`` (judgment_log.adapter_version 은 64자)."""
    version = (server_version or "unknown").strip() or "unknown"
    out = f"{ADAPTER_CODE_VERSION}+{SERVER_TAG}@{version}"
    name = (model or "").strip()
    if name:
        out += f"+{name}"
    return out[:64]


def model_of(raw: dict[str, Any]) -> str | None:
    """판정기 원응답의 모델 이름(JEV: ``"model": "jev-1.13.0"``). 없으면 None."""
    value = raw.get("model") if isinstance(raw, dict) else None
    return value.strip() if isinstance(value, str) and value.strip() else None


@dataclass(frozen=True, slots=True)
class ToolResponse:
    """전송 계층이 돌려주는 도구 응답 1건. raw = 판정기 원응답 JSON(임계값·decision 포함)."""

    raw: dict[str, Any]
    is_error: bool
    duration_ms: int


@runtime_checkable
class Transport(Protocol):
    """판정기 프로세스와의 연결. 실패는 전부 ``JudgeUnavailable``."""

    def server_version(self) -> str: ...

    def call(self, tool_name: str, arguments: JudgePayload) -> ToolResponse: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class Normalized:
    """판정기 원응답 → 봉투의 status·result·confidence (도구별 정규화 결과)."""

    status: Status
    result: dict[str, Any]
    confidence: float | None = None


@runtime_checkable
class JudgeCaller(Protocol):
    """pipeline.py 가 쓰는 호출 모양: 계약 9개 메서드 + 행에 snapshot·complex 를 남기는 ``call``."""

    @property
    def adapter_version(self) -> str: ...

    def call(
        self,
        tool: JudgeTool,
        payload: JudgePayload,
        purpose: str,
        *,
        snapshot_id: int | None = None,
        complex_id: int | None = None,
    ) -> JudgmentEnvelope: ...


def _now() -> str:
    return now_kst().isoformat(timespec="seconds")


def _clamp_confidence(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    f = float(value)
    if f != f:  # NaN
        return None
    return min(1.0, max(0.0, f))


class CachedJudgeAdapter:
    """guard · 캐시 · judgment_log 를 강제하는 어댑터 뼈대. 하위 클래스는 ``normalize`` 만 정한다.

    ``session_factory`` 는 호출마다 새 세션을 연다(호출자의 트랜잭션과 독립 — 실패 행도 반드시 남는다).
    """

    def __init__(
        self,
        transport: Transport,
        *,
        session_factory: SessionFactory | None = None,
        secrets: Sequence[str] | None = None,
    ) -> None:
        self._transport = transport
        if session_factory is None:
            from app.core.db import get_sessionmaker

            session_factory = get_sessionmaker()
        self._session_factory = session_factory
        self._secrets = list(secrets) if secrets is not None else guard.default_secrets()
        self._adapter_version: str | None = None
        self._server_version: str | None = None
        self._model: str | None = None

    # ------------------------------------------------------------------ 버전

    @property
    def adapter_version(self) -> str:
        """판정기 서버 버전(처음 한 번 연결) + 마지막으로 본 모델. 연결 실패면 JudgeUnavailable."""
        if self._adapter_version is None:
            self._server_version = self._transport.server_version()
            if self._model is None:
                self._model = self._last_model(make_adapter_version(self._server_version))
            self._adapter_version = make_adapter_version(self._server_version, self._model)
        return self._adapter_version

    def _last_model(self, prefix: str) -> str | None:
        """같은 코드·서버 버전으로 기록된 마지막 행의 모델(재시작해도 같은 hash 가 되도록)."""
        with self._session_factory() as session:
            last = cache.last_adapter_version(session, prefix + "+")
        if not last:
            return None
        return last[len(prefix) + 1 :] or None

    def _observe_model(self, raw: dict[str, Any]) -> bool:
        """응답의 모델이 지금 버전과 다르면 버전을 바꾸고 True."""
        model = model_of(raw)
        if model is None or model == self._model or self._server_version is None:
            return False
        self._model = model
        self._adapter_version = make_adapter_version(self._server_version, model)
        return True

    def close(self) -> None:
        self._transport.close()

    # ------------------------------------------------------------------ 정규화 (하위 클래스)

    def normalize(
        self, tool: JudgeTool, raw: dict[str, Any], payload: JudgePayload, purpose: str
    ) -> Normalized:
        raise NotImplementedError

    # ------------------------------------------------------------------ 9개 메서드

    def screen(self, payload: JudgePayload, purpose: str) -> JudgmentEnvelope:
        return self.call("screen", payload, purpose)

    def extract(self, payload: JudgePayload, purpose: str) -> JudgmentEnvelope:
        return self.call("extract", payload, purpose)

    def audit(self, payload: JudgePayload, purpose: str) -> JudgmentEnvelope:
        return self.call("audit", payload, purpose)

    def classify(self, payload: JudgePayload, purpose: str) -> JudgmentEnvelope:
        return self.call("classify", payload, purpose)

    def compare(self, payload: JudgePayload, purpose: str) -> JudgmentEnvelope:
        return self.call("compare", payload, purpose)

    def noul(self, payload: JudgePayload, purpose: str) -> JudgmentEnvelope:
        return self.call("noul", payload, purpose)

    def rerank(self, payload: JudgePayload, purpose: str) -> JudgmentEnvelope:
        return self.call("rerank", payload, purpose)

    def decide(self, payload: JudgePayload, purpose: str) -> JudgmentEnvelope:
        return self.call("decide", payload, purpose)

    def verify(self, payload: JudgePayload, purpose: str) -> JudgmentEnvelope:
        return self.call("verify", payload, purpose)

    # ------------------------------------------------------------------ 공통 경로

    def call(
        self,
        tool: JudgeTool,
        payload: JudgePayload,
        purpose: str,
        *,
        snapshot_id: int | None = None,
        complex_id: int | None = None,
    ) -> JudgmentEnvelope:
        if tool not in TOOL_NAMES:
            raise ValueError(f"알 수 없는 도구: {tool!r}")
        if not purpose or len(purpose) > 128:
            raise ValueError("purpose 는 1~128자")
        checked = guard.check_payload(payload, secrets=self._secrets)
        version = self.adapter_version
        key = cache.compute_hash(tool, purpose, payload, version)
        length = cache.payload_length(payload)

        with self._session_factory() as session:
            existing = cache.find(session, key)
            if existing is not None and cache.is_final(existing):
                env = cache.envelope_from_row(existing, cached=True, result=self._result_of(existing))
                log.log_call(env, cached=True)
                return env

            if not checked.ok:
                row = log.record(
                    session,
                    existing=existing,
                    tool=tool,
                    purpose=purpose,
                    input_hash=key,
                    input_len=length,
                    input_json=guard.blocked_input_json(checked),
                    output_json={"reason": "guard", "findings": checked.summary()},
                    status="blocked",
                    confidence=None,
                    duration_ms=0,
                    adapter_version=version,
                    snapshot_id=snapshot_id,
                    complex_id=complex_id,
                    error_text=f"guard: {', '.join(checked.kinds())}",
                    created_at=_now(),
                )
                return self._commit(session, row, result={}, key=key)

            try:
                response = self._transport.call(TOOL_NAMES[tool], payload)
            except JudgeUnavailable as exc:
                self._record_error(session, existing, tool, purpose, key, length, payload, version,
                                   snapshot_id, complex_id, f"unavailable: {exc}", None)  # fmt: skip
                raise
            if response.is_error:
                message = str(response.raw.get("error") or response.raw)[:_ERROR_TEXT_MAX]
                self._record_error(session, existing, tool, purpose, key, length, payload, version,
                                   snapshot_id, complex_id, f"tool error: {message}", response)  # fmt: skip
                raise JudgeUnavailable(f"{TOOL_NAMES[tool]} 오류 응답")

            if self._observe_model(response.raw):
                # 모델이 바뀌었다(또는 처음 알았다) → 이 응답은 새 버전의 hash 로 기록한다
                version = self.adapter_version
                key = cache.compute_hash(tool, purpose, payload, version)
                renewed = cache.find(session, key)
                if renewed is not None and cache.is_final(renewed):
                    env = cache.envelope_from_row(renewed, cached=True, result=self._result_of(renewed))
                    log.log_call(env, cached=True)
                    return env
                # 새 hash 에 행이 없으면 옛 hash 의 error 행(있으면)을 새 hash 로 옮겨 갱신한다
                existing = renewed if renewed is not None else existing

            normalized = self.normalize(tool, response.raw, payload, purpose)
            row = log.record(
                session,
                existing=existing,
                tool=tool,
                purpose=purpose,
                input_hash=key,
                input_len=length,
                input_json=payload,
                output_json=response.raw,
                status=normalized.status,
                confidence=_clamp_confidence(normalized.confidence),
                duration_ms=response.duration_ms,
                adapter_version=version,
                snapshot_id=snapshot_id,
                complex_id=complex_id,
                error_text=None,
                created_at=_now(),
            )
            return self._commit(session, row, result=normalized.result, key=key)

    # ------------------------------------------------------------------ 내부

    def _result_of(self, row: Any) -> dict[str, Any]:
        if row.status in {"blocked", "error"}:
            return {}
        return self.normalize(row.tool, row.output_json, row.input_json, row.purpose).result

    def _commit(self, session: Session, row: Any, *, result: dict[str, Any], key: str) -> JudgmentEnvelope:
        try:
            session.commit()
        except IntegrityError:
            # 다른 worker 가 같은 input_hash 를 먼저 기록했다 → 그 행이 정답(재호출 금지)
            session.rollback()
            winner = cache.find(session, key)
            if winner is None:
                raise
            env = cache.envelope_from_row(winner, cached=True, result=self._result_of(winner))
            log.log_call(env, cached=True)
            return env
        env = cache.envelope_from_row(row, cached=False, result=result)
        log.log_call(env, cached=False)
        return env

    def _record_error(
        self,
        session: Session,
        existing: Any,
        tool: JudgeTool,
        purpose: str,
        key: str,
        length: int,
        payload: JudgePayload,
        version: str,
        snapshot_id: int | None,
        complex_id: int | None,
        error_text: str,
        response: ToolResponse | None,
    ) -> None:
        row = log.record(
            session,
            existing=existing,
            tool=tool,
            purpose=purpose,
            input_hash=key,
            input_len=length,
            input_json=payload,
            output_json=response.raw if response is not None else {},
            status="error",
            confidence=None,
            duration_ms=response.duration_ms if response is not None else None,
            adapter_version=version,
            snapshot_id=snapshot_id,
            complex_id=complex_id,
            error_text=redact_text(error_text, self._secrets)[:_ERROR_TEXT_MAX],
            created_at=_now(),
        )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return
        log.log_call(cache.envelope_from_row(row, cached=False, result={}), cached=False)

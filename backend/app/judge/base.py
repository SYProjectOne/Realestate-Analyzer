"""판정기 어댑터 공통 (RA §4-3 JudgeAdapter, DECISIONS D6).

흐름(모든 도구 공통, ``CachedJudgeAdapter.call``)::

    guard(payload) 검사(결과는 아래에서 씀)
    adapter_version(서버 initialize, 어댑터당 1회 — 그 뒤는 메모리)
         │ 연결 실패(판정기 다운, R3 minor 11) → judgment_log 마지막 정상 행(ok·review·escaped)의 버전으로
         │   캐시 조회 → 있으면 cached=True 봉투(재생), 없으면 guard 거부면 blocked 행·봉투,
         │   아니면 error 행 + JudgeUnavailable
    input_hash(tool, purpose, payload, adapter_version) → judgment_log 조회
         │ 있고 error 가 아니면 → cached=True 봉투 (판정기 호출 없음, T17)
    guard 거부 → status='blocked' 행 + 봉투 (판정기에 보내지 않음)
         │ 통과
    [잠금: 같은 hash 는 한 번에 하나, 모델 확정 전에는 모든 호출을 하나씩 → 실제 호출 1회 보장]
    meter += 1; transport.call(jev_<tool>, payload) ─ 실패 → status='error' 행 + JudgeUnavailable (T18)
         │
    normalize(tool, raw, payload, purpose) → status·result·confidence
         │
    judgment_log 행(insert, error 행이면 update; result_json = 정규화 결과) → cached=False 봉투

- 어댑터는 임계값을 넘기지 않는다. payload 는 JEV 입력 그대로(``payloads.py``)이고 임계 인자를 넣지 않는다.
- adapter_version(캐시 키) = ``<ADAPTER_CODE_VERSION>+jev-mcp@<initialize.serverInfo.version>+<고정 모델>``
  (DECISIONS D6 보강 → **D18-1**). 고정 모델 = **모델을 실제로 부른 응답**(``provider`` ≠ ``none``)이 알려 준
  모델. provider none(JEV 로컬 단락 — 0.14.1 extract 는 이때 ``model: "jev-latest"``) 응답의 model 은 무시한다.
  시작할 때 judgment_log 에서 같은 코드·서버 버전으로 기록된 마지막 '모델 호출' 응답의 model 을 읽어 고정한다.
  - 모델을 아직 모르면(빈 DB) 접미 없이 시작하고, 첫 모델 호출 응답에서 고정한다. 그때 접미 없이 쓴 이번
    버전의 정상 행을 새 버전의 hash 로 옮긴다(``_adopt_first_model``) — 같은 입력이 다시 판정기로 가지 않는다.
  - 고정 모델과 다른 모델이 응답에 보이면(모델 변경) **그 실행(어댑터 수명) 중에는 키를 바꾸지 않는다** —
    replay 도 없다. ``observed_version``·``model_change_pending`` 으로 알리고, 파이프라인이
    change_event(judge·version·critical)를 남긴 뒤 어댑터를 버린다 → 다음 실행(새 어댑터)이 새 모델로 고정해
    전체 재판정한다.
  - 응답의 실제 ``model``·``provider`` 는 judgment_log.output_json(원응답)에 그대로 남는다.
- 실제 호출 수(**D18-2**) = 전송 계층으로 보낸 ``tools/call`` 수(``CallMeter``). 캐시 적중은 0 이다.
  잡 stats·G7 이 이 수를 쓴다(``scheduler.pipeline.CountingCaller``·``scheduler.runner``).
- 버전 근거(R3 M12): 시작 모델·캐시 선조회 버전은 error·blocked 행을 보지 않는다 — 그 행은 모델을 모르는
  채(또는 연결 없이) 쓰인 버전일 수 있다.
- 로그에는 input_hash·길이·도구·상태만(``log.py``). payload 원문은 judgment_log.input_json 에만(guard 통과분).
"""

# ruff: noqa: E501  (한국어 docstring·주석)

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Final, Literal, Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.contracts_gen import JudgmentEnvelope
from app.core.protocols import JUDGE_TOOLS, JudgePayload, JudgeTool, JudgeUnavailable
from app.core.redact import redact_text
from app.core.time import now_kst
from app.judge import cache, guard, log
from app.models import JudgmentLog

__all__ = [
    "ADAPTER_CODE_VERSION",
    "CANONICAL_FINGERPRINT",
    "CANONICAL_SAMPLE",
    "TOOL_NAMES",
    "CachedJudgeAdapter",
    "CallMeter",
    "JudgeCaller",
    "Normalized",
    "SessionFactory",
    "Status",
    "ToolResponse",
    "Transport",
    "called_model",
    "make_adapter_version",
    "model_of",
]

ADAPTER_CODE_VERSION: Final = "0.2.0"
"""어댑터 코드 버전. 정규화·payload 규칙이 바뀌면 올린다 → 모든 input_hash가 바뀌어 전체 재판정 1회.

0.2.0 (R3b): R3 의 hash 정준화 변경(``protocols.canonical_value`` — 1 = 1.0 = Decimal('1') 등)과
호재 분류 클래스 추가('호재 아님', D10-6). 정준화 정의가 바뀌면 ``CANONICAL_FINGERPRINT`` 테스트가 깨진다 —
버전을 올리고 지문을 갱신한다."""

CANONICAL_SAMPLE: Final[dict[str, Any]] = {
    "b": [1, 1.0, 2.5, "가", None, True],
    "a": {"z": -0.0, "y": 1e-7, "x": 10**12},
}
"""정준화 지문 표본(정수와 같은 실수·작은 실수·큰 정수·한글·null·bool·키 순서)."""
CANONICAL_FINGERPRINT: Final = "c7cb948ddeaa750287cb53a6c92509b66dd12eed6fb470d1e8a617727d7f0aa3"
"""``sha256(canonical_hash_json(CANONICAL_SAMPLE))`` — ADAPTER_CODE_VERSION 0.2.0 시점의 정준화 정의."""

SERVER_TAG: Final = "jev-mcp"
TOOL_NAMES: Final[dict[JudgeTool, str]] = {t: f"jev_{t}" for t in JUDGE_TOOLS}
"""계약 도구 이름 → JEV MCP 도구 이름 (DECISIONS D6). find·gate·review 는 쓰지 않는다."""

Status = Literal["ok", "review", "escaped", "blocked", "error"]
SessionFactory = Callable[[], Session]
_ERROR_TEXT_MAX = 300
_LOCK_STRIPES = 64


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


def called_model(raw: dict[str, Any]) -> str | None:
    """모델을 실제로 부른 응답의 모델(D18-1). ``provider`` 가 ``none``(로컬 단락)이면 None — 그 응답의 model 은
    고정 모델 근거가 아니다. provider 가 없는 응답(옛 JEV·가짜 서버)은 모델 호출로 본다."""
    if not isinstance(raw, dict):
        return None
    provider = raw.get("provider")
    if isinstance(provider, str) and provider.strip().lower() == "none":
        return None
    return model_of(raw)


class CallMeter:
    """판정기로 보낸 ``tools/call`` 수(D18-2) — 도구별. 스레드 안전. 캐시 적중·guard 차단은 세지 않는다.

    어댑터는 전송 직전에 센다(연결 실패로 끝난 시도도 1 — 보수적). 잡 집계는 잡 시작·끝의 차이로 낸다."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_tool: dict[str, int] = {}

    def add(self, tool: str) -> None:
        with self._lock:
            self._by_tool[tool] = self._by_tool.get(tool, 0) + 1

    def by_tool(self) -> dict[str, int]:
        with self._lock:
            return dict(self._by_tool)

    def total(self) -> int:
        with self._lock:
            return sum(self._by_tool.values())

    @staticmethod
    def delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
        """두 ``by_tool`` 사이의 도구별 증가분(0 은 뺀다)."""
        out = {t: n - before.get(t, 0) for t, n in after.items()}
        return {t: n for t, n in sorted(out.items()) if n > 0}


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
        self._model: str | None = (
            None  # 고정 모델(캐시 키, D18-1) — 처음 알 때만 정하고 어댑터 수명 동안 그대로
        )
        self._observed_model: str | None = None  # 이 실행에서 모델 호출 응답이 마지막으로 알려 준 모델
        self._model_confirmed = False  # 고정 모델을 안다(DB 또는 모델 호출 응답) — 모르면 호출을 하나씩
        self.meter = CallMeter()
        """tools/call 계수기(D18-2). 스케줄러는 잡을 넘어 쌓이는 자기 계수기로 바꿔 끼운다."""
        self._version_lock = threading.Lock()
        self._first_call_lock = threading.Lock()
        self._key_locks = [threading.Lock() for _ in range(_LOCK_STRIPES)]

    # ------------------------------------------------------------------ 버전

    @property
    def adapter_version(self) -> str:
        """캐시 키 버전 = 판정기 서버 버전(처음 한 번 연결) + 고정 모델. 연결 실패면 JudgeUnavailable."""
        with self._version_lock:
            if self._adapter_version is None:
                server = self._transport.server_version()
                self._server_version = server
                if self._model is None:
                    self._model = self._last_model(make_adapter_version(server))
                    self._model_confirmed = self._model is not None
                self._adapter_version = make_adapter_version(server, self._model)
            return self._adapter_version

    @property
    def observed_version(self) -> str | None:
        """이 실행에서 모델 호출 응답이 알려 준 모델의 버전(버전 변경 감지용, D18-1). 아직 없으면 None."""
        with self._version_lock:
            if self._observed_model is None or self._server_version is None:
                return None
            return make_adapter_version(self._server_version, self._observed_model)

    @property
    def model_change_pending(self) -> bool:
        """응답 모델이 고정 모델과 다르다 — 다음 실행(새 어댑터)부터 새 키로 전체 재판정해야 한다."""
        with self._version_lock:
            return (
                self._model is not None
                and self._observed_model is not None
                and self._observed_model != self._model
            )

    def _last_model(self, prefix: str) -> str | None:
        """같은 코드·서버 버전으로 기록된 마지막 '모델 호출' 응답(provider ≠ none)의 model(재시작해도 같은 hash).
        error·blocked 행은 근거로 쓰지 않는다(R3 M12). 행의 버전 접미가 아니라 응답의 model 을 본다 — 모델이 바뀐
        실행의 행은 옛 키로 기록되지만 응답에는 새 모델이 있다(D18-1: 다음 실행부터 새 키)."""
        stmt = (
            select(JudgmentLog.adapter_version, JudgmentLog.output_json)
            .where(
                JudgmentLog.adapter_version.startswith(prefix, autoescape=True),
                JudgmentLog.status.not_in(cache.NOT_VERSION_EVIDENCE),
            )
            .order_by(JudgmentLog.seq.desc())
            .execution_options(yield_per=200)
        )
        with self._session_factory() as session:
            for version, output in session.execute(stmt):
                if version != prefix and not version.startswith(prefix + "+"):
                    continue  # 접두만 같은 다른 서버 버전(0.14.1 ↔ 0.14.10)
                model = called_model(output if isinstance(output, dict) else {})
                if model is not None:
                    return model
        return None

    def _known_version(self, session: Session) -> str | None:
        """서버에 묻지 않고 아는 버전: 확인한 버전, 없으면 judgment_log 마지막 정상 행의 버전
        (판정기 다운 시 캐시 재생용)."""
        if self._adapter_version is not None:
            return self._adapter_version
        return cache.last_adapter_version(session, f"{ADAPTER_CODE_VERSION}+{SERVER_TAG}@", final_only=True)

    def _observe_model(self, raw: dict[str, Any]) -> bool:
        """모델 호출 응답의 모델을 기록한다. 고정 모델을 **처음** 알게 됐으면 고정하고 True(키에 접미가 붙는다).
        이미 고정돼 있으면 다른 모델이어도 키를 바꾸지 않는다(D18-1 — ``model_change_pending``).
        provider none 응답은 아무것도 바꾸지 않는다."""
        model = called_model(raw)
        with self._version_lock:
            if model is None or self._server_version is None:
                return False
            self._observed_model = model
            if self._model is not None:
                return False
            self._model = model
            self._model_confirmed = True
            self._adapter_version = make_adapter_version(self._server_version, model)
            return True

    def _adopt_first_model(self, session: Session, bare: str, version: str) -> int:
        """고정 모델을 처음 알게 됐다 → 접미 없는 ``bare`` 버전으로 기록한 정상 행(ok·review·escaped)을 새 버전의
        hash 로 옮긴다(같은 입력이 이 실행·다음 실행에서 다시 판정기로 가지 않게). 옮긴 행 수. commit 은 호출자.

        blocked 행은 input_json 이 가려져 있어 옮기지 않는다(다시 와도 guard 가 판정기 없이 막는다). 옮길 hash 에
        이미 행이 있으면 그대로 둔다."""
        rows = list(
            session.scalars(
                select(JudgmentLog).where(
                    JudgmentLog.adapter_version == bare,
                    JudgmentLog.status.not_in(cache.NOT_VERSION_EVIDENCE),
                )
            )
        )
        moved = 0
        for row in rows:
            key = cache.compute_hash(row.tool, row.purpose, row.input_json, version)  # type: ignore[arg-type]
            if cache.find(session, key) is not None:
                continue
            row.input_hash = key
            row.adapter_version = version
            moved += 1
        session.flush()
        return moved

    @contextmanager
    def _call_slot(self, key: str) -> Iterator[None]:
        """실제 호출 구간 잠금: 같은 hash 는 한 번에 하나, 모델 확정 전에는 모든 호출을 하나씩(경합 시 실제
        호출
        2회 방지, R3 minor 11). 잠금을 얻은 뒤 호출자는 버전·캐시를 다시 본다."""
        with self._key_locks[hash(key) % _LOCK_STRIPES]:
            if self._model_confirmed:
                yield
                return
            with self._first_call_lock:
                yield

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
        length = cache.payload_length(payload)

        with self._session_factory() as session:
            # 1) 버전: 프로세스당 한 번만 서버에 묻는다(그 뒤는 메모리 — 캐시 조회에 왕복 없음).
            #    서버 버전이 바뀌면 hash 가 바뀌어야 하므로(D6) 연결되는 동안은 확인한 버전을 쓴다.
            try:
                version = self.adapter_version
            except JudgeUnavailable as exc:
                # 2) 판정기가 죽어 있다 → judgment_log 의 마지막 정상 버전으로 캐시를 재생한다(R3 minor 11)
                known = self._known_version(session)
                fallback = known or make_adapter_version("unknown")
                key = cache.compute_hash(tool, purpose, payload, fallback)
                existing = cache.find(session, key)
                if existing is not None and cache.is_final(existing):
                    return self._replay(existing)
                if not checked.ok:  # 보내지 않을 payload — 판정기 연결과 무관하게 blocked
                    return self._blocked(session, existing, checked, tool, purpose, key, length, fallback,
                                         snapshot_id, complex_id)  # fmt: skip
                self._record_error(session, existing, tool, purpose, key, length, payload, fallback,
                                   snapshot_id, complex_id, f"unavailable: {exc}", None)  # fmt: skip
                raise
            key = cache.compute_hash(tool, purpose, payload, version)
            hit = self._cached(session, key)
            if hit is not None:
                return hit
            if not checked.ok:
                return self._blocked(session, cache.find(session, key), checked, tool, purpose, key, length,
                                     version, snapshot_id, complex_id)  # fmt: skip

            with self._call_slot(key):
                # 기다리는 동안 다른 호출이 모델을 확정했거나 같은 입력을 기록했을 수 있다
                version = self.adapter_version
                key = cache.compute_hash(tool, purpose, payload, version)
                session.rollback()  # 읽기 트랜잭션을 끝내 다른 호출이 방금 쓴 행을 본다(아직 쓴 것 없음)
                existing = cache.find(session, key)
                if existing is not None and cache.is_final(existing):
                    return self._replay(existing)
                return self._invoke(session, existing, tool, payload, purpose, key, length, version,
                                    snapshot_id, complex_id)  # fmt: skip

    def _invoke(
        self,
        session: Session,
        existing: Any,
        tool: JudgeTool,
        payload: JudgePayload,
        purpose: str,
        key: str,
        length: int,
        version: str,
        snapshot_id: int | None,
        complex_id: int | None,
    ) -> JudgmentEnvelope:
        self.meter.add(tool)  # D18-2: 판정기로 보내는 tools/call 1건(실패로 끝나도 센다)
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
            # 고정 모델을 처음 알았다(빈 DB) → 이 응답과 이번 버전의 앞선 행을 새 버전의 hash 로 기록한다.
            # 앞선 행은 접미 없는 버전이었다 — 같은 입력이면 그 hash 로 이미 찾았으므로 여기서 replay 할 일이 없다.
            bare = version
            version = self.adapter_version
            key = cache.compute_hash(tool, purpose, payload, version)
            self._adopt_first_model(session, bare, version)
            renewed = cache.find(session, key)
            if renewed is not None and cache.is_final(renewed):  # pragma: no cover - 방어(모델 확정 전 잠금)
                return self._commit(session, renewed, result=self._result_of(renewed), key=key)
            # 새 hash 에 행이 없으면 옛 hash 의 error 행(있으면)을 새 hash 로 옮겨 갱신한다
            existing = renewed if renewed is not None else existing

        if existing is None:
            existing = self._bare_error_row(session, tool, purpose, payload, version)
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
            result_json=normalized.result,
        )
        return self._commit(session, row, result=normalized.result, key=key)

    def _bare_error_row(
        self, session: Session, tool: JudgeTool, purpose: str, payload: JudgePayload, version: str
    ) -> Any:
        """W12a: 모델을 모를 때(접미 없는 버전) 같은 입력으로 남긴 error 행. 이번 정상 응답이 그 행을 대신한다
        (새 hash 로 옮겨 갱신) — 판정기 첫 사용 중 다운된 흔적이 복구 뒤 error 로 남지 않게."""
        if self._server_version is None:
            return None
        bare = make_adapter_version(self._server_version)
        if bare == version:
            return None
        row = cache.find(session, cache.compute_hash(tool, purpose, payload, bare))
        return row if row is not None and row.status == "error" else None

    def _cached(self, session: Session, key: str) -> JudgmentEnvelope | None:
        existing = cache.find(session, key)
        if existing is not None and cache.is_final(existing):
            return self._replay(existing)
        return None

    def _replay(self, row: Any) -> JudgmentEnvelope:
        env = cache.envelope_from_row(row, cached=True, result=self._result_of(row))
        log.log_call(env, cached=True)
        return env

    def _blocked(
        self,
        session: Session,
        existing: Any,
        checked: guard.GuardResult,
        tool: JudgeTool,
        purpose: str,
        key: str,
        length: int,
        version: str,
        snapshot_id: int | None,
        complex_id: int | None,
    ) -> JudgmentEnvelope:
        if existing is not None and cache.is_final(existing):
            return self._replay(existing)
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

    # ------------------------------------------------------------------ 내부

    def _result_of(self, row: Any) -> dict[str, Any]:
        """캐시 행의 정규화 결과: result_json(계약 2026-10-09.3), 옛 행(NULL)은 원응답을 다시 정규화."""
        if row.status in {"blocked", "error"}:
            return {}
        stored = getattr(row, "result_json", None)
        if isinstance(stored, dict) and stored:
            return dict(stored)
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

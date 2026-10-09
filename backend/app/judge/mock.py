"""MockAdapter — 픽스처 재생 (contracts/fixtures/README.md 'MockAdapter 규칙').

- ``adapter_version`` = ``<fixture>/judgments/_meta.json`` 의 값(녹화와 해시를 맞춘다).
- 호출마다 ``input_hash(tool, purpose, payload, adapter_version)`` → ``judgments/<tool>/<hex>.json`` 을 찾아
  그 봉투를 ``cached=True`` 로 돌려준다(봉투 동일).
- 없으면 ``status='review'`` 봉투(result={}, raw={"reason": "no recording"}, confidence=None)
  — 테스트가 조용히 통과하지 않게. 예외를 던지지 않는다.
- ``unavailable=True`` 면 모든 호출이 ``JudgeUnavailable`` (판정기 다운 시뮬레이션, T18).
- guard 는 mock 에서도 적용한다(blocked 봉투).
- ``session_factory`` 가 있으면(``get_adapter`` 는 설정 DB 를 넘긴다) 재생한 녹화 봉투를
  judgment_log 에 1행 남기고(같은 hash 행이 있으면 그 행) 그 행의 ``judgment_seq`` 를 단다 — 판정
  확률 Fact 의 출처 ``jl_<seq>`` 가 실제 어댑터와 같은 출처표를 가리킨다(R3 마무리: 없으면 mock
  재판정의 사다리 확률이 전부 '확인 불가(출처 누락)' → 종합 미계산). 녹화가 없는 review 봉투·
  blocked 봉투는 기록하지 않는다. session_factory 가 없으면 DB 에 쓰지 않는다.
- ``write_recording`` 은 녹화 파일을 만든다(WP9 픽스처·R4 녹화용).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.contracts_gen import JudgmentEnvelope
from app.core.protocols import JudgePayload, JudgeTool, JudgeUnavailable
from app.core.time import now_kst
from app.judge import cache, guard, log

__all__ = ["MockAdapter", "load_meta_version", "log_replay", "recording_path", "write_recording"]


def load_meta_version(fixture_dir: Path) -> str:
    meta = json.loads((fixture_dir / "judgments" / "_meta.json").read_text(encoding="utf-8"))
    version = meta.get("adapter_version")
    if not isinstance(version, str) or not version:
        raise ValueError(f"{fixture_dir}/judgments/_meta.json 에 adapter_version 이 없다")
    return version


def recording_path(fixture_dir: Path, tool: str, input_hash: str) -> Path:
    hex_ = input_hash.removeprefix("sha256:")
    if len(hex_) != 64 or any(c not in "0123456789abcdef" for c in hex_):
        raise ValueError(f"input_hash 형식 오류: {input_hash!r}")
    return fixture_dir / "judgments" / tool / f"{hex_}.json"


def write_recording(fixture_dir: Path, envelope: JudgmentEnvelope) -> Path:
    path = recording_path(fixture_dir, envelope.tool, envelope.input_hash)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(envelope.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def log_replay(
    session_factory: Callable[[], Session],
    envelope: JudgmentEnvelope,
    payload: JudgePayload,
    *,
    snapshot_id: int | None,
    complex_id: int | None,
) -> JudgmentEnvelope:
    """녹화 봉투 → judgment_log 행(같은 input_hash 의 최종 행이 있으면 그 행).

    그 행의 봉투(judgment_seq 포함)를 돌려준다. 값(status·result·raw·confidence·created_at·
    adapter_version)은 녹화 그대로 — 판정하지 않는다. cached 는 넘겨받은 값.
    """
    with session_factory() as session:
        row = cache.find(session, envelope.input_hash)
        if row is None or not cache.is_final(row):
            row = log.record(
                session,
                existing=row,
                tool=envelope.tool,
                purpose=envelope.purpose,
                input_hash=envelope.input_hash,
                input_len=envelope.input_len or cache.payload_length(payload),
                input_json=dict(payload),
                output_json=dict(envelope.raw or {}),
                status=envelope.status,
                confidence=envelope.confidence,
                duration_ms=envelope.duration_ms,
                adapter_version=envelope.adapter_version or "",
                snapshot_id=snapshot_id,
                complex_id=complex_id,
                error_text=envelope.error_text,
                created_at=envelope.created_at,
                result_json=dict(envelope.result or {}),
            )
            try:
                session.commit()
            except IntegrityError:  # 다른 worker 가 같은 hash 를 먼저 남겼다 — 그 행이 정답
                session.rollback()
                row = cache.find(session, envelope.input_hash)
                if row is None:
                    raise
        result = dict(row.result_json or {}) or dict(envelope.result or {})
        return cache.envelope_from_row(row, cached=envelope.cached, result=result)


class MockAdapter:
    """JudgeAdapter 픽스처 재생 구현."""

    def __init__(
        self,
        fixture_dir: Path,
        *,
        unavailable: bool = False,
        secrets: Sequence[str] | None = None,
        session_factory: Callable[[], Session] | None = None,
    ) -> None:
        self._dir = Path(fixture_dir)
        self._session_factory = session_factory
        self._version = load_meta_version(self._dir)
        self.unavailable = unavailable
        self._secrets = list(secrets) if secrets is not None else guard.default_secrets()

    @property
    def adapter_version(self) -> str:
        return self._version

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

    def call(
        self,
        tool: JudgeTool,
        payload: JudgePayload,
        purpose: str,
        *,
        snapshot_id: int | None = None,
        complex_id: int | None = None,
    ) -> JudgmentEnvelope:
        if self.unavailable:
            raise JudgeUnavailable("mock: 판정기 다운 시뮬레이션")
        key = cache.compute_hash(tool, purpose, payload, self._version)
        length = cache.payload_length(payload)
        checked = guard.check_payload(payload, secrets=self._secrets)
        if not checked.ok:
            return self._synthetic(tool, purpose, key, length, "blocked", {"reason": "guard",
                                   "findings": checked.summary()}, snapshot_id, complex_id,
                                   f"guard: {', '.join(checked.kinds())}")  # fmt: skip
        path = recording_path(self._dir, tool, key)
        if path.is_file():
            env = JudgmentEnvelope.model_validate_json(path.read_text(encoding="utf-8"))
            env = env.model_copy(update={"cached": True})
            if self._session_factory is not None:
                env = log_replay(
                    self._session_factory, env, payload, snapshot_id=snapshot_id, complex_id=complex_id
                )
            return env
        return self._synthetic(
            tool, purpose, key, length, "review", {"reason": "no recording"}, snapshot_id, complex_id, None
        )

    def _synthetic(
        self,
        tool: JudgeTool,
        purpose: str,
        key: str,
        length: int,
        status: str,
        raw: dict[str, object],
        snapshot_id: int | None,
        complex_id: int | None,
        error_text: str | None,
    ) -> JudgmentEnvelope:
        return JudgmentEnvelope(
            tool=tool,
            purpose=purpose,
            input_hash=key,
            input_len=length,
            status=status,
            confidence=None,
            cached=False,
            result={},
            raw=raw,
            duration_ms=0,
            judgment_seq=None,
            created_at=now_kst().isoformat(timespec="seconds"),
            adapter_version=self._version,
            snapshot_id=snapshot_id,
            complex_id=complex_id,
            error_text=error_text,
        )

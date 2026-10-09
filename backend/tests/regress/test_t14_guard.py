"""T14 보안 guard (RA §9) — 시스템 경계: 운영 설정(환경변수 → Settings → guard.default_secrets) + 운영 어댑터 경로.

RA §9 기대 결과(원문 그대로): "호출 거부, `judgment_log`에 status=blocked 행, 로그에 원문 없음"
(케이스: payload에 전화번호·이메일·환경변수 값 삽입). 픽스처 ``raw/guard/t14_payloads.json``(전화·이메일·주민번호·환경변수 값).

- JEV 경로: ``JevMcpAdapter``(FakeJev 전송, secrets 기본값 = 운영 설정) → FakeJev 실제 호출 0, judgment_log blocked 행,
  input_json·output_json·error_text·API(/ops/judgments)·로그 어디에도 원문 없음(input_hash·길이만).
- mock 경로: ``app.judge.get_adapter``(JUDGE_ADAPTER=mock, 녹화 재생)도 같은 guard → blocked 봉투.
- 판정기 자격 증명 환경변수(OPENROUTER_API_KEY 등) 값도 같은 규칙(RA §10 보안 규칙 1).
"""

# ruff: noqa: E501

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
from sqlalchemy import select

from .conftest import FIXTURE, RegressEnv, api_get, load_json, make_settings

pytestmark = pytest.mark.regress

CASES = load_json(FIXTURE / "raw" / "guard" / "t14_payloads.json")
JUDGE_CRED = ("OPENROUTER_API_KEY", "fx-t14-openrouter-not-real-91c2")


def _raw_values() -> list[str]:
    """payload 에 심은 원문(검사 대상): 전화·이메일·주민번호·환경변수 값."""
    return [
        "010-1234-5678",
        "test.user@example.com",
        "900101-1234567",
        CASES["env"]["DATA_GO_KR_KEY"],
        JUDGE_CRED[1],
    ]


@pytest.fixture
def prod_settings(env: RegressEnv, monkeypatch: pytest.MonkeyPatch) -> Any:
    """비밀값이 환경변수에만 있는 운영 설정(RA §10): DATA_GO_KR_KEY + 판정기 자격 증명 환경변수."""
    from app.core.settings import set_settings

    for name, value in CASES["env"].items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv(*JUDGE_CRED)
    db = env.tmp / "regress.db"
    s = make_settings(db, env.settings.raw_dir, env.tmp / "reports")
    assert (
        s.data_go_kr_key is not None and s.data_go_kr_key.get_secret_value() == CASES["env"]["DATA_GO_KR_KEY"]
    )
    set_settings(s)
    return s


def _cases() -> list[dict[str, Any]]:
    extra = {
        "kind": "judge_credential_env",
        "tool": "screen",
        "purpose": "screen:t14:judge-cred",
        "payload": {"text": f"토큰 {JUDGE_CRED[1]}"},
        "expect_status": "blocked",
    }
    return [*CASES["cases"], extra]


def _assert_no_raw(blob: str, where: str) -> None:
    for v in _raw_values():
        assert v not in blob, f"{where} 에 원문 {v!r}"


def test_t14_jev_adapter_blocks_and_logs_without_raw(
    env: RegressEnv, prod_settings: Any, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.core.logging import configure_logging
    from app.judge.guard import default_secrets
    from app.judge.jev_mcp import JevMcpAdapter
    from app.models import JudgmentLog

    secrets = default_secrets()  # 운영 기본값(설정 비밀값 + 판정기 자격 증명 환경변수 값)
    assert CASES["env"]["DATA_GO_KR_KEY"] in secrets and JUDGE_CRED[1] in secrets
    configure_logging(prod_settings)  # 운영 로그 핸들러(JSON/텍스트) — stderr 출력도 본다
    caplog.set_level(logging.DEBUG)
    with env.session() as s:
        seq0 = max(s.scalars(select(JudgmentLog.seq)))

    adapter = JevMcpAdapter(transport=env.jev, session_factory=env.factory)  # secrets 기본값 = 운영 경로
    envs = []
    for c in _cases():
        e = adapter.call(c["tool"], c["payload"], c["purpose"], snapshot_id=12)
        assert e.status == c["expect_status"] == "blocked", (c["kind"], e.status)
        assert e.result == {} and e.cached is False
        envs.append((c, e))
    assert env.jev.calls == []  # 호출 거부: 판정기로 나간 요청 0

    # 같은 payload 재시도 → 같은 blocked 행(캐시), 여전히 호출 0
    again = adapter.call(_cases()[0]["tool"], _cases()[0]["payload"], _cases()[0]["purpose"], snapshot_id=12)
    assert again.status == "blocked" and again.cached is True and env.jev.calls == []

    with env.session() as s:
        rows = list(s.scalars(select(JudgmentLog).where(JudgmentLog.seq > seq0).order_by(JudgmentLog.seq)))
    assert [r.status for r in rows] == ["blocked"] * len(_cases())
    assert [r.tool for r in rows] == [c["tool"] for c in _cases()]
    for (c, e), r in zip(envs, rows, strict=True):
        assert e.judgment_seq == r.seq and r.input_hash == e.input_hash
        assert r.input_json.get("blocked") is True and r.input_json.get("findings"), r.input_json
        assert (r.error_text or "").startswith("guard:"), r.error_text
        dump = json.dumps(
            {
                "in": r.input_json,
                "out": r.output_json,
                "res": r.result_json,
                "err": r.error_text,
                "purpose": r.purpose,
            },
            ensure_ascii=False,
        )
        _assert_no_raw(dump, f"judgment_log #{r.seq}({c['kind']})")

    # API(G8 판정 운영): blocked 집계, 응답에 원문 없음
    body = api_get(env, "/ops/judgments", since="2000-01-01", size=1000)
    assert body["stats"]["blocked"] >= len(_cases())
    _assert_no_raw(json.dumps(body, ensure_ascii=False), "GET /api/ops/judgments")

    # 로그: 원문 없음(레코드 원본·포맷 결과·stderr 모두), input_hash·길이는 있음
    judge_recs = [r for r in caplog.records if r.name == "app.judge"]
    assert len(judge_recs) >= len(_cases())
    for r in judge_recs:
        assert {"input_hash", "payload_length"} <= set(r.__dict__), r.__dict__
    blob = "\n".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    _assert_no_raw(blob, "로그 레코드")
    _assert_no_raw(caplog.text, "로그 출력")
    out, err = capsys.readouterr()
    _assert_no_raw(out + err, "stdout/stderr")


def test_t14_mock_adapter_from_settings_blocks(
    env: RegressEnv, prod_settings: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """JUDGE_ADAPTER=mock(get_adapter) 경로도 같은 guard: blocked 봉투, 원문 없음."""
    from app.judge import get_adapter

    caplog.set_level(logging.DEBUG)
    adapter = get_adapter(prod_settings, fixture_dir=FIXTURE)
    for c in _cases():
        e = adapter.call(c["tool"], c["payload"], c["purpose"])
        assert e.status == "blocked", (c["kind"], e.status)
        assert (e.error_text or "").startswith("guard:")
        _assert_no_raw(e.model_dump_json(), f"mock 봉투({c['kind']})")
    _assert_no_raw("\n".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records), "로그 레코드")


def test_t14_clean_payload_passes_guard(env: RegressEnv, prod_settings: Any) -> None:
    """대조군: 같은 경로에서 민감값이 없는 payload 는 판정기로 나간다(guard 가 모든 호출을 막는 것이 아님)."""
    from app.judge.jev_mcp import JevMcpAdapter

    adapter = JevMcpAdapter(transport=env.jev, session_factory=env.factory)
    e = adapter.call(
        "screen",
        {"text": "엘리프 검단 포레듀 선착순 문의는 대표번호로", "purpose": "t14"},
        "screen:t14:clean",
    )
    assert e.status == "ok" and [t for t, _ in env.jev.calls] == ["jev_screen"]

"""T6 verify 복합 주장 contradicted(0.35) (RA §9) — 시스템 경계: rejudge 잡(worker) → P9 verify → FakeJev 실제 호출·claim 행.

RA §9 기대 결과(원문 그대로): "`ClaimSplitter` → 주장 ≥2개, 각각 verify 입력; 복합 문장 그대로 verify에 보내면 테스트 실패"
(케이스: "3개는 unlikely이고 나머지는 uncertain"). 픽스처 ``raw/claims/t6_composite.json``(+ 녹화 #131).

- 픽스처 복합 문장 2개 → 파이프라인이 쓰는 공개 분할기(``RuleClaimSplitter``) → 주장 ≥2, 각각 원자.
- P9 공개 진입(``pipeline.p9_verify``, 운영 어댑터 경로) → 판정기로 나간 verify 의 claims = 원자 주장 목록(복합 문장 0).
- 분할하지 않는 splitter 로 복합 문장을 그대로 넣으면 payload 단계에서 거부(``CompoundClaimError``) — 판정기 호출 0.
- worker: rejudge 잡 → 나간 모든 jev_verify 의 claims 가 원자이고, claim 행 1개 = verify 입력 1개.
"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from .conftest import FIXTURE, SNAP, WRITE, RegressEnv, api_get, cur, load_json

pytestmark = pytest.mark.regress

T6 = load_json(FIXTURE / "raw" / "claims" / "t6_composite.json")
EVIDENCE = [
    (
        "e1",
        "jev_noul #118~123 판정 label: 고촌센트럴자이 +10% unlikely, +20% unlikely, 롯데캐슬 +20% unlikely, 그 밖의 명제 uncertain",
    )
]


def _verify_calls(env: RegressEnv) -> list[dict[str, Any]]:
    return [a for t, a in env.jev.calls if t == "jev_verify"]


def test_t06_fixture_composites_split_to_atomic_claims() -> None:
    from app.judge.claims import RuleClaimSplitter, is_atomic

    need = T6["expected_min_atomic_claims"]
    for c in T6["claims"]:
        assert not is_atomic(c["text"]), c["text"]
        parts = RuleClaimSplitter().split(c["text"], section=c["section"], snapshot_id=c["snapshot_id"])
        texts = [p.text for p in parts]
        assert len(parts) >= need, texts
        assert all(is_atomic(t) for t in texts), texts
        assert c["text"] not in texts
        assert [p.ordinal for p in parts] == list(range(len(parts)))
    assert [p.text for p in RuleClaimSplitter().split("3개는 unlikely이고 나머지는 uncertain")] == [
        "3개는 unlikely",
        "나머지는 uncertain",
    ]


def test_t06_p9_verify_sends_each_atomic_claim_never_the_composite(env: RegressEnv) -> None:
    from app.judge import pipeline as jp
    from app.judge.claims import RuleClaimSplitter, is_atomic
    from app.judge.jev_mcp import JevMcpAdapter
    from app.models import JudgmentLog

    adapter = JevMcpAdapter(transport=env.jev, session_factory=env.factory, secrets=[])
    for c in T6["claims"]:
        env.jev.calls.clear()
        out = jp.p9_verify(adapter, section="t6", text=c["text"], evidence=EVIDENCE, snapshot_id=SNAP)
        calls = _verify_calls(env)
        assert len(calls) == 1
        sent = calls[0]["claims"]
        want = [p.text for p in RuleClaimSplitter().split(c["text"])]
        assert sent == want and len(sent) >= 2, sent  # 주장 ≥2, 각각 verify 입력
        assert c["text"] not in sent and all(is_atomic(t) for t in sent)
        assert [o.text for o in out] == want and all(o.judgment_seq is not None for o in out)
        with env.session() as s:
            row = s.get(JudgmentLog, out[0].judgment_seq)
            assert row is not None and row.tool == "verify" and row.input_json["claims"] == want


def test_t06_composite_sent_as_is_is_refused(env: RegressEnv) -> None:
    """복합 문장 그대로(분할 안 하는 splitter) → verify payload 거부, 판정기 호출 0."""
    from app.core.contracts_gen import Claim
    from app.judge import pipeline as jp
    from app.judge.claims import CompoundClaimError
    from app.judge.jev_mcp import JevMcpAdapter
    from app.judge.payloads import verify_payload

    class NoSplit:
        def split(
            self,
            text: str,
            *,
            section: str = "",
            snapshot_id: int | None = None,
            complex_id: int | None = None,
        ) -> list[Claim]:
            return [
                Claim(
                    snapshot_id=snapshot_id,
                    section=section,
                    complex_id=complex_id,
                    text=text,
                    evidence_text=None,
                    verify_status=None,
                    judgment_seq=None,
                    parent_claim_id=None,
                    ordinal=0,
                )
            ]

    adapter = JevMcpAdapter(transport=env.jev, session_factory=env.factory, secrets=[])
    for c in T6["claims"]:
        with pytest.raises(CompoundClaimError):
            verify_payload([c["text"]], EVIDENCE)
        with pytest.raises(CompoundClaimError):
            jp.p9_verify(
                adapter, section="t6", text=c["text"], evidence=EVIDENCE, snapshot_id=SNAP, splitter=NoSplit()
            )
    assert _verify_calls(env) == []


def test_t06_rejudge_job_verify_inputs_are_atomic(env: RegressEnv) -> None:
    from app.judge.claims import is_atomic
    from app.judge.jev_mcp import JevMcpAdapter
    from app.models import Claim, JudgmentLog

    # 정상 운영 상태(판정기 버전 기록됨) — D6 버전 변경 전체 재판정과 분리
    JevMcpAdapter(transport=env.jev, session_factory=env.factory, secrets=[]).call(
        "screen", {"text": "warm", "purpose": "warm"}, "screen:regress:t06-warm"
    )
    env.jev.calls.clear()

    r = env.client.post(
        "/api/jobs",
        headers=WRITE,
        json={
            "job_name": "rejudge",
            "payload": {"snapshot_id": SNAP, "scenario_id": None, "complex_ids": [1, 2], "reason": "T6 회귀"},
        },
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]
    env.worker(env.ctx("fake"))
    job = api_get(env, f"/jobs/{job_id}")
    assert job["status"] == "done", job
    st = job["stats"]
    # 복합 문장으로 건너뛴 verify 없음
    assert not any(k.startswith("verify:") for k in st["skipped"]), st["skipped"]

    calls = _verify_calls(env)
    assert calls, f"P9 verify 호출 없음: {st}"
    sent = [t for a in calls for t in a["claims"]]
    assert all(is_atomic(t) for t in sent), [t for t in sent if not is_atomic(t)]
    assert any(len(a["claims"]) >= 2 for a in calls), [a["claims"] for a in calls]  # 여러 사실 → 주장 여러 개
    with env.session() as s:
        seqs = sorted(
            {
                r.seq
                for r in s.scalars(
                    select(JudgmentLog).where(
                        JudgmentLog.tool == "verify",
                        JudgmentLog.snapshot_id == cur(env),
                        JudgmentLog.complex_id.in_([1, 2]),
                    )
                )
            }
        )
        rows = list(
            s.scalars(select(Claim).where(Claim.snapshot_id == cur(env), Claim.judgment_seq.in_(seqs)))
        )
        assert rows and len(rows) == len(sent), (len(rows), len(sent))
        for row in rows:
            jl = s.get(JudgmentLog, row.judgment_seq)
            assert jl is not None and row.text in jl.input_json["claims"]  # claim 행 1개 = verify 입력 1개
            assert is_atomic(row.text) and row.verify_status == "verified"

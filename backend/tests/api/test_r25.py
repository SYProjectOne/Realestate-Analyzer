"""계약 2026-10-09.3 WP5: 미리보기 cache_hits = 같은 payload hash 의 judgment_log 행 존재,
judge_scope = 저장 값, 판정 봉투 result = judgment_log.result_json."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_session
from app.models import JudgmentLog, Scenario, ScoreRun, ScoreTotal
from app.scheduler.payloads import cache_status, scenario_payloads
from app.scheduler.pipeline import load_scenarios

from ._support import WRITE, validate

SNAP = 12


def _preview(client: TestClient, scenario_id: int) -> dict[str, object]:
    r = client.get(f"/api/scenarios/{scenario_id}/preview", params={"snapshot": SNAP}, headers=WRITE)
    assert r.status_code == 200, r.text
    body = r.json()
    validate("previewScenario", 200, body)
    return body


def test_preview_cache_hits_follow_payload_hashes(client: TestClient) -> None:
    with get_session() as s:
        sc_id = s.scalars(select(Scenario.id).where(Scenario.code == "B")).one()
        (dto,) = load_scenarios(s, sc_id)
        plan = scenario_payloads(s, SNAP, dto)
        want = cache_status(s, plan)
    body = _preview(client, sc_id)
    assert (body["cache_hits"], body["cache_misses"], body["calls_by_tool"]) == (
        want.hits,
        want.misses,
        want.calls_by_tool,
    )
    assert body["cache_hits"] + body["cache_misses"] == len(plan.calls)
    # 미스였던 noul 호출 1건의 hash 로 최종 행을 넣으면 정확히 히트 1 증가(같은 payload hash = 재호출 없음)
    missing = next(
        c
        for c in plan.calls
        if c.tool == "noul" and c.payload is not None and plan.adapter_version is not None
        and _row(c.input_hash(plan.adapter_version)) is None
    )  # fmt: skip
    assert plan.adapter_version is not None and missing.payload is not None
    key = missing.input_hash(plan.adapter_version)
    with get_session() as s:
        s.add(
            JudgmentLog(
                snapshot_id=SNAP, tool="noul", purpose=missing.purpose, complex_id=missing.complex_id,
                input_hash=key, input_len=1, input_json=dict(missing.payload),
                output_json={}, result_json={}, status="ok", created_at="2026-10-09T00:00:00+09:00",
                adapter_version=plan.adapter_version,
            )
        )  # fmt: skip
        s.commit()
    after = _preview(client, sc_id)
    assert after["cache_hits"] == body["cache_hits"] + 1  # type: ignore[operator]
    assert after["cache_misses"] == body["cache_misses"] - 1  # type: ignore[operator]
    # error 행은 최종이 아니다 → 히트가 아니다
    with get_session() as s:
        row = s.scalars(select(JudgmentLog).where(JudgmentLog.purpose == missing.purpose)).one()
        row.status = "error"
        s.commit()
    assert _preview(client, sc_id)["cache_hits"] == body["cache_hits"]


def _row(key: str | None) -> JudgmentLog | None:
    if key is None:
        return None
    with get_session() as s:
        return s.scalars(select(JudgmentLog).where(JudgmentLog.input_hash == key)).one_or_none()


def test_judge_scope_is_the_stored_value(client: TestClient) -> None:
    with get_session() as s:
        runs = [r for r in s.scalars(select(ScoreRun.id).where(ScoreRun.snapshot_id == SNAP))]
        totals = list(s.scalars(select(ScoreTotal).where(ScoreTotal.score_run_id.in_(runs))))
        assert totals and all(t.judge_scope for t in totals)  # devseed 도 저장한다
        target = next(t.complex_id for t in totals if t.judge_scope == "판정 대상")
        for t in totals:
            if t.complex_id == target:
                t.judge_scope = "참고"
        s.commit()
    body = client.get(f"/api/snapshots/{SNAP}/complexes", params={"size": 100}, headers=WRITE).json()
    scope = {it["complex_id"]: it["judge_scope"] for it in body["items"]}
    # 기대값 갱신(R3 마무리): R3 C2 이후 API 는 저장 값이 아니라 공용 함수(analysis.scope.judge_scope)로 현재 사실에서
    # 계산한다. 예전에는 첫 '판정 대상' 저장 행이 그란테르(1)였고 픽스처 접수 '불가'라 계산 값도 우연히 '참고'였다 —
    # W1(접수 '미정') 뒤로는 계산 값 = '판정 대상'. 저장 값을 바꿔도 화면 범위는 바뀌지 않는다(사다리로도 추정하지 않음).
    assert target == 1
    assert scope[target] == "판정 대상"


def test_envelope_result_reads_result_json(client: TestClient) -> None:
    with get_session() as s:
        row = s.scalars(
            select(JudgmentLog).where(JudgmentLog.tool == "decide").order_by(JudgmentLog.seq)
        ).first()
        assert row is not None and row.result_json  # devseed: 정규화 결과 = result_json
        assert "_result" not in (row.output_json or {})
        row.result_json = {**row.result_json, "warnings": ["result_json 에서 읽음"]}
        seq = row.seq
        s.commit()
    body = client.get("/api/ops/judgments", params={"tool": "decide", "size": 200}, headers=WRITE).json()
    env = next(e for e in body["items"] if e["judgment_seq"] == seq)
    assert env["result"]["warnings"] == ["result_json 에서 읽음"]

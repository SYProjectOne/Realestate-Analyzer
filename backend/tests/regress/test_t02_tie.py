"""T2 상황 B 동률 (RA §9) — 시스템 경계: devseed 적재(녹화 decide #127) → API(G4 비교·G2 리스트), 그리고
worker 재판정(FakeJev decide confidence < 0.6) → decision 행·API.

RA §9 T2 기대 결과(그대로): "`tie=true`, 두 단지 모두 chosen 표시, C7에 TieBadge"
픽스처: decide 봉투(#127) 칸타빌 0.54, 엘리프 0.42, confidence 0.48.
규칙(RA §6-4): decide `confidence < 0.6`이면 상위 2개를 `tie=true`로 표시하고 1순위를 하나로 말하지 않는다.
C7 TieBadge 는 프런트(WP6) — 여기서는 그것을 그리는 API 데이터(decisions·decision 배지)를 본다.
"""

# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from .conftest import FIXTURE, SNAP, WRITE, FakeJev, RegressEnv, api_get, by_key, load_json

pytestmark = pytest.mark.regress

TIE_CONFIDENCE = 0.6


def _t2() -> dict[str, Any]:
    t2: dict[str, Any] = load_json(FIXTURE / "expected_scores.json")["t2"]
    return t2


def _scenario_id(env: RegressEnv, code: str) -> int:
    rows = api_get(env, "/scenarios")
    return next(int(s["id"]) for s in rows if s.get("code") == code)


def test_t02_fixture_envelope_127_is_tie_case() -> None:
    """녹화 #127 이 T2 입력(칸타빌 0.54·엘리프 0.42·conf 0.48)인지 — 아래 API 검사의 전제."""
    t2 = _t2()
    ids = by_key()
    idx = load_json(FIXTURE / "judgments" / "_index.json")
    row = next(r for r in idx if r["judgment_seq"] == t2["judgment_seq"])
    assert row["tool"] == "decide" and row["purpose"] == f"decide:scenario_{t2['scenario']}"
    env = load_json(FIXTURE / "judgments" / row["file"])
    assert env["confidence"] == t2["confidence"] < TIE_CONFIDENCE
    probs = env["result"]["probs"]
    for key, p in t2["probs"].items():
        assert probs[f"complex:{ids[key]}"] == p


def test_t02_compare_api_decisions_b_tie_both_chosen(env: RegressEnv) -> None:
    """G4 비교 API(scenario=B): decisions.B = #127, tie=true, 칸타빌·엘리프 둘 다 chosen·tie, 다른 후보는 아님."""
    t2 = _t2()
    ids = by_key()
    chosen_ids = [ids[k] for k in t2["expected"]["chosen"]]
    body = api_get(
        env, f"/snapshots/{SNAP}/compare", ids=",".join(str(i) for i in chosen_ids), scenario=t2["scenario"]
    )
    ds = body["decisions"][t2["scenario"]]
    assert ds["judgment_seq"] == t2["judgment_seq"], ds
    assert ds["status"] == "ok"
    assert ds["tie"] is t2["expected"]["tie"] is True
    assert ds["confidence"]["v"] == pytest.approx(t2["confidence"])
    assert ds["confidence"]["label"] == "추정"
    items = {it["complex_id"]: it for it in ds["items"] if it["option_key"] == "complex"}
    for key, p in t2["probs"].items():
        it = items[ids[key]]
        assert it["chosen"] is True and it["tie"] is True, (key, it)
        assert it["prob"]["v"] == pytest.approx(p), (key, it["prob"])
        assert it["confidence"] == pytest.approx(t2["confidence"])
    # 두 단지만 chosen·tie(1순위를 하나로 말하지 않는다 — 그러나 동률은 상위 2개뿐)
    assert sorted(cid for cid, it in items.items() if it["chosen"]) == sorted(chosen_ids)
    assert sorted(cid for cid, it in items.items() if it["tie"]) == sorted(chosen_ids)
    hatches = [it for it in ds["items"] if it["option_key"] != "complex"]
    assert all(not it["chosen"] and not it["tie"] for it in hatches), hatches
    # 비교 행(score_row.decision 배지) — C7 TieBadge 데이터
    rows = {r["complex_id"]: r for r in body["rows"]}
    for cid in chosen_ids:
        badge = rows[cid]["decision"]
        assert badge is not None, cid
        assert badge["tie"] is True and badge["chosen"] is True, (cid, badge)
        assert badge["confidence"] == pytest.approx(t2["confidence"])


def test_t02_dashboard_decision_badges(env: RegressEnv) -> None:
    """G1 대시보드(scenario=B) TOP 5 행의 decision 배지(score_row.decision): 두 단지 tie·chosen, 나머지 tie 아님.

    (G2 리스트 행 ComplexRow 계약에는 decision 이 없다 — 배지는 score_row 를 쓰는 G1·G4 에만.)
    """
    t2 = _t2()
    ids = by_key()
    chosen_ids = {ids[k] for k in t2["expected"]["chosen"]}
    dash = api_get(env, f"/snapshots/{SNAP}/dashboard", scenario=t2["scenario"])
    assert dash["scenario_code"] == t2["scenario"]
    seen: set[int] = set()
    for r in dash["top5"]:
        b = r.get("decision")
        if r["complex_id"] in chosen_ids:
            seen.add(r["complex_id"])
            assert b is not None and b["tie"] and b["chosen"], r
            assert b["confidence"] == pytest.approx(t2["confidence"])
        elif b is not None:
            assert not b["tie"] and not b["chosen"], r
    # 상황 B TOP 5 에 두 단지가 있으면 둘 다 배지가 보여야 한다(없으면 비교 화면 검사로 충분)
    assert seen <= chosen_ids


# ---------------------------------------------------------------- 파이프라인(worker) 경로


@dataclass
class LowConfidenceJev(FakeJev):
    """상황 B decide 만 confidence 0.48(< 0.6) — 확률 상위 2개 0.54·0.42(칸타빌·엘리프가 후보면 그 둘)."""

    def _decide(self, a: dict[str, Any]) -> dict[str, Any]:
        out = super()._decide(a)
        if "B 가점" not in str(a.get("decision", "")):
            return out
        ids = [c["id"] for c in a["candidates"]]
        pref = [i for i in ("complex_7", "complex_2") if i in ids]
        top = (pref + [i for i in ids if i not in pref])[:2]
        probs = {cid: 0.01 for cid in ids}
        probs[top[0]], probs[top[1]] = 0.54, 0.42
        probs.update({"ask_user": 0.02, "investigate": 0.0})
        out["recommendation"] = {
            "selected": top[0],
            "escaped": False,
            "confidence": 0.48,
            "probabilities": probs,
        }
        return out


def test_t02_pipeline_low_confidence_decide_marks_top2_tie(env: RegressEnv) -> None:
    """worker 재판정(상황 B) — FakeJev decide conf 0.48 → 저장된 decision 상위 2개 tie=true·chosen=true, API decisions.B tie."""
    from sqlalchemy import select

    from app.models import Decision, ScoreRun

    env.jev = LowConfidenceJev()
    sc_b = _scenario_id(env, "B")
    r = env.client.post(
        "/api/jobs",
        headers=WRITE,
        json={
            "job_name": "rejudge",
            "payload": {"snapshot_id": SNAP, "scenario_id": sc_b, "complex_ids": None, "reason": "T2 회귀"},
        },
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]
    env.worker(env.ctx("fake"))
    job = api_get(env, f"/jobs/{job_id}")
    assert job["status"] == "done", job
    # 상황 B decide 실제 호출 1회(판정기 버전 변경 → 전체 재판정 1회(D6)가 같은 drain 에서 돌아도 B 는 캐시)
    decides = [
        a
        for t, a in env.jev.calls
        if t.removeprefix("jev_") == "decide" and "B 가점" in str(a.get("decision"))
    ]
    assert len(decides) == 1, [t for t, _ in env.jev.calls]

    with env.session() as s:
        run = s.scalars(
            select(ScoreRun)
            .where(ScoreRun.snapshot_id == SNAP, ScoreRun.scenario_id == sc_b)
            .order_by(ScoreRun.id.desc())
        ).first()
        assert run is not None and run.id > 5, "새 score_run 이 없다"
        rows = list(s.scalars(select(Decision).where(Decision.score_run_id == run.id)))
        assert rows, "decision 행 없음"
        cx = [d for d in rows if d.option_key == "complex"]
        assert all(d.confidence is not None and float(d.confidence) == pytest.approx(0.48) for d in rows)
        top2 = sorted(cx, key=lambda d: -float(d.prob or 0))[:2]
        assert [float(d.prob or 0) for d in top2] == [pytest.approx(0.54), pytest.approx(0.42)]
        top2_ids = sorted(int(d.complex_id or 0) for d in top2)
        assert sorted(int(d.complex_id or 0) for d in cx if d.tie) == top2_ids, [
            (d.complex_id, d.prob, d.tie) for d in cx
        ]
        assert sorted(int(d.complex_id or 0) for d in cx if d.chosen) == top2_ids, [
            (d.complex_id, d.prob, d.chosen) for d in cx
        ]
        assert not any(d.tie or d.chosen for d in rows if d.option_key != "complex")

    body = api_get(env, f"/snapshots/{SNAP}/compare", ids=",".join(str(i) for i in top2_ids), scenario="B")
    ds = body["decisions"]["B"]
    assert ds["score_run_id"] == run.id and ds["tie"] is True
    assert ds["confidence"]["v"] == pytest.approx(0.48)
    badges = {r["complex_id"]: r["decision"] for r in body["rows"]}
    assert all(badges[c] and badges[c]["tie"] and badges[c]["chosen"] for c in top2_ids), badges


def test_t02_pipeline_confident_decide_no_tie(env: RegressEnv) -> None:
    """대조: 같은 경로에서 confidence 0.8(≥ 0.6) → tie 없음, chosen = selected 1개."""
    from sqlalchemy import select

    from app.models import Decision, ScoreRun

    sc_b = _scenario_id(env, "B")
    r = env.client.post(
        "/api/jobs",
        headers=WRITE,
        json={
            "job_name": "rejudge",
            "payload": {"snapshot_id": SNAP, "scenario_id": sc_b, "complex_ids": None, "reason": "T2 대조"},
        },
    )
    assert r.status_code == 202, r.text
    env.worker(env.ctx("fake"))
    with env.session() as s:
        run = s.scalars(
            select(ScoreRun)
            .where(ScoreRun.snapshot_id == SNAP, ScoreRun.scenario_id == sc_b)
            .order_by(ScoreRun.id.desc())
        ).first()
        assert run is not None and run.id > 5
        cx = [
            d
            for d in s.scalars(select(Decision).where(Decision.score_run_id == run.id))
            if d.option_key == "complex"
        ]
        assert cx and not any(d.tie for d in cx)
        assert sum(1 for d in cx if d.chosen) == 1

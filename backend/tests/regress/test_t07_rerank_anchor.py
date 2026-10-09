"""T7 rerank 8 → 16 후보 (RA §9, §6-5 고정 앵커) — 시스템 경계: devseed 적재(녹화 #71·#124) → API, 그리고
worker 재판정(FakeJev)으로 후보군을 8 → 16 으로 바꿔 rerank 호출·delta_rerank·점수를 본다.

RA §9 T7 기대 결과(그대로): "후보 변경 시 호출 1회(16개 전부), `delta_rerank` 열 생성, 종합 점수는 새 호출 값만"
픽스처: 인천 8 녹화(#71) + 인천·김포 16 녹화(#124), ``expected_scores.json`` t7_incheon_only.
§6-5: 한 score_run 의 rerank 값은 같은 judgment_seq 한 호출에서 나온 것만 쓴다. 후보군이 바뀌면 과거 후보를 전부 포함해
1회 재호출하고, 이전 run 과의 차이를 delta_rerank 로 낸다.

delta_rerank 정의(R3 minor 25, F2 — §6-5 "이전 run 과의 점수 차이"): **rerank 점수(0~10) 차** =
s_rerank(이번 호출) − s_rerank(이전 호출), s_rerank = 10 × (N − rank)/(N − 1)(각 호출의 N). 이전 후보가 아니면 null.
``expected_scores.json`` t7 의 ``delta_rerank`` 열은 보고서 정의(relevance 차)라 보고서 대조(녹화 #71·#124)에만 쓴다.

파이프라인 검사의 '인천 8 단계'는 김포·계양 단지 8개를 inclusion_class='범위 경계'(D2-6, 후보군 제외)로 두어 만든다
(단지 추가 대신 후보군 제외 → 복원 — 같은 '후보 변경'). 그 외 입력은 devseed 그대로.
"""

# ruff: noqa: E501

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import pytest

from .conftest import FIXTURE, SNAP, WRITE, RegressEnv, api_get, by_key, load_json

pytestmark = pytest.mark.regress

SEQ_PREV = 71
SEQ_NEW = 124


def _t7() -> dict[str, Any]:
    t7: dict[str, Any] = load_json(FIXTURE / "expected_scores.json")["t7_incheon_only"]
    return t7


def _rerank_envelopes(env: RegressEnv) -> dict[int, dict[str, Any]]:
    body = api_get(env, "/ops/judgments", tool="rerank", since="2026-01-01", size=1000)
    return {int(e["judgment_seq"]): e for e in body["items"]}


def _items(envelope: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {int(i["complex_id"]): i for i in envelope["result"]["items"]}


def _q4(v: float) -> float:
    return float(Decimal(str(v)).quantize(Decimal("0.0001"), ROUND_HALF_UP))


def _s(rank: int, n: int) -> Decimal:
    """s_rerank = 10 × (N − rank)/(N − 1), 소수 4자리(app.analysis.score 와 같은 반올림)."""
    if n <= 1:
        return Decimal(10)
    return (Decimal(10) * (n - rank) / (n - 1)).quantize(Decimal("0.0001"), ROUND_HALF_UP)


def _score_delta(new: dict[str, Any], prev: dict[str, Any], n_new: int, n_prev: int) -> float:
    """delta_rerank = 점수 차(§6-5, F2) — 각 호출의 순위·후보 수로 낸 s_rerank 의 차."""
    return float(_s(int(new["rank"]), n_new) - _s(int(prev["rank"]), n_prev))


def _score_rows(env: RegressEnv, ids: list[int], scenario: str = "base") -> dict[int, dict[str, Any]]:
    """G4 비교 API(2~6개씩)로 score_row(성분·delta_rerank 포함)를 모은다."""
    out: dict[int, dict[str, Any]] = {}
    chunks = [ids[i : i + 6] for i in range(0, len(ids), 6)]
    if len(chunks[-1]) == 1:  # 비교는 2~6개
        chunks[-1] = [chunks[-2].pop(), *chunks[-1]]
    for chunk in chunks:
        body = api_get(env, f"/snapshots/{SNAP}/compare", ids=",".join(map(str, chunk)), scenario=scenario)
        out.update({r["complex_id"]: r for r in body["rows"]})
    return out


# ---------------------------------------------------------------- devseed(녹화) 경로


def test_t07_recorded_anchors_8_then_16_superset(env: RegressEnv) -> None:
    """녹화 #71(인천 8) → #124(16): 16 후보가 이전 8 후보를 전부 포함하고, relevance 차 = t7 delta_rerank(보고서 대조)."""
    t7 = _t7()
    assert (t7["rerank_judgment_seq_prev"], t7["rerank_judgment_seq"]) == (SEQ_PREV, SEQ_NEW)
    ids = by_key()
    envs = _rerank_envelopes(env)
    prev, new = _items(envs[SEQ_PREV]), _items(envs[SEQ_NEW])
    assert len(prev) == 8 and len(new) == 16
    assert set(prev) <= set(new), "후보 변경 시 과거 후보 전부 포함(§6-5)"
    assert set(prev) == {ids[r["key"]] for r in t7["rows"]}
    for r in t7["rows"]:
        cid = ids[r["key"]]
        assert prev[cid]["relevance"] == pytest.approx(r["relevance_prev"]), r["key"]
        assert new[cid]["relevance"] == pytest.approx(r["relevance"]), r["key"]
        assert _q4(new[cid]["relevance"] - prev[cid]["relevance"]) == pytest.approx(r["delta_rerank"]), r["key"]


def test_t07_recorded_anchors_score_delta(env: RegressEnv) -> None:
    """같은 녹화(#71 → #124)의 delta_rerank(점수 차 정의, §6-5·F2) = s_rerank(#124 순위, N=16) − s_rerank(#71 순위, N=8).

    예: 한내들 #71 1위/8 = 10 → #124 1위/16 = 10 → 0; 마리나베이 #71 8위/8 = 0 → #124 15위/16 ≈ 0.6667.
    """
    from app.analysis.score import rerank_component
    from app.core.contracts_gen import ComplexScoreInput, RerankAnchor, RerankItem, RerankPrev

    envs = _rerank_envelopes(env)
    prev, new = _items(envs[SEQ_PREV]), _items(envs[SEQ_NEW])
    anchor = RerankAnchor(
        judgment_seq=SEQ_NEW, status="ok", items=[RerankItem.model_validate(i) for i in new.values()],
        prev=RerankPrev(judgment_seq=SEQ_PREV, items=[RerankItem.model_validate(i) for i in prev.values()]),
    )  # fmt: skip
    base = ComplexScoreInput.model_validate(
        load_json(FIXTURE / "expected_scores_v2.json")["inputs"]["complexes"][0]
    )
    for cid in new:
        comp = rerank_component(base.model_copy(update={"complex_id": cid}), anchor)
        want = _score_delta(new[cid], prev[cid], len(new), len(prev)) if cid in prev else None
        got = None if comp.delta is None else float(comp.delta)
        assert got == (None if want is None else pytest.approx(want, abs=1e-4)), (cid, got, want)


def test_t07_devseed_scores_use_only_call_124(env: RegressEnv) -> None:
    """devseed score_run(5개 시나리오)의 rerank 앵커 = #124 한 호출; API 성분 raw 는 #124 relevance, prov jl_124."""
    from sqlalchemy import select

    from app.models import ScoreRun

    with env.session() as s:
        runs = list(s.scalars(select(ScoreRun).where(ScoreRun.snapshot_id == SNAP)))
    assert runs and {r.rerank_judgment_seq for r in runs} == {SEQ_NEW}
    new = _items(_rerank_envelopes(env)[SEQ_NEW])
    rows = _score_rows(env, list(range(1, 17)))
    for cid, item in new.items():
        comp = rows[cid]["components"]["rerank"]
        raw = comp["raw"]
        assert raw is not None, cid
        assert raw["prov"] == f"jl_{SEQ_NEW}", (cid, raw)
        assert raw["v"] == pytest.approx(item["relevance"]), (cid, raw, item)


# ---------------------------------------------------------------- worker 파이프라인 경로

INCHEON_ONLY_BOUNDARY = "범위 경계"


def _rejudge(env: RegressEnv, reason: str, scenario_id: int | None = 1) -> int:
    r = env.client.post(
        "/api/jobs",
        headers=WRITE,
        json={"job_name": "rejudge", "payload": {"snapshot_id": SNAP, "scenario_id": scenario_id, "complex_ids": None, "reason": reason}},
    )
    assert r.status_code == 202, r.text
    job_id = int(r.json()["id"])
    env.worker(env.ctx("fake"))
    job = api_get(env, f"/jobs/{job_id}")
    assert job["status"] == "done", job
    return job_id


def _rerank_calls(env: RegressEnv, since: int) -> list[dict[str, Any]]:
    return [a for t, a in env.jev.calls[since:] if t.removeprefix("jev_") == "rerank"]


def _latest_base_run(env: RegressEnv) -> Any:
    from sqlalchemy import select

    from app.models import ScoreRun

    with env.session() as s:
        run = s.scalars(select(ScoreRun).where(ScoreRun.snapshot_id == SNAP, ScoreRun.scenario_id == 1).order_by(ScoreRun.id.desc())).first()
        assert run is not None
        s.expunge(run)
        return run


def test_t07_pipeline_candidates_8_to_16_one_call_delta_and_new_call_only(env: RegressEnv) -> None:
    from sqlalchemy import select

    from app.models import Complex, ScoreComponent, ScoreTotal

    t7 = _t7()
    ids = by_key()
    incheon = sorted(ids[r["key"]] for r in t7["rows"])
    others = sorted(set(range(1, 17)) - set(incheon))

    # --- 인천 8 단계: 김포·계양 8개를 후보군 밖(범위 경계)으로
    with env.session() as s:
        saved = {cx.id: cx.inclusion_class for cx in s.scalars(select(Complex).where(Complex.id.in_(others)))}
        for cx in s.scalars(select(Complex).where(Complex.id.in_(others))):
            cx.inclusion_class = INCHEON_ONLY_BOUNDARY
        s.commit()
    _rejudge(env, "T7 인천 8")
    calls1 = _rerank_calls(env, 0)
    assert len(calls1) == 1, f"인천 8: rerank 실제 호출 {len(calls1)}회 (1회여야)"
    cand1 = sorted(int(c["id"].split(":")[1]) for c in calls1[0]["candidates"])
    assert cand1 == incheon
    run1 = _latest_base_run(env)
    s1 = run1.rerank_judgment_seq
    assert s1 is not None and s1 > 132

    # --- 16 단계: 후보군 복원 → 후보 변경
    with env.session() as s:
        for cx in s.scalars(select(Complex).where(Complex.id.in_(others))):
            cx.inclusion_class = saved[cx.id]
        s.commit()
    mark = len(env.jev.calls)
    _rejudge(env, "T7 인천·김포 16")
    calls2 = _rerank_calls(env, mark)
    assert len(calls2) == 1, f"후보 변경 시 rerank 실제 호출 {len(calls2)}회 (1회여야)"
    cand2 = sorted(int(c["id"].split(":")[1]) for c in calls2[0]["candidates"])
    assert cand2 == list(range(1, 17)), "16개 전부(과거 후보 포함)"
    run2 = _latest_base_run(env)
    s2 = run2.rerank_judgment_seq
    assert s2 is not None and s2 != s1, (s1, s2)
    assert run2.prev_score_run_id is not None

    envs = _rerank_envelopes(env)
    it1, it2 = _items(envs[s1]), _items(envs[s2])
    assert sorted(it1) == incheon and sorted(it2) == list(range(1, 17))
    n = len(it2)

    with env.session() as s:
        comps = {
            c.complex_id: c
            for c in s.scalars(select(ScoreComponent).where(ScoreComponent.score_run_id == run2.id, ScoreComponent.component == "rerank"))
        }
        totals = {t.complex_id: t for t in s.scalars(select(ScoreTotal).where(ScoreTotal.score_run_id == run2.id))}
        all_comps = list(s.scalars(select(ScoreComponent).where(ScoreComponent.score_run_id == run2.id)))
    bad: list[str] = []
    for cid, item in it2.items():
        c = comps.get(cid)
        if c is None:
            bad.append(f"{cid}: rerank 성분 없음")
            continue
        # 종합 점수는 새 호출 값만: 점수 = 10 × (N − rank)/(N − 1), 원값 = 새 호출 relevance, 식에 새 seq
        want = _q4(10 * (n - item["rank"]) / (n - 1))
        # score_component.score_0_10 은 소수 3자리로 저장된다(모델 열 정밀도) — 0.0005 까지 같은 값
        if c.score_0_10 is None or abs(float(c.score_0_10) - want) > 5e-4 + 1e-9:
            bad.append(f"{cid}: rerank score {c.score_0_10} != {want} (rank {item['rank']}/{n}, jl_{s2})")
        if c.raw_value is None or abs(float(c.raw_value) - item["relevance"]) > 1e-6:
            bad.append(f"{cid}: rerank raw {c.raw_value} != {item['relevance']}")
        if f"jl_{s2}" not in (c.formula_text or "") or f"jl_{s1}" in (c.formula_text or ""):
            bad.append(f"{cid}: formula_text 앵커 {c.formula_text!r}")
        # delta_rerank: 이전 후보(인천 8)는 rerank 점수 차(§6-5, F2), 새 후보는 없음
        if cid in it1:
            want_d = _score_delta(item, it1[cid], n, len(it1))
            if c.delta is None or abs(float(c.delta) - want_d) > 1e-4:
                bad.append(f"{cid}: delta {c.delta} != {want_d}")
        elif c.delta is not None:
            bad.append(f"{cid}: 새 후보인데 delta {c.delta}")
    # 다른 성분에는 delta 없음
    bad += [f"{c.complex_id}/{c.component}: delta {c.delta}" for c in all_comps if c.component != "rerank" and c.delta is not None]
    # 종합 = Σ w·s (rerank 는 위의 새 호출 값) — 미계산 성분이 있으면 null
    weights = {k: Decimal(str(v)) for k, v in (run2.weights or {}).items()}
    by_cx: dict[int, dict[str, Any]] = {}
    for c in all_comps:
        by_cx.setdefault(c.complex_id, {})[c.component] = c.score_0_10
    for cid, t in totals.items():
        sc = by_cx.get(cid, {})
        if t.total is None or any(sc.get(k) is None for k in weights):
            continue
        want_t = sum((w * Decimal(str(sc[k])) for k, w in weights.items()), Decimal(0))
        if abs(Decimal(str(t.total)) - want_t) > Decimal("0.001"):
            bad.append(f"{cid}: total {t.total} != Σ w·s {want_t}")
    assert not bad, "\n".join(bad)

    # API: score_row.delta_rerank 열(G4) — 인천 8 은 값, 김포 8 은 null; rerank raw prov = 새 호출
    rows = _score_rows(env, list(range(1, 17)))
    for cid in range(1, 17):
        d = rows[cid]["delta_rerank"]
        raw = rows[cid]["components"]["rerank"]["raw"]
        assert raw is not None and raw["prov"] == f"jl_{s2}", (cid, raw)
        if cid in it1:
            assert d is not None and d["v"] == pytest.approx(_score_delta(it2[cid], it1[cid], n, len(it1)), abs=1e-4), (cid, d)
        else:
            assert d is None, (cid, d)

    # --- 후보 그대로면 재호출 없음(같은 앵커)
    mark = len(env.jev.calls)
    _rejudge(env, "T7 변경 없음")
    assert _rerank_calls(env, mark) == [], "후보·카드 그대로인데 rerank 실제 호출"
    assert _latest_base_run(env).rerank_judgment_seq == s2

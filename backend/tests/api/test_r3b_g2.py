"""R3b G2 — 재리뷰 N-C1(D10-1): 스냅샷 화면·KPI·TOP 5·단지 목록·상세의 범위·순위·총점·성분 = 저장값.

devseed 기본 스냅샷(12, published)에서 리뷰 재현: 사람 확인 '불가' 입력 뒤에도 TOP 5·KPI 는 그 score_run 의 저장값
(judge_scope·rank·total)을 그대로 보이고, 현재 사실로 계산한 범위가 다르면 '재판정 필요'(내부 플래그 — 계약 .6 전)만 선다.
"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.views import load_bundles, rejudge_needed, scope_result, score_ctx, shown_scope
from app.core.db import get_session
from app.models import Complex, Scenario, ScoreRun, ScoreTotal

from ._support import WRITE, validate

SNAP = 12


def _stored(run_id: int) -> dict[int, ScoreTotal]:
    with get_session() as s:
        return {
            t.complex_id: t for t in s.scalars(select(ScoreTotal).where(ScoreTotal.score_run_id == run_id))
        }


def _dashboard(client: TestClient) -> dict[str, Any]:
    r = client.get(f"/api/snapshots/{SNAP}/dashboard", headers=WRITE)
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    validate("getDashboard", 200, body)
    return body


def _check_stored(client: TestClient, body: dict[str, Any]) -> dict[int, ScoreTotal]:
    stored = _stored(int(body["score_run_id"]))
    # TOP 5: 범위·순위·총점 = 저장값(같은 실행)
    for row in body["top5"]:
        t = stored[row["complex_id"]]
        assert row["judge_scope"] == (t.judge_scope or row["judge_scope"]), row["complex_id"]
        assert row["rank"] == t.rank and row["score_run_id"] == body["score_run_id"]
        # p10 성분 점수가 있으면 p10 사실값도 있다(성분과 사실값이 같은 사다리 — 리뷰: 성분 3.9 인데 사실값 null)
        if row["components"]["p10"]["score"]["v"] is not None:
            assert row["p10"]["v"] is not None, row["complex_id"]
    # KPI 판정 대상 수 = 저장 judge_scope '판정 대상' 수(출처 식 st_<run>)와 같은 값 — TOP 5 와 같은 실행
    judged = sum(1 for t in stored.values() if t.judge_scope == "판정 대상")
    assert body["kpis"]["judged_count"]["v"] == judged
    assert body["kpis"]["judged_count"]["prov"] == f"st_{body['score_run_id']}"
    assert all(stored[r["complex_id"]].judge_scope in (None, "판정 대상") for r in body["top5"])
    return stored


def _flags(cids: list[int]) -> dict[int, tuple[str, str, bool]]:
    """단지 → (현재 사실 범위, 화면 범위, 재판정 필요)."""
    with get_session() as s:
        sc = s.scalars(select(Scenario).where(Scenario.code == "base")).one()
        ctx = score_ctx(s, SNAP, sc)
        bundles = load_bundles(s, list(s.scalars(select(Complex).where(Complex.id.in_(cids)))), SNAP)
        return {
            c: (scope_result(b).scope, shown_scope(b, ctx), rejudge_needed(b, ctx))
            for c, b in bundles.items()
        }


def test_n_c1_dashboard_top5_kpi_list_detail_show_stored_values(client: TestClient) -> None:
    before = _dashboard(client)
    stored = _check_stored(client, before)
    assert before["top5"], "devseed 기본 스냅샷에 TOP 5 가 있어야 한다"
    first = before["top5"][0]
    cid = first["complex_id"]
    flags_before = _flags([x["complex_id"] for x in before["top5"]])
    # 리뷰 재현(devseed 기본): 현재 사실 범위가 저장값과 다른 TOP 5 단지(예: 지금은 '미해결')도 화면은 저장값 + 재판정 필요
    for c, (cur, shown, flag) in flags_before.items():
        assert shown == stored[c].judge_scope == "판정 대상", c
        assert flag == (cur != shown), c

    # 리뷰 재현: 1위 단지에 사람 확인 '불가' → 현재 사실 범위 '참고'
    r = client.post(
        "/api/ops/human-checks",
        headers=WRITE,
        json={
            "complex_id": cid, "field": "intake_status", "value_text": "불가", "kind": "phone",
            "checked_at": "2026-10-09", "entered_by": "운영자", "note": "R3b N-C1 재현",
        },
    )  # fmt: skip
    assert r.status_code == 201, r.text

    after = _dashboard(client)
    _check_stored(client, after)
    row = next(x for x in after["top5"] if x["complex_id"] == cid)
    # 저장값 그대로(현재 사실과 섞지 않는다): 범위·순위·총점 불변
    assert (row["judge_scope"], row["rank"], row["total"]["v"]) == (
        first["judge_scope"], first["rank"], first["total"]["v"],
    )  # fmt: skip
    assert after["kpis"]["judged_count"]["v"] == before["kpis"]["judged_count"]["v"]

    # 현재 사실로 계산한 범위는 '참고' → '재판정 필요'(계약 .6 전 내부 플래그)
    with get_session() as s:
        cx = s.get(Complex, cid)
        assert cx is not None
        sc = s.scalars(select(Scenario).where(Scenario.code == "base")).one()
        ctx = score_ctx(s, SNAP, sc)
        b = load_bundles(s, [cx], SNAP)[cid]
        assert scope_result(b).scope == "참고"
        assert shown_scope(b, ctx) == stored[cid].judge_scope == "판정 대상"
        assert rejudge_needed(b, ctx) is True
    # 바뀌지 않은 다른 TOP 5 단지의 재판정 필요 여부는 그대로
    others = [x["complex_id"] for x in after["top5"] if x["complex_id"] != cid]
    assert {o: f for o, f in _flags(others).items()} == {o: flags_before[o] for o in others}

    # 단지 목록(G2)·상세도 저장값
    lst = client.get(f"/api/snapshots/{SNAP}/complexes?size=1000", headers=WRITE)
    assert lst.status_code == 200, lst.text
    items = {it["complex_id"]: it for it in lst.json()["items"]}
    assert items[cid]["judge_scope"] == "판정 대상" and items[cid]["rank"] == first["rank"]
    for c, it in items.items():
        t = stored.get(c)
        if t is not None and t.judge_scope:
            assert it["judge_scope"] == t.judge_scope, c
    det = client.get(f"/api/complexes/{cid}", headers=WRITE)
    assert det.status_code == 200, det.text
    score = det.json()["score"]
    assert score is not None and score["judge_scope"] == "판정 대상" and score["rank"] == first["rank"]


def test_n_c1_unscored_complex_without_row_falls_back_and_flags(client: TestClient) -> None:
    """점수 실행이 있는데 그 단지 행이 없는 옛 실행(devseed — 점수 밖 단지 행 없음): 현재 범위가 점수 밖이면 그대로,
    점수 대상이면 '재판정 필요'."""
    with get_session() as s:
        sc = s.scalars(select(Scenario).where(Scenario.code == "base")).one()
        ctx = score_ctx(s, SNAP, sc)
        run = s.scalars(
            select(ScoreRun).where(ScoreRun.snapshot_id == SNAP).order_by(ScoreRun.id.desc())
        ).first()
        assert run is not None and ctx.run is not None
        cxs = list(s.scalars(select(Complex)))
        bundles = load_bundles(s, cxs, SNAP)
        for c in cxs:
            if c.id in ctx.totals:
                continue
            b = bundles[c.id]
            cur = scope_result(b).scope
            assert shown_scope(b, ctx) in (cur, "제외", "미해결")
            assert rejudge_needed(b, ctx) == (cur in ("판정 대상", "참고", "보류"))

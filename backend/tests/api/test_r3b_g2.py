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
        # 저장 범위가 있으면 그 값 그대로(R3 3차 minor 8: 전에는 저장값 None 이면 늘 참인 단언)
        assert t.judge_scope is not None, row["complex_id"]
        assert row["judge_scope"] == t.judge_scope, row["complex_id"]
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


def _flags(cids: list[int], sid: int = SNAP) -> dict[int, tuple[str, str, bool, bool]]:
    """단지 → (현재 사실 범위, 화면 범위, 재판정 필요, 점수 실행 뒤 재판정 변경 있음)."""
    with get_session() as s:
        sc = s.scalars(select(Scenario).where(Scenario.code == "base")).one()
        ctx = score_ctx(s, sid, sc)
        bundles = load_bundles(s, list(s.scalars(select(Complex).where(Complex.id.in_(cids)))), sid)
        return {
            c: (scope_result(b).scope, shown_scope(b, ctx), rejudge_needed(b, ctx), b.changed_after_run)
            for c, b in bundles.items()
        }


def test_n_c1_dashboard_top5_kpi_list_detail_show_stored_values(client: TestClient) -> None:
    """N-C1(D10-1): 화면은 점수 실행 저장값. D11-1(계약 .8): 발행 스냅샷은 불변 — 사람 확인 접수는 새 리비전에 들어가고
    발행 12 의 화면·KPI 는 그대로다. R3 3차 minor 5: '재판정 필요' = 저장 범위 ≠ 현재 범위 또는 점수 실행 뒤 재판정 변경,
    지역 최신 스냅샷만(과거 리비전은 오늘 사실과 비교하지 않는다)."""
    before = _dashboard(client)
    stored = _check_stored(client, before)
    assert before["top5"], "devseed 기본 스냅샷에 TOP 5 가 있어야 한다"
    first = before["top5"][0]
    cid = first["complex_id"]
    flags_before = _flags([x["complex_id"] for x in before["top5"]])
    for c, (cur, shown, flag, changed) in flags_before.items():
        assert shown == stored[c].judge_scope == "판정 대상", c
        assert flag == (cur != shown or changed), c
    assert {x["complex_id"]: x["rejudge_needed"] for x in before["top5"]} == {
        c: f for c, (_cur, _shown, f, _ch) in flags_before.items()
    }

    # 1위 단지에 사람 확인 '불가' → 같은 기준일 새 리비전(발행 12 는 불변)
    r = client.post(
        "/api/ops/human-checks",
        headers=WRITE,
        json={
            "complex_id": cid, "field": "intake_status", "value_text": "불가", "kind": "phone",
            "checked_at": "2026-10-09", "entered_by": "운영자", "note": "R3b N-C1 재현",
        },
    )  # fmt: skip
    assert r.status_code == 201, r.text
    rev = r.json()["created_intake"]["snapshot_id"]
    assert rev != SNAP

    after = _dashboard(client)
    _check_stored(client, after)
    row = next(x for x in after["top5"] if x["complex_id"] == cid)
    # 발행 12: 저장값·범위·순위·총점·KPI 그대로(현재 사실과 섞지 않는다)
    assert (row["judge_scope"], row["rank"], row["total"]["v"]) == (
        first["judge_scope"], first["rank"], first["total"]["v"],
    )  # fmt: skip
    assert after["kpis"] == {**before["kpis"], "data_freshness": after["kpis"]["data_freshness"]}
    # 12 는 이제 과거 리비전 — 오늘 사실과 비교하지 않는다(재판정 필요 없음, 새 리비전이 재판정 대상)
    assert row["rejudge_needed"] is False and after["rejudge_needed"] is False

    # 새 리비전(building, 점수 실행 전): 현재 사실로 계산한 범위 '참고'(사람 확인 '불가')
    with get_session() as s:
        cx = s.get(Complex, cid)
        assert cx is not None
        b = load_bundles(s, [cx], rev)[cid]
        assert scope_result(b).scope == "참고"
        snap12 = load_bundles(s, [cx], SNAP)[cid]
        assert scope_result(snap12).scope == flags_before[cid][0], "발행 12 의 접수 행은 그대로"

    # 단지 목록(G2)·상세도 저장값
    lst = client.get(f"/api/snapshots/{SNAP}/complexes?size=1000", headers=WRITE)
    assert lst.status_code == 200, lst.text
    items = {it["complex_id"]: it for it in lst.json()["items"]}
    assert items[cid]["judge_scope"] == "판정 대상" and items[cid]["rank"] == first["rank"]
    for c, it in items.items():
        t = stored.get(c)
        if t is not None and t.judge_scope:
            assert it["judge_scope"] == t.judge_scope, c
    det = client.get(f"/api/complexes/{cid}", params={"snapshot": SNAP}, headers=WRITE)
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

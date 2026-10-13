"""R7-FIX2(CEO 결정): 공동 순위 안의 표시 순서 = 종합 점수 높은 순 → complex_id — 대시보드 TOP 5·단지 목록 ``sort=rank``·
``sort=-rank`` 가 같은 키(``analysis._ranking.display_order_key``)를 쓴다. 예전 API 는 (rank, complex_id)였다(인천: 16 → 41,
4.64 가 4.67 위).

devseed 의 공동 5위 두 단지(작은 id·큰 id)의 저장 total 을 큰 id 가 더 높게 바꿔(같은 rank·tie_group 그대로) 순서를 본다.
"""

# ruff: noqa: E501

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from ._support import READ, as_live


def _tie_pair() -> tuple[int, int, int]:
    """기본 지역 최신 스냅샷의 base 마지막 점수 실행에서 공동 5위 두 단지 → (스냅샷 id, 작은 id, 큰 id). 큰 id 의 total 을 올린다."""
    from app.core.db import get_session
    from app.models import Scenario, ScoreRun, ScoreTotal, Snapshot

    as_live()
    with get_session() as s:
        snap = s.scalars(
            select(Snapshot).where(Snapshot.region_id == 1).order_by(Snapshot.asof_date.desc(), Snapshot.revision.desc())
        ).first()
        assert snap is not None
        base = s.scalars(select(Scenario).where(Scenario.code == "base")).one()
        run = s.scalars(
            select(ScoreRun).where(ScoreRun.snapshot_id == snap.id, ScoreRun.scenario_id == base.id).order_by(ScoreRun.id.desc())
        ).first()
        assert run is not None
        tail = sorted(
            s.scalars(select(ScoreTotal).where(ScoreTotal.score_run_id == run.id, ScoreTotal.rank == 5)),
            key=lambda t: t.complex_id,
        )
        assert len(tail) == 2 and tail[0].tie_group is not None and tail[0].tie_group == tail[1].tie_group
        lo, hi = tail
        lo.total, hi.total = Decimal("4.6050"), Decimal("4.6400")
        return snap.id, lo.complex_id, hi.complex_id


def test_dashboard_top5_tie_group_ordered_by_total_then_id(client: TestClient) -> None:
    sid, lo, hi = _tie_pair()
    body = client.get(f"/api/snapshots/{sid}/dashboard", params={"scenario": "base"}, headers=READ).json()
    tail = [r["complex_id"] for r in body["top5"] if r["rank"] == 5]
    assert tail == [hi, lo], body["top5"]
    ranks = [r["rank"] for r in body["top5"]]
    assert ranks == sorted(ranks)


def test_complex_list_sort_rank_tie_group_ordered_by_total_then_id(client: TestClient) -> None:
    sid, lo, hi = _tie_pair()
    for sort in ("rank", "-rank"):
        body = client.get(
            f"/api/snapshots/{sid}/complexes", params={"scenario": "base", "sort": sort, "size": 100}, headers=READ
        ).json()
        tail = [r["complex_id"] for r in body["items"] if r.get("rank") == 5]
        assert tail == [hi, lo], (sort, [(r["complex_id"], r.get("rank")) for r in body["items"]])
        ranked = [r["rank"] for r in body["items"] if r.get("rank") is not None]
        assert ranked == sorted(ranked, reverse=sort.startswith("-")), sort

"""R3g CORE5 — R3 7차 리뷰 M4(D15-5) · minor 3 · 12 · 15 (WP8 보고서).

| 항목 | 테스트 |
| --- | --- |
| M4 / D15-5 | 사용자 시나리오 보고서 §12 12-1 순위표·TOP 5 는 같은 시나리오끼리만 — 비교 기준에 그 시나리오가 없으면 사유와 함께 생략 |
| minor 3 | 접수 상태 ``checked_at``(UTC 'Z')은 KST 날짜로 표시('2026-10-09T20:00:00Z' → 2026-10-10) |
| minor 12 | 보고서 저장본 계산 중 출처 누락이 ``missing_provenance`` 에 세어진다 |
| minor 15 | CLI ``--compare`` 도 API 와 같은 규칙(앞선 리비전·같은 지역·발행) — 종료 코드 6 |

리뷰 재현: scratchpad ``r7/c/test_c_reports.py::test_s12_rank_rows_mix_base_and_user_scenario`` ("12위 → 1위").
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from bs4 import BeautifulSoup
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import get_session
from app.models import (
    FieldProvenance,
    IntakeStatus,
    Scenario,
    ScoreComponent,
    ScoreRun,
    ScoreTotal,
    Snapshot,
)
from tests.api import conftest as api_conftest
from tests.api._support import WRITE

from ._seed import live

# API fixture(테스트마다 쓰기 가능한 devseed DB 복사본 + TestClient) — 시나리오·리비전을 만들어 발행하는 테스트용
seeded_db = api_conftest.seeded_db
api_settings = api_conftest.api_settings
client = api_conftest.client

SNAP = 12  # devseed 발행 스냅샷(지역 1)
PREV = 11

USER_SC = {
    "name": "R3g 사용자",
    "params": {"equity_won": 250000000, "loan_limit_won": 600000000, "holding_years": 4},
    "weights": {"p10": 0.3, "rerank": 0.15, "gap": 0.2, "benchmark": 0.1, "supply": 0.1, "move_in": 0.15},
    "requirements": None,
    "policy": None,
}

RANK_OMITTED = "비교 기준 리비전에 이 시나리오가 없어"


# ---------------------------------------------------------------------------- M4 / D15-5


def _user_scenario(client: Any) -> int:
    r = client.post("/api/scenarios", json=USER_SC, headers=WRITE)
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


def _scenario_run_revision(sc_id: int, at: str) -> int:
    """시나리오 실행 리비전: 가장 새 발행 리비전 이월 + 사용자 시나리오 점수 실행(기본 실행 복사, 순위 뒤집음) → 발행."""
    from app.scheduler.persist import carry_forward
    from app.scheduler.snapshots import latest_for_region, new_revision, publish_with_stats

    with get_session() as s:
        base_snap = latest_for_region(s, 1)
        assert base_snap is not None and base_snap.status == "published"
        rev = new_revision(s, base_snap, reason="R3g 시나리오 실행", created_at=at)
        carry_forward(s, base_snap.id, rev.id, created_at=at)
        base_sc = s.scalars(select(Scenario).where(Scenario.code == "base")).one()
        run = s.scalars(
            select(ScoreRun)
            .where(ScoreRun.snapshot_id == rev.id, ScoreRun.scenario_id == base_sc.id)
            .order_by(ScoreRun.id.desc())
        ).first()
        assert run is not None
        new = ScoreRun(
            snapshot_id=rev.id,
            scenario_id=sc_id,
            weights=run.weights,
            rerank_judgment_seq=run.rerank_judgment_seq,
            prev_score_run_id=None,
            created_at=at,
        )
        s.add(new)
        s.flush()
        totals = list(s.scalars(select(ScoreTotal).where(ScoreTotal.score_run_id == run.id)))
        n = len([t for t in totals if t.rank])
        for t in totals:
            s.add(
                ScoreTotal(
                    score_run_id=new.id,
                    complex_id=t.complex_id,
                    total=t.total,
                    rank=(n + 1 - t.rank) if t.rank else None,
                    tie_group=None,
                    unstable=False,
                    judge_scope=t.judge_scope,
                )
            )
        for c in s.scalars(select(ScoreComponent).where(ScoreComponent.score_run_id == run.id)):
            s.add(
                ScoreComponent(
                    score_run_id=new.id,
                    complex_id=c.complex_id,
                    component=c.component,
                    raw_value=c.raw_value,
                    unadjusted_gap_pct=c.unadjusted_gap_pct,
                    unadjusted_median_won=c.unadjusted_median_won,
                    score_0_10=c.score_0_10,
                    formula_text=c.formula_text,
                    label=c.label,
                    reason=c.reason,
                    delta=c.delta,
                    flags=c.flags,
                )
            )
        snap = s.get(Snapshot, rev.id)
        assert snap is not None
        snap.status = "ready"
        rid = rev.id
        s.commit()
        ok, nn, _st = publish_with_stats(s, rid, now=at)
        assert ok, nn
        return rid


def _s12(html: str) -> Any:
    sec = BeautifulSoup(html, "html.parser").find("section", id="s12")
    assert sec is not None
    return sec


def test_m4_user_scenario_s12_does_not_mix_base_ranks(client: Any) -> None:
    """비교 기준(SNAP)에 사용자 시나리오가 없다 → 12-1 순위표·TOP 5 진입·이탈은 사유와 함께 생략, 건수 비교는 그대로.

    예전: 기본 시나리오 순위(SNAP)와 사용자 시나리오 순위(rev, 뒤집음)를 한 표에 — '12위 → 1위'."""
    from app.reports.data import load_report
    from app.reports.render import render_html

    sc = _user_scenario(client)
    rev = _scenario_run_revision(sc, "2026-10-10T09:00:00+09:00")
    with get_session() as s:
        data = load_report(s, rev, scenario_id=sc, compare_snapshot_id=SNAP)
    x = data.extra
    assert x is not None
    assert x.rank_rows == [], x.rank_rows[:3]
    assert x.rank_note is not None and RANK_OMITTED in x.rank_note
    assert "TOP 5 진입:" not in x.summary and RANK_OMITTED in x.summary, x.summary
    assert "대비 후보" in x.summary and "추가" in x.summary  # D14-3 건수 비교는 시나리오와 무관하게
    assert "rerank" in x.summary

    sec = _s12(render_html(data).html)
    h = next(h for h in sec.find_all("h3") if h.get_text().startswith("12-1."))
    nxt = h.find_next_sibling()
    assert nxt is not None and nxt.name == "p" and RANK_OMITTED in nxt.get_text(), nxt
    assert sec.find("table", id="rank-table") is None


def test_m4_same_scenario_in_both_revisions_keeps_rank_table(client: Any) -> None:
    """두 리비전 모두 그 사용자 시나리오가 있으면 12-1 은 같은 시나리오 순위끼리(뒤집은 순위 = 그대로 → 변화 없음)."""
    from app.reports.data import load_report
    from app.reports.render import render_html

    sc = _user_scenario(client)
    a = _scenario_run_revision(sc, "2026-10-10T09:00:00+09:00")
    b = _scenario_run_revision(sc, "2026-10-10T10:00:00+09:00")
    with get_session() as s:
        data = load_report(s, b, scenario_id=sc, compare_snapshot_id=a)
    x = data.extra
    assert x is not None and x.rank_note is None
    assert x.rank_rows
    assert all(r0 == r1 for _n, r0, r1, _t0, _t1 in x.rank_rows), x.rank_rows
    assert "TOP 5 진입: 없음; 이탈: 없음" in x.summary, x.summary
    sec = _s12(render_html(data).html)
    table = sec.find("table", id="rank-table")
    assert table is not None and len(table.find_all("tr")) == len(x.rank_rows) + 1


def test_m4_base_scenario_report_keeps_rank_table(client: Any) -> None:
    from app.reports.data import load_report

    rev = _scenario_run_revision(_user_scenario(client), "2026-10-10T09:00:00+09:00")
    with get_session() as s:
        data = load_report(s, rev, compare_snapshot_id=SNAP)
    assert data.extra is not None and data.extra.rank_note is None and data.extra.rank_rows
    assert "TOP 5 진입" in data.extra.summary


def test_m4_user_scenario_report_job_html(client: Any) -> None:
    """잡 경로(export.generate): 12-1 사유 + 12-2 '비교 기준에 이 시나리오 없음' 둘 다."""
    from app.core.paths import report_dir
    from tests.api._support import run_job

    sc = _user_scenario(client)
    rev = _scenario_run_revision(sc, "2026-10-10T09:00:00+09:00")
    r = client.post(
        "/api/reports", json={"snapshot_id": rev, "format": "html", "scenario_id": sc}, headers=WRITE
    )
    assert r.status_code == 202, r.text
    status, stats = run_job(int(r.json()["id"]))
    assert status == "done", stats
    sec = _s12((report_dir() / stats["path"]).read_text(encoding="utf-8"))
    text = sec.get_text()
    assert RANK_OMITTED in text and "비교 기준에 이 시나리오 없음" in text
    assert sec.find("table", id="rank-table") is None


# ---------------------------------------------------------------------------- minor 3 KST 날짜


@pytest.fixture
def scratch(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory() as s:
        live(s)
        try:
            yield s
        finally:
            s.rollback()


def test_minor3_intake_view_text_uses_kst_day() -> None:
    from app.reports.data import IntakeView

    iv = IntakeView(
        id=1,
        status="확인 불가",
        path="official_popup",
        path_label="공식 팝업",
        checked_at="2026-10-09T20:00:00Z",
        http_status=403,
        reason=None,
        evidence_url=None,
        note=None,
        used=True,
    )
    assert iv.text == "확인 불가(403, 2026-10-10)"
    assert iv.checked_day == "2026-10-10"
    iv.checked_at = "2026-10-09"  # 날짜만(옛 행)은 그대로
    assert iv.checked_day == "2026-10-09"


def test_minor3_report_intake_dates_are_kst(scratch: Session) -> None:
    """접수 상태 확인 시각 'Z'(UTC 20시) → 보고서 §4 표·배지·실패 출처·부록 B 날짜 = KST 다음 날."""
    from app.reports.data import load_report
    from app.reports.render import render_html

    row = scratch.scalars(
        select(IntakeStatus).where(IntakeStatus.snapshot_id == SNAP).order_by(IntakeStatus.id)
    ).first()
    assert row is not None
    row.status, row.http_status, row.reason = "확인 불가", 403, None
    row.checked_at = "2026-10-09T20:00:00Z"
    row.evidence_url = "https://example-intake.co.kr/r3g-minor3"
    scratch.flush()
    data = load_report(scratch, SNAP)
    iv = next(i for i in data.complex_by_id[row.complex_id].intake if i.id == row.id)
    assert iv.text == "확인 불가(403, 2026-10-10)"
    fs = next(f for f in data.failed_sources if f.url == row.evidence_url)
    assert fs.fetched_at == "2026-10-10"
    ref = next(r for r in data.references if r.url == row.evidence_url)
    assert ref.checked_at == "2026-10-10"
    soup = BeautifulSoup(render_html(data).html, "html.parser")
    s04 = soup.find("section", id="s4")
    assert s04 is not None
    rows = [tr for tr in s04.find_all("tr") if "확인 불가(403, 2026-10-10)" in tr.get_text()]
    assert rows
    for tr in rows:
        assert "2026-10-09" not in tr.get_text(), tr  # 표 칸·배지 모두 KST 날짜


# ---------------------------------------------------------------------------- minor 12 출처 누락 건수


def test_minor12_report_missing_provenance_is_counted(scratch: Session) -> None:
    """저장본 계산(report 만) 중 보고서가 낸 '확인 불가(출처 누락)'이 ``stats.missing_provenance`` 에 세어진다."""
    from app import snapshot_view as sv

    snap = scratch.get(Snapshot, SNAP)
    assert snap is not None
    before = int(sv.compute(scratch, snap, kinds={"report"}).stats["missing_provenance"])
    scratch.execute(
        delete(FieldProvenance).where(
            FieldProvenance.entity == "complex",
            FieldProvenance.entity_id == 1,
            FieldProvenance.field == "units_total",
        )
    )
    scratch.flush()
    after = int(sv.compute(scratch, snap, kinds={"report"}).stats["missing_provenance"])
    assert after > before, (before, after)


def test_minor12_counter_box_counts_report_missing_even_in_dev(scratch: Session) -> None:
    """카운터가 켜져 있으면(저장본 계산) ENV=dev 라도 예외 대신 라벨 + 건수(API ``FactMaker.missing`` 과 같은 규칙)."""
    from app.api.facts import MISSING_COUNT
    from app.reports.data import load_report_live

    scratch.execute(
        delete(FieldProvenance).where(
            FieldProvenance.entity == "complex",
            FieldProvenance.entity_id == 1,
            FieldProvenance.field == "units_total",
        )
    )
    scratch.flush()
    box = [0]
    token = MISSING_COUNT.set(box)
    try:
        data = load_report_live(scratch, SNAP, env="dev")
    finally:
        MISSING_COUNT.reset(token)
    f = data.complex_by_id[1].facts["units_total"]
    assert f.label == "확인 불가" and f.reason == "출처 누락"
    assert box[0] >= 1


# ---------------------------------------------------------------------------- minor 15 CLI --compare


def _snap(sid: int, region: int, asof: str, rev: int, status: str = "published") -> Snapshot:
    return Snapshot(id=sid, region_id=region, asof_date=asof, revision=rev, status=status, created_at="x")


def test_minor15_compare_problem_rules() -> None:
    from app.reports.data import compare_problem

    cur = _snap(12, 1, "2026-10-07", 1)
    assert compare_problem(cur, _snap(11, 1, "2026-09-30", 1)) is None
    assert compare_problem(cur, _snap(10, 1, "2026-10-07", 1)) is None  # 같은 기준일·같은 리비전 번호 → id 로
    assert "같거나 더 새" in (compare_problem(cur, cur) or "")
    assert "같거나 더 새" in (compare_problem(cur, _snap(13, 1, "2026-10-07", 2)) or "")
    assert "같거나 더 새" in (compare_problem(_snap(11, 1, "2026-09-30", 1), cur) or "")
    assert "다른 지역" in (compare_problem(cur, _snap(5, 2, "2026-09-30", 1)) or "")
    assert "발행 전" in (compare_problem(cur, _snap(11, 1, "2026-09-30", 1, "building")) or "")


def test_minor15_cli_rejects_same_or_newer_compare(
    client: Any, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    from app.reports.cli import main

    for snap, cmp in ((PREV, SNAP), (SNAP, SNAP)):
        rc = main(
            ["--snapshot", str(snap), "--compare", str(cmp), "--format", "html", "--out", str(tmp_path)]
        )
        assert rc == 6, (snap, cmp, rc)
        err = capsys.readouterr().err
        assert "compare_snapshot_id" in err and "같거나 더 새" in err, err
    assert not list(tmp_path.glob("*.html"))


def test_minor15_cli_rejects_unpublished_compare(
    client: Any, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    from app.reports.cli import main

    with get_session() as s:
        prev = s.get(Snapshot, PREV)
        assert prev is not None
        prev.status = "ready"
    rc = main(["--snapshot", str(SNAP), "--compare", str(PREV), "--format", "html", "--out", str(tmp_path)])
    assert rc == 6
    assert "발행 전" in capsys.readouterr().err


def test_minor15_cli_accepts_earlier_compare(
    client: Any, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    from app.reports.cli import main

    rc = main(["--snapshot", str(SNAP), "--compare", str(PREV), "--format", "html", "--out", str(tmp_path)])
    assert rc == 0, capsys.readouterr().err
    assert list(tmp_path.glob("*.html"))

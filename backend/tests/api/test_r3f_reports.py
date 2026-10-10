"""R3f CORE4 — R3 6차 N-M1(D14-3) · m4 · m5 · m6 · m7 (계약 2026-10-09.11): 보고서.

리뷰 재현(scratchpad c/sc_report.py): 사용자 시나리오 보고서가 시나리오 실행 리비전에서 늘 실패 — 비교 기준(revision_of)이
시나리오 생성 전 발행이라 저장본 없음 ``failed NotInRevision``. POST 는 202. ``diff.py`` 사용자 시나리오 code NULL.
"""

# ruff: noqa: E501

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_session
from app.models import Complex, Region, Scenario, Snapshot

from ._support import WRITE, publish_revision, run_job
from .test_r3b_g3 import SNAP

USER_SC = {
    "name": "N-M1 사용자",
    "params": {"equity_won": 250000000, "loan_limit_won": 600000000, "holding_years": 4},
    "weights": {"p10": 0.3, "rerank": 0.15, "gap": 0.2, "benchmark": 0.1, "supply": 0.1, "move_in": 0.15},
    "requirements": None,
    "policy": None,
}


def _user_scenario(client: TestClient) -> int:
    r = client.post("/api/scenarios", json=USER_SC, headers=WRITE)
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


def test_nm1_report_for_scenario_created_after_publish_is_422(client: TestClient) -> None:
    """대상 리비전 발행 뒤 만든 사용자 시나리오 → POST 단계에서 422 scenario_not_in_revision(예전: 202 → 잡 실패)."""
    sc = _user_scenario(client)
    r = client.post(
        "/api/reports", json={"snapshot_id": SNAP, "format": "html", "scenario_id": sc}, headers=WRITE
    )
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["code"] == "scenario_not_in_revision"
    assert body["field_errors"][0]["loc"] == ["body", "scenario_id"]


def test_nm1_user_scenario_report_on_revision_with_it_succeeds_and_omits_delta(
    client: TestClient, tmp_path: Path
) -> None:
    """시나리오를 만든 뒤 발행한 리비전(시나리오 실행 리비전과 같은 상황) → 보고서 성공. 비교 기준(revision_of = 시나리오
    생성 전 발행)에 그 시나리오가 없으면 delta 표만 '비교 기준에 이 시나리오 없음', §12 건수 비교는 그대로(D14-3)."""
    sc = _user_scenario(client)
    rev = publish_revision(1, "N-M1 시나리오 실행 리비전")
    r = client.post(
        "/api/reports", json={"snapshot_id": rev, "format": "html", "scenario_id": sc}, headers=WRITE
    )
    assert r.status_code == 202, r.text
    status, stats = run_job(int(r.json()["id"]))
    assert status == "done", stats
    from app.core.paths import report_dir

    html = (report_dir() / stats["path"]).read_text(encoding="utf-8")
    assert "비교 기준에 이 시나리오 없음" in html
    assert 'id="s12"' in html and "대비 후보" in html  # §12 건수 비교는 시나리오와 무관하게
    # 같은 리비전 + 기본 시나리오 = delta 표 그대로
    r = client.post("/api/reports", json={"snapshot_id": rev, "format": "html"}, headers=WRITE)
    status, stats = run_job(int(r.json()["id"]))
    assert status == "done"
    assert "비교 기준에 이 시나리오 없음" not in (report_dir() / stats["path"]).read_text(encoding="utf-8")


def test_nm1_cli_scenario_not_in_revision_exit_code(
    client: TestClient, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    from app.reports.cli import main

    sc = _user_scenario(client)
    assert (
        main(["--snapshot", str(SNAP), "--format", "html", "--scenario", str(sc), "--out", str(tmp_path)])
        == 4
    )
    assert "scenario_not_in_revision" in capsys.readouterr().err
    rev = publish_revision(1, "N-M1 CLI")
    assert (
        main(["--snapshot", str(rev), "--format", "html", "--scenario", str(sc), "--out", str(tmp_path)]) == 0
    )


def test_nm1_diff_finds_user_scenario_by_id_code_null(client: TestClient) -> None:
    """``diff.py`` 시나리오 식별은 id(사용자 시나리오 code NULL) — 예전 code 로 찾아 '시나리오 None 없음'."""
    from app.reports.diff import diff_snapshots

    sc = _user_scenario(client)
    a = publish_revision(1, "N-M1 diff A")
    b = publish_revision(1, "N-M1 diff B")
    with get_session() as s:
        assert s.get(Scenario, sc).code is None  # type: ignore[union-attr]
        d = diff_snapshots(s, a, b, scenario_id=sc)
        assert d.note is None and d.scenario_code
        d2 = diff_snapshots(s, SNAP, b, scenario_id=sc)
        assert d2.note == "비교 기준에 이 시나리오 없음" and d2.rows == []


def test_m5_compare_snapshot_self_or_newer_is_422(client: TestClient) -> None:
    rev = publish_revision(1, "m5 새 리비전")
    for body in (
        {"snapshot_id": SNAP, "compare_snapshot_id": SNAP},
        {"snapshot_id": SNAP, "compare_snapshot_id": rev},
    ):
        r = client.post("/api/reports", json={**body, "format": "html"}, headers=WRITE)
        assert r.status_code == 422, r.text
        assert r.json()["field_errors"][0]["loc"] == ["body", "compare_snapshot_id"]
    r = client.post(
        "/api/reports",
        json={"snapshot_id": rev, "compare_snapshot_id": SNAP, "format": "html"},
        headers=WRITE,
    )
    assert r.status_code == 202, r.text


@pytest.mark.parametrize(
    "rel",
    ["x/C:outside.txt", "C:outside.txt", "x/../../outside.txt", "x/D:/a.html", "\\\\server\\share\\a.html"],
)
def test_m6_report_path_rejects_drive_relative_and_escape(tmp_path: Path, rel: str) -> None:
    from app.api.routers.reports import _report_path

    base = tmp_path / "reports"
    base.mkdir()
    assert _report_path(base, rel) is None


def test_m6_report_path_keeps_normal_names(tmp_path: Path) -> None:
    from app.api.routers.reports import _report_path

    base = tmp_path / "reports"
    base.mkdir()
    got = _report_path(base, "report_r1_2026-10-08-r1_j9.html")
    assert got == base / "report_r1_2026-10-08-r1_j9.html"


def test_m7_report_diff_names_only_region_complexes(client: TestClient) -> None:
    """R3 6차 m7: diff 입력(저장본 report_diff)의 단지 이름은 그 리비전 지역 단지뿐(다른 지역 단지 이름을 저장하지 않는다)."""
    from app.reports.diff import diff_digest_live

    with get_session() as s:
        other = Region(name="다른 지역", query_text="q", selections=[], sido_codes=[], sigungu_codes=[], legal_dong_codes=[],
                       living_areas=[], age_premium_coef={}, applyhome_query={}, status="ready", created_at="2026-10-10")  # fmt: skip
        s.add(other)
        s.flush()
        s.add(Complex(region_id=other.id, applyhome_id="2099000001", name="다른 지역 단지", former_names=[], apply_dates=[],
                      contract_dates=[], inclusion_class="미분류"))  # fmt: skip
        s.flush()
        base = s.scalars(select(Scenario).where(Scenario.code == "base")).one()
        dig = diff_digest_live(s, SNAP, base)
        assert "다른 지역 단지" not in dig["names"].values()
        region_ids = {str(i) for i in s.scalars(select(Complex.id).where(Complex.region_id == 1))}
        assert set(dig["names"]) == region_ids


def test_m4_generated_at_is_render_time_not_stored(client: TestClient, tmp_path: Path) -> None:
    """R3 6차 m4: 발행 리비전 보고서의 '생성 시각'은 만드는 지금(저장본에 고정된 계산 시각이 아니다)."""
    from app.reports.data import load_report

    with get_session() as s:
        snap = s.get(Snapshot, SNAP)
        assert snap is not None and snap.status == "published"
        a = load_report(s, SNAP).generated_at
        from app.core.time import now_kst

        assert a[:13] == now_kst().isoformat(timespec="seconds")[:13]
    from app.reports.export import generate

    with get_session() as s:
        rep = generate(s, SNAP, "html", out_dir=tmp_path)
    html = rep.path.read_text(encoding="utf-8")
    m = re.search(r'<time class="generated-at" datetime="([^"]+)">', html)
    assert m is not None

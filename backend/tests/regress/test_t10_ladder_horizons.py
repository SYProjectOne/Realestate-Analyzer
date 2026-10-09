"""T10 사다리 시점 불일치 (RA §9, §6-3) — 시스템 경계: devseed 적재(녹화 #119·#120) → API, 그리고
worker 재판정(FakeJev, complex_ids [9, 11]) → noul 호출·ladder 행·API(G3 상세·G4 비교).

RA §9 T10 기대 결과(그대로): "horizon 3종 명제 생성, `asof_plus_3y` 목표 시점이 두 단지 동일, 연율 열 계산"
픽스처: 고촌센트럴자이(id 11, 2024-06 준공 → 즉시 입주) vs 한강 푸르지오 리버프론트(id 9, 2031-01 입주 → 1년 뒤 2032-01).
§6-3: move_in_plus_1y = 입주월 + 12개월(즉시 입주면 기준일 + 12개월), asof_plus_3y = 기준일 + 36개월,
asof_plus_5y = 기준일 + 60개월, 연율 r = (1+g)^(12/m) − 1 (g = 0.05·0.10·0.20, m = 기준일부터 목표 시점까지 개월 수).
"""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

import pytest

from .conftest import SNAP, WRITE, RegressEnv, api_get, cur

pytestmark = pytest.mark.regress

RIVERFRONT = 9
GOCHON = 11
ASOF_YM = (2026, 10)  # 스냅샷 12 기준일 2026-10-08
HORIZONS = {"move_in_plus_1y", "asof_plus_3y", "asof_plus_5y"}
GAINS = {"p5": 0.05, "p10": 0.10, "p20": 0.20}

# 기대 목표 시점(§6-3 식을 손으로 푼 값)
EXPECTED = {
    RIVERFRONT: {
        "move_in_plus_1y": ("2032-01", 63),
        "asof_plus_3y": ("2029-10", 36),
        "asof_plus_5y": ("2031-10", 60),
    },
    GOCHON: {
        "move_in_plus_1y": ("2027-10", 12),
        "asof_plus_3y": ("2029-10", 36),
        "asof_plus_5y": ("2031-10", 60),
    },
}


def _annual(months: int) -> dict[str, float]:
    return {k: round((1 + g) ** (12 / months) - 1, 4) for k, g in GAINS.items()}


def _ladders_api(env: RegressEnv, cid: int) -> dict[str, dict[str, Any]]:
    body = api_get(env, f"/complexes/{cid}", snapshot=cur(env))
    return {lad["horizon"]: lad for lad in body["ladder"]}


def test_t10_devseed_recorded_move_in_ladders(env: RegressEnv) -> None:
    """녹화(#119 리버프론트, #120 고촌)는 move_in_plus_1y 만 — 목표 시점이 단지마다 다르다(시점 불일치의 원인)."""
    rf, gc = _ladders_api(env, RIVERFRONT), _ladders_api(env, GOCHON)
    assert rf["move_in_plus_1y"]["judgment_seq"] == 119 and gc["move_in_plus_1y"]["judgment_seq"] == 120
    for cid, lad in ((RIVERFRONT, rf), (GOCHON, gc)):
        m = lad["move_in_plus_1y"]
        want_ym, want_m = EXPECTED[cid]["move_in_plus_1y"]
        assert (m["target_ym"], m["months_from_asof"]) == (want_ym, want_m), (cid, m)
        assert m["annualized"] == pytest.approx(_annual(want_m), abs=1e-4), (cid, m["annualized"])
    assert rf["move_in_plus_1y"]["target_ym"] != gc["move_in_plus_1y"]["target_ym"]


def test_t10_pipeline_three_horizons_same_asof3y_target_annualized(env: RegressEnv) -> None:
    from sqlalchemy import select

    from app.models import Complex, Ladder

    r = env.client.post(
        "/api/jobs",
        headers=WRITE,
        json={
            "job_name": "rejudge",
            "payload": {
                "snapshot_id": SNAP,
                "scenario_id": 1,
                "complex_ids": [RIVERFRONT, GOCHON],
                "reason": "T10 회귀",
            },
        },
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]
    env.worker(env.ctx("fake"))
    assert api_get(env, f"/jobs/{job_id}")["status"] == "done"

    with env.session() as s:
        names = {c.id: c.name for c in s.scalars(select(Complex).where(Complex.id.in_([RIVERFRONT, GOCHON])))}
        rows = {
            (lad.complex_id, lad.horizon): lad
            for lad in s.scalars(
                select(Ladder).where(
                    Ladder.snapshot_id == cur(env), Ladder.complex_id.in_([RIVERFRONT, GOCHON])
                )
            )
        }
        for row in rows.values():
            s.expunge(row)

    # 1) noul 명제: 단지마다 horizon 3종(호출 3회 × 명제 4개), 시점 설명이 §6-3 대로
    noul = [a for t, a in env.jev.calls if t.removeprefix("jev_") == "noul"]
    for cid in (RIVERFRONT, GOCHON):
        mine = [a["propositions"] for a in noul if all(p.startswith(names[cid]) for p in a["propositions"])]
        assert len(mine) == 3, (cid, len(mine))
        assert all(len(p) == 4 for p in mine)
        joined = [" ".join(p) for p in mine]
        assert sum("기준일+3년 시점인 2029 하반기" in j for j in joined) == 1, joined
        assert sum("기준일+5년 시점인 2031 하반기" in j for j in joined) == 1, joined
        if cid == GOCHON:
            assert sum("기준일+1년 시점인 2027 하반기" in j for j in joined) == 1, joined
        else:
            assert sum("입주(2031-01) 후 1년 시점인 2032 상반기" in j for j in joined) == 1, joined
        for props in mine:
            assert [p.rsplit(" ", 1)[-1] for p in props] == [
                "이상이다",
                "이상이다",
                "이상이다",
                "이하(보합·하락)이다",
            ], props
            assert "+5%" in props[0] and "+10%" in props[1] and "+20%" in props[2]

    # 2) ladder 행: 3 horizon, ok, 새 판정 seq, 목표 시점·개월·연율
    bad: list[str] = []
    for cid in (RIVERFRONT, GOCHON):
        got = {h for (c, h) in rows if c == cid}
        if got != HORIZONS:
            bad.append(f"{cid}: horizons {sorted(got)}")
            continue
        for h, (ym, months) in EXPECTED[cid].items():
            lad = rows[(cid, h)]
            if (lad.target_ym, lad.months_from_asof) != (ym, months):
                bad.append(f"{cid}/{h}: target {lad.target_ym}/{lad.months_from_asof} != {ym}/{months}")
            if lad.status != "ok" or lad.judgment_seq is None or lad.judgment_seq <= 132:
                bad.append(f"{cid}/{h}: status {lad.status} seq {lad.judgment_seq}")
            want = _annual(months)
            ann = {k: (float(v) if v is not None else None) for k, v in (lad.annualized or {}).items()}
            if any(ann.get(k) is None or abs(ann[k] - want[k]) > 1e-4 for k in want):  # type: ignore[operator]
                bad.append(f"{cid}/{h}: annualized {ann} != {want}")
            if lad.p10 is None:
                bad.append(f"{cid}/{h}: p10 없음")
    assert not bad, "\n".join(bad)
    # asof_plus_3y(·5y) 목표 시점이 두 단지 동일, move_in_plus_1y 는 다르다
    assert (
        rows[(RIVERFRONT, "asof_plus_3y")].target_ym == rows[(GOCHON, "asof_plus_3y")].target_ym == "2029-10"
    )
    assert rows[(RIVERFRONT, "asof_plus_5y")].target_ym == rows[(GOCHON, "asof_plus_5y")].target_ym
    assert rows[(RIVERFRONT, "move_in_plus_1y")].target_ym != rows[(GOCHON, "move_in_plus_1y")].target_ym

    # 3) API: G3 상세 ladder 표(연율 열)·G4 비교 ladders
    for cid in (RIVERFRONT, GOCHON):
        api = _ladders_api(env, cid)
        assert set(api) == HORIZONS, (cid, sorted(api))
        for h, (ym, months) in EXPECTED[cid].items():
            view = api[h]
            assert (view["target_ym"], view["months_from_asof"], view["status"]) == (ym, months, "ok"), (
                cid,
                h,
                view,
            )
            assert view["annualized"] == pytest.approx(_annual(months), abs=1e-4), (cid, h)
            assert view["p10"]["label"] == "추정" and view["p10"]["prov"] == f"jl_{view['judgment_seq']}", (
                view["p10"]
            )
            assert view["target_label"], view
    cmp = api_get(env, f"/snapshots/{cur(env)}/compare", ids=f"{RIVERFRONT},{GOCHON}")
    by_h = {cid: {lad["horizon"]: lad for lad in cmp["ladders"][str(cid)]} for cid in (RIVERFRONT, GOCHON)}
    assert (
        by_h[RIVERFRONT]["asof_plus_3y"]["target_ym"]
        == by_h[GOCHON]["asof_plus_3y"]["target_ym"]
        == "2029-10"
    )
    assert (
        by_h[RIVERFRONT]["asof_plus_3y"]["months_from_asof"]
        == by_h[GOCHON]["asof_plus_3y"]["months_from_asof"]
        == 36
    )

"""T11 스위첸 비교군 대체 (RA §9) — 시스템 경계. CEO 결정 W5(2026-10-09, R3_FIX 'WP9 통합 발견 배정').

RA §9 기대 결과(원문): "`substitute=true`, 보정·미보정 중앙값 둘 다, 라벨 "추정(대체·보정 c=0.015)", C2에 점선 점".
W5: RA §6-2 규칙(준공 2020년 이후 = 신축) 유지. 대체 경로는 **스위첸 생활권을 사용자가 편집한 하위 생활권(장기·운양
법정동)으로 둔 픽스처 변형**(``raw/rtms/t11_switzen_subarea.json``)으로 본다 — 그 생활권 2020년 이후 준공 거래 0건 →
대체 = 가장 최근 준공 한강센트럴자이(2017) → 보정(c × min(2028 − 2017, 8) = 0.12). 리버시티(2020)는 신축이라 대체가 아니다.

경로: (변형) PUT /api/regions/1/living-areas 로 김포시 생활권에서 장기·운양을 떼어 하위 생활권을 만들고 스위첸을 그 생활권에
둔다(단지 배치는 법정동 자동 배정이므로 테스트 DB 사본에서 직접 — 사용자 편집 변형) → 김포 기존 거래 행을 비운 상태에서
POST /api/jobs ``collect.weekly``(rtms) → worker 가 실제 ``RtmsCollector``(재가공 폴백)로 픽스처 거래 적재 → rejudge(FakeJev)
→ comparable_set → GET /complexes/4?snapshot=… 의 ``gap``(C2 데이터)·출처 패널.

- ``test_t11a_*``: 픽스처 그대로(생활권 = 김포시 전체) — 리버시티(2020)·고촌 센트럴자이(2024)는 신축(1차 비교군), 대체 아님.
- ``test_t11b_*``: W5 변형 — comparable_set(DB)·API 값, API 라벨(adjusted_median, F3 W6).
- ``test_t11c_*``: W5 변형 — API 미보정 갭(gap_pct_unadjusted, F3 W7).
"""

# ruff: noqa: E501

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import pytest
from sqlalchemy import delete, select

from .conftest import FIXTURE, WRITE, RegressEnv, api_get, load_json

pytestmark = pytest.mark.regress

T11 = FIXTURE / "raw" / "rtms" / "t11_switzen_comparables.json"
T11_SUB = FIXTURE / "raw" / "rtms" / "t11_switzen_subarea.json"  # W5 변형
TARGET = 4  # 오퍼스 한강 스위첸(입주 2028-08 → Y_ref 2028)
GIMPO = "41570"
REASON = "대체·보정 c=0.015"


class FixtureTradeSource:
    """``ReprocessedTradeSource`` — 픽스처 거래를 월별 원문(JSON)으로 돌려준다(네트워크 없음)."""

    name = "regress-fixture"

    def __init__(self, trades: list[dict[str, Any]], legal_dong_code: str) -> None:
        self.trades = trades
        self.code = legal_dong_code

    def fetch_month(self, lawd_cd: str, deal_ym: str) -> Any:
        from app.core.http import FetchResult

        rows = [
            {**t, "legal_dong_code": t.get("legal_dong_code") or self.code}
            for t in self.trades
            if lawd_cd == GIMPO and t["deal_date"][:7].replace("-", "") == deal_ym
        ]
        body = json.dumps({"lawd": lawd_cd, "ym": deal_ym, "trades": rows}, ensure_ascii=False).encode(
            "utf-8"
        )
        return FetchResult(
            url=f"https://regress.invalid/rtms?lawd={lawd_cd}&ym={deal_ym}", status=200,
            headers={"content-type": "application/json"}, content=body, error=None, elapsed_ms=0, attempts=1,
        )  # fmt: skip

    def parse(self, content: bytes) -> list[Any]:
        from app.collectors.rtms.parse import TradeRecord

        return [
            TradeRecord(
                apt_name=t["apt_name"],
                dong=None,
                legal_dong_code=t["legal_dong_code"],
                completed_year=t["completed_year"],
                area_m2=Decimal(str(t["area_m2"])),
                floor=t["floor"],
                price_won=int(t["price_won"]),
                deal_date=t["deal_date"],
                cancelled=bool(t["cancelled"]),
                is_presale=bool(t["is_presale"]),
                source="reprocessed",
                label="재가공",
            )
            for t in json.loads(content)["trades"]
        ]


def _clear_gimpo_trades(env: RegressEnv) -> str:
    """전제: 김포 법정동(시군구 41570)의 기존 rtms_trade 행을 비운다(테스트 DB 사본) — 픽스처 거래만 남긴다. 대표 법정동 코드."""
    from app.models import Region, RtmsTrade

    with env.session() as s:
        region = s.get(Region, 1)
        assert region is not None
        codes = [c for c in region.legal_dong_codes or [] if c.startswith(GIMPO)]
        s.execute(delete(RtmsTrade).where(RtmsTrade.legal_dong_code.in_(codes)))
        s.commit()
        return "4157010100" if "4157010100" in codes else str(codes[0])


def _subarea(env: RegressEnv) -> tuple[str, dict[str, Any]]:
    """W5 변형: PUT /regions/1/living-areas — 김포시(la_4)에서 장기·운양을 떼어 하위 생활권 → 스위첸을 그 생활권에 둔다."""
    from app.models import Complex, Region

    doc = load_json(T11_SUB)
    edit = doc["living_area_edit"]
    with env.session() as s:
        region = s.get(Region, 1)
        assert region is not None
        areas = [dict(a) for a in region.living_areas]
    body = []
    for a in areas:
        codes = list(a["legal_dong_codes"])
        if a["id"] == edit["split_from"]:
            codes = [c for c in codes if c not in edit["new_area"]["legal_dong_codes"]]
        body.append({"id": a["id"], "name": a["name"], "legal_dong_codes": codes})
    body.append({"name": edit["new_area"]["name"], "legal_dong_codes": edit["new_area"]["legal_dong_codes"]})
    r = env.client.put("/api/regions/1/living-areas", headers=WRITE, json={"living_areas": body})
    assert r.status_code == 202, r.text  # 계약 .11(D14-5): 202 + job_id
    body_out = r.json()
    region_out = body_out.get("region", body_out)  # Region(+ change_event·rejudge 잡)
    new_id = next(a["id"] for a in region_out["living_areas"] if a["name"] == edit["new_area"]["name"])
    with env.session() as s:
        for cid in edit["complex_ids"]:
            cx = s.get(Complex, cid)
            assert cx is not None
            cx.living_area = new_id  # 사용자 편집 변형(소재 법정동 향산리는 그대로)
        s.commit()
    return str(new_id), doc


def _run(env: RegressEnv, trades: list[dict[str, Any]]) -> int:
    from app.collectors.rtms import RtmsCollector

    src = FixtureTradeSource(trades, _clear_gimpo_trades(env))

    def rtms(ctx: Any) -> Any:
        return RtmsCollector(service_key=None, fallback=src, months=12, raw_dir=env.tmp / "raw")

    r = env.client.post(
        "/api/jobs",
        headers=WRITE,
        json={"job_name": "collect.weekly", "payload": {"region_id": 1, "sources": ["rtms"]}},
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]
    env.worker(env.ctx("fake", collectors={"rtms": rtms}))
    weekly = api_get(env, f"/jobs/{job_id}")
    assert weekly["status"] == "done", weekly
    stats = weekly["stats"]
    assert stats["loaded"]["rtms"]["inserted"] == len(trades), stats
    rejudge = api_get(env, f"/jobs/{stats['rejudge_job_id']}")
    assert rejudge["status"] == "done", rejudge
    return int(stats["snapshot_id"])


def _members(env: RegressEnv, sid: int) -> dict[str, Any]:
    from app.models import ComparableSet

    with env.session() as s:
        rows = s.scalars(
            select(ComparableSet).where(ComparableSet.snapshot_id == sid, ComparableSet.complex_id == TARGET)
        ).all()
        return {r.member_apt_name: r for r in rows}


def _won(x: Decimal) -> int:
    return int(x.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def test_t11a_fixture_as_given_new_builds_not_substitute(env: RegressEnv) -> None:
    """픽스처 그대로(생활권 = 김포시 전체): 리버시티(2020)·고촌 센트럴자이(2024)는 RA §6-2 신축 → 1차 비교군(대체 아님, W5)."""
    trades = load_json(T11)["trades"]
    sid = _run(env, trades)
    members = _members(env, sid)
    assert {n for n in members} == {t["apt_name"] for t in trades}, sorted(members)
    for name, m in members.items():
        assert m.completed_year is not None and m.completed_year >= 2020, (name, m.completed_year)
        assert (m.substitute, m.adjusted, m.coef_used, m.adjusted_median_won) == (False, False, None, None), (
            name
        )


def _sub_run(env: RegressEnv) -> tuple[int, dict[str, Any], dict[str, Any]]:
    from app.models import Complex

    new_id, doc = _subarea(env)
    sid = _run(env, [*doc["trades"], *doc["outside_trades"]])
    with env.session() as s:
        cx = s.get(Complex, TARGET)
        assert cx is not None and cx.living_area == new_id, (cx.living_area if cx else None, new_id)
    return sid, doc, _members(env, sid)


def test_t11b_subarea_substitute_saved_with_both_medians(env: RegressEnv) -> None:
    """W5 변형 → comparable_set·API: 대체 = 한강센트럴자이 1·2단지(2017)만, substitute·adjusted, c×년수 0.12, 보정·미보정 중앙값."""
    sid, doc, members = _sub_run(env)
    exp = doc["expected"]
    assert set(members) == set(exp["substitute_members"]), sorted(
        members
    )  # 리버시티·고촌 센트럴자이(신축, 생활권 밖) 없음
    by_apt: dict[str, list[int]] = {}
    for t in doc["trades"]:
        by_apt.setdefault(t["apt_name"], []).append(t["price_won"])
    factor = Decimal("1") + Decimal(str(exp["coef_used"]))
    for name, m in members.items():
        prices = by_apt[name]
        assert m.completed_year == exp["substitute_completed_year"], (name, m.completed_year)
        assert (m.substitute, m.adjusted) == (True, True), name
        assert m.coef_used is not None and Decimal(m.coef_used) == Decimal("0.12"), (name, m.coef_used)
        assert m.median_won is not None and min(prices) <= m.median_won <= max(prices), (name, m.median_won)
        # 보정 중앙 = 미보정 중앙 × (1 + c·min(Y_ref − Y_built, 8)) (원 단위 반올림 ±1)
        assert m.adjusted_median_won is not None
        assert abs(m.adjusted_median_won - _won(Decimal(m.median_won) * factor)) <= 1, (
            name,
            m.adjusted_median_won,
        )
    gap = api_get(env, f"/complexes/{TARGET}", snapshot=sid)["gap"]
    comps = {c["name"]: c for c in gap["comps"]}
    assert set(comps) == set(exp["substitute_members"])
    for name, c in comps.items():
        assert c["substitute"] is True and c["adjusted"] is True, c
        assert c["median"]["v"] == members[name].median_won
        assert (
            c["adjusted_median"] is not None
            and c["adjusted_median"]["v"] == members[name].adjusted_median_won
        )
        assert c["adjusted_median"]["v"] > c["median"]["v"]
        assert c["coef_used"] == pytest.approx(0.12)  # 저장값 = c × min(Y_ref − Y_built, 8)
    for key in ("gap_pct", "score"):
        f = gap[key]
        assert f["v"] is not None, (key, f)
        assert (f["label"], f["reason"]) == (exp["label"], exp["reason"]), (key, f)
    formula = api_get(env, f"/provenance/{gap['score']['prov']}")["formula_text"] or ""
    assert "미보정 중앙" in formula and "c=0.015" in formula, formula


def test_t11b_api_adjusted_median_label(env: RegressEnv) -> None:
    """C2 점선 점(보정 중앙)의 라벨 = '추정(대체·보정 c=0.015)' — c 는 연 계수(region.age_premium_coef.c_per_year). F3 W6."""
    sid, _doc, _members = _sub_run(env)
    gap = api_get(env, f"/complexes/{TARGET}", snapshot=sid)["gap"]
    bad = {
        c["name"]: (c["adjusted_median"]["label"], c["adjusted_median"]["reason"])
        for c in gap["comps"]
        if (c["adjusted_median"]["label"], c["adjusted_median"]["reason"]) != ("추정", REASON)
    }
    assert not bad, (
        f"adjusted_median 라벨이 '추정({REASON})' 가 아님(연식 보정 총 배율 c×년수를 c 로 표기 — F3 W6): {bad}"
    )


def test_t11c_api_gap_shows_adjusted_and_unadjusted(env: RegressEnv) -> None:
    """'보정·미보정 둘 다' — 계약(GapView): gap_pct 는 보정 중앙값 기준, gap_pct_unadjusted 는 미보정 기준(둘 다 표시). F3 W7."""
    sid, _doc, _m = _sub_run(env)
    gap = api_get(env, f"/complexes/{TARGET}", snapshot=sid)["gap"]
    assert all(c["substitute"] for c in gap["comps"]), gap["comps"]
    assert gap["gap_pct"]["v"] is not None
    unadj = gap["gap_pct_unadjusted"]
    assert unadj is not None and unadj.get("v") is not None, (
        f"대체 비교군인데 API gap.gap_pct_unadjusted = {unadj!r} (gap_pct = {gap['gap_pct']['v']}) — F3 W7"
    )
    assert float(unadj["v"]) > float(gap["gap_pct"]["v"]), "미보정 중앙값이 더 낮으니 미보정 갭이 더 크다"

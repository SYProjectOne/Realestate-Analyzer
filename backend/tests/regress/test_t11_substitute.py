"""T11 스위첸 비교군 대체 (RA §9) — 시스템 경계.

RA §9 기대 결과(원문): "`substitute=true`, 보정·미보정 중앙값 둘 다, 라벨 "추정(대체·보정 c=0.015)", C2에 점선 점".
(픽스처: 신축 0건, 리버시티·센트럴자이 거래 = ``raw/rtms/t11_switzen_comparables.json``, 대상 complex_id 4)

경로: 생활권 la_4(김포시)의 기존 거래 행을 비운 상태(= 같은 생활권 신축 거래 0건)에서
POST /api/jobs ``collect.weekly``(rtms) → worker 가 실제 ``RtmsCollector``(재가공 폴백)로 픽스처 거래 적재 →
rejudge(FakeJev) → ``score_base``/``gap`` → ``persist.save_comparables`` → comparable_set →
GET /complexes/4?snapshot=… 의 ``gap``(C2 데이터)·출처 패널.

- ``test_t11a_fixture_as_given``: 픽스처 그대로(리버시티 준공 2020·센트럴자이 2024).
- ``test_t11b_*``: 같은 거래를 준공 2019 로 내린 변형(§6-2 '준공 2020년 이후'가 0건이 되도록) — 대체 경로의 저장·API.
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

        rows = [t for t in self.trades if lawd_cd == GIMPO and t["deal_date"][:7].replace("-", "") == deal_ym]
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
                legal_dong_code=self.code,
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


def _clear_living_area_trades(env: RegressEnv, la_id: str) -> str:
    """전제 '같은 생활권 신축 거래 0건': la_4 법정동의 기존 rtms_trade 행을 비운다(테스트 DB 사본). 대표 법정동 코드를 돌려준다."""
    from app.models import Region, RtmsTrade

    with env.session() as s:
        region = s.get(Region, 1)
        assert region is not None
        codes = next(a for a in region.living_areas if a["id"] == la_id)["legal_dong_codes"]
        s.execute(delete(RtmsTrade).where(RtmsTrade.legal_dong_code.in_(codes)))
        s.commit()
        return str(codes[0])


def _run(env: RegressEnv, trades: list[dict[str, Any]]) -> int:
    from app.collectors.rtms import RtmsCollector

    src = FixtureTradeSource(trades, _clear_living_area_trades(env, "la_4"))

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


def _older(trades: list[dict[str, Any]], year: int = 2019) -> list[dict[str, Any]]:
    return [{**t, "completed_year": year} for t in trades]


def test_t11a_fixture_as_given_substitute(env: RegressEnv) -> None:
    """픽스처 그대로 → RA §9: 리버시티·센트럴자이 = 대체(substitute=true) 비교군."""
    trades = load_json(T11)["trades"]
    sid = _run(env, trades)
    members = _members(env, sid)
    assert {n for n in members} == {t["apt_name"] for t in trades}, sorted(members)
    years = {n: m.completed_year for n, m in members.items()}
    flags = {
        n: (m.substitute, m.adjusted, None if m.coef_used is None else float(m.coef_used))
        for n, m in members.items()
    }
    assert all(m.substitute and m.adjusted for m in members.values()), (
        "RA §9 T11: 신축 0건 → 리버시티·센트럴자이 substitute=true 여야 함. "
        f"실제 (substitute, adjusted, coef) = {flags}, 준공 연도 = {years}. "
        "app/analysis/gap.py NEW_BUILD_YEAR=2020(RA §6-2 '준공 2020년 이후')이라 픽스처 준공 2020·2024 는 신축(1차 비교군)으로 잡힌다"
    )


def test_t11b_substitute_saved_with_both_medians_and_label(env: RegressEnv) -> None:
    """대체 경로(준공 2019 변형): comparable_set·API 에 substitute·보정/미보정 중앙값·라벨 '추정(대체·보정 c=0.015)'."""
    trades = _older(load_json(T11)["trades"])
    sid = _run(env, trades)
    members = _members(env, sid)
    by_apt: dict[str, list[int]] = {}
    for t in trades:
        by_apt.setdefault(t["apt_name"], []).append(t["price_won"])
    assert set(members) == set(by_apt), sorted(members)
    factor = Decimal("1") + Decimal("0.015") * 8  # Y_ref 2028 − 2019 = 9 → 상한 8년
    for name, m in members.items():
        prices = by_apt[name]
        assert (m.substitute, m.adjusted) == (True, True), name
        assert m.coef_used is not None and Decimal(m.coef_used) == Decimal("0.12"), (name, m.coef_used)
        assert m.median_won is not None and min(prices) <= m.median_won <= max(prices), (name, m.median_won)
        # 보정 중앙 = 미보정 중앙 × (1 + c·min(Y_ref − Y_built, 8)) (원 단위 반올림 ±1)
        assert (
            m.adjusted_median_won is not None
            and abs(m.adjusted_median_won - _won(Decimal(m.median_won) * factor)) <= 1
        ), (name, m.adjusted_median_won)

    body = api_get(env, f"/complexes/{TARGET}", snapshot=sid)
    gap = body["gap"]
    # C2: 비교 단지마다 미보정 중앙(median)·보정 중앙(adjusted_median, 점선 점)·대체 배지
    comps = {c["name"]: c for c in gap["comps"]}
    assert set(comps) == set(by_apt)
    for name, c in comps.items():
        assert c["substitute"] is True and c["adjusted"] is True, c
        assert c["median"]["v"] == members[name].median_won
        adj = c["adjusted_median"]
        assert adj is not None and adj["v"] == members[name].adjusted_median_won, c
        assert adj["v"] > c["median"]["v"]
        assert adj["label"] == "추정", adj
        assert c["coef_used"] == pytest.approx(0.12)  # 저장값 = c × min(Y_ref − Y_built, 8)
    # 가격 갭 값·점수 라벨 = 추정(대체·보정 c=0.015)
    for key in ("gap_pct", "score"):
        f = gap[key]
        assert f["v"] is not None, (key, f)
        assert (f["label"], f["reason"]) == ("추정", REASON), (key, f)
    formula = api_get(env, f"/provenance/{gap['score']['prov']}")["formula_text"] or ""
    assert "미보정 중앙" in formula and "c=0.015" in formula, formula
    # C2 점선 점(보정 중앙)의 라벨도 같은 '추정(대체·보정 c=0.015)' — c 는 연 계수(region.age_premium_coef.c_per_year)
    bad = {
        n: c["adjusted_median"]["reason"]
        for n, c in comps.items()
        if c["adjusted_median"]["reason"] != REASON
    }
    assert not bad, (
        f"adjusted_median.reason 이 '{REASON}' 가 아님(연식 보정 총 배율 c×년수를 c 로 표기): {bad}"
    )


def test_t11c_api_gap_shows_adjusted_and_unadjusted(env: RegressEnv) -> None:
    """'보정·미보정 둘 다' — 계약(GapView): gap_pct 는 보정 중앙값 기준, gap_pct_unadjusted 는 미보정 기준(둘 다 표시)."""
    trades = _older(load_json(T11)["trades"])
    sid = _run(env, trades)
    gap = api_get(env, f"/complexes/{TARGET}", snapshot=sid)["gap"]
    assert all(c["substitute"] for c in gap["comps"]), gap["comps"]
    assert gap["gap_pct"]["v"] is not None
    unadj = gap["gap_pct_unadjusted"]
    assert unadj is not None and unadj.get("v") is not None, (
        f"대체 비교군인데 API gap.gap_pct_unadjusted = {unadj!r} (gap_pct = {gap['gap_pct']['v']})"
    )
    assert float(unadj["v"]) > float(gap["gap_pct"]["v"]), "미보정 중앙값이 더 낮으니 미보정 갭이 더 크다"

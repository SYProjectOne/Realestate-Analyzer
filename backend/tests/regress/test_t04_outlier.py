"""T4 메트로자이 2단지 "11억" 타입 오류 의심 (RA §9) — 시스템 경계.

RA §9 기대 결과(원문): "`gap.py` 이상치 규칙(중앙값 대비 1.5×IQR 밖) → 비교군에서 제외 + `comparable_set`에
"이상치 제외" 기록; 원본 행은 삭제 안 함".

경로: POST /api/jobs ``collect.weekly``(sources=[rtms]) → worker(``runner.main --once``)가 실제 ``RtmsCollector``
(키 없음 → 재가공 폴백 경로)로 픽스처 ``raw/rtms/t4_metroxi2_84.json`` 거래를 받아 ``rtms_trade`` 에 적재 →
시장 변경 → rejudge 잡(FakeJev) → 파이프라인 점수 → ``persist.save_comparables`` → comparable_set →
API(GET /complexes/{id}·GET /provenance/cs_…)와 DB 행으로 확인한다.
"""

# ruff: noqa: E501

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select

from .conftest import FIXTURE, WRITE, RegressEnv, api_get, load_json

pytestmark = pytest.mark.regress

T4 = FIXTURE / "raw" / "rtms" / "t4_metroxi2_84.json"
APT = "한강메트로자이 2단지"
OUTLIER_WON = 1_100_000_000
TARGET = 4  # 오퍼스 한강 스위첸 — 같은 생활권(la_4, 김포시)
GIMPO = "41570"


class FixtureTradeSource:
    """``ReprocessedTradeSource`` — 재가공 원천 대신 픽스처 거래를 월별 원문(JSON)으로 돌려준다(네트워크 없음)."""

    name = "regress-fixture"

    def __init__(self, trades: list[dict[str, Any]], legal_dong_code: str) -> None:
        self.trades = trades
        self.code = legal_dong_code
        self.months: list[tuple[str, str]] = []

    def fetch_month(self, lawd_cd: str, deal_ym: str) -> Any:
        from app.core.http import FetchResult

        self.months.append((lawd_cd, deal_ym))
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

        out = []
        for t in json.loads(content)["trades"]:
            out.append(
                TradeRecord(
                    apt_name=t["apt_name"], dong=None, legal_dong_code=self.code,
                    completed_year=t["completed_year"], area_m2=Decimal(str(t["area_m2"])), floor=t["floor"],
                    price_won=int(t["price_won"]), deal_date=t["deal_date"], cancelled=bool(t["cancelled"]),
                    is_presale=bool(t["is_presale"]), source="reprocessed", label="재가공",
                )
            )  # fmt: skip
        return out


def _la_code(env: RegressEnv, la_id: str) -> str:
    from app.models import Region

    with env.session() as s:
        region = s.get(Region, 1)
        assert region is not None
        area = next(a for a in region.living_areas if a["id"] == la_id)
        return str(area["legal_dong_codes"][0])


def _weekly_rtms(env: RegressEnv, trades: list[dict[str, Any]]) -> dict[str, Any]:
    """collect.weekly(rtms) 를 API 로 넣고 worker 로 돌린다 → (주간 잡, 후속 rejudge 잡) 상태."""
    from app.collectors.rtms import RtmsCollector

    src = FixtureTradeSource(trades, _la_code(env, "la_4"))

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
    rj_id = stats.get("rejudge_job_id")
    assert rj_id, f"시장 자료 변경 → rejudge 잡 없음: {stats}"
    rejudge = api_get(env, f"/jobs/{rj_id}")
    assert rejudge["status"] == "done", rejudge
    return {"snapshot_id": stats["snapshot_id"], "weekly": weekly, "rejudge": rejudge, "source": src}


def test_t04_outlier_excluded_recorded_and_raw_row_kept(env: RegressEnv) -> None:
    from app.models import ComparableSet, RtmsTrade

    doc = load_json(T4)
    trades = doc["trades"]
    assert sum(1 for t in trades if t["price_won"] == OUTLIER_WON) == 1
    with env.session() as s:
        before = s.scalars(
            select(RtmsTrade).where(RtmsTrade.apt_name == APT, RtmsTrade.price_won == OUTLIER_WON)
        ).all()
        assert before == [], "전제: 11억 거래는 아직 DB 에 없다(devseed 미적재)"

    run = _weekly_rtms(env, trades)
    sid = run["snapshot_id"]
    assert sid > 12, run["weekly"]["stats"]

    # 1) 원본 행은 삭제·변경 안 함: 11억 거래 행이 그대로 남는다(cancelled=false, 재가공 원문 연결)
    with env.session() as s:
        rows = s.scalars(
            select(RtmsTrade).where(RtmsTrade.apt_name == APT, RtmsTrade.price_won == OUTLIER_WON)
        ).all()
        assert len(rows) == 1, rows
        raw11 = rows[0]
        assert (raw11.deal_date, raw11.cancelled, raw11.source) == ("2026-09-24", False, "reprocessed")
        assert raw11.raw_document_id is not None
        n_fixture_rows = len(
            s.scalars(
                select(RtmsTrade.id).where(RtmsTrade.apt_name == APT, RtmsTrade.area_m2 == Decimal("84.00"))
            ).all()
        )
        assert n_fixture_rows == len(trades)

        # 2) comparable_set: 이 스냅샷·이 단지 비교군에서 1건 제외 + '이상치 제외' 기록
        cs = s.scalars(
            select(ComparableSet).where(
                ComparableSet.snapshot_id == sid,
                ComparableSet.complex_id == TARGET,
                ComparableSet.member_apt_name == APT,
            )
        ).all()
        assert len(cs) == 1, f"comparable_set 에 {APT} 행이 없음(snapshot {sid}, complex {TARGET})"
        m = cs[0]
        assert m.outliers_excluded == 1, (m.outliers_excluded, m.note)
        assert m.excluded_reason == "이상치 제외"
        assert m.note and "11억" in m.note and "2026-09-24" in m.note and f"id {raw11.id}" in m.note, m.note
        assert m.high_won == 680_000_000, "11억은 비교군 가격 범위에서 빠진다"
        assert m.substitute is False

    # 3) API: 상세 C2 데이터(비교 단지 열)와 출처 패널(cs_)
    body = api_get(env, f"/complexes/{TARGET}", snapshot=sid)
    comps = {c["name"]: c for c in body["gap"]["comps"]}
    assert APT in comps, sorted(comps)
    c = comps[APT]
    assert c["outliers_excluded"] == 1
    assert c["high"]["v"] == 680_000_000 and c["high"]["prov"] == f"cs_{m.id}"
    panel = api_get(env, f"/provenance/cs_{m.id}")
    assert panel["kind"] == "comparable_set" and panel["reason"] == "이상치 제외", panel
    assert "11억" in (panel["excerpt"] or ""), panel
    # 가격 갭 식에도 제외 건수가 남는다(score_component.formula_text → sc_ 출처 패널)
    gap_prov = body["gap"]["score"]["prov"]
    assert gap_prov and gap_prov.startswith("sc_"), body["gap"]["score"]
    formula = api_get(env, f"/provenance/{gap_prov}")["formula_text"] or ""
    assert "이상치 제외" in formula, formula

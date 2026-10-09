"""R3 F1a: 수집 뒤 데이터 조립(``scheduler/assemble.py``) — collect.weekly → 벤치마크(C1), collect.daily →
잔여 공고 이력(M5)·체크리스트(M7), 뉴스 → 호재 후보(M6).

수집기는 가짜다(네트워크 없음). 벤치마크 원천은 수집기의 ``fetch_history``(청약홈 과거 공고)·``backfill``(rtms 과거 월).
"""

# ruff: noqa: E501  (한국어 docstring·픽스처 행)

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.collectors.applyhome import api as ah_api
from app.core.contracts_gen import RawDocument as RawDTO
from app.core.contracts_gen import Region as RegionDTO
from app.core.contracts_gen import Snapshot as SnapshotDTO
from app.core.snapshot import store_raw
from app.models import (
    Benchmark,
    Catalyst,
    ChangeEvent,
    ChecklistItem,
    Complex,
    LegalDong,
    RawDocument,
    RemainingEvent,
    RtmsTrade,
)
from app.normalize.store import raw_dto
from app.scheduler.assemble import BENCHMARK_HISTORY_YEARS, RTMS_BACKFILL_MONTHS
from app.scheduler.collect import collect
from app.scheduler.context import SchedulerContext

from .conftest import Clock, seed_region, seed_scenarios

SONGDO = "2818510600"
ADDR = "인천광역시 연수구 송도동 1"


def _seed(factory: sessionmaker[Session]) -> None:
    with factory() as s:
        seed_scenarios(s)
        seed_region(s)
        s.add(
            LegalDong(
                code=SONGDO, sido_name="인천광역시", sigungu_name="연수구", eupmyeondong_name="송도동",
                ri_name=None, full_name="인천광역시 연수구 송도동", sigungu_code="28185", active=True,
                source_date="2026-09-01",
            )
        )  # fmt: skip
        s.commit()


def _save(s: Session, content: str, *, source_kind: str, url: str, region_id: int, ext: str = "json") -> RawDTO:
    data = content.encode("utf-8")
    sha = hashlib.sha256(data).hexdigest()
    row = s.scalars(select(RawDocument).where(RawDocument.sha256 == sha)).first()
    if row is None:
        stored = store_raw(data, source=source_kind, day=date(2026, 10, 8), ext=ext)
        row = RawDocument(
            source_kind=source_kind, url=url, fetched_at="2026-10-08T06:00:00+09:00", http_status=200,
            sha256=stored.sha256, path=stored.relpath, content_type="application/json", region_id=region_id,
        )  # fmt: skip
        s.add(row)
        s.flush()
    return raw_dto(row)


def _page(rows: list[dict[str, Any]]) -> str:
    return json.dumps({"data": rows, "matchCount": len(rows), "page": 1, "perPage": 100}, ensure_ascii=False)


@dataclass
class FakeApplyhome:
    factory: sessionmaker[Session]
    daily_docs: Callable[[Session], list[RawDTO]] = lambda s: []
    history_calls: list[int] = field(default_factory=list)

    def fetch(self, region: RegionDTO, snapshot: SnapshotDTO, since: str | None) -> list[RawDTO]:
        with self.factory() as s:
            out = self.daily_docs(s)
            s.commit()
        return out

    def fetch_history(self, region: RegionDTO, snapshot: SnapshotDTO, *, years: int) -> list[RawDTO]:
        self.history_calls.append(years)
        row = {
            "HOUSE_MANAGE_NO": "2021000101", "PBLANC_NO": "2021000101", "HOUSE_NM": "송도 테스트 1차",
            "HSSPLY_ADRES": ADDR, "RCRIT_PBLANC_DE": "2021-03-10", "MVN_PREARNGE_YM": "202406",
            "HOUSE_DTL_SECD_NM": "민영", "SUBSCRPT_AREA_CODE_NM": "인천",
        }  # fmt: skip
        model = {"HOUSE_MANAGE_NO": "2021000101", "PBLANC_NO": "2021000101", "HOUSE_TY": "084.9000A", "LTTOT_TOP_AMOUNT": "70000"}
        with self.factory() as s:
            lst = _save(
                s, _page([row]), source_kind="applyhome_list", region_id=region.id,
                url=ah_api.doc_url(ah_api.ENDPOINTS["apt"].detail, ah_api.list_params("apt", "인천", date(2016, 10, 1), date(2026, 10, 8), 1)),
            )  # fmt: skip
            mdl = _save(
                s, _page([model]), source_kind="applyhome_detail", region_id=region.id,
                url=ah_api.doc_url(ah_api.ENDPOINTS["apt"].model, ah_api.item_params("2021000101", "2021000101")),
            )  # fmt: skip
            s.commit()
        return [lst, mdl]


@dataclass
class FakeRtms:
    factory: sessionmaker[Session]
    backfill_calls: list[int] = field(default_factory=list)

    def fetch(self, region: RegionDTO, snapshot: SnapshotDTO, since: str | None) -> list[RawDTO]:
        return []

    def backfill(self, region: RegionDTO, snapshot: SnapshotDTO, *, months: int) -> list[RawDTO]:
        self.backfill_calls.append(months)
        with self.factory() as s:
            if s.scalars(select(RtmsTrade)).first() is None:
                for price, day in ((80000, "2026-01-10"), (90000, "2026-05-10"), (100000, "2026-09-10")):
                    s.add(
                        RtmsTrade(
                            region_id=region.id, apt_name="송도테스트1차", legal_dong_code=SONGDO, completed_year=2024,
                            area_m2=Decimal("84.90"), floor=5, price_won=price * 10_000, deal_date=day,
                            cancelled=False, is_presale=False, source="openapi",
                        )
                    )  # fmt: skip
            s.commit()
        return []


def test_weekly_collect_assembles_benchmarks(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], clock: Clock
) -> None:
    _seed(factory)
    ah, rt = FakeApplyhome(factory), FakeRtms(factory)
    ctx = make_ctx(collectors={"applyhome": lambda c: ah, "rtms": lambda c: rt})
    res = collect(ctx, 1, ["rtms"], asof_date="2026-10-08")

    assert ah.history_calls == [BENCHMARK_HISTORY_YEARS] and rt.backfill_calls == [RTMS_BACKFILL_MONTHS]
    with factory() as s:
        rows = list(s.scalars(select(Benchmark).order_by(Benchmark.id)))
        own = [b for b in rows if b.living_area == "la_1"]
        assert [(b.name, b.sale_price_84_won, b.trade_median_won, b.sale_period) for b in own] == [
            ("송도 테스트 1차", 700_000_000, 900_000_000, "저가 분양기")
        ]
        assert {b.living_area for b in rows} == {"la_1", "la_2", "la_3", "la_4"}  # 나머지는 지역 전체 대체
        events = list(s.scalars(select(ChangeEvent).where(ChangeEvent.id.in_(res.change_event_ids))))
        assert [(e.entity, e.severity) for e in events] == [("benchmark", "notice")]
    st = res.stats()["assembled"]["benchmark"]
    assert st["samples"] == {"la_1": 1, "la_2": 0, "la_3": 0, "la_4": 0}
    assert st["substituted"] == ["la_2", "la_3", "la_4"]
    assert res.errors == {}

    again = collect(ctx, 1, ["rtms"], asof_date="2026-10-08")
    assert again.stats()["assembled"]["benchmark"]["inserted"] == 0
    assert again.change_event_ids == []


def test_benchmark_error_is_recorded_and_does_not_stop_collect(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], clock: Clock
) -> None:
    _seed(factory)

    class Broken(FakeApplyhome):
        def fetch_history(self, region: RegionDTO, snapshot: SnapshotDTO, *, years: int) -> list[RawDTO]:
            raise RuntimeError("history down")

    ctx = make_ctx(collectors={"applyhome": lambda c: Broken(factory), "rtms": lambda c: FakeRtms(factory)})
    res = collect(ctx, 1, ["rtms"], asof_date="2026-10-08")
    assert "history down" in res.errors["assemble.benchmark_history"]
    assert "benchmark" in res.stats()["assembled"]  # 받은 자료만으로라도 조립은 돈다


def _daily_docs(s: Session) -> list[RawDTO]:
    apt = {
        "HOUSE_MANAGE_NO": "2025000777", "PBLANC_NO": "2025000777", "HOUSE_NM": "송도 바다 아파트",
        "HSSPLY_ADRES": ADDR, "RCRIT_PBLANC_DE": "2025-12-01", "MVN_PREARNGE_YM": "202812",
        "PRZWNER_PRESNATN_DE": "2025-12-20", "TOT_SUPLY_HSHLDCO": 500, "HOUSE_DTL_SECD_NM": "민영",
    }  # fmt: skip
    rem = {
        "HOUSE_MANAGE_NO": "2026910500", "PBLANC_NO": "2026910500", "HOUSE_NM": "송도 바다 아파트(2차)",
        "HOUSE_SECD": "04", "HSSPLY_ADRES": ADDR, "RCRIT_PBLANC_DE": "2026-09-30",
        "SUBSCRPT_RCEPT_BGNDE": "2026-10-12", "SUBSCRPT_RCEPT_ENDDE": "2026-10-12", "TOT_SUPLY_HSHLDCO": 2,
    }  # fmt: skip
    return [
        _save(s, _page([apt]), source_kind="applyhome_detail", region_id=1,
              url=ah_api.doc_url(ah_api.ENDPOINTS["apt"].detail, ah_api.item_params("2025000777", "2025000777"))),
        _save(s, _page([rem]), source_kind="applyhome_detail", region_id=1,
              url=ah_api.doc_url(ah_api.ENDPOINTS["remndr"].detail, ah_api.item_params("2026910500", "2026910500"))),
    ]  # fmt: skip


def test_daily_collect_assembles_remaining_events_and_checklist(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], clock: Clock
) -> None:
    _seed(factory)
    ah = FakeApplyhome(factory, daily_docs=_daily_docs)
    ctx = make_ctx(collectors={"applyhome": lambda c: ah})
    clock.day = date(2026, 10, 8)
    res = collect(ctx, 1, ["applyhome_list"])
    with factory() as s:
        original = s.scalars(select(Complex).where(Complex.applyhome_id == "2025000777")).one()
        [ev] = s.scalars(select(RemainingEvent)).all()
        assert (ev.complex_id, ev.kind, ev.notice_no, ev.apply_dates) == (original.id, "무순위", "2026910500", ["2026-10-12"])
        items = s.scalars(select(ChecklistItem).where(ChecklistItem.complex_id == original.id)).all()
        assert {i.kind for i in items} >= {"법적 확인"}
        crit = s.scalars(select(ChangeEvent).where(ChangeEvent.entity == "remaining_event")).all()
        assert [c.id for c in crit if c.severity == "critical"] and all(c.id in res.change_event_ids for c in crit)
    st = res.stats()["assembled"]
    assert st["remaining"]["inserted"] == 1 and st["checklist"]["inserted"] >= 2
    assert ah.history_calls == []  # 일일 수집은 과거 공고를 받지 않는다


@dataclass
class FakeNews:
    factory: sessionmaker[Session]

    def fetch(self, region: RegionDTO, snapshot: SnapshotDTO, since: str | None) -> list[RawDTO]:
        body = {"items": [{"title": "송도 트램 기본계획", "originallink": "https://news.example.com/1", "description": "발췌"}]}
        with self.factory() as s:
            doc = _save(s, json.dumps(body, ensure_ascii=False), source_kind="news", region_id=region.id,
                        url="https://naverapihub.apigw.ntruss.com/search/v1/news?query=q")  # fmt: skip
            s.commit()
        return [doc]


def test_weekly_news_becomes_catalyst_candidates(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], clock: Clock
) -> None:
    _seed(factory)
    ctx = make_ctx(collectors={"news": lambda c: FakeNews(factory)})
    res = collect(ctx, 1, ["news"], asof_date="2026-10-08")
    with factory() as s:
        [cat] = s.scalars(select(Catalyst)).all()
        assert (cat.name, cat.stage, cat.location_confirmed) == ("송도 트램 기본계획", "미확정", False)
    assert res.stats()["assembled"]["catalyst"] == {"inserted": 1, "existing": 0}

"""D31-3: 주간 수집 조립 — 2020년 이전 분양 단지마다 뉴스 '<이름> 분양가' 1회 검색 → 판정기 P2 extract → 벤치마크 행.

수집기·판정기는 가짜다(네트워크 없음). 판정기(SynthJev)는 extract 필드 값을 그대로 auto 로 돌려준다.
"""

# ruff: noqa: E501  (한국어 docstring·픽스처 행)

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.contracts_gen import RawDocument as RawDTO
from app.core.contracts_gen import Region as RegionDTO
from app.core.contracts_gen import Snapshot as SnapshotDTO
from app.models import Benchmark, FieldProvenance, RtmsTrade
from app.scheduler.collect import collect
from app.scheduler.context import SchedulerContext

from .conftest import Clock, SynthJev
from .test_assemble_f1a import SONGDO, FakeApplyhome, FakeRtms, _save, _seed

ARTICLE = "https://news.example.com/a/1"
OLD = "송도옛단지더베뉴"


@dataclass
class FakeRtmsWithOld(FakeRtms):
    def backfill(self, region: RegionDTO, snapshot: SnapshotDTO, *, months: int) -> list[RawDTO]:
        out = super().backfill(region, snapshot, months=months)
        with self.factory() as s:
            if s.scalars(select(RtmsTrade).where(RtmsTrade.apt_name == OLD)).first() is None:
                doc = _save(
                    s,
                    "<response>old</response>",
                    source_kind="rtms",
                    url="https://apis.example/rtms?LAWD_CD=28185",
                    region_id=region.id,
                    ext="xml",
                )
                for price, day in ((60000, "2026-01-10"), (62000, "2026-06-10")):
                    s.add(
                        RtmsTrade(
                            region_id=region.id, apt_name=OLD, legal_dong_code=SONGDO, completed_year=2021,
                            area_m2=Decimal("84.90"), floor=7, price_won=price * 10_000, deal_date=day,
                            cancelled=False, is_presale=False, source="openapi", raw_document_id=doc.id,
                        )
                    )  # fmt: skip
            s.commit()
        return out


@dataclass
class FakeNews:
    factory: sessionmaker[Session]
    queries: list[str] = field(default_factory=list)
    enabled: bool = True

    def fetch(self, region: RegionDTO, snapshot: SnapshotDTO, since: str | None) -> list[RawDTO]:
        return []

    def search_url(self, query: str, *, sort: str = "sim", display: int = 10) -> str:
        return "https://news.example/search?" + urlencode({"query": query, "sort": sort, "display": display})

    def search(
        self, region: RegionDTO, queries: list[str], *, sort: str = "sim", display: int = 10
    ) -> list[RawDTO]:
        self.queries.extend(queries)
        body = {
            "items": [
                {
                    "title": "'송도 옛단지 더 베뉴' 견본주택", "originallink": ARTICLE, "link": ARTICLE,
                    "description": "전용 84㎡ 3억8820만~4억1320만원", "pubDate": "Fri, 06 Dec 2019 10:00:00 +0900",
                }
            ]
        }  # fmt: skip
        with self.factory() as s:
            docs = [
                _save(
                    s,
                    json.dumps({**body, "query": q}, ensure_ascii=False),
                    source_kind="news",
                    url=self.search_url(q),
                    region_id=region.id,
                )
                for q in queries
            ]
            s.commit()
        return docs


def test_weekly_collect_adds_news_priced_benchmark_once(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], clock: Clock, jev: SynthJev
) -> None:
    _seed(factory)
    jev.extract_values["price_84"] = "4억1320만원"
    news = FakeNews(factory)
    ctx = make_ctx(
        collectors={
            "applyhome": lambda c: FakeApplyhome(factory), "rtms": lambda c: FakeRtmsWithOld(factory),
            "news": lambda c: news,
        }
    )  # fmt: skip
    res = collect(ctx, 1, ["rtms"], asof_date="2026-10-08")
    assert res.errors == {}
    st = res.stats()["assembled"]["benchmark_news"]
    assert (st["targets"], st["searched"], st["prices"]) == (1, 1, 1)
    assert news.queries == [f"인천 {OLD} 분양가"]
    with factory() as s:
        row = s.scalars(select(Benchmark).where(Benchmark.name == OLD, Benchmark.living_area == "la_1")).one()
        assert (row.sale_price_84_won, row.sale_price_label, row.sale_year, row.completed_year) == (
            413_200_000,
            "비공식",
            2019,
            2021,
        )
        sale = s.scalars(
            select(FieldProvenance).where(
                FieldProvenance.entity_id == row.id,
                FieldProvenance.field == "sale_price_84_won",
                FieldProvenance.chosen.is_(True),
            )
        ).one()
        assert sale.url == ARTICLE
    assert res.stats()["assembled"]["benchmark"]["news"] == 1

    again = collect(ctx, 1, ["rtms"], asof_date="2026-10-08")
    assert news.queries == [f"인천 {OLD} 분양가"]  # 받은 원문을 다시 쓴다(검색 1회)
    assert again.stats()["assembled"]["benchmark"]["inserted"] == 0


def test_without_news_search_benchmark_is_built_as_before(
    make_ctx: Callable[..., SchedulerContext], factory: sessionmaker[Session], clock: Clock
) -> None:
    _seed(factory)
    ctx = make_ctx(
        collectors={"applyhome": lambda c: FakeApplyhome(factory), "rtms": lambda c: FakeRtmsWithOld(factory)}
    )
    res = collect(ctx, 1, ["rtms"], asof_date="2026-10-08")
    assert res.stats()["assembled"]["benchmark_news"] == {"skipped": "뉴스 수집기에 검색 없음(또는 키 없음)"}
    assert res.stats()["assembled"]["benchmark"]["samples"]["la_1"] == 1

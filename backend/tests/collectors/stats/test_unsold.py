"""stats: 미분양 월별(통계누리 녹화) → unsold (합계·준공 후, 시군구 코드 매칭, 멱등)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.collectors.reference.legal_dong import parse_legal_dong_zip
from app.collectors.reference.load import upsert_legal_dongs
from app.collectors.stats.unsold import (
    MOLIT_DATA_URL,
    SigunguResolver,
    UnsoldCollector,
    merge_unsold,
    parse_unsold_post_completion,
    parse_unsold_total,
    sido_abbrev,
)
from app.core.contracts_gen import Region, Snapshot
from app.core.http import HttpClient
from app.models import RawDocument, Unsold


@pytest.fixture
def legal_dongs(db_engine: Engine, reference_copy: Path) -> Iterator[None]:
    with Session(db_engine) as s:
        upsert_legal_dongs(
            s,
            parse_legal_dong_zip((reference_copy / "legal_dong_full.zip").read_bytes()),
            source_date="2026-10-09",
        )
        s.commit()
    yield


def test_parse_total_and_post_completion(fixtures_dir: Path) -> None:
    total = parse_unsold_total((fixtures_dir / "molit_unsold_2082_202608.json").read_bytes())
    post = parse_unsold_post_completion((fixtures_dir / "molit_unsold_5328_202608.json").read_bytes())
    t = {(r.sido, r.sigungu): r.value for r in total}
    p = {(r.sido, r.sigungu): r.value for r in post}
    assert t[("인천", "연수구")] == 505
    assert t[("인천", "검단구")] == 737
    assert t[("경기", "김포시")] == 787
    assert p[("인천", "영종구")] == 280
    assert ("인천", "계") not in t and ("인천", "계") not in p  # 시도 합계 행 제외
    assert {r.ym for r in total} == {"2026-08"}
    assert parse_unsold_total((fixtures_dir / "molit_unsold_2082_202609.json").read_bytes()) == []  # 미공표
    assert parse_unsold_total(b"<html>error</html>") == []


@pytest.mark.parametrize(
    ("name", "short"),
    [
        ("인천광역시", "인천"),
        ("경기도", "경기"),
        ("충청북도", "충북"),
        ("경상남도", "경남"),
        ("전북특별자치도", "전북"),
        ("강원특별자치도", "강원"),
        ("세종특별자치시", "세종"),
        ("서울특별시", "서울"),
    ],
)
def test_sido_abbrev(name: str, short: str) -> None:
    assert sido_abbrev(name) == short


@pytest.mark.usefixtures("legal_dongs")
def test_resolver_maps_names_to_sigungu_codes(db_engine: Engine, fixtures_dir: Path) -> None:
    with Session(db_engine) as s:
        resolver = SigunguResolver(s)
        assert resolver.resolve("인천", "연수구") == "28185"
        assert resolver.resolve("경기", "김포시") == "41570"
        assert resolver.resolve("인천", "검단구") == "28290"
        assert resolver.resolve("인천", "서구") == "28260"  # 분구 전 이름(폐지 코드)
        assert resolver.resolve("부산", "서구") == "26140"  # 같은 이름 다른 시도
        assert resolver.resolve("세종", "세종시") == "36110"  # 시군구 없는 시
        records, unresolved = merge_unsold(
            resolver,
            parse_unsold_total((fixtures_dir / "molit_unsold_2082_202608.json").read_bytes()),
            parse_unsold_post_completion((fixtures_dir / "molit_unsold_5328_202608.json").read_bytes()),
        )
    yeonsu = next(r for r in records if r.scope_code == "28185")
    assert (yeonsu.ym, yeonsu.total) == ("2026-08", 505)
    assert yeonsu.post_completion is not None
    assert len(records) > 200
    assert unresolved == []


def _route(fx: Path) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        form = request.url.params.get("formId")
        name = "molit_unsold_2082_202608.json" if form == "2082" else "molit_unsold_5328_202608.json"
        return httpx.Response(
            200, content=(fx / name).read_bytes(), headers={"content-type": "application/text"}
        )

    return handler


@pytest.mark.usefixtures("legal_dongs")
def test_collector_loads_region_sigungu_only_and_is_idempotent(
    db_engine: Engine,
    region_ctx: tuple[Region, Snapshot],
    fixtures_dir: Path,
    http: HttpClient,
    count: Callable[[type[Any]], int],
) -> None:
    region, snapshot = region_ctx
    sept = snapshot.model_copy(update={"asof_date": "2026-09-15"})  # 전월 2026-08 통계
    with respx.mock(assert_all_called=False) as router:
        router.get("https://stat.molit.go.kr/robots.txt").respond(
            200, text="User-agent: Googlebot\nDisallow: */portal/board/centerList.do\n"
        )
        route = router.get(MOLIT_DATA_URL).mock(side_effect=_route(fixtures_dir))
        collector = UnsoldCollector(http=http, months=1)
        docs = collector.fetch(region, sept, None)
        assert route.call_count == 2
        assert {c.request.url.params["startDate"] for c in route.calls} == {"202608"}
        assert len(docs) == 2 and all(d.http_status == 200 for d in docs)
        n_raw, n_unsold = count(RawDocument), count(Unsold)
        assert n_unsold == 2  # region.sigungu_codes = 연수구·김포시

        UnsoldCollector(http=http, months=1).fetch(region, sept, None)
        assert (count(RawDocument), count(Unsold)) == (n_raw, n_unsold)

    with Session(db_engine) as s:
        rows = {u.scope_code: u for u in s.scalars(select(Unsold))}
    assert rows["28185"].total == 505 and rows["41570"].total == 787
    assert rows["28185"].post_completion is not None
    assert {u.source_label for u in rows.values()} == {"확인됨"}
    assert all(u.raw_document_id is not None and u.ym == "2026-08" for u in rows.values())


def test_collector_records_failure_rows(
    db_engine: Engine,
    region_ctx: tuple[Region, Snapshot],
    http: HttpClient,
    count: Callable[[type[Any]], int],
) -> None:
    region, snapshot = region_ctx
    with respx.mock(assert_all_called=False) as router:
        router.get("https://stat.molit.go.kr/robots.txt").respond(404)
        router.get(MOLIT_DATA_URL).respond(500)
        docs = UnsoldCollector(http=http).fetch(region, snapshot, None)
    assert [d.http_status for d in docs] == [500, 500]
    assert all(d.path is None for d in docs)
    assert count(Unsold) == 0


@pytest.mark.live
@pytest.mark.usefixtures("legal_dongs")
def test_live_unsold(region_ctx: tuple[Region, Snapshot], count: Callable[[type[Any]], int]) -> None:
    region, snapshot = region_ctx
    collector = UnsoldCollector(months=3)
    docs = collector.fetch(region, snapshot, None)
    assert all(d.http_status == 200 for d in docs)
    assert collector.last is not None and collector.last.unresolved == []
    assert count(Unsold) > 0

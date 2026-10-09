"""stats: 주민등록 세대수 파싱·적재 (DECISIONS D2-1 household_stat)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.collectors.stats.households import (
    JUMIN_CSV_URL,
    HouseholdCollector,
    jumin_form,
    load_household_stats,
    parse_household_csv,
)
from app.core.contracts_gen import Region, Snapshot
from app.core.http import HttpClient
from app.models import HouseholdStat, RawDocument


def test_parse_household_csv_copy(reference_copy: Path) -> None:
    ym, records = parse_household_csv((reference_copy / "jumin_households_202609.csv").read_bytes())
    assert ym == "2026-09"
    by_key = {(r.scope_kind, r.scope_code): r for r in records}
    songdo1 = by_key[("admin_dong", "2818582000")]
    assert (songdo1.name, songdo1.households) == ("인천광역시 연수구 송도1동", 14632)
    assert by_key[("sigungu", "28290")].households == 113858  # 검단구 시군구 행
    assert ("sigungu", "41570") in by_key  # 김포시
    assert all(r.scope_code[2:] != "00000000" for r in records)  # 시도 행 없음
    assert all(len(r.scope_code) == (5 if r.scope_kind == "sigungu" else 10) for r in records)
    assert len(records) > 3_500


def test_unpublished_month_is_header_only(fixtures_dir: Path) -> None:
    assert parse_household_csv((fixtures_dir / "jumin_202610_unpublished.csv").read_bytes()) == (None, [])
    assert parse_household_csv(b"") == (None, [])


def test_form_is_whole_country_one_month() -> None:
    form = jumin_form("2026-09")
    assert (
        form["sltOrgLvl1"],
        form["searchYearStart"],
        form["searchMonthStart"],
        form["searchMonthEnd"],
    ) == (
        "A",
        "2026",
        "09",
        "09",
    )


def _csv_by_month(fx: Path, ref: Path) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        if (form.get("searchYearStart"), form.get("searchMonthStart")) == ("2026", "09"):
            return httpx.Response(200, content=(ref / "jumin_households_202609.csv").read_bytes())
        return httpx.Response(200, content=(fx / "jumin_202610_unpublished.csv").read_bytes())

    return handler


def test_collector_walks_back_to_published_month_and_is_idempotent(
    db_engine: Engine,
    region_ctx: tuple[Region, Snapshot],
    fixtures_dir: Path,
    reference_copy: Path,
    http: HttpClient,
    count: Callable[[type[Any]], int],
) -> None:
    region, snapshot = region_ctx
    late = snapshot.model_copy(update={"asof_date": "2026-11-02"})  # 전월 = 2026-10(미공표) → 2026-09
    with respx.mock(assert_all_called=False) as router:
        router.get("https://jumin.mois.go.kr/robots.txt").respond(404)
        route = router.post(JUMIN_CSV_URL).mock(side_effect=_csv_by_month(fixtures_dir, reference_copy))
        collector = HouseholdCollector(http=http)
        docs = collector.fetch(region, late, None)
        assert route.call_count == 2
        assert len(docs) == 2  # 미공표 응답(머리글만)도 원문으로 남긴다
        assert collector.last is not None and collector.last.ym == "2026-09"
        n_raw, n_hh = count(RawDocument), count(HouseholdStat)
        assert n_hh > 3_500

        again = HouseholdCollector(http=http)
        again.fetch(region, late, None)
        assert (count(RawDocument), count(HouseholdStat)) == (n_raw, n_hh)
        assert again.last is not None and again.last.load is not None
        assert again.last.load.total_changes == 0

    with Session(db_engine) as s:
        rows = s.scalars(select(HouseholdStat).where(HouseholdStat.scope_kind == "sigungu")).all()
        assert {(r.label, r.reason) for r in rows} == {("추정", "주민등록 세대")}
        assert all(r.raw_document_id is not None for r in rows)
        urls = {d.url for d in s.scalars(select(RawDocument))}
        assert all(u.startswith(JUMIN_CSV_URL) for u in urls)


def test_load_updates_changed_counts(db_engine: Engine, reference_copy: Path) -> None:
    _, records = parse_household_csv((reference_copy / "jumin_households_202609.csv").read_bytes())
    with Session(db_engine) as s:
        first = load_household_stats(s, records[:10], raw_document_id=None)
        assert first.inserted == 10
        same = load_household_stats(s, records[:10], raw_document_id=None)
        assert (same.inserted, same.updated, same.unchanged) == (0, 0, 10)
        bumped = [replace(records[0], households=records[0].households + 1), *records[1:10]]
        changed = load_household_stats(s, bumped, raw_document_id=None)
        assert (changed.inserted, changed.updated, changed.unchanged) == (0, 1, 9)


def test_collect_uses_copy_when_site_is_down(
    db_engine: Engine, reference_copy: Path, http: HttpClient, count: Callable[[type[Any]], int]
) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get("https://jumin.mois.go.kr/robots.txt").respond(404)
        router.post(JUMIN_CSV_URL).respond(503)
        with Session(db_engine) as s:
            result = HouseholdCollector(http=http, fallback_dir=reference_copy).collect(
                s, asof=date(2026, 10, 9)
            )
            s.commit()
    assert result.used_fallback == "jumin_households_202609.csv"
    assert result.ym == "2026-09"
    assert [d.http_status for d in result.documents] == [503, None]  # 사본은 HTTP 응답이 아니다
    assert result.documents[1].url == "fixture://reference/jumin_households_202609.csv"
    assert count(HouseholdStat) > 3_500


@pytest.mark.live
def test_live_households(db_engine: Engine) -> None:
    with Session(db_engine) as s:
        result = HouseholdCollector().collect(s, asof=date.today())
        s.commit()
    assert result.used_fallback is None and len(result.records) > 3_500

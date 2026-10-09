"""D4 완료 기준(HTML): 스냅샷 2개 생성 · 외부 URL 리소스 0 · 참고자료 URL 형식 · §8 숫자 = score_total ·
diff 표 · contradicted 거부 · 모든 수치에 라벨."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from urllib.parse import urlparse

import pytest
from bs4 import BeautifulSoup, Tag
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.protocols import Exporter
from app.models import RawDocument, ScoreTotal
from app.reports.diff import diff_snapshots
from app.reports.errors import ReportBlocked
from app.reports.export import ReportExporter, generate
from app.reports.render import find_echarts_bundle
from app.reports.sections import DISCLAIMER, SECTION_TITLES

from ._seed import add_contradicted_claim

LABELS = {"확인됨", "추정", "비공식", "재가공", "확인 불가"}
_cache: dict[tuple[int, int | None], str] = {}


def _html(factory: sessionmaker[Session], out_dir: Path, sid: int, compare: int | None = None) -> str:
    key = (sid, compare)
    if key not in _cache:
        with factory() as s:
            rep = generate(s, sid, "html", compare_snapshot_id=compare, out_dir=out_dir)
        assert rep.path.is_file() and rep.path.suffix == ".html"
        assert rep.size_bytes == rep.path.stat().st_size and len(rep.sha256) == 64
        _cache[key] = rep.path.read_text(encoding="utf-8")
    return _cache[key]


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def test_section_titles_are_the_fixed_eleven() -> None:
    assert len(SECTION_TITLES) == 11
    assert len(set(SECTION_TITLES)) == 11


@pytest.mark.parametrize("sid", [11, 12])
def test_html_for_both_fixture_snapshots_has_eleven_anchored_sections(
    factory: sessionmaker[Session], out_dir: Path, sid: int
) -> None:
    soup = _soup(_html(factory, out_dir, sid))
    for n, title in enumerate(SECTION_TITLES, start=1):
        sec = soup.find("section", id=f"s{n}")
        assert isinstance(sec, Tag), f"§{n} 앵커 없음"
        h2 = sec.find("h2")
        assert isinstance(h2, Tag) and title in h2.get_text(" ", strip=True)
    toc = soup.find("nav", id="toc")
    assert isinstance(toc, Tag)
    hrefs = {a["href"] for a in toc.find_all("a")}
    assert {f"#s{n}" for n in range(1, 12)} <= hrefs


@pytest.mark.parametrize("sid", [11, 12])
def test_html_has_zero_external_url_resources(
    factory: sessionmaker[Session], out_dir: Path, sid: int
) -> None:
    html = _html(factory, out_dir, sid, 11 if sid == 12 else None)
    soup = _soup(html)
    ext = re.compile(r"^\s*(https?:)?//", re.I)
    for tag in soup.find_all(
        ["script", "img", "iframe", "source", "video", "audio", "embed", "track", "input"]
    ):
        assert not ext.match(str(tag.get("src") or "")), tag
    for tag in soup.find_all("link"):
        assert not ext.match(str(tag.get("href") or "")), tag
    for tag in soup.find_all("object"):
        assert not ext.match(str(tag.get("data") or "")), tag
    css = " ".join(t.get_text() for t in soup.find_all("style"))
    css += " ".join(str(t.get("style") or "") for t in soup.find_all(style=True))
    assert not re.search(r"url\(\s*['\"]?(https?:)?//", css, re.I)
    assert not re.search(r"@import", css, re.I)


def test_echarts_bundle_is_inlined(factory: sessionmaker[Session], out_dir: Path) -> None:
    if find_echarts_bundle() is None:
        pytest.skip("echarts.min.js 없음(frontend npm ci 전) — 표만 생성")
    soup = _soup(_html(factory, out_dir, 12))
    scripts = [t.get_text() for t in soup.find_all("script") if not t.get("src")]
    assert any("echarts" in s and len(s) > 100_000 for s in scripts), "ECharts 번들 인라인 안 됨"
    charts = soup.select("div.chart[data-option-id]")
    assert len(charts) >= 3
    for div in charts:
        opt = soup.find("script", id=div["data-option-id"])
        assert isinstance(opt, Tag) and opt.get("type") == "application/json"


@pytest.mark.parametrize("sid", [11, 12])
def test_reference_urls_are_all_well_formed(factory: sessionmaker[Session], out_dir: Path, sid: int) -> None:
    soup = _soup(_html(factory, out_dir, sid))
    sec = soup.find("section", id="s11")
    assert isinstance(sec, Tag)
    links = sec.select("a.ref-url")
    assert links, "참고자료 없음"
    for a in links:
        href = str(a["href"])
        u = urlparse(href)
        assert u.scheme in ("http", "https") and u.netloc and " " not in href, href
        assert a.get_text(strip=True) == href  # 전문 그대로(잘림 없음)
    with factory() as s:
        urls = set(s.scalars(select(RawDocument.url).where(RawDocument.region_id == 1)))
    shown = {str(a["href"]) for a in links}
    assert urls <= shown, urls - shown


def test_section8_numbers_equal_score_total(factory: sessionmaker[Session], out_dir: Path) -> None:
    soup = _soup(_html(factory, out_dir, 12))
    sec = soup.find("section", id="s8")
    assert isinstance(sec, Tag)
    cells = sec.select('[data-prov^="st_"]')
    assert len(cells) >= 20, len(cells)
    with factory() as s:
        for cell in cells:
            st = s.get(ScoreTotal, int(str(cell["data-prov"])[3:]))
            assert st is not None and st.total is not None
            want = Decimal(st.total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            val = cell.select_one(".v")
            assert val is not None and val.get_text(strip=True) == f"{want}", (cell, want)


@pytest.mark.parametrize("sid", [11, 12])
def test_every_fact_has_a_label(factory: sessionmaker[Session], out_dir: Path, sid: int) -> None:
    soup = _soup(_html(factory, out_dir, sid))
    facts = soup.select(".fact")
    assert len(facts) > 200
    for f in facts:
        lb = f.select_one(".lb")
        assert lb is not None and lb.get("data-label") in LABELS, f
        assert lb.get_text(strip=True), f


def test_disclaimer_on_every_judgment_section(factory: sessionmaker[Session], out_dir: Path) -> None:
    soup = _soup(_html(factory, out_dir, 12))
    for n in (3, 6, 7, 8):
        sec = soup.find("section", id=f"s{n}")
        assert isinstance(sec, Tag) and DISCLAIMER in sec.get_text(" ", strip=True)
    header = soup.find("header")
    assert isinstance(header, Tag) and DISCLAIMER in header.get_text(" ", strip=True)


def test_contradicted_claim_refuses_generation(factory: sessionmaker[Session], out_dir: Path) -> None:
    with factory() as s:
        add_contradicted_claim(s, 12)
        with pytest.raises(ReportBlocked) as exc:
            generate(s, 12, "html", out_dir=out_dir / "blocked")
        s.rollback()
    assert "contradicted" in str(exc.value)
    assert not (out_dir / "blocked").exists() or not any((out_dir / "blocked").iterdir())


def test_split_contradicted_claim_does_not_block(factory: sessionmaker[Session], out_dir: Path) -> None:
    """#131 복합 주장은 contradicted 지만 분할 재검증(자식 verified)됐다 → 남은 contradicted 0."""
    _html(factory, out_dir, 12)


def test_diff_table_between_snapshots(factory: sessionmaker[Session], out_dir: Path) -> None:
    with factory() as s:
        diff = diff_snapshots(s, 11, 12)
    kinds = {r.kind for r in diff.rows}
    assert {"added", "changed"} <= kinds
    added = {r.complex_id for r in diff.rows if r.kind == "added" and r.table == "score_total"}
    assert added == {4, 7, 8, 9, 10, 11, 13, 14}
    elif_total = [
        r for r in diff.rows if r.complex_id == 2 and r.table == "score_total" and r.field == "total"
    ]
    assert elif_total and elif_total[0].old == "5.74" and elif_total[0].new == "5.70"
    soup = _soup(_html(factory, out_dir, 12, 11))
    table = soup.find("table", id="diff-table")
    assert isinstance(table, Tag)
    body = table.find("tbody")
    assert isinstance(body, Tag) and len(body.find_all("tr")) == len(diff.rows)
    extra = soup.find("section", id="s12")
    assert isinstance(extra, Tag)


def test_exporter_protocol(factory: sessionmaker[Session], out_dir: Path) -> None:
    from app.core.contracts_gen import Snapshot as SnapshotDTO

    exp = ReportExporter(factory, out_dir=out_dir / "exp")
    assert isinstance(exp, Exporter)
    snap = SnapshotDTO(
        id=12,
        region_id=1,
        asof_date="2026-10-08",
        status="published",
        degraded=False,
        created_at="2026-10-08T00:00:00+09:00",
    )
    path = exp.render(snap, "html")
    assert path.is_file() and path.parent == out_dir / "exp"

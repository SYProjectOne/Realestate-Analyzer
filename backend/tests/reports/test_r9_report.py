"""R9-REPORT(D28-4, 30-proposal §11-2 WP8 요청서): 첫 장·본문/부록·차트 머리꼬리·용어·증감 표식.

| 완료 기준(30-proposal §11-2 (3) + CEO 지시) | 테스트 |
| --- | --- |
| 1쪽 메타 상자 + 요약 블록(HTML·PDF) | ``test_cover_meta_box_and_summary`` · ``test_pdf_first_page_has_cover_and_page_counts`` |
| 요약은 기존 값만(새 판단·새 숫자 없음) | ``test_cover_facts_exist_elsewhere_in_report`` · ``test_cover_top_and_scenarios_match_data`` |
| 본문 요약 표 열 ≤ 4, 부록에 전체 표 | ``test_body_summary_tables_have_at_most_four_columns`` |
| 차트마다 위 제목(단위)·아래 '자료:' 줄·대응 표, 범례 단위 | ``test_every_chart_has_title_source_line_and_table`` |
| 용어 부록 = 용어 원본 전 항목, 첫 등장 괄호 풀이 1회 | ``test_glossary_appendix_lists_every_item`` · ``test_terms_explained_once_on_first_use`` |
| 새 문구 금지어 없음(장 제목·용어·템플릿 고정 문구) | ``test_no_forbidden_words_in_new_text`` |
| 기존 수치·라벨·출처 id 하나도 빠지지 않음 | ``test_fact_cells_superset_of_before`` |
| 증감 ▲▼ + 글자(색만으로 말하지 않음) | ``test_change_markers_have_text`` · ``test_marker_helpers`` |
| '§8 종합 추천' 이름 변경, 장 11개 유지 | ``test_section_titles_renamed_but_eleven`` |
"""

# ruff: noqa: E501

from __future__ import annotations

import json
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest
from bs4 import BeautifulSoup, Tag
from sqlalchemy.orm import Session, sessionmaker

from app.core.contracts_gen import Fact
from app.reports.cover import delta_mark, diff_mark, rank_move
from app.reports.data import load_report
from app.reports.diff import DiffRow
from app.reports.export import generate
from app.reports.glossary import GLOSSARY, forbidden_hits
from app.reports.pdf import count_pages
from app.reports.sections import (
    APPENDIX_C_TITLE,
    APPENDIX_D_TITLE,
    DISCLAIMER,
    EXTRA_TITLE,
    ORIGINAL_TITLES,
    SECTION_TITLES,
)

GOLDEN = Path(__file__).parent / "golden" / "r9_fact_cells_before.json"
TEMPLATES = Path(__file__).resolve().parents[2] / "app" / "reports" / "templates"
_cache: dict[str, str] = {}


def _html(factory: sessionmaker[Session], out_dir: Path) -> str:
    if "html" not in _cache:
        with factory() as s:
            rep = generate(s, 12, "html", compare_snapshot_id=11, out_dir=out_dir)
        _cache["html"] = rep.path.read_text(encoding="utf-8")
    return _cache["html"]


def _soup(factory: sessionmaker[Session], out_dir: Path) -> BeautifulSoup:
    return BeautifulSoup(_html(factory, out_dir), "lxml")


def _cells(root: Tag | BeautifulSoup) -> set[tuple[str, str, str]]:
    out = set()
    for f in root.select(".fact"):
        v, lb = f.select_one(".v"), f.select_one(".lb")
        out.add(
            (
                str(f.get("data-prov") or ""),
                v.get_text(strip=True) if v else "",
                str(lb.get("data-label")) if lb else "",
            )
        )
    return out


# ---------------------------------------------------------------------------- 장 제목


def test_section_titles_renamed_but_eleven() -> None:
    """장 11개·번호·순서는 그대로(T15), 제목만 쉬운 말 + 원 용어 괄호. '§8 종합 추천' → '§8 종합 정리(판정기 결과)'."""
    assert len(SECTION_TITLES) == len(ORIGINAL_TITLES) == 11
    for n, (new, old) in enumerate(zip(SECTION_TITLES, ORIGINAL_TITLES, strict=True), start=1):
        assert new.startswith(f"§{n} ") and old.startswith(f"§{n} "), (new, old)
    assert SECTION_TITLES[7] == "§8 종합 정리(판정기 결과)"
    assert "부록 A" in SECTION_TITLES[9] and "부록 B" in SECTION_TITLES[10]
    titles = (*SECTION_TITLES, EXTRA_TITLE, APPENDIX_C_TITLE, APPENDIX_D_TITLE)
    assert len(set(titles)) == len(titles)
    for t in titles:
        assert not forbidden_hits(t), t
    # 한 제목이 다른 제목의 앞부분이면 PDF 쪽 묶음 판별(count_pages)이 헷갈린다
    for a in titles:
        for b in titles:
            assert a == b or not re.sub(r"\s+", "", b).startswith(re.sub(r"\s+", "", a)), (a, b)


# ---------------------------------------------------------------------------- 첫 장


def test_cover_meta_box_and_summary(factory: sessionmaker[Session], out_dir: Path) -> None:
    soup = _soup(factory, out_dir)
    cover = soup.find("header", id="cover")
    assert isinstance(cover, Tag)
    # 첫 장이 목차·본문보다 먼저
    first = soup.body.find(["header", "nav", "main", "section"]) if soup.body else None
    assert first is cover
    text = cover.get_text(" ", strip=True)
    with factory() as s:
        data = load_report(s, 12, compare_snapshot_id=11)
    meta = cover.select_one("table.meta-box")
    assert meta is not None
    heads = [th.get_text(strip=True) for th in meta.select("th")]
    for h in (
        "지역",
        "기준일 · 리비전",
        "발행 · 생성",
        "보고서 시나리오",
        "비교 기준일",
        "쪽수",
        "자료 출처 · 확인일",
        "판정기 버전",
        "계약 버전",
        "고지",
    ):
        assert h in heads, h
    mt = meta.get_text(" ", strip=True)
    assert "2026-10-08" in mt and "리비전 1" in mt and "2026-10-07" in mt
    assert f"참고자료 {len(data.references)}건" in mt
    for v in data.adapter_versions:
        assert v in mt
    assert {el["data-pages"] for el in meta.select("[data-pages]")} == {"body", "appendix", "total"}
    assert meta.select_one("[data-pages-note]") is not None  # HTML판: 쪽수는 PDF판에만
    assert DISCLAIMER in text
    items = cover.select("ol.summary > li")
    assert [li["class"][0] for li in items] == [
        "sum-open",
        "sum-top",
        "sum-decide",
        "sum-unknown",
        "sum-diff",
    ]
    assert cover.find("h2", string=re.compile("이 보고서 읽는 법")) is not None
    assert len(cover.select("ul.howto > li")) == 3
    notation = cover.select_one("p.notation")
    assert notation is not None
    nt = notation.get_text(" ", strip=True)
    for needle in ("억", "만 원", "소수 둘째 자리", "할인", "▲", "▼", "KST"):
        assert needle in nt, needle


def test_cover_top_and_scenarios_match_data(factory: sessionmaker[Session], out_dir: Path) -> None:
    """요약 블록 = 기존 데이터의 값과 판정기 결과만: 접수 가능 단지·상위 3곳 점수(st_ 출처)·상황별 선택·confidence."""
    soup = _soup(factory, out_dir)
    cover = soup.find("header", id="cover")
    assert isinstance(cover, Tag)
    with factory() as s:
        data = load_report(s, 12, compare_snapshot_id=11)
    open_now = [
        c.name
        for c in data.complexes
        if c.judge_scope != "제외" and c.intake_shown is not None and c.intake_shown.status == "가능"
    ]
    li = cover.select_one("li.sum-open")
    assert li is not None
    assert f"지금 접수 가능 {len(open_now)}곳" in li.get_text(" ", strip=True)
    for name in open_now:
        assert name in li.get_text(" ", strip=True)
    top = cover.select_one("li.sum-top")
    assert top is not None
    provs = [str(f["data-prov"]) for f in top.select(".fact")]
    assert provs == [str(s.total.prov) for s in data.top5[:3]]
    assert all(p.startswith("st_") for p in provs)
    for f, s in zip(top.select(".fact .v"), data.top5[:3], strict=True):
        assert (
            f.get_text(strip=True)
            == f"{Decimal(str(s.total.v)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"
        )
    table = cover.select_one("table.scenario-cover")
    assert table is not None
    rows = table.select("tbody tr")
    assert len(rows) == len(data.scenarios) > 0
    for tr, b in zip(rows, data.scenarios, strict=True):
        t = tr.get_text(" ", strip=True)
        for d in b.decisions:
            if d.chosen:
                assert d.option in t, (b.code, d.option)
        if b.tie:
            assert "1순위를 하나로 말하지 않음" in t
    # 동률 상황(B)이 실제로 있다(픽스처 전제)
    assert any(b.tie for b in data.scenarios)


def test_cover_facts_exist_elsewhere_in_report(factory: sessionmaker[Session], out_dir: Path) -> None:
    """첫 장 숫자는 새로 만든 값이 아니다 — 첫 장 Fact 칸(출처·값·라벨)이 모두 본문·부록에도 있다."""
    soup = _soup(factory, out_dir)
    cover = soup.find("header", id="cover")
    main = soup.find("main")
    assert isinstance(cover, Tag) and isinstance(main, Tag)
    cover_cells = _cells(cover)
    assert cover_cells
    missing = cover_cells - _cells(main)
    assert not missing, sorted(missing)[:5]


def test_fact_cells_superset_of_before(factory: sessionmaker[Session], out_dir: Path) -> None:
    """R9 전 보고서(스냅샷 12·비교 11·base)의 Fact 칸(data-prov·값·라벨) 집합이 하나도 빠지지 않았다(30-proposal §11-2 (3))."""
    before = {tuple(x) for x in json.loads(GOLDEN.read_text(encoding="utf-8"))["cells"]}
    assert len(before) > 500
    after = _cells(_soup(factory, out_dir))
    missing = before - after
    assert not missing, sorted(missing)[:10]


# ---------------------------------------------------------------------------- 본문/부록


def test_body_summary_tables_have_at_most_four_columns(factory: sessionmaker[Session], out_dir: Path) -> None:
    soup = _soup(factory, out_dir)
    s4 = soup.find("section", id="s4")
    assert isinstance(s4, Tag)
    tables = s4.select("table")
    assert len(tables) == 2  # (A)·(B) 요약 표만
    for t in tables:
        assert len(t.select("thead th")) <= 4
    s1 = soup.find("section", id="s1")
    assert isinstance(s1, Tag)
    for t in s1.select("table.body-summary"):
        assert len(t.select("thead th")) <= 4
    appx = soup.find("section", id="appx-d")
    assert isinstance(appx, Tag)
    h2 = appx.find("h2")
    assert isinstance(h2, Tag) and APPENDIX_D_TITLE in h2.get_text()
    widths = [len(t.select("thead th")) for t in appx.select("table")]
    assert 11 in widths and 9 in widths  # 단지 전수 11열 · 제도 요약 9열
    for anchor in ("appx-d1", "appx-d2", "appx-d3", "appx-d4", "appx-d5", "appx-d6"):
        assert appx.find(id=anchor) is not None, anchor
    with factory() as s:
        data = load_report(s, 12, compare_snapshot_id=11)
    # 6-4 본문은 TOP 5 만, 전체 탈락 사유는 부록 D-6
    s6 = soup.find("section", id="s6")
    assert isinstance(s6, Tag)
    assert "부록 D-6" in s6.get_text(" ", strip=True)
    body_rows = [tr.find_all("td")[1] for tr in s6.select("table")[-1].select("tbody tr")]
    assert len(body_rows) == len(data.top5) < len(data.scores)
    for td, sv in zip(body_rows, data.top5, strict=True):
        assert td.get_text(" ", strip=True).startswith(sv.name)


def test_toc_lists_appendices_c_and_d(factory: sessionmaker[Session], out_dir: Path) -> None:
    soup = _soup(factory, out_dir)
    toc = soup.find("nav", id="toc")
    assert isinstance(toc, Tag)
    hrefs = [a["href"] for a in toc.find_all("a")]
    assert hrefs[-2:] == ["#appx-c", "#appx-d"]
    assert "#s12" in hrefs


# ---------------------------------------------------------------------------- 차트


def test_every_chart_has_title_source_line_and_table(factory: sessionmaker[Session], out_dir: Path) -> None:
    soup = _soup(factory, out_dir)
    figs = soup.select("figure.chart-fig")
    assert len(figs) >= 4
    for fig in figs:
        children = [c for c in fig.children if isinstance(c, Tag)]
        assert children[0].name == "figcaption", fig.get("id")
        assert "단위" in children[0].get_text(), children[0].get_text()
        div = fig.select_one("div.chart")
        src = fig.select_one("p.chart-source")
        table = fig.select_one("table.chart-table")
        assert div is not None and src is not None and table is not None
        assert src.get_text(strip=True).startswith("자료:") and "확인일" in src.get_text()
        order = [c for c in fig.descendants if isinstance(c, Tag) and c in (div, src, table)]
        assert order == [div, src, table]  # 그림 → 자료 줄 → 표
        assert table.select("tbody tr"), "그림만 있고 표가 없다"
        opt = soup.find("script", id=div["data-option-id"])
        assert isinstance(opt, Tag)
        option = json.loads(opt.get_text())
        assert re.search(r"\{name\} \(.+\)", option["legend"]["formatter"]), option["legend"]


# ---------------------------------------------------------------------------- 용어


def test_glossary_appendix_lists_every_item(factory: sessionmaker[Session], out_dir: Path) -> None:
    soup = _soup(factory, out_dir)
    sec = soup.find("section", id="appx-c")
    assert isinstance(sec, Tag)
    h2 = sec.find("h2")
    assert isinstance(h2, Tag) and APPENDIX_C_TITLE in h2.get_text()
    keys = [str(tr["data-key"]) for tr in sec.select("tr[data-key]")]
    assert sorted(keys) == sorted(GLOSSARY) and len(keys) == len(set(keys))
    for it in GLOSSARY.values():
        assert it.term.strip() and it.short.strip(), it.key
    # 30-proposal §7-3 고칠 것 반영
    assert "84점" not in GLOSSARY["point_system"].short
    assert "만 30세" not in GLOSSARY["points"].short and "계산하지 않습니다" in GLOSSARY["points"].short
    assert "중앙값" in GLOSSARY["gap"].short and "범위보다" not in GLOSSARY["gap"].short
    assert "당첨 확률이 아닙니다" in GLOSSARY["p10"].short
    assert "할인" in GLOSSARY["current_price"].short
    assert "판정기가 분류한" in GLOSSARY["intake_status"].short


def test_terms_explained_once_on_first_use(factory: sessionmaker[Session], out_dir: Path) -> None:
    soup = _soup(factory, out_dir)
    must = ("resale_limit", "residency", "rewin", "no_rank", "gap", "p10", "total", "judge_scope", "label")
    seen: dict[str, int] = {}
    first_has_gloss: dict[str, bool] = {}
    for el in soup.select(".term[data-term]"):
        k = str(el["data-term"])
        nxt = el.find_next_sibling()
        has = isinstance(nxt, Tag) and "gloss" in (nxt.get("class") or [])
        seen[k] = seen.get(k, 0) + (1 if has else 0)
        first_has_gloss.setdefault(k, has)
    for k in must:
        assert k in first_has_gloss, f"{k} 본문에 없음"
        assert first_has_gloss[k], f"{k} 첫 등장에 괄호 풀이 없음"
    for k, n in seen.items():
        assert n <= 1, f"{k} 괄호 풀이 {n}번"
    # 첫 장이 가장 먼저 쓰는 용어들
    cover = soup.find("header", id="cover")
    assert isinstance(cover, Tag)
    glossed = set()
    for g in cover.select(".gloss"):
        head = g.find_previous_sibling(class_="term")
        if isinstance(head, Tag):
            glossed.add(str(head["data-term"]))
    assert {"intake_status", "total", "judge_scope", "label"} <= glossed


# ---------------------------------------------------------------------------- 금지어


def test_no_forbidden_words_in_new_text(factory: sessionmaker[Session], out_dir: Path) -> None:
    for it in GLOSSARY.values():
        assert not forbidden_hits(it.term + " " + it.short + " " + it.inline), it.key
    # 템플릿 고정 문구(Jinja 식·주석 제외)
    for path in sorted(TEMPLATES.glob("*.j2")):
        raw = re.sub(r"\{#.*?#\}|\{\{.*?\}\}|\{%.*?%\}", " ", path.read_text(encoding="utf-8"), flags=re.S)
        assert not forbidden_hits(raw), (path.name, forbidden_hits(raw))
    soup = _soup(factory, out_dir)
    cover = soup.find("header", id="cover")
    assert isinstance(cover, Tag)
    assert not forbidden_hits(cover.get_text(" ", strip=True))
    toc = soup.find("nav", id="toc")
    assert isinstance(toc, Tag) and "추천" not in toc.get_text()


# ---------------------------------------------------------------------------- 증감 표식


def test_change_markers_have_text(factory: sessionmaker[Session], out_dir: Path) -> None:
    soup = _soup(factory, out_dir)
    table = soup.find("table", id="diff-table")
    assert isinstance(table, Tag)
    marks = [tr.find_all("td")[5] for tr in table.select("tbody tr")]
    assert marks
    for td in marks:
        t = td.get_text(" ", strip=True)
        assert re.match(r"^(＋ 추가|－ 제외|▲ 증가\(변경\)|▼ 감소\(변경\)|변경)$", t), t
    assert any("▲" in td.get_text() or "▼" in td.get_text() for td in marks)
    rank = soup.find("table", id="rank-table")
    assert isinstance(rank, Tag)
    assert "변화" in rank.select("thead th")[-1].get_text()
    for tr in rank.select("tbody tr"):
        cell = tr.find_all("td")[-1]
        assert cell.get_text(strip=True), tr  # 기호만 있는 칸 없음(글자 동반)
        for d in cell.select(".delta"):
            assert re.search(r"[가-힣]", d.get_text()), d


def test_marker_helpers() -> None:
    def f(v: object) -> Fact:
        return Fact.model_validate(
            {"v": v, "label": "추정", "prov": "fp_1", "checked_at": None, "unit": "pct"}
        )

    assert (
        "▲ 오름" in delta_mark(f(3.2)) and "▼ 내림" in delta_mark(f(-1)) and "변동 없음" in delta_mark(f(0))
    )
    assert delta_mark(f(None)) == ""
    row = DiffRow(
        table="score_total",
        complex_id=1,
        complex_name="x",
        field="total",
        old="5.74",
        new="5.70",
        kind="changed",
        label="추정",
    )
    assert "▼ 감소" in diff_mark(row)
    assert "▲ 증가" in diff_mark(
        DiffRow(
            table="t", complex_id=1, complex_name="x", field="f", old="1", new="2", kind="changed", label=""
        )
    )
    assert (
        diff_mark(
            DiffRow(
                table="t",
                complex_id=1,
                complex_name="x",
                field="f",
                old="가능",
                new="미정",
                kind="changed",
                label="",
            )
        ).striptags()
        == "변경"
    )
    assert "＋ 추가" in diff_mark(
        DiffRow(table="t", complex_id=1, complex_name="x", field="f", old="", new="1", kind="added", label="")
    )
    assert "▲ 2계단 오름" in rank_move("4위", "2위")
    assert "▼ 1계단 내림" in rank_move("2위", "3위")
    assert "새로 순위에 듦" in rank_move("—", "5위")
    assert "점수 낮아짐" in rank_move("1위", "1위", f(5.74), f(5.70))


# ---------------------------------------------------------------------------- PDF


@pytest.mark.slow
def test_pdf_first_page_has_cover_and_page_counts(factory: sessionmaker[Session], out_dir: Path) -> None:
    from pypdf import PdfReader

    with factory() as s:
        rep = generate(s, 12, "pdf", compare_snapshot_id=11, out_dir=out_dir)
    raw = rep.path.read_bytes()
    counts = count_pages(raw)
    reader = PdfReader(str(rep.path))
    assert counts["total"] == len(reader.pages)
    assert counts["body"] + counts["appendix"] == counts["total"]
    assert counts["appendix"] >= 4  # 부록 A·B·C·D 각 1쪽 이상
    p1 = re.sub(r"\s+", "", reader.pages[0].extract_text() or "")
    for needle in ("한눈에보기", "이보고서읽는법", "지금접수가능", "기준일·리비전", "투자권유아님·상대비교"):
        assert needle in p1, needle
    assert f"본문{counts['body']}쪽·부록{counts['appendix']}쪽(전체{counts['total']}쪽)" in p1
    assert "HTML판은쪽이없어" not in p1
    # 목차는 2쪽부터 — 첫 장은 요약만
    assert "§1기준일과제도" not in p1

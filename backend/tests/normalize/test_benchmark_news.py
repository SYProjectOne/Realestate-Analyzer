"""D31-3: 2020년 이전 분양 단지의 언론 기사 분양가 — 대상 고르기·판정기 입력·값 파싱·벤치마크 행·출처.

값을 고르는 것은 판정기(P2 extract)다. 여기서는 판정기가 auto 로 준 문자열(필드 → 원문)을 넣고, 문자열 처리
(숫자 파싱·기사 줄 찾기·단위 검사)와 조립만 시험한다.
"""

# ruff: noqa: E501  (한국어 docstring·발췌 문구)

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.news.collector import NewsItem
from app.models import Benchmark, FieldProvenance, Region
from app.normalize.benchmark import build_benchmarks
from app.normalize.benchmark_news import (
    NewsPrice,
    NewsTarget,
    money_won,
    news_document,
    news_price,
    news_query,
    news_targets,
)

from ._assemble_support import ASOF, add_list, add_model, add_trade, notice_row, rtms_url
from ._support import AddRaw

SONGDO = "2818510600"
ARTICLE = "https://news.example.com/a/1"


def _target(name: str = "송도더베뉴", completed: int = 2021) -> NewsTarget:
    return NewsTarget("ntabc", name, name, "송도동", "la_1", completed)


def _items() -> list[NewsItem]:
    return [
        NewsItem("다른 단지 분양", "https://news.example.com/a/0", "옆 단지 84㎡ 4억800만원", "Tue, 05 Nov 2019 09:00:00 +0900"),
        NewsItem(
            "'송도 더 베뉴' 견본주택", ARTICLE, "84㎡ 3억8820만~4억1320만원, 3.3㎡당 1238만원",
            "Fri, 06 Dec 2019 10:00:00 +0900",
        ),
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("text", "won"),
    [
        ("4억3000만원", 430_000_000),
        ("4억 800만 원", 408_000_000),
        ("3억 9천만원", 390_000_000),
        ("1억2천500만원", 125_000_000),
        ("1,247만원", 12_470_000),
        ("4억원", 400_000_000),
        ("만원", None),
        ("abc", None),
    ],
)
def test_money_won_parses_korean_amounts(text: str, won: int | None) -> None:
    assert money_won(text) == won


def test_news_query_drops_parenthesis() -> None:
    assert news_query("송도더휴캐널파크(THEHUECANALPARK)") == "송도더휴캐널파크 분양가"


def test_news_document_numbers_articles_and_keeps_line_spans() -> None:
    doc, spans = news_document(_target(), _items())
    assert doc.splitlines()[0] == "단지: 송도더베뉴 (법정동 송도동, 준공 2021년)"
    assert doc.splitlines()[2].startswith("[2] 2019-12-06 '송도 더 베뉴' 견본주택 — ")
    assert [doc[a:b] for a, b, _ in spans] == doc.splitlines()[1:]
    assert news_document(_target(), []) == ("", [])


def test_price_84_from_article_is_unofficial_with_source_line() -> None:
    doc, spans = news_document(_target(), _items())
    p, why = news_price(_target(), doc, spans, {"price_84": "4억1320만원"}, raw_document_id=7)
    assert why == "ok" and p is not None
    assert (p.won, p.label, p.article_url, p.article_date) == (413_200_000, "비공식", ARTICLE, "2019-12-06")
    assert p.excerpt.startswith("[2] ") and p.sale_year == 2019  # min(2019, 2021 − 2)
    assert "min(기사 연도 2019, 준공 2021 − 2)" in p.sale_year_formula


def test_price_per_pyeong_is_estimated_times_34() -> None:
    doc, spans = news_document(_target(), _items())
    p, _ = news_price(_target(), doc, spans, {"price_per_3_3": "1238만원"}, raw_document_id=7)
    assert p is not None and (p.won, p.label) == (420_920_000, "추정")
    assert "× 34" in p.basis


def test_sale_year_is_capped_two_years_before_completion() -> None:
    items = [NewsItem("t", ARTICLE, "84㎡ 4억원", "Mon, 06 Apr 2026 10:00:00 +0900")]
    doc, spans = news_document(_target(), items)
    p, _ = news_price(_target(), doc, spans, {"price_84": "4억원"}, raw_document_id=7)
    assert p is not None and p.sale_year == 2019


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({}, "기사에서 분양가를 찾지 못함"),
        ({"price_84": "4억1320만원", "public_sale": "공공분양"}, "공공분양(기사 표현 — 판정기)"),
        ({"price_84": "4320만원"}, "분양가 단위 확인 불가"),  # 84㎡ 분양가로 1억 미만 — 단위 검사
        ({"price_84": "9억9900만원"}, "분양가가 든 기사 줄을 찾지 못함"),  # 판정기 값이 문서에 없다
    ],
)
def test_no_price_when_judge_gives_nothing_usable(fields: dict[str, str], reason: str) -> None:
    doc, spans = news_document(_target(), _items())
    assert news_price(_target(), doc, spans, fields, raw_document_id=7) == (None, reason)


# ---------------------------------------------------------------- 대상·조립


def _trades(db: Session, add_raw: AddRaw, region: Region, name: str, built: int) -> int:
    doc = add_raw(
        f"<response>{name}</response>",
        source_kind="rtms",
        url=rtms_url("28185", "202609"),
        region_id=region.id,
        ext="xml",
    )
    for price, day in ((60000, "2026-01-10"), (64000, "2026-06-10"), (62000, "2026-09-10")):
        add_trade(db, region.id, name, price, day, legal=SONGDO, built=built, raw_document_id=doc.id)
    return doc.id


def _news_doc(add_raw: AddRaw, region: Region) -> int:
    return add_raw(
        '{"items":[]}',
        source_kind="news",
        url="https://naverapihub.example/search?q=1",
        region_id=region.id,
        ext="json",
    ).id


def test_targets_are_recent_unmatched_complexes_in_living_areas(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    _trades(db_session, add_raw, region, "송도더베뉴", 2021)
    _trades(db_session, add_raw, region, "송도옛단지", 2014)  # 준공 10년 넘음
    _trades(db_session, add_raw, region, "힐스테이트레이크송도2차", 2024)  # 공고와 이어진 단지
    add_list(
        add_raw,
        region.id,
        "인천",
        [
            notice_row(
                "2021000101",
                "힐스테이트 레이크 송도 2차",
                "인천광역시 연수구 송도동 1-1",
                "2021-03-10",
                "202406",
            )
        ],
    )
    add_model(add_raw, region.id, "2021000101", [("084.9500A", 70000, 300)])
    got = news_targets(db_session, region.id, ASOF)
    assert [(t.name, t.completed_year) for t in got] == [("송도더베뉴", 2021)]
    assert got[0].key.startswith("nt") and got[0].living_area


def _price(target: NewsTarget, raw_id: int, won: int = 413_200_000) -> NewsPrice:
    return NewsPrice(
        target=target, won=won, label="비공식", basis="기사에 난 전용 84㎡ 분양가(범위면 높은 값)",
        value_text="4억1320만원", excerpt="[2] 2019-12-06 '송도 더 베뉴' 견본주택 — 84㎡ 3억8820만~4억1320만원",
        article_url=ARTICLE, article_date="2019-12-06", sale_year=2019,
        sale_year_formula="분양 연도 = min(기사 연도 2019, 준공 2021 − 2) = 2019", raw_document_id=raw_id,
    )  # fmt: skip


def test_news_price_becomes_benchmark_row_with_article_provenance(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    _trades(db_session, add_raw, region, "송도더베뉴", 2021)
    target = news_targets(db_session, region.id, ASOF)[0]
    res = build_benchmarks(
        db_session, region.id, asof_date=ASOF, news_prices=[_price(target, _news_doc(add_raw, region))]
    )
    rows = [b for b in db_session.scalars(select(Benchmark)) if b.note and "대체" not in b.note]
    assert len(rows) == 1 and res.news == 1
    b = rows[0]
    assert (b.name, b.sale_price_84_won, b.sale_price_label) == ("송도더베뉴", 413_200_000, "비공식")
    assert (b.sale_year, b.completed_year, b.n_trades, b.trade_median_won) == (2019, 2021, 3, 620_000_000)
    assert (
        b.note is not None
        and b.note.startswith("[bm:news:")
        and ARTICLE in b.note
        and "판정기 P2 추출" in b.note
    )
    sale = db_session.scalars(
        select(FieldProvenance).where(
            FieldProvenance.entity == "benchmark", FieldProvenance.entity_id == b.id,
            FieldProvenance.field == "sale_price_84_won", FieldProvenance.chosen.is_(True),
        )
    ).one()  # fmt: skip
    assert (sale.url, sale.label) == (ARTICLE, "비공식") and "4억1320만원" in (sale.excerpt or "")
    year = db_session.scalars(
        select(FieldProvenance).where(FieldProvenance.entity_id == b.id, FieldProvenance.field == "sale_year")
    ).one()
    assert year.label == "추정" and "min(" in (year.reason or "")
    built = db_session.scalars(
        select(FieldProvenance).where(
            FieldProvenance.entity_id == b.id, FieldProvenance.field == "completed_year"
        )
    ).one()
    assert built.label == "확인됨" and "건축년도" in (built.reason or "")


def test_news_rows_are_kept_when_prices_are_unavailable_and_removed_when_gone(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    _trades(db_session, add_raw, region, "송도더베뉴", 2021)
    target = news_targets(db_session, region.id, ASOF)[0]
    price = _price(target, _news_doc(add_raw, region))
    build_benchmarks(db_session, region.id, asof_date=ASOF, news_prices=[price])
    again = build_benchmarks(db_session, region.id, asof_date=ASOF, news_prices=[price])
    assert (again.inserted, again.updated, again.removed) == (0, 0, 0)  # 멱등
    kept = build_benchmarks(db_session, region.id, asof_date=ASOF, news_prices=None)  # 판정기·키 없음
    assert kept.removed == 0 and any(
        b.note and b.note.startswith("[bm:news:") for b in db_session.scalars(select(Benchmark))
    )
    gone = build_benchmarks(db_session, region.id, asof_date=ASOF, news_prices=[])
    assert gone.removed >= 1
    assert not any(b.note and b.note.startswith("[bm:news:") for b in db_session.scalars(select(Benchmark)))


def test_document_drops_articles_that_only_repeat_earlier_amounts() -> None:
    """같은 값이 여러 기사에 되풀이되면 판정기 확률이 나뉜다 — 새 후보가 없는 기사는 넣지 않는다(문자열 중복 제거)."""
    items = [
        NewsItem("a", "u1", "분양가는 3.3㎡당 평균 1150만원대", None),
        NewsItem("b", "u2", "평균 분양가는 3.3㎡당 1,150만원이다", None),  # 쉼표만 다른 같은 값
        NewsItem("c", "u3", "견본주택 개관, 가격 언급 없음", None),  # 후보 없음
        NewsItem("d", "u4", "옆 단지는 3.3㎡당 1201만원", None),
    ]
    doc, spans = news_document(_target(), items)
    assert [it.url for _, _, it in spans] == ["u1", "u4"]
    assert doc.splitlines()[1].startswith("[1] ") and doc.splitlines()[2].startswith("[4] ")


def test_candidate_patterns_match_the_judge_fields() -> None:
    from app.judge.payloads import benchmark_price_extract_fields
    from app.normalize.benchmark_news import PRICE_PATTERNS

    assert tuple(f.pattern for f in benchmark_price_extract_fields("x")) == PRICE_PATTERNS

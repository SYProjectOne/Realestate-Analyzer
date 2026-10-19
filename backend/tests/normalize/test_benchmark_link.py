"""D31-6: 이름이 바뀐 단지 — 문자열로 못 이은 공고의 후보(같은 동·준공 ±1년·아직 안 이어진 묶음)와 판정기가 고른 매칭.

같은 단지인지는 판정기가 정한다(여기서는 ``links`` 를 직접 넣는다). 이 모듈은 후보 좁히기·조립만 시험한다.
"""

# ruff: noqa: E501  (한국어 docstring·발췌 문구)

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Benchmark, Region
from app.normalize.benchmark import JUDGE_LINK, build_benchmarks, normalize_apt_name
from app.normalize.benchmark_link import link_requests
from app.normalize.benchmark_news import news_targets

from ._assemble_support import ASOF, add_list, add_model, add_trade, notice_row, rtms_url
from ._support import AddRaw

SONGDO = "2818510600"
ADDR = "인천광역시 연수구 송도동 1-1"
NEW_NAME = "신송도역센트럴뷰"


def _trades(
    db: Session,
    add_raw: AddRaw,
    region: Region,
    name: str,
    built: int | None,
    *,
    presale: bool = False,
    days: tuple[str, ...] = ("2026-01-10", "2026-06-10"),
) -> None:
    doc = add_raw(
        f"<response>{name}</response>",
        source_kind="rtms",
        url=rtms_url("28185", "202609"),
        region_id=region.id,
        ext="xml",
    )
    for i, day in enumerate(days):
        add_trade(
            db,
            region.id,
            name,
            60000 + i * 1000,
            day,
            legal=SONGDO,
            built=built,
            presale=presale,
            raw_document_id=doc.id,
        )


def _seed(db: Session, add_raw: AddRaw, region: Region) -> None:
    add_list(
        add_raw, region.id, "인천",
        [
            notice_row("2021000101", "송도 미래 1차", ADDR, "2021-03-10", "202406"),  # 실거래에서는 이름이 바뀌었다
            notice_row("2021000202", "힐스테이트 레이크 송도 2차", ADDR, "2021-04-10", "202406"),  # 이름으로 이어진다
        ],
    )  # fmt: skip
    add_model(add_raw, region.id, "2021000101", [("084.9500A", 50000, 300)])
    add_model(add_raw, region.id, "2021000202", [("084.9500A", 70000, 300)])
    _trades(db, add_raw, region, NEW_NAME, 2024)
    _trades(db, add_raw, region, "송도옛단지", 2010)  # 준공 연도가 멀다
    _trades(db, add_raw, region, "힐스테이트레이크송도2차", 2024)  # 다른 공고와 이어진 묶음


def test_requests_offer_same_dong_unlinked_complexes_near_move_in_year(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    _seed(db_session, add_raw, region)
    reqs = link_requests(db_session, region.id, ASOF)
    assert [r.key for r in reqs] == ["2021000101:2021000101"]
    rq = reqs[0]
    assert "청약 공고 단지: 송도 미래 1차" in rq.text and "입주 예정: 2024-06" in rq.text
    assert [(c.cid, c.name) for c in rq.candidates] == [("g1", normalize_apt_name(NEW_NAME))]
    assert f"'{NEW_NAME}'" in rq.candidates[0].text and "건축년도 2024" in rq.candidates[0].text


def test_judge_link_builds_row_and_removes_the_group_from_news_targets(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    _seed(db_session, add_raw, region)
    assert NEW_NAME in {t.name for t in news_targets(db_session, region.id, ASOF)}
    links = {"2021000101:2021000101": (normalize_apt_name(NEW_NAME), "송도동")}
    build_benchmarks(db_session, region.id, asof_date=ASOF, links=links)
    rows = {b.name: b for b in db_session.scalars(select(Benchmark)) if b.note and "대체" not in b.note}
    row = rows["송도 미래 1차"]
    assert (row.sale_price_84_won, row.n_trades) == (500_000_000, 2)
    assert (
        row.note is not None
        and f"{JUDGE_LINK}('{normalize_apt_name(NEW_NAME)}', 판정기 classify)" in row.note
    )
    assert NEW_NAME not in {t.name for t in news_targets(db_session, region.id, ASOF, links)}


def test_judge_linked_rows_are_kept_when_judge_is_unavailable(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    _seed(db_session, add_raw, region)
    links = {"2021000101:2021000101": (normalize_apt_name(NEW_NAME), "송도동")}
    build_benchmarks(db_session, region.id, asof_date=ASOF, links=links)
    kept = build_benchmarks(db_session, region.id, asof_date=ASOF, links=None)
    assert kept.removed == 0
    assert any(b.name == "송도 미래 1차" for b in db_session.scalars(select(Benchmark)))
    gone = build_benchmarks(db_session, region.id, asof_date=ASOF, links={})
    assert gone.removed >= 1
    assert not any(b.name == "송도 미래 1차" for b in db_session.scalars(select(Benchmark)))


def test_link_adds_renamed_group_when_name_match_has_no_post_move_in_trades(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    """이름으로 이은 묶음에는 오래된 분양권 거래뿐(입주 후 거래 없음) — 판정기가 고른 바뀐 이름의 묶음을 합친다."""
    add_list(
        add_raw, region.id, "인천", [notice_row("2021000101", "송도 미래 1차", ADDR, "2021-03-10", "202406")]
    )
    add_model(add_raw, region.id, "2021000101", [("084.9500A", 50000, 300)])
    _trades(db_session, add_raw, region, "송도미래1차", None, presale=True, days=("2023-12-10",))
    _trades(db_session, add_raw, region, NEW_NAME, 2024)
    reqs = link_requests(db_session, region.id, ASOF)
    assert [r.key for r in reqs] == ["2021000101:2021000101"]
    links = {"2021000101:2021000101": (normalize_apt_name(NEW_NAME), "송도동")}
    build_benchmarks(db_session, region.id, asof_date=ASOF, links=links)
    row = next(
        b
        for b in db_session.scalars(select(Benchmark))
        if b.name == "송도 미래 1차" and "대체" not in (b.note or "")
    )
    assert row.is_presale is False and row.n_trades == 2
    assert row.note is not None and "이름 완전 일치" in row.note and JUDGE_LINK in row.note

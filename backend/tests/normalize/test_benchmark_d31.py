"""D31-1·D31-2: 벤치마크 표본 넓히기 — 입주 뒤 분양권 거래만 있는 단지, 이름 끝부분 매칭, 같은 동 다른 표기 합치기.

- D31-1 입주는 했지만 입주 뒤 일반 거래가 아직 없고 분양권 거래만 있으면 ``is_presale=true`` 행(점수 제외)
- D31-2 완전 일치가 없을 때만 이름 끝부분 일치(블록 번호·'(민영주택)'·'본청약' 제거, 실거래 이름이 그 키로 끝날 때만, 블록 번호 다르면 아님),
  후보 둘 이상이면 매칭 모호. 같은 동에서 한 이름이 다른 이름의 끝부분이면 거래를 합친다.
"""

# ruff: noqa: E501  (한국어 docstring·발췌 문구)

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Benchmark, Region
from app.normalize.benchmark import block_codes, build_benchmarks, name_tail_keys, tail_matches

from ._assemble_support import ASOF, add_list, add_model, add_trade, rtms_url
from ._assemble_support import notice_row as _notice
from ._support import AddRaw

SONGDO = "2818510600"
ADDR = "인천광역시 연수구 송도동 1-1"


def _own(db_session: Session) -> dict[str, Benchmark]:
    rows = db_session.scalars(select(Benchmark).order_by(Benchmark.id))
    return {b.name: b for b in rows if b.note and "대체" not in b.note}


def _doc(add_raw: AddRaw, region: Region) -> int:
    return add_raw(
        "<response>t</response>",
        source_kind="rtms",
        url=rtms_url("28185", "202609"),
        region_id=region.id,
        ext="xml",
    ).id


def _one_notice(add_raw: AddRaw, region: Region, name: str, move_in: str = "202406") -> None:
    add_list(add_raw, region.id, "인천", [_notice("2021000101", name, ADDR, "2021-03-10", move_in)])
    add_model(add_raw, region.id, "2021000101", [("084.9500A", 50000, 300)])


@pytest.mark.parametrize(
    ("name", "first", "last"),
    [
        ("인천 검단신도시 AB17BL 우미린 클래스원", "인천검단신도시우미린클래스원", "우미린클래스원"),
        ("인천 검단신도시 AB3-1블록 대성베르힐", "인천검단신도시대성베르힐", "검단신도시대성베르힐"),
        ("인천검단신도시 디에트르 더 에듀(AA20BL)", "인천검단신도시디에트르더에듀", "디에트르더에듀"),
        ("힐스테이트 검단 웰카운티(민영주택)", "힐스테이트검단웰카운티", "검단웰카운티"),
        (
            "인천 청라국제도시 A-3블록 호반베르디움",
            "인천청라국제도시호반베르디움",
            "청라국제도시호반베르디움",
        ),
        ("제일풍경채 검단Ⅲ 본청약", "제일풍경채검단iii", "제일풍경채검단iii"),
    ],
)
def test_name_tail_keys_drop_block_codes_and_generic_words(name: str, first: str, last: str) -> None:
    keys = name_tail_keys(name)
    assert keys[0] == first and keys[-1] == last
    assert "검단iii" not in keys  # 끝 차수 번호를 뺀 글자가 5자 미만이면 키가 아니다
    assert (
        "호반베르디움" not in keys and "대성베르힐" not in keys
    )  # 낱말 하나(브랜드 이름)만으로는 잇지 않는다


def test_tail_matches_only_at_the_end_of_the_trade_name() -> None:
    assert tail_matches("신검단중앙역우미린클래스원", "우미린클래스원")
    assert not tail_matches(
        "검단신도시대성베르힐라프리미어", "대성베르힐"
    )  # 뒤에 다른 말 — 다른 단지일 수 있다
    assert not tail_matches("제일풍경채검단ii", "제일풍경채검단i")
    assert not tail_matches("푸르지오작전1단지", "푸르지오작전")
    assert block_codes("송도 AA13-1블록 자이") == {"aa13-1블록"} and block_codes("검단 AB17BL 우미린") == {
        "ab17블록"
    }


def test_tail_match_needs_equal_block_codes_when_both_have_one(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    _one_notice(add_raw, region, "송도 AA13-1블록 더샵 퍼스트")
    doc = _doc(add_raw, region)
    add_trade(
        db_session,
        region.id,
        "송도AA13-2블록더샵퍼스트",
        70000,
        "2026-01-10",
        legal=SONGDO,
        raw_document_id=doc,
    )
    res = build_benchmarks(db_session, region.id, asof_date=ASOF)
    assert _own(db_session) == {}
    assert [u["reason"] for u in res.unmatched] == ["실거래 없음(매칭 단지 없음)"]


def test_tail_match_links_prefixed_notice_name_to_trade_name(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    _one_notice(add_raw, region, "인천 송도국제도시 AB17BL 우미린 클래스원")
    doc = _doc(add_raw, region)
    for price, day in ((70000, "2026-01-10"), (72000, "2026-05-10")):
        add_trade(
            db_session, region.id, "신송도중앙역우미린클래스원", price, day, legal=SONGDO, raw_document_id=doc
        )
    build_benchmarks(db_session, region.id, asof_date=ASOF)
    row = _own(db_session)["인천 송도국제도시 AB17BL 우미린 클래스원"]
    assert row.n_trades == 2 and row.is_presale is False
    assert row.note is not None and "이름 끝부분 일치('우미린클래스원')" in row.note


def test_tail_match_does_not_cross_phase_numbers(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    _one_notice(add_raw, region, "제일풍경채 송도Ⅰ")
    doc = _doc(add_raw, region)
    add_trade(
        db_session, region.id, "제일풍경채송도Ⅱ", 70000, "2026-01-10", legal=SONGDO, raw_document_id=doc
    )
    res = build_benchmarks(db_session, region.id, asof_date=ASOF)
    assert _own(db_session) == {}
    assert [u["reason"] for u in res.unmatched] == ["실거래 없음(매칭 단지 없음)"]


def test_tail_match_with_two_candidates_is_ambiguous(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    _one_notice(add_raw, region, "인천 송도 AB5블록 대성베르힐")
    doc = _doc(add_raw, region)
    add_trade(
        db_session, region.id, "신송도대성베르힐", 70000, "2026-01-10", legal=SONGDO, raw_document_id=doc
    )
    add_trade(
        db_session, region.id, "구송도대성베르힐", 71000, "2026-01-11", legal=SONGDO, raw_document_id=doc
    )
    res = build_benchmarks(db_session, region.id, asof_date=ASOF)
    assert _own(db_session) == {}
    assert [u["reason"] for u in res.unmatched] == ["확인 불가(매칭 모호)"]


def test_exact_match_wins_over_tail_match(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    _one_notice(add_raw, region, "송도 대성베르힐")
    doc = _doc(add_raw, region)
    add_trade(db_session, region.id, "송도대성베르힐", 70000, "2026-01-10", legal=SONGDO, raw_document_id=doc)
    add_trade(
        db_session,
        region.id,
        "송도대성베르힐더센트로",
        99000,
        "2026-01-11",
        legal=SONGDO,
        raw_document_id=doc,
    )
    build_benchmarks(db_session, region.id, asof_date=ASOF)
    row = _own(db_session)["송도 대성베르힐"]
    assert row.trade_median_won == 700_000_000
    assert row.note is not None and "단지 매칭: 이름 완전 일치 + 법정동" in row.note


def test_same_complex_spelled_two_ways_in_one_dong_is_merged(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    """공고 이름과 같은 실거래 표기에는 분양권 거래만, 입주 뒤 거래는 머리말 없는 표기에 있다 → 합쳐서 입주 후 실거래 행."""
    _one_notice(add_raw, region, "송도신도시 롯데캐슬 넥스티엘", move_in="202604")
    doc = _doc(add_raw, region)
    add_trade(
        db_session,
        region.id,
        "송도신도시롯데캐슬넥스티엘",
        60000,
        "2026-02-10",
        legal=SONGDO,
        presale=True,
        raw_document_id=doc,
    )
    for price, day in ((80000, "2026-05-10"), (82000, "2026-09-10")):
        add_trade(db_session, region.id, "롯데캐슬넥스티엘", price, day, legal=SONGDO, raw_document_id=doc)
    build_benchmarks(db_session, region.id, asof_date=ASOF)
    row = _own(db_session)["송도신도시 롯데캐슬 넥스티엘"]
    assert row.is_presale is False and row.n_trades == 2
    assert row.note is not None and "같은 동 다른 표기 '롯데캐슬넥스티엘'" in row.note


def test_moved_in_complex_with_presale_trades_only_is_a_presale_row(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    _one_notice(add_raw, region, "송도 칸타빌 더 스위트", move_in="202606")
    doc = _doc(add_raw, region)
    for price, day in ((65000, "2026-03-10"), (66000, "2026-08-10")):
        add_trade(
            db_session,
            region.id,
            "송도칸타빌더스위트",
            price,
            day,
            legal=SONGDO,
            presale=True,
            raw_document_id=doc,
        )
    res = build_benchmarks(db_session, region.id, asof_date=ASOF)
    row = _own(db_session)["송도 칸타빌 더 스위트"]
    assert row.is_presale is True and row.n_trades == 2
    assert row.note is not None and "분양권 거래(입주 뒤 일반 거래 아직 없음)" in row.note
    assert res.presale == 1 and all(n == 0 for n in res.samples.values())  # 점수 표본 아님


def test_moved_in_complex_with_general_trades_keeps_ignoring_presale(
    db_session: Session, add_raw: AddRaw, region: Region
) -> None:
    _one_notice(add_raw, region, "송도 칸타빌 더 스위트", move_in="202606")
    doc = _doc(add_raw, region)
    add_trade(
        db_session,
        region.id,
        "송도칸타빌더스위트",
        65000,
        "2026-03-10",
        legal=SONGDO,
        presale=True,
        raw_document_id=doc,
    )
    add_trade(
        db_session, region.id, "송도칸타빌더스위트", 90000, "2026-08-10", legal=SONGDO, raw_document_id=doc
    )
    build_benchmarks(db_session, region.id, asof_date=ASOF)
    row = _own(db_session)["송도 칸타빌 더 스위트"]
    assert row.is_presale is False and (row.n_trades, row.trade_median_won) == (1, 900_000_000)

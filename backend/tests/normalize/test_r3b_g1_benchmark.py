"""R3b G1 — 벤치마크·잔여 공고 (N-M1 = D10-5, F1a minor).

N-M1: 단지 매칭은 정규화 이름 **완전 일치**(차수·단지·블록 유지) + 법정동 일치만. 포함·준공연도 근사 금지.
리뷰 재현 3건(부정): '더샵 송도 퍼스트'→'더샵송도퍼스트파크2단지', '힐스테이트 송도'→'…2차', AA13-1 ≠ AA13-2.
F1a: 분양가 라벨은 실거래 라벨과 섞지 않는다 · 대체 행 note 에 '확인됨' 없음 · 84㎡ 최근접이 80~85㎡ 밖이면
표본 아님 · 법정동 변환 실패 공고 기록 · 원문 재읽기·N+1 없음 · 첫 적재 과거 잔여 공고는 info.
"""

# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models import Benchmark, Region
from app.normalize import benchmark as bm
from app.normalize.benchmark import build_benchmarks, normalize_apt_name

from ._assemble_support import ASOF, add_list, add_model, add_trade, notice_row, rtms_url
from ._support import AddRaw

SONGDO = "2818510600"


def _rows(db_session: Session) -> list[Benchmark]:
    return list(db_session.scalars(select(Benchmark).order_by(Benchmark.id)))


def _own(db_session: Session) -> dict[str, Benchmark]:
    return {b.name: b for b in _rows(db_session) if b.note and "대체" not in b.note}


def _trades(db_session: Session, add_raw: AddRaw, region: Region, name: str, *, source: str = "openapi") -> None:
    doc = add_raw(f"<r>{name}</r>", source_kind="rtms", url=rtms_url("28185", "202609") + f"&t={name}",
                  region_id=region.id, ext="xml")  # fmt: skip
    for price, day in ((80000, "2025-12-15"), (90000, "2026-03-02")):
        add_trade(db_session, region.id, name, price, day, legal=SONGDO, built=2024,
                  raw_document_id=doc.id, source=source)  # fmt: skip


def _notice(add_raw: AddRaw, region: Region, hm: str, name: str, *, types: Any = None, addr: str = "인천광역시 연수구 송도동 1-1") -> None:
    add_list(add_raw, region.id, "인천", [notice_row(hm, name, addr, "2021-03-10", "202406")],
             url=f"https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail?x={hm}")  # fmt: skip
    add_model(add_raw, region.id, hm, types or [("084.9500A", 70000, 300)])


# ---------------------------------------------------------------- N-M1 (D10-5)


def test_nm1_name_key_keeps_phase_complex_and_block_numbers() -> None:
    assert normalize_apt_name("검단 AA13-1블록 우미린") != normalize_apt_name("검단 AA13-2블록 우미린")
    assert normalize_apt_name("검단신도시 AB12블록 우미린") != normalize_apt_name("검단신도시 우미린")
    assert normalize_apt_name("힐스테이트 송도") != normalize_apt_name("힐스테이트 송도 2차")
    assert normalize_apt_name("푸르지오 1단지") != normalize_apt_name("푸르지오 2단지")
    # 같은 것: 공백·대소문자·괄호 기호, 잔여 공고 회차 괄호
    assert normalize_apt_name("힐스테이트 레이크 송도(2차)") == normalize_apt_name("힐스테이트레이크송도2차")
    assert normalize_apt_name("e편한세상 김포") == normalize_apt_name("E편한세상김포")
    assert normalize_apt_name("더샵 송도마리나베이(조합원 자격상실세대 3회차)") == normalize_apt_name("더샵송도마리나베이")


@pytest.mark.parametrize(
    ("notice_name", "trade_name"),
    [
        ("더샵 송도 퍼스트", "더샵송도퍼스트파크2단지"),  # 리뷰 재현 1: 포함 매칭
        ("힐스테이트 송도", "힐스테이트송도2차"),  # 리뷰 재현 2: 차수 다른 단지
        ("송도 AA13-1블록 자이", "송도AA13-2블록자이"),  # 리뷰 재현 3: 블록 번호 제거
    ],
)
def test_nm1_review_repro_no_contains_or_block_stripping_match(
    db_session: Session, add_raw: AddRaw, region: Region, notice_name: str, trade_name: str
) -> None:
    _notice(add_raw, region, "2021000101", notice_name)
    _trades(db_session, add_raw, region, trade_name)
    res = build_benchmarks(db_session, region.id, asof_date=ASOF)
    assert _rows(db_session) == []
    assert [u["reason"] for u in res.unmatched] == ["실거래 없음(매칭 단지 없음)"]


def test_nm1_exact_block_name_matches(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    _notice(add_raw, region, "2021000101", "송도 AA13-1블록 자이")
    _trades(db_session, add_raw, region, "송도AA13-2블록자이")
    _trades(db_session, add_raw, region, "송도AA13-1블록자이")
    build_benchmarks(db_session, region.id, asof_date=ASOF)
    assert set(_own(db_session)) == {"송도 AA13-1블록 자이"}
    assert _own(db_session)["송도 AA13-1블록 자이"].n_trades == 2


def test_nm1_build_year_is_not_used_for_matching(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    """준공연도 근사(±1)로 거르거나 고르지 않는다 — 이름·법정동 완전 일치면 매칭."""
    _notice(add_raw, region, "2021000101", "송도 센트럴")
    doc = add_raw("<r/>", source_kind="rtms", url=rtms_url("28185", "202609"), region_id=region.id, ext="xml")
    add_trade(db_session, region.id, "송도센트럴", 90000, "2026-03-02", legal=SONGDO, built=2015, raw_document_id=doc.id)
    build_benchmarks(db_session, region.id, asof_date=ASOF)
    assert set(_own(db_session)) == {"송도 센트럴"}


# ---------------------------------------------------------------- F1a 라벨·note·74㎡


def test_f1a_sale_price_label_not_mixed_with_trade_label(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    _notice(add_raw, region, "2021000101", "송도 센트럴")
    _trades(db_session, add_raw, region, "송도센트럴", source="reprocessed")
    build_benchmarks(db_session, region.id, asof_date=ASOF)
    row = _own(db_session)["송도 센트럴"]
    assert row.sale_price_label == "확인됨"  # 분양가(청약홈 공식 API) — 실거래 '재가공' 과 섞지 않는다
    assert row.note is not None and "재가공" in row.note


def test_f1a_substitute_note_does_not_claim_confirmed(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    _notice(add_raw, region, "2021000101", "송도 센트럴")
    _trades(db_session, add_raw, region, "송도센트럴")
    build_benchmarks(db_session, region.id, asof_date=ASOF)
    subs = [b for b in _rows(db_session) if b.note and "대체" in b.note]
    assert subs
    for b in subs:
        assert b.sale_price_label == "추정"
        assert "확인됨" not in (b.note or "")


def test_f1a_nearest_type_outside_84_band_is_not_compared(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    """84㎡ 최근접 주택형이 74㎡면 80~85㎡ 실거래와 비교하지 않는다(사유 기록)."""
    _notice(add_raw, region, "2021000101", "송도 센트럴", types=[("074.9000A", 50000, 100), ("101.0000A", 90000, 50)])
    _trades(db_session, add_raw, region, "송도센트럴")
    res = build_benchmarks(db_session, region.id, asof_date=ASOF)
    assert _rows(db_session) == []
    assert res.unmatched and res.unmatched[0]["reason"].startswith("확인 불가(84㎡대 주택형 없음")


def test_f1a_legal_dong_conversion_failure_is_recorded(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    """지역 시군구 안 주소인데 법정동으로 못 바꾸면 사유를 남긴다(무기록 소실 금지). 지역 밖 주소는 기록하지 않는다."""
    _notice(add_raw, region, "2021000101", "송도 센트럴", addr="인천광역시 연수구 없는동 1")
    _notice(add_raw, region, "2021000102", "부산 단지", addr="부산광역시 해운대구 우동 1")
    res = build_benchmarks(db_session, region.id, asof_date=ASOF)
    reasons = {u["notice_no"]: u["reason"] for u in res.unmatched}
    assert reasons == {"2021000101": "확인 불가(법정동 변환 실패)"}


# ---------------------------------------------------------------- F1a 원문 재읽기·N+1


@contextmanager
def _count_sql(db_session: Session, *tables: str) -> Iterator[list[str]]:
    seen: list[str] = []
    engine = db_session.get_bind()

    def on(conn: Any, cursor: Any, statement: str, *a: Any) -> None:
        low = statement.lower()
        if low.lstrip().startswith("select") and any(f"from {t}" in low for t in tables):
            seen.append(statement)

    event.listen(engine, "before_cursor_execute", on)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", on)


def _seed_n(db_session: Session, add_raw: AddRaw, region: Region, n: int, start: int = 0) -> None:
    idx = range(start, start + n)
    rows = [notice_row(f"20210{i:05d}", f"송도 단지{i}", f"인천광역시 연수구 송도동 {i}", "2021-03-10", "202406") for i in idx]
    add_list(add_raw, region.id, "인천", rows, url=f"https://api.odcloud.kr/api/x/getAPTLttotPblancDetail?s={start}")
    for i in idx:
        add_model(add_raw, region.id, f"20210{i:05d}", [("084.9500A", 70000, 300)])
        _trades(db_session, add_raw, region, f"송도단지{i}")


def test_f1a_no_n_plus_one_queries(db_session: Session, add_raw: AddRaw, region: Region) -> None:
    _seed_n(db_session, add_raw, region, 2)
    with _count_sql(db_session, "legal_dong", "raw_document") as few:
        build_benchmarks(db_session, region.id, asof_date=ASOF)
    _seed_n(db_session, add_raw, region, 8, start=10)
    with _count_sql(db_session, "legal_dong", "raw_document") as many:
        build_benchmarks(db_session, region.id, asof_date=ASOF)
    assert len(_own(db_session)) >= 8
    assert len(many) == len(few), (len(few), len(many))


def test_f1a_same_url_is_read_once(db_session: Session, add_raw: AddRaw, region: Region, monkeypatch: pytest.MonkeyPatch) -> None:
    """같은 URL 을 매일 다시 받은 원문은 최신 것만 읽는다(옛 원문 재읽기 없음)."""
    for day in ("2026-10-06", "2026-10-07", "2026-10-08"):
        add_list(add_raw, region.id, "인천",
                 [notice_row("2021000101", "송도 센트럴", "인천광역시 연수구 송도동 1", "2021-03-10", "202406") | {"X": day}],
                 fetched_at=f"{day}T06:00:00+09:00")  # fmt: skip
    add_model(add_raw, region.id, "2021000101", [("084.9500A", 70000, 300)])
    calls: list[int] = []
    real = bm.read_raw_row

    def spy(row: Any) -> str | None:
        calls.append(row.id)
        return real(row)

    monkeypatch.setattr(bm, "read_raw_row", spy)
    build_benchmarks(db_session, region.id, asof_date=ASOF)
    assert len(calls) == 2  # 목록 1(최신) + 주택형 1

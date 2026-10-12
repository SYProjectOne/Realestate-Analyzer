"""R4 재시험 N5(major, D21-4) — 실거래 사실의 출처는 원문 문서 단위(``rd_<raw_document_id>``), 시장 생활권 시세 블록 복구.

R4: 실거래 52,163건은 수집기 적재(``collectors.rtms.collector.load_trades``)라 거래 행마다 ``field_provenance`` 가 없다. C2 수정으로
시장 탭이 거래를 쓰기 시작하자 출처 누락 거래가 하나라도 있으면 생활권 블록을 통째로 빼(``market.py``) G3 시장
``living_area_prices`` 가 빈 목록, 발행 stats ``missing_provenance`` 5,938 → 5,973(1차의 10배, 전부 ``rtms_trade.price_won``).

D21-4: 거래 행마다 출처 행을 만들지 않고, 그 거래를 실은 실거래 API 원문(raw_document)을 출처로 쓴다 — Fact ``prov`` =
``rd_<id>``(출처 서랍 = 원문 URL·확인일, D15-2 의 rd_ 서랍과 같다), 라벨 = 실거래 Open API 1차 '확인됨'.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.facts import MISSING_COUNT
from app.api.routers.market import market_body
from app.core.settings import Settings
from app.models import RawDocument, RtmsTrade, Snapshot


def _attach_raw(s: Session) -> int:
    raw = RawDocument(
        source_kind="rtms",
        url="https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade?LAWD_CD=28185&DEAL_YMD=202609",
        fetched_at="2026-10-07T05:00:00+09:00", http_status=200, sha256="c" * 64,
        path="rtms/2026-10-07/" + "c" * 64 + ".xml", content_type="application/xml", region_id=1,
    )  # fmt: skip
    s.add(raw)
    s.flush()
    for t in s.scalars(select(RtmsTrade)):
        t.raw_document_id = raw.id
    s.commit()
    return raw.id


def _body(factory: sessionmaker[Session], settings: Settings, sid: int) -> tuple[dict[str, Any], int]:
    box = [0]
    token = MISSING_COUNT.set(box)  # 저장본 계산(materialize)과 같은 모드 — 출처 누락은 라벨 + 건수
    try:
        with factory() as s:
            snap = s.get(Snapshot, sid)
            assert snap is not None
            body = market_body(s, settings, snap, None)
    finally:
        MISSING_COUNT.reset(token)
    return body, box[0]


def test_living_area_prices_use_raw_document_provenance(
    factory: sessionmaker[Session], seeded: int, test_settings: Settings
) -> None:
    before, missing_before = _body(factory, test_settings, seeded)
    assert before["living_area_prices"] == [], "원문도 출처 행도 없는 거래(옛 시드)는 출처 누락 — 빈 출처를 지어내지 않는다"
    with factory() as s:
        rid = _attach_raw(s)
        n_trades = len(list(s.scalars(select(RtmsTrade))))
    body, missing = _body(factory, test_settings, seeded)
    prices = body["living_area_prices"]
    assert prices, "실거래 출처 행이 없어도 생활권 84㎡ 시세 블록이 있다(원문 문서 단위 출처)"
    for p in prices:
        for key in ("median_won", "low_won", "high_won", "n_trades"):
            f = p[key]
            assert f["label"] == "확인됨" and f["prov"] == f"rd_{rid}", (key, f)
            assert f["checked_at"] == "2026-10-07"
    # 시드의 다른 사실(출처 행 없는 단지 필드)은 그대로 — 줄어든 만큼이 실거래 거래(출처 누락 → rd_)
    assert 0 < missing_before - missing <= n_trades, (missing_before, missing, n_trades)

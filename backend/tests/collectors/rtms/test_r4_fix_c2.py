"""R4-FIX C2 (D18-3) — 실제 실거래 응답에는 ``umdCd`` 가 없다 → ``sggCd + umdNm`` 을 참조 표(legal_dong)로 매칭.

녹화(실제 응답, R4 2026-10-12 수집분을 법정동마다 1건으로 줄임 — 키 없음):
- ``openapi_trade_28290_202609_trim.xml`` 검단구(신설 구) 8개 동 — '오류동' 은 계양구에도 있다(시군구 코드로만 구별)
- ``openapi_trade_41570_202609_trim.xml`` 김포시 16개 — '고촌읍 신곡리' 처럼 읍면 + 리 두 낱말

| 테스트 | 확인 |
| --- | --- |
| ``test_real_shape_has_no_umdcd_but_keeps_sgg`` | 실제 모양: umdCd 없음, 거래에 시군구 코드가 남는다 |
| ``test_load_matches_sgg_and_umd_name`` | 적재 시 참조 표 매칭 → 법정동 코드, 매칭률 stats |
| ``test_unmatched_and_ambiguous_stay_null_with_reason`` | 매칭 실패·모호는 NULL + 사유(stats) |
| ``test_existing_null_rows_are_repaired`` | 이미 적재된 NULL 행 보정(원문 URL 의 LAWD_CD + 동 이름) — 다시 받은 달·안 받은 달 모두 |
| ``test_reload_after_fix_does_not_duplicate`` | 보정 전 적재분(키 = 동 이름)과 같은 거래를 다시 받아도 행이 늘지 않는다 |
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from pathlib import Path

import httpx
import respx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collectors.rtms import RTMS_API_URL, RtmsCollector, load_trades, parse_trade_xml
from app.core.contracts_gen import Region, Snapshot
from app.core.http import HttpClient
from app.models import LegalDong, RawDocument, RtmsTrade

GEOMDAN = "openapi_trade_28290_202609_trim.xml"
GIMPO = "openapi_trade_41570_202609_trim.xml"
URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade?LAWD_CD={}&DEAL_YMD=202609&numOfRows=1000&pageNo=1"


def _ld(code: str, sido: str, sgg: str, emd: str, ri: str | None = None, *, active: bool = True) -> LegalDong:
    full = " ".join(x for x in (sido, sgg, emd, ri) if x)
    return LegalDong(
        code=code, sido_name=sido, sigungu_name=sgg, eupmyeondong_name=emd, ri_name=ri, full_name=full,
        sigungu_code=code[:5], active=active, source_date="2026-10-12",
    )  # fmt: skip


GEOMDAN_DONGS = {
    "백석동": "2829010100", "시천동": "2829010200", "마전동": "2829010300", "당하동": "2829010400",
    "원당동": "2829010500", "대곡동": "2829010600", "금곡동": "2829010700", "오류동": "2829010800",
    "왕길동": "2829010900", "불로동": "2829011000",
}  # fmt: skip


def _seed_reference(s: Session) -> None:
    for name, code in GEOMDAN_DONGS.items():
        s.add(_ld(code, "인천광역시", "검단구", name))
        # 분구 전 서구 행(폐지) — 시군구 코드가 달라 매칭에 끼지 않는다
        s.add(_ld("28260" + code[5:], "인천광역시", "서구", name, active=False))
    s.add(_ld("2824511800", "인천광역시", "계양구", "오류동"))  # 같은 동 이름, 다른 구
    s.add(_ld("4157010600", "경기도", "김포시", "풍무동"))
    s.add(_ld("4157010100", "경기도", "김포시", "북변동"))
    s.add(_ld("4157025324", "경기도", "김포시", "고촌읍", "신곡리"))
    s.add(_ld("4157025300", "경기도", "김포시", "고촌읍"))
    s.flush()


def _doc(s: Session, lawd: str) -> int:
    row = RawDocument(
        source_kind="rtms", url=URL.format(lawd), fetched_at="2026-10-12T06:30:00+09:00", http_status=200,
        sha256=lawd * 2, path=f"rtms/2026-10-12/{lawd}.xml", content_type="application/xml", region_id=1,
    )  # fmt: skip
    s.add(row)
    s.flush()
    return int(row.id)


def test_real_shape_has_no_umdcd_but_keeps_sgg(fixtures_dir: Path) -> None:
    content = (fixtures_dir / GEOMDAN).read_bytes()
    assert b"<umdCd>" not in content and b"serviceKey" not in content
    page = parse_trade_xml(content)
    assert page.ok and len(page.items) == 8
    assert {t.sgg_code for t in page.items} == {"28290"}
    assert all(t.legal_dong_code is None for t in page.items)  # 파서는 참조 표 없이 만들지 않는다
    gimpo = parse_trade_xml((fixtures_dir / GIMPO).read_bytes())
    assert "고촌읍 신곡리" in {t.dong for t in gimpo.items}


def test_load_matches_sgg_and_umd_name(
    region_ctx: tuple[Region, Snapshot], fixtures_dir: Path, db_session: Session
) -> None:
    s = db_session
    _seed_reference(s)
    g, k = _doc(s, "28290"), _doc(s, "41570")
    trades = [(g, t) for t in parse_trade_xml((fixtures_dir / GEOMDAN).read_bytes()).items]
    trades += [(k, t) for t in parse_trade_xml((fixtures_dir / GIMPO).read_bytes()).items]
    stats = load_trades(s, 1, trades)
    s.flush()
    codes = {(r.dong, r.legal_dong_code) for r in s.scalars(select(RtmsTrade))}
    assert ("오류동", "2829010800") in codes, "오류동은 시군구 코드(28290)로 검단구 — 계양구 오류동 아님"
    assert ("고촌읍 신곡리", "4157025324") in codes
    assert ("풍무동", "4157010600") in codes
    assert stats.legal_dong["matched"] == 8 + 3
    assert stats.legal_dong["unmatched"] == 16 - 3  # 참조 표에 넣지 않은 김포 동
    assert stats.legal_dong["ambiguous"] == 0
    assert 0 < stats.legal_dong_match_rate() < 1


def test_unmatched_and_ambiguous_stay_null_with_reason(
    region_ctx: tuple[Region, Snapshot], fixtures_dir: Path, db_session: Session
) -> None:
    from app.collectors.rtms.legal import LegalDongIndex

    s = db_session
    _seed_reference(s)
    s.add(_ld("4157010699", "경기도", "김포시", "풍무동"))  # 같은 시군구·같은 이름 2개 → 모호
    s.flush()
    idx = LegalDongIndex.load(s, ["28290", "41570"])
    assert idx.resolve("28290", "오류동") == ("2829010800", None)
    assert idx.resolve("41570", "풍무동")[0] is None and idx.resolve("41570", "풍무동")[1] == "모호"
    assert idx.resolve("41570", "없는동") == (None, "참조 표에 없음")
    assert idx.resolve(None, "오류동") == (None, "시군구 코드 없음")


def test_existing_null_rows_are_repaired(
    region_ctx: tuple[Region, Snapshot], fixtures_dir: Path, db_session: Session
) -> None:
    """R4 DB 처럼 법정동 코드 없이 적재된 행: 원문 URL 의 LAWD_CD + 동 이름으로 보정한다(다시 받지 않은 달 포함)."""
    from app.collectors.rtms.legal import repair_legal_dong_codes

    s = db_session
    _seed_reference(s)
    g = _doc(s, "28290")
    for t in parse_trade_xml((fixtures_dir / GEOMDAN).read_bytes()).items:
        s.add(RtmsTrade(region_id=1, apt_name=t.apt_name, dong=t.dong, legal_dong_code=None, area_m2=t.area_m2,
                        floor=t.floor, price_won=t.price_won, deal_date=t.deal_date, cancelled=t.cancelled,
                        is_presale=False, source="openapi", raw_document_id=g))  # fmt: skip
    s.flush()
    out = repair_legal_dong_codes(s, 1)
    assert out == {"repaired": 8, "unmatched": 0, "ambiguous": 0, "no_sgg": 0}
    assert (
        s.scalar(select(func.count()).select_from(RtmsTrade).where(RtmsTrade.legal_dong_code.is_(None))) == 0
    )
    assert repair_legal_dong_codes(s, 1)["repaired"] == 0  # 멱등


def test_reload_after_fix_does_not_duplicate(
    region_ctx: tuple[Region, Snapshot], fixtures_dir: Path, db_session: Session
) -> None:
    s = db_session
    _seed_reference(s)
    g = _doc(s, "28290")
    items = parse_trade_xml((fixtures_dir / GEOMDAN).read_bytes()).items
    for t in items:  # 보정 전 적재분(코드 NULL)
        s.add(RtmsTrade(region_id=1, apt_name=t.apt_name, dong=t.dong, legal_dong_code=None, area_m2=t.area_m2,
                        floor=t.floor, price_won=t.price_won, deal_date=t.deal_date, cancelled=t.cancelled,
                        is_presale=False, source="openapi", raw_document_id=g))  # fmt: skip
    s.flush()
    stats = load_trades(s, 1, [(g, t) for t in items])
    assert stats.inserted == 0 and stats.unchanged + stats.updated == 8
    assert s.scalar(select(func.count()).select_from(RtmsTrade)) == 8
    assert (
        s.scalar(select(func.count()).select_from(RtmsTrade).where(RtmsTrade.legal_dong_code.is_(None))) == 0
    )


def test_collector_replay_records_match_rate(
    region_ctx: tuple[Region, Snapshot], fixtures_dir: Path, db_session: Session, http: HttpClient
) -> None:
    """녹화 재생(수집기 전체 경로): 김포 실제 응답 → 참조 표 매칭 코드 + load_stats 매칭률(수집 stats 로 나간다)."""
    region, snapshot = region_ctx
    _seed_reference(db_session)
    db_session.commit()
    snap = snapshot.model_copy(update={"asof_date": "2026-09-30"})
    gimpo = (fixtures_dir / GIMPO).read_bytes()
    empty = (fixtures_dir / "openapi_trade_empty.xml").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        body = gimpo if request.url.params["LAWD_CD"] == "41570" else empty
        return httpx.Response(200, content=body, headers={"content-type": "application/xml"})

    with respx.mock(assert_all_called=False) as router:
        router.get(RTMS_API_URL).mock(side_effect=handler)
        collector = RtmsCollector(service_key="TEST%2BKEY%3D%3D", http=http, months=1, presale=False)
        collector.fetch(region, snap, None)
    st = collector.load_stats
    assert st is not None and st.inserted == 16
    legal = st.legal_dong_stats()  # type: ignore[attr-defined]
    assert (legal["matched"], legal["unmatched"], legal["ambiguous"]) == (3, 13, 0)
    assert legal["match_rate"] == round(3 / 16, 4)
    with Session(db_session.get_bind()) as s:
        coded = {r.dong: r.legal_dong_code for r in s.scalars(select(RtmsTrade))}
    assert coded["고촌읍 신곡리"] == "4157025324" and coded["풍무동"] == "4157010600"

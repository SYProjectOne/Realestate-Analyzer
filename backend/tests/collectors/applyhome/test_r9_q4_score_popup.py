"""R9-PARSE Q4(20-gap §2-2, D28-5) — 당첨가점(최저·최고·평균)은 청약홈 **웹 경쟁률 팝업**에만 있다(공식 API 경쟁률에 없음).

수집기는 API 경로에서 웹 경쟁률 팝업을 API 경쟁률이 실패했을 때만 받았다 → 가점이 한 번도 수집되지 않았다(운영 원문 226개 HTML 중
경쟁률 팝업 0). 이제 APT 공고는 당첨자 발표·접수 마감(``last_date``)이 지난 뒤 팝업을 받는다(그 전 팝업은 가점 칸이 '-'). 받아 둔
팝업이 발표 뒤 것이면 다시 받지 않는다(멱등). 잔여세대·임의공급 팝업에는 가점이 없다. 원 공고 다시 받기(``fetch_originals``)도
팝업을 받는다. 공개 페이지만, ``core.http`` 속도 제한·robots(청약홈 robots 404 = 제한 없음).

픽스처 ``fixtures/r9_q4/``: 운영 수집(2026-10-13) 공식 API 상세·경쟁률 원문(키 없음)과 2026-10-14 받은 웹 경쟁률 팝업(2025000560).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx
import respx
from sqlalchemy.orm import Session

from app.collectors.applyhome import ApplyhomeCollector, api, site
from app.core.contracts_gen import Region, Snapshot
from app.core.http import HttpClient

from .conftest import FIXTURES, make_region

R9 = FIXTURES / "r9_q4"
FAKE_KEY = "TEST%2BKEY%3D%3D"
HM = "2025000560"
EMPTY_OK = b'{"currentCount":0,"data":[],"matchCount":0,"page":1,"perPage":100,"totalCount":2900}'
POPUP = site.competition_url("apt", HM, HM)


def _row(kind: api.ApiKind = "apt", last: str | None = "2025-12-09") -> api.ApiRow:
    return api.ApiRow(
        kind=kind,
        house_manage_no=HM,
        pblanc_no=HM,
        name="x",
        address=None,
        area_name="인천",
        notice_date="2025-11-21",
        last_date=last,
    )


def _known(fetched: str) -> Any:
    return SimpleNamespace(fetched_at=fetched)


def test_popup_due_rule() -> None:
    c = ApplyhomeCollector(today=lambda: date(2026, 10, 14), service_key=FAKE_KEY)
    assert c._score_popup_due(_row(), None)  # 발표 지남·받은 팝업 없음
    assert c._score_popup_due(_row(), _known("2025-12-05T10:00:00+09:00"))  # 발표 전에 받은 팝업(가점 '-')
    assert not c._score_popup_due(
        _row(), _known("2025-12-10T10:00:00+09:00")
    )  # 발표 뒤 받은 팝업 — 다시 받지 않음
    assert not c._score_popup_due(_row("remndr"), None) and not c._score_popup_due(
        _row("opt"), None
    )  # 가점 없는 팝업
    assert not c._score_popup_due(_row(last=None), None)
    early = ApplyhomeCollector(today=lambda: date(2025, 12, 9), service_key=FAKE_KEY)
    assert not early._score_popup_due(_row(), None)  # 발표 당일까지는 가점이 없다
    off = ApplyhomeCollector(today=lambda: date(2026, 10, 14), service_key=FAKE_KEY, web_detail=False)
    assert not off._score_popup_due(_row(), None)


def _api_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    q = dict(parse_qsl(urlsplit(str(request.url)).query))
    if "getAPTLttotPblancDetail" in path:
        if q.get("cond[HOUSE_MANAGE_NO::EQ]") == HM or "cond[RCRIT_PBLANC_DE::GTE]" in q:
            body = (R9 / "api_APTDetail_2025000560.json").read_bytes()
        else:
            body = EMPTY_OK
    elif "getAPTLttotPblancCmpet" in path:
        body = (R9 / "api_APTCmpet_2025000560.json").read_bytes()
    elif "getAPTLttotPblancMdl" in path:
        body = b'{"currentCount":1,"data":[{"HOUSE_MANAGE_NO":"2025000560","HOUSE_TY":"059.9801 ","SUPLY_HSHLDCO":73,"SPSPLY_HSHLDCO":84,"PBLANC_NO":"2025000560","MODEL_NO":"01"}],"matchCount":1,"page":1,"perPage":100,"totalCount":2900}'
    else:  # 잔여세대·임의공급 목록 — 정상 0건
        body = EMPTY_OK
    return httpx.Response(200, content=body, headers={"content-type": "application/json"})


def _mock(router: respx.MockRouter) -> respx.Route:
    router.route(host="api.odcloud.kr").mock(side_effect=_api_handler)
    router.get("https://www.applyhome.co.kr/robots.txt").respond(404)
    router.get(url__startswith=site.BASE + site.ENDPOINTS["apt"].detail_path).respond(
        200, html="<html>상세</html>"
    )
    return router.get(url__startswith=site.BASE + site.ENDPOINTS["apt"].competition_path).respond(
        200,
        content=(R9 / "web_competition_2025000560.html").read_bytes(),
        headers={"content-type": "text/html;charset=UTF-8"},
    )


def _region() -> Region:
    return make_region(
        selections=[{"kind": "sigungu", "code": "28177", "full_name": "인천광역시 미추홀구"}],
        sido_codes=["28"],
        sigungu_codes=["28177"],
        legal_dong_codes=[],
    )


def test_api_path_fetches_popup_once_after_winners(
    http: HttpClient, db_session: Session, seeded_region: Region, snapshot: Snapshot
) -> None:
    region = _region()
    with respx.mock(assert_all_called=False) as router:
        popup = _mock(router)
        c = ApplyhomeCollector(
            http=http,
            session=db_session,
            today=lambda: date(2026, 10, 14),
            service_key=FAKE_KEY,
            window=("2025-11", "2025-12"),
        )
        docs = c.fetch(region, snapshot, None)
        assert popup.call_count == 1
        got = [d for d in docs if d.url == POPUP]
        assert [(d.source_kind, d.http_status) for d in got] == [("applyhome_detail", 200)]
        assert Path(got[0].path or "").suffix == ".html"
        # 다음 수집(같은 날, 이미 끝난 공고 — since 가 발표일 뒤): 받아 둔 발표 뒤 팝업을 다시 쓰고 요청하지 않는다
        again = ApplyhomeCollector(
            http=http,
            session=db_session,
            today=lambda: date(2026, 10, 14),
            service_key=FAKE_KEY,
            window=("2025-11", "2025-12"),
        )
        docs2 = again.fetch(region, snapshot, "2026-10-13T00:00:00+09:00")
        assert popup.call_count == 1
        assert [d.id for d in docs2 if d.url == POPUP] == [got[0].id]


def test_originals_refetch_gets_popup(
    http: HttpClient, db_session: Session, seeded_region: Region, snapshot: Snapshot
) -> None:
    with respx.mock(assert_all_called=False) as router:
        popup = _mock(router)
        c = ApplyhomeCollector(
            http=http, session=db_session, today=lambda: date(2026, 10, 14), service_key=FAKE_KEY
        )
        docs = c.fetch_originals(seeded_region, snapshot, [HM])
        assert popup.call_count == 1 and [d.http_status for d in docs if d.url == POPUP] == [200]
        c.fetch_originals(seeded_region, snapshot, [HM])
        assert popup.call_count == 1  # 받아 둔 성공 원문 — 다시 받지 않는다

"""R3b F1a (청약홈 API): 경쟁률 페이지 순회 + 인코딩된 키 마스킹.

1. 경쟁률(``…Cmpet``) 1건 조회는 ``perPage=100`` 한 페이지만 받아 주택형×순위×거주지역 행이
   100을 넘으면 잘렸다(``api.py:115-122``). ``matchCount`` 를 채울 때까지 페이지를 돌고, 페이지마다
   원문 1행(URL 의 page 로 구별).
2. 오류 문구에서 키를 디코딩 형태만 가렸다(``api.py:224``). httpx 오류 메시지의 URL 에는 퍼센트
   인코딩된 키가 있다 → 원문·``quote``·``quote_plus``·인코딩 키 어느 형태로도 FetchResult·
   raw_document·경로 사유에 남지 않는다.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, quote_plus, unquote

import httpx
import respx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.applyhome import ApplyhomeCollector, api
from app.core.contracts_gen import Region, Snapshot
from app.core.http import HttpClient
from app.models import RawDocument as RawRow

from .conftest import TODAY

HM = "2026000999"
ROW = {
    "HOUSE_MANAGE_NO": HM,
    "PBLANC_NO": HM,
    "HOUSE_NM": "테스트 경쟁률 단지",
    "HSSPLY_ADRES": "인천광역시 연수구 송도동 1-1",
    "SUBSCRPT_AREA_CODE_NM": "인천",
    "RCRIT_PBLANC_DE": "2026-09-01",
    "RCEPT_ENDDE": "2026-09-10",
    "PRZWNER_PRESNATN_DE": "2026-09-20",
}
MODEL = {"HOUSE_MANAGE_NO": HM, "PBLANC_NO": HM, "HOUSE_TY": "084.9000A", "LTTOT_TOP_AMOUNT": "70000"}
N_COMP = 150
# 실제 키 모양(+ / = 가 들어 있다) — 가짜
ENCODED_KEY = "Zx9%2BQw%2FEr7Ty5Ui3Op%3D%3D"
DECODED_KEY = unquote(ENCODED_KEY)


def key_forms(key: str = DECODED_KEY) -> set[str]:
    return {key, quote(key, safe=""), quote(key), quote_plus(key), ENCODED_KEY}


def _page(rows: list[dict[str, Any]], *, match: int, page: int = 1, total: int = 99_999) -> dict[str, Any]:
    return {
        "page": page,
        "perPage": api.PER_PAGE,
        "currentCount": len(rows),
        "matchCount": match,
        "totalCount": total,  # 조건 없는 전체 건수(odcloud) — 순회 기준이 아니다(서비스마다 다르다)
        "data": rows,
    }


def _comp_rows() -> list[dict[str, Any]]:
    return [
        {
            "HOUSE_MANAGE_NO": HM,
            "PBLANC_NO": HM,
            "HOUSE_TY": f"{59 + i // 6:03d}.9000A",
            "SUBSCRPT_RANK_CODE": 1 + (i // 3) % 2,
            "RESIDE_SECD": f"0{1 + i % 3}",
            "RESIDE_SENM": ("해당지역", "기타경기", "기타지역")[i % 3],
            "SUPLY_HSHLDCO": 10,
            "REQ_CNT": str(i),
            "CMPET_RATE": f"{i / 10:.2f}",
        }
        for i in range(N_COMP)
    ]


def _handler(calls: list[httpx.URL]) -> Callable[[httpx.Request], httpx.Response]:
    comp = _comp_rows()

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        p = dict(request.url.params)
        path = request.url.path
        page = int(p.get("page", "1"))
        if "cond[SUBSCRPT_AREA_CODE_NM::EQ]" in p:  # 시도 목록
            rows = (
                [ROW]
                if path.endswith("getAPTLttotPblancDetail") and p["cond[SUBSCRPT_AREA_CODE_NM::EQ]"] == "인천"
                else []
            )
            return httpx.Response(200, json=_page(rows, match=len(rows)))
        if path.endswith("Detail"):  # 1건 조회(목록 페이지와 본문이 같으면 sha 가 같아 한 행이 된다)
            return httpx.Response(200, json=_page([ROW], match=1, total=2_900))
        if path.endswith("Mdl"):
            return httpx.Response(200, json=_page([MODEL], match=1))
        assert path.endswith("getAPTLttotPblancCmpet"), path
        per = int(p["perPage"])
        chunk = comp[(page - 1) * per : page * per]
        return httpx.Response(200, json=_page(chunk, match=N_COMP, page=page))

    return handler


def _collector(http: HttpClient, session: Session, **kw: Any) -> ApplyhomeCollector:
    return ApplyhomeCollector(
        http=http, session=session, today=lambda: TODAY, service_key=ENCODED_KEY, web_detail=False, **kw
    )


def test_competition_pages_until_match_count(
    http: HttpClient, db_session: Session, seeded_region: Region, snapshot: Snapshot, raw_dir: object
) -> None:
    calls: list[httpx.URL] = []
    with respx.mock(assert_all_called=False) as router:
        router.route(host="api.odcloud.kr").mock(side_effect=_handler(calls))
        c = _collector(http, db_session)
        docs = c.fetch(seeded_region, snapshot, None)
    assert c.paths == {"28": "api", "41": "api"}
    comp_calls = [u for u in calls if u.path.endswith("Cmpet")]
    assert [u.params["page"] for u in comp_calls] == ["1", "2"]  # 150행 = 100 + 50
    comp_docs = [d for d in docs if "Cmpet" in d.url]
    assert len(comp_docs) == 2
    assert {httpx.URL(d.url).params["page"] for d in comp_docs} == {"1", "2"}
    assert all(d.http_status == 200 and d.path and d.region_id == seeded_region.id for d in comp_docs)
    # 웹 경쟁률 폴백은 없다(API 성공)
    assert not any("Competition" in d.url for d in docs)
    got = 0
    from app.core.paths import resolve_raw_path

    for d in comp_docs:
        assert d.path is not None
        got += len(json.loads(resolve_raw_path(d.path).read_bytes())["data"])
    assert got == N_COMP  # 잘림 없음

    # since(마감·발표 이후): 다시 받지 않고 두 페이지 원문을 모두 돌려준다
    calls.clear()
    with respx.mock(assert_all_called=False) as router:
        router.route(host="api.odcloud.kr").mock(side_effect=_handler(calls))
        daily = _collector(http, db_session).fetch(seeded_region, snapshot, "2026-10-08T06:00:00+09:00")
    assert not [str(u) for u in calls if u.path.endswith(("Cmpet", "Mdl")) or "HOUSE_MANAGE_NO" in str(u)]
    assert {d.id for d in daily if "Cmpet" in d.url} == {d.id for d in comp_docs}


def test_competition_single_page_and_api_failure_unchanged(http: HttpClient) -> None:
    """한 페이지에 다 들어오면 1회, 실패(401)면 1회(웹 폴백은 수집기 몫)."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["page"])
        if request.url.path.endswith("OPTLttotPblancCmpet"):
            return httpx.Response(401, json={"code": -401, "msg": "유효하지 않은 인증키 입니다."})
        return httpx.Response(200, json=_page(_comp_rows()[:7], match=7))

    with respx.mock() as router:
        router.route(host="api.odcloud.kr").mock(side_effect=handler)
        client = api.ApplyhomeApi(http, ENCODED_KEY)
        ok = client.get_pages(api.ENDPOINTS["apt"].competition, api.item_params(HM, HM))
        bad = client.get_pages(api.ENDPOINTS["opt"].competition, api.item_params(HM, HM))
    assert len(ok) == 1 and ok[0].ok and len(bad) == 1 and bad[0].status == 401
    assert seen == ["1", "1"]


# ---------------------------------------------------------------- 키 마스킹


def _leaks(text: str | None) -> list[str]:
    return sorted(f for f in key_forms() if text and f in text)


def test_error_text_masks_encoded_key(http: HttpClient) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        # httpx 오류 메시지에 요청 URL(퍼센트 인코딩된 serviceKey 포함)이 들어가는 경우
        raise httpx.ConnectError(f"connection refused while fetching {request.url}", request=request)

    with respx.mock() as router:
        route = router.route(host="api.odcloud.kr").mock(side_effect=boom)
        r = api.ApplyhomeApi(http, ENCODED_KEY).get("/x/v1/y", {"page": "1"})
    sent = str(route.calls[0].request.url)
    assert any(f in sent for f in key_forms() - {DECODED_KEY})  # 전제: 실제 요청 URL 에는 인코딩 형태가 있다
    assert not r.ok and r.error is not None and "connection refused" in r.error
    for text in (r.error, r.url, r.final_url, r.content.decode()):
        assert _leaks(text) == [], text


def test_api_echoing_key_in_body_is_masked(
    http: HttpClient, db_session: Session, seeded_region: Region, snapshot: Snapshot, raw_dir: object
) -> None:
    """목록 API 가 오류 문구에 키를 되돌려 주면(형식 오류 등) 원문 행·경로 사유·FetchResult 어디에도
    남지 않는다."""

    def handler(request: httpx.Request) -> httpx.Response:
        echoed = f"invalid serviceKey={quote(DECODED_KEY, safe='')} ({DECODED_KEY})"
        return httpx.Response(500, json={"code": -4, "msg": echoed})

    with respx.mock(assert_all_called=False) as router:
        router.route(host="api.odcloud.kr").mock(side_effect=handler)
        router.route(host="www.applyhome.co.kr").respond(503)
        c = _collector(http, db_session)
        docs = c.fetch(seeded_region, snapshot, None)
        r = api.ApplyhomeApi(http, ENCODED_KEY).get("/x/v1/y", {"page": "1"})
    assert all(v.startswith("web(api 실패: ") for v in c.paths.values())
    for v in c.paths.values():
        assert _leaks(v) == [], v
    assert _leaks(r.content.decode()) == [] and _leaks(r.error) == []
    rows = db_session.scalars(select(RawRow)).all()
    assert rows and docs
    for row in rows:
        assert _leaks(row.url) == [] and _leaks(row.error_text) == []

"""R3b F1a (rtms): 키(DATA_GO_KR_KEY)가 원문·퍼센트 인코딩(quote·quote_plus) 어느 형태로도 raw_document
(url·error_text·저장 본문)·PageOutcome·FetchResult 오류 문구에 남지 않는다.

이전에는 403 본문의 errMsg 를 그대로 error_text 상세로 붙였다 — 포털이 오류 문구에 키를 되돌려
주면 DB 에 남는다.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, quote_plus, unquote

import httpx
import respx
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.collectors.rtms import PRESALE_API_URL, RTMS_API_URL, RtmsCollector
from app.core.contracts_gen import Region, Snapshot
from app.core.http import HttpClient
from app.core.paths import resolve_raw_path
from app.models import RawDocument

ENCODED_KEY = "Zx9%2BQw%2FEr7Ty5Ui3Op%3D%3D"
DECODED_KEY = unquote(ENCODED_KEY)
FORMS = {DECODED_KEY, ENCODED_KEY, quote(DECODED_KEY, safe=""), quote(DECODED_KEY), quote_plus(DECODED_KEY)}


def _leaks(text: str | None) -> list[str]:
    return sorted(f for f in FORMS if text and f in text)


def _echo_403(request: httpx.Request) -> httpx.Response:
    body = (
        "<OpenAPI_ServiceResponse><cmmMsgHeader>"
        f"<errMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR {request.url.params['serviceKey']} "
        f"{quote(DECODED_KEY, safe='')}</errMsg>"
        "<returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>"
    )
    return httpx.Response(403, content=body.encode(), headers={"content-type": "application/xml"})


def _echo_200(request: httpx.Request) -> httpx.Response:
    body = (
        "<response><header><resultCode>000</resultCode>"
        f"<resultMsg>OK {request.url}</resultMsg></header>"
        "<body><items/><numOfRows>1000</numOfRows><pageNo>1</pageNo><totalCount>0</totalCount></body></response>"
    )
    return httpx.Response(200, content=body.encode(), headers={"content-type": "application/xml"})


def _boom(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError(f"refused: {request.url}", request=request)


def test_key_never_stored_in_any_form(
    db_engine: Engine, region_ctx: tuple[Region, Snapshot], http: HttpClient
) -> None:
    region, snapshot = region_ctx
    with respx.mock(assert_all_called=False) as router:
        router.get("https://apis.data.go.kr/robots.txt").respond(400)

        def trade(request: httpx.Request) -> httpx.Response:
            lawd = request.url.params["LAWD_CD"]
            return _echo_403(request) if lawd == "28185" else _echo_200(request)

        router.get(RTMS_API_URL).mock(side_effect=trade)
        router.get(PRESALE_API_URL).mock(side_effect=_boom)
        col = RtmsCollector(service_key=ENCODED_KEY, http=http, months=1)
        docs = col.fetch(region, snapshot, None)
    assert {d.http_status for d in docs} == {403, 200, None}
    failed = next(d for d in docs if d.http_status == 403)
    assert failed.error_text is not None and failed.error_text.startswith(
        "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"
    )
    for p in col.pages:
        assert _leaks(p.result_msg) == [], p
    with Session(db_engine) as s:
        rows = list(s.scalars(select(RawDocument)))
    assert rows
    for row in rows:
        assert _leaks(row.url) == [] and _leaks(row.error_text) == [], (row.url, row.error_text)
        if row.path:
            assert _leaks(resolve_raw_path(row.path).read_bytes().decode("utf-8")) == []


def test_scrubbed_fetch_result(http: HttpClient) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get("https://apis.data.go.kr/robots.txt").respond(400)
        router.get(RTMS_API_URL).mock(side_effect=_boom)
        col = RtmsCollector(service_key=ENCODED_KEY, http=http, months=1)
        r = col.get(
            RTMS_API_URL, {"LAWD_CD": "28185", "DEAL_YMD": "202609", "numOfRows": "10", "pageNo": "1"}
        )
    assert not r.ok and r.error is not None and r.error.startswith("connect: refused")
    for text in (r.error, r.url, r.final_url):
        assert _leaks(text) == [], text


def test_fixture_dir_has_no_keys(fixtures_dir: Path) -> None:
    for f in fixtures_dir.iterdir():
        assert "serviceKey=" not in f.read_text(encoding="utf-8", errors="replace"), f

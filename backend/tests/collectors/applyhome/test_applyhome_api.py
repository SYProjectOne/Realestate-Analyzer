"""청약홈 공식 API(odcloud) 1순위 + 웹 폴백 — 녹화 재생(respx) 오프라인 테스트.

녹화
- ``applyhome_api_2026-10-09.zip``: 2026-10-09 실제 API 응답(``record_api.py``). URL 에 serviceKey 없음.
  경쟁률 서비스(ApplyhomeInfoCmpetRtSvc, data.go.kr 15098905)는 키가 활용신청되지 않아 실제로 401 이다.
- ``applyhome_2026-10-09.zip``: 같은 날 웹 녹화(웹 상세·경쟁률 폴백과 웹 전용 비교에 쓴다).
"""

from __future__ import annotations

import json
import os
import zipfile
from collections import Counter
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collectors.applyhome import ApplyhomeCollector, api, site
from app.collectors.applyhome.parse import detail_supply_address
from app.core.contracts_gen import RawDocument, Region, Snapshot
from app.core.http import FetchResult, HttpClient
from app.models import RawDocument as RawRow

from .conftest import FIXTURES, RECORDING, TODAY, make_region, make_snapshot
from .replay import Recording

API_RECORDING = FIXTURES / "applyhome_api_2026-10-09.zip"
FAKE_KEY = "TEST%2BKEY%3D%3D"  # 가짜(인코딩 키 형태)
SIGUNGU = ("연수구", "서구", "검단구", "계양구", "김포시")


@pytest.fixture
def merged() -> Recording:
    return Recording.load(RECORDING).merged(Recording.load(API_RECORDING))


def _collector(http: HttpClient, session: Session, **kw: object) -> ApplyhomeCollector:
    kw.setdefault("window", ("2025-12", "2026-11"))  # 녹화 때 조회 창(계약 .15 기본 창은 녹화에 없다)
    return ApplyhomeCollector(http=http, session=session, today=lambda: TODAY, **kw)  # type: ignore[arg-type]


def _count(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(RawRow)) or 0)


def _api_manifest() -> list[dict[str, object]]:
    with zipfile.ZipFile(API_RECORDING) as z:
        entries: list[dict[str, object]] = json.loads(z.read("manifest.json"))["entries"]
    return entries


def _hm(url: str) -> str | None:
    q = dict(httpx.URL(url).params)
    return q.get("cond[HOUSE_MANAGE_NO::EQ]") or q.get("houseManageNo")


# ---------------------------------------------------------------- 요청 형식·응답 해석


def test_request_shapes_have_no_key() -> None:
    p = api.list_params("opt", "인천", date(2025, 12, 1), date(2026, 11, 30), 2)
    assert p["cond[SUBSCRPT_AREA_CODE_NM::EQ]"] == "인천" and p["page"] == "2"
    assert (p["cond[RCRIT_PBLANC_DE::GTE]"], p["cond[RCRIT_PBLANC_DE::LTE]"]) == ("20251201", "20261130")
    p2 = api.list_params("apt", "경기", date(2025, 12, 1), date(2026, 11, 30), 1)
    assert p2["cond[RCRIT_PBLANC_DE::GTE]"] == "2025-12-01"
    url = api.doc_url(api.ENDPOINTS["apt"].model, api.item_params("2026000458", "2026000458"))
    assert url.startswith("https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancMdl?")
    assert "serviceKey" not in url
    assert api.ENDPOINTS["apt"].competition == "/ApplyhomeInfoCmpetRtSvc/v1/getAPTLttotPblancCmpet"
    assert {k: e.web_kind for k, e in api.ENDPOINTS.items()} == {
        "apt": "apt",
        "remndr": "remndr",
        "opt": "remndr",
    }


def test_client_sends_decoded_key_but_returns_keyless_url() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": [], "matchCount": 0})

    with (
        respx.mock() as router,
        HttpClient(sleep=lambda _s: None, max_retries=0, jitter=0) as http,
    ):
        router.route(host="api.odcloud.kr").mock(side_effect=handler)
        r = api.ApplyhomeApi(http, FAKE_KEY).get("/x/v1/y", {"page": "1"})
    assert seen[0].url.params["serviceKey"] == "TEST+KEY=="
    assert "serviceKey" not in r.url and "TEST" not in r.url and r.final_url is None


def test_parse_recorded_pages() -> None:
    entries = _api_manifest()
    with zipfile.ZipFile(API_RECORDING) as z:
        ok = next(e for e in entries if "getAPTLttotPblancDetail" in str(e["url"]) and e["status"] == 200)
        unauthorized = next(e for e in entries if e["status"] == 401)
        ok_body, bad_body = z.read(str(ok["file"])), z.read(str(unauthorized["file"]))
    for body in (ok_body, bad_body):
        assert b"serviceKey" not in body
    page = api.parse_page(_fr(200, ok_body))
    assert page.ok and page.rows and page.match_count is not None
    row = api.to_row("apt", page.rows[0])
    assert row is not None and row.house_manage_no and row.address and row.notice_date
    bad = api.parse_page(_fr(401, bad_body))
    assert not bad.ok and bad.error == "401: 유효하지 않은 인증키 입니다."
    assert "ApplyhomeInfoCmpetRtSvc" in str(unauthorized["url"])  # 401 은 경쟁률 서비스뿐
    assert not api.parse_page(_fr(200, b"<html>")).ok
    assert not api.parse_page(_fr(200, b'{"code": -4, "msg": "x"}')).ok
    assert api.iso_date("20261008") == "2026-10-08" and api.iso_date("2026-10-08") == "2026-10-08"


def _fr(status: int, body: bytes) -> FetchResult:
    return FetchResult(
        url="https://api.odcloud.kr/x",
        status=status,
        headers={"content-type": "application/json"},
        content=body,
        error=None if status < 400 else f"HTTP {status}",
        elapsed_ms=1,
        attempts=1,
    )


# ---------------------------------------------------------------- 수집기: API 1순위


def test_api_first_replay(
    merged: Recording,
    http: HttpClient,
    db_session: Session,
    seeded_region: Region,
    snapshot: Snapshot,
    raw_dir: object,
) -> None:
    entries = _api_manifest()
    n_lists = sum(1 for e in entries if "SUBSCRPT_AREA_CODE_NM" in str(e["url"]))
    in_region = {_hm(str(e["url"])) for e in entries if "HOUSE_MANAGE_NO" in str(e["url"])}
    assert n_lists >= 6 and len(in_region) >= 40  # 녹화 규모

    with merged.mock():
        c = _collector(http, db_session, service_key=FAKE_KEY)
        docs = c.fetch(seeded_region, snapshot, None)
    assert c.paths == {"28": "api", "41": "api"}
    lists = [d for d in docs if d.source_kind == "applyhome_list"]
    assert len(lists) == n_lists and all(d.url.startswith(api.BASE) for d in lists)
    # 웹 목록은 한 번도 부르지 않는다(POST 0), 지역 밖 웹 상세도 받지 않는다
    assert merged.calls["www.applyhome.co.kr"] == 2 * len(in_region)
    by_kind = Counter(_doc_kind(d) for d in docs if d.source_kind == "applyhome_detail")
    assert by_kind["api_detail"] == by_kind["api_model"] == len(in_region)
    assert by_kind["api_comp_401"] == len(in_region)  # 경쟁률 API 401(실제) → 실패 행
    assert by_kind["web_comp"] >= 1 and by_kind["web_detail"] >= 1  # 폴백 웹 경쟁률 + 공고문 링크용 웹 상세
    assert {_hm(d.url) for d in docs if d.source_kind == "applyhome_detail"} == in_region
    assert all(d.region_id == seeded_region.id for d in docs)
    assert all("serviceKey" not in d.url and "TEST" not in d.url for d in docs)

    # 같은 입력 2회 → raw_document 증가 0
    rows = _count(db_session)
    with merged.mock():
        _collector(http, db_session, service_key=FAKE_KEY).fetch(seeded_region, snapshot, None)
    assert _count(db_session) == rows

    # since(어제): 일정이 끝난 공고는 다시 받지 않고 기존 행을 돌려준다
    merged.calls.clear()
    with merged.mock():
        daily = _collector(http, db_session, service_key=FAKE_KEY).fetch(
            seeded_region, snapshot, "2026-10-08T06:00:00+09:00"
        )
    assert _count(db_session) == rows
    daily_ids, all_ids = {d.id for d in daily}, {d.id for d in docs}
    # 끝난 공고는 성공 원문만 돌려준다(실패 행 = 그날의 경쟁률 401 은 다시 부르지 않으므로 빠진다)
    assert {d.id for d in docs if d.path} <= daily_ids <= all_ids
    assert merged.calls["api.odcloud.kr"] < n_lists + 3 * len(in_region)


def _doc_kind(d: RawDocument) -> str:
    if d.url.startswith(api.BASE):
        if "Cmpet" in d.url:
            return "api_comp_401" if d.http_status == 401 else "api_comp"
        return "api_model" if "Mdl" in d.url else "api_detail"
    return "web_comp" if "Competition" in d.url else "web_detail"


def test_web_detail_can_be_skipped_when_api_ok(
    merged: Recording, http: HttpClient, db_session: Session, seeded_region: Region, snapshot: Snapshot
) -> None:
    """web_detail=False: API 상세·주택형이 성공하면 웹 상세는 받지 않는다(경쟁률 401 폴백만 웹)."""
    with merged.mock():
        docs = _collector(http, db_session, service_key=FAKE_KEY, web_detail=False).fetch(
            seeded_region, snapshot, None
        )
    kinds = Counter(_doc_kind(d) for d in docs if d.source_kind == "applyhome_detail")
    assert kinds["web_detail"] == 0 and kinds["web_comp"] >= 1


# ---------------------------------------------------------------- API 실패 → 웹 경로


@pytest.mark.parametrize("status", [401, 500])
def test_api_list_failure_falls_back_to_web(
    status: int,
    recording: Recording,
    http: HttpClient,
    db_session: Session,
    seeded_region: Region,
    snapshot: Snapshot,
) -> None:
    """API 목록이 401/5xx 면 그 시도는 웹 경로(목록 POST → 상세 → 경쟁률)로 — 웹 전용 실행과 같은 결과."""
    with recording.mock() as router:
        router.route(host="api.odcloud.kr").respond(status, json={"code": -status, "msg": "x"})
        c = _collector(http, db_session, service_key=FAKE_KEY)
        docs = c.fetch(seeded_region, snapshot, None)
    assert set(c.paths) == {"28", "41"}
    assert all(p.startswith(f"web(api 실패: apt 목록 {status}") for p in c.paths.values())
    api_rows = [d for d in docs if d.url.startswith(api.BASE)]
    assert [(d.source_kind, d.http_status, d.path) for d in api_rows] == [
        ("applyhome_list", status, None)
    ] * 2
    web = [d for d in docs if not d.url.startswith(api.BASE)]

    session2_rows = _count(db_session)
    with recording.mock():
        web_only = _collector(http, db_session, service_key=None).fetch(seeded_region, snapshot, None)
    assert {d.id for d in web} == {d.id for d in web_only}  # 같은 원문 = 같은 행
    assert _count(db_session) == session2_rows


def test_api_network_failure_falls_back_to_web(
    recording: Recording, http: HttpClient, db_session: Session, seeded_region: Region, snapshot: Snapshot
) -> None:
    with recording.mock() as router:
        router.route(host="api.odcloud.kr").mock(side_effect=httpx.ConnectError("getaddrinfo failed"))
        c = _collector(http, db_session, service_key=FAKE_KEY)
        docs = c.fetch(seeded_region, snapshot, None)
    assert all(p.startswith("web(api 실패: apt 목록 connect") for p in c.paths.values())
    assert any(d.source_kind == "applyhome_list" and d.url.startswith(site.BASE) for d in docs)


def test_api_detail_failure_uses_web_detail(
    merged: Recording, http: HttpClient, db_session: Session, seeded_region: Region, snapshot: Snapshot
) -> None:
    """공고 단위: API 상세가 5xx 면 웹 상세로(web_detail=False 여도)."""

    def first(router: respx.MockRouter) -> None:
        router.route(host="api.odcloud.kr", path__regex=r".*/getAPTLttotPblancMdl$").respond(503)

    with merged.mock(first):
        docs = _collector(http, db_session, service_key=FAKE_KEY, web_detail=False).fetch(
            seeded_region, snapshot, None
        )
    failed = {_hm(d.url) for d in docs if "Mdl" in d.url and d.http_status == 503}
    web_details = {_hm(d.url) for d in docs if _doc_kind(d) == "web_detail"}
    assert failed and failed <= web_details


def test_no_key_means_web_only(
    recording: Recording, http: HttpClient, db_session: Session, seeded_region: Region, snapshot: Snapshot
) -> None:
    with recording.mock() as router:
        odcloud = router.route(host="api.odcloud.kr").respond(500)
        c = _collector(http, db_session)  # test_settings: DATA_GO_KR_KEY 없음
        c.fetch(seeded_region, snapshot, None)
    assert not c.api_enabled and odcloud.call_count == 0 and c.paths == {"28": "web", "41": "web"}


# ---------------------------------------------------------------- API vs 웹 단지 수 비교


def _sigungu(address: str | None) -> str:
    tokens = set((address or "").replace("(", " ").replace(")", " ").replace(",", " ").split())
    hit = [s for s in SIGUNGU if s in tokens]
    return hit[0] if hit else "시군구 없음"


def _web_complexes(recording: Recording) -> dict[str, set[str]]:
    """웹 녹화(같은 사전 필터를 통과한 상세)의 지역 안 단지(주택관리번호) — 시군구별."""
    out: dict[str, set[str]] = {}
    for e in recording.entries.values():
        if e.method != "GET" or not any(
            e.url.startswith(site.BASE + ep.detail_path) for ep in site.ENDPOINTS.values()
        ):
            continue
        address = detail_supply_address(recording.body(e).decode("utf-8"))
        out.setdefault(_sigungu(address), set()).add(str(_hm(e.url)))
    return out


def test_compare_api_vs_web_complex_counts(
    merged: Recording,
    recording: Recording,
    http: HttpClient,
    db_session: Session,
    seeded_region: Region,
    snapshot: Snapshot,
) -> None:
    """같은 지역·같은 창(2025-12 ~ 2026-11)에서 API 경로와 웹 경로가 고른 지역 안 단지 수(시군구별)."""
    with merged.mock():
        api_docs = _collector(http, db_session, service_key=FAKE_KEY).fetch(seeded_region, snapshot, None)
    api_hms = {h for d in api_docs if d.url.startswith(api.BASE) and "Detail?" in d.url and (h := _hm(d.url))}
    with recording.mock():
        web_docs = _collector(http, db_session, service_key=None).fetch(seeded_region, snapshot, None)
    web_hms = {h for d in web_docs if _doc_kind(d) == "web_detail" and (h := _hm(d.url))}

    addr: dict[str, str | None] = {}
    for d in api_docs:
        if d.url.startswith(api.BASE) and "Detail?" in d.url and d.path:
            body = json.loads(raw_path_of(d).read_bytes())
            for r in body["data"]:
                addr[str(r["HOUSE_MANAGE_NO"])] = r.get("HSSPLY_ADRES")
    for d in web_docs:
        if _doc_kind(d) == "web_detail" and d.path:
            addr.setdefault(
                str(_hm(d.url)), detail_supply_address(raw_path_of(d).read_text(encoding="utf-8"))
            )

    table = []
    for sgg in (*SIGUNGU, "시군구 없음"):
        a = {h for h in api_hms if _sigungu(addr.get(str(h))) == sgg}
        w = {h for h in web_hms if _sigungu(addr.get(str(h))) == sgg}
        table.append(
            (sgg, len(a), len(w), len(a & w), sorted(str(x) for x in a - w), sorted(str(x) for x in w - a))
        )
    lines = ["| 시군구 | API | 웹(녹화) | 공통 | API만 | 웹만 |", "| --- | --- | --- | --- | --- | --- |"]
    lines += [
        f"| {s} | {a} | {w} | {c} | {', '.join(ao) or '-'} | {', '.join(wo) or '-'} |"
        for s, a, w, c, ao, wo in table
    ]
    lines.append(f"| 계 | {len(api_hms)} | {len(web_hms)} | {len(api_hms & web_hms)} | | |")
    print("\n" + "\n".join(lines))
    if os.environ.get("APPLYHOME_COMPARE_OUT"):
        with open(os.environ["APPLYHOME_COMPARE_OUT"], "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    # API 가 웹보다 단지를 놓치지 않는다(웹만 있는 단지 = 0)
    assert web_hms <= api_hms, sorted(str(x) for x in web_hms - api_hms)


def raw_path_of(d: RawDocument) -> Path:
    from app.core.paths import resolve_raw_path

    assert d.path is not None
    return resolve_raw_path(d.path)


# ---------------------------------------------------------------- live


@pytest.fixture
def live_key() -> Iterator[str]:
    from app.core.settings import load_settings

    s = load_settings()
    key = s.data_go_kr_key.get_secret_value() if s.data_go_kr_key else os.environ.get("DATA_GO_KR_KEY")
    if not key:
        pytest.skip("DATA_GO_KR_KEY 없음 (ENV_FILE 로 .env 경로를 준다)")
    yield key


@pytest.mark.live
def test_live_api_endpoints(live_key: str) -> None:
    """실제 호출: 분양정보 상세·주택형(200, JSON) 3종 + 경쟁률 서비스 상태(활용신청 전이면 401).

    실행: ``ENV_FILE=<메인 체크아웃>/.env uv run pytest -m live tests/collectors/applyhome``
    """
    firsts: dict[str, api.ApiRow] = {}
    with HttpClient(max_retries=1) as http:
        client = api.ApplyhomeApi(http, live_key)
        for kind in api.API_KINDS:
            ep = api.ENDPOINTS[kind]
            r = client.get(ep.detail, api.list_params(kind, "인천", date(2026, 1, 1), date(2026, 12, 31), 1))
            page = api.parse_page(r)
            assert page.ok and page.rows, (kind, r.status, page.error)
            assert {x.get("SUBSCRPT_AREA_CODE_NM") for x in page.rows} == {"인천"}  # 지역명 조건이 먹는다
            row = api.to_row(kind, page.rows[0])
            assert row is not None
            firsts[kind] = row
            m = api.parse_page(client.get(ep.model, api.item_params(row.house_manage_no, row.pblanc_no)))
            assert m.ok and m.rows and all("HOUSE_TY" in x for x in m.rows)
            assert live_key not in r.url
        apt = firsts["apt"]
        comp = client.get(
            api.ENDPOINTS["apt"].competition, api.item_params(apt.house_manage_no, apt.pblanc_no)
        )
        print(f"\n[live] 경쟁률 서비스: HTTP {comp.status} {api.parse_page(comp).error or 'ok'}")
        assert comp.status in (200, 401)


@pytest.mark.live
def test_live_collector_api_first(live_key: str, db_session: Session, seeded_region: Region) -> None:
    """실제 키로 수집기 1회(연수구만, 최근 2개월) — 경로가 api 이고 실패 행 외에 키가 남지 않는다."""
    region = make_region(
        selections=[{"kind": "sigungu", "code": "28185", "full_name": "인천광역시 연수구"}],
        sido_codes=["28"],
        sigungu_codes=["28185"],
        applyhome_query={"from_ym": "2026-09"},
    )
    with HttpClient(max_retries=1) as http:
        c = ApplyhomeCollector(http=http, session=db_session, service_key=live_key)
        docs = c.fetch(region, make_snapshot(), None)
    assert c.paths == {"28": "api"}
    assert docs and all(live_key not in d.url for d in docs)

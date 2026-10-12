"""R4 4차 재시험 N15(major, D23-4) — 청약홈 API 빈 데이터셋(조건 없는 totalCount 0)은 정상 0건이 아니라 실패 행이다.

R4 4차 첫 시도(2026-10-13 00:01 KST): 청약홈 API 데이터셋이 재적재 중이라 목록이 200 · ``{"totalCount":0,"matchCount":0,"data":[]}``
(녹화 ``fixtures/r4d_empty_dataset.json`` — R4 4차 run0 원문 그대로, 키 없음)였다. 수집기는 이것을 "조건에 맞는 공고 0건"으로 받아
웹 경로로 넘어가지도, 실패 행을 남기지도 않아 bootstrap 이 단지 24개(정상 72)로 끝나고 아무 경고 없이 발행됐다.

D23-4: 조건 없는 전체 건수 0 = 실패 — 원문은 실패 행(http_status 200 · path 없음 · error_text ``empty_dataset: totalCount 0``), 목록은
그 시도를 웹 경로로(기존 'API 목록 실패' 규칙), 수집기는 ``empty_datasets`` 에 남긴다(수집 단계 degraded → bootstrap 미발행·재시도 —
``tests/scheduler/test_core10_n15_degraded.py``). 조건에 맞는 것만 0건(matchCount 0, totalCount > 0)은 정상이다.
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import json
from datetime import UTC, datetime

import respx
from sqlalchemy.orm import Session

from app.api.routers.ops import _ok, _reason
from app.collectors.applyhome import ApplyhomeCollector, api
from app.collectors.applyhome.raw import RawStore
from app.core.contracts_gen import Region, Snapshot
from app.core.http import HttpClient

from .conftest import FIXTURES, TODAY
from .replay import Recording

EMPTY = (FIXTURES / "r4d_empty_dataset.json").read_bytes()
FAKE_KEY = "TEST%2BKEY%3D%3D"
EMPTY_DATASET = "empty_dataset: totalCount 0"  # = api.EMPTY_DATASET(실패 행 error_text)


def test_recorded_empty_dataset_is_a_failure_result() -> None:
    """``ApplyhomeApi.get`` 이 빈 데이터셋 200 을 실패 결과로 — parse_page 도 실패(사유 그대로)."""
    with respx.mock() as router, HttpClient(sleep=lambda _s: None, max_retries=0, jitter=0) as http:
        router.route(host="api.odcloud.kr").respond(
            200, content=EMPTY, headers={"content-type": "application/json"}
        )
        r = api.ApplyhomeApi(http, FAKE_KEY).get(
            api.ENDPOINTS["apt"].detail, api.list_params("apt", "인천", TODAY, TODAY, 1)
        )
    assert json.loads(EMPTY)["totalCount"] == 0 and json.loads(EMPTY)["data"] == []
    assert r.status == 200 and not r.ok and r.error == EMPTY_DATASET, (r.status, r.ok, r.error)
    page = api.parse_page(r)
    assert not page.ok and page.error == EMPTY_DATASET


def test_no_match_with_nonempty_dataset_is_still_ok() -> None:
    """조건에 맞는 것만 0건(matchCount 0, totalCount 2900 — 데이터셋은 있음)은 정상 0건이다(회귀 방지)."""
    body = b'{"currentCount":0,"data":[],"matchCount":0,"page":1,"perPage":100,"totalCount":2900}'
    with respx.mock() as router, HttpClient(sleep=lambda _s: None, max_retries=0, jitter=0) as http:
        router.route(host="api.odcloud.kr").respond(
            200, content=body, headers={"content-type": "application/json"}
        )
        r = api.ApplyhomeApi(http, FAKE_KEY).get("/x/v1/y", {"page": "1"})
    assert r.ok and api.parse_page(r).ok and api.parse_page(r).rows == []


def test_empty_dataset_raw_row_is_a_failure_row(db_session: Session, seeded_region: Region) -> None:
    """실패 행: http_status 200 · path 없음 · error_text 'empty_dataset: totalCount 0' · 같은 날 재시도는 행이 늘지 않는다.
    G7 출처 상태(``/ops/sources``)는 실패로 센다."""
    from app.core.http import FetchResult

    r = FetchResult(
        url=api.doc_url("/x", {"page": "1"}), status=200, headers={"content-type": "application/json"},
        content=EMPTY, error=EMPTY_DATASET, elapsed_ms=1, attempts=1,
        fetched_at=datetime(2026, 10, 12, 15, 1, tzinfo=UTC),
    )  # fmt: skip
    store = RawStore(db_session)
    a = store.save(r, source_kind="applyhome_list", ext="json", region_id=seeded_region.id)
    b = store.save(r, source_kind="applyhome_list", ext="json", region_id=seeded_region.id)
    row = a.row
    assert (row.http_status, row.path, row.error_text) == (200, None, EMPTY_DATASET)
    assert not a.ok and b.row.id == row.id and not b.created
    assert not _ok(row) and _reason(row) == EMPTY_DATASET


def test_empty_api_list_falls_back_to_web_and_is_recorded(
    recording: Recording, http: HttpClient, db_session: Session, seeded_region: Region, snapshot: Snapshot
) -> None:
    """R4 4차 첫 시도 모양(API 목록이 빈 데이터셋): 그 시도는 웹 경로로(웹 전용 실행과 같은 원문), API 목록은 실패 행, 수집기가
    ``empty_datasets`` 에 남긴다(수집 단계 degraded 의 근거)."""
    with recording.mock() as router:
        router.route(host="api.odcloud.kr").respond(
            200, content=EMPTY, headers={"content-type": "application/json"}
        )
        c = ApplyhomeCollector(
            http=http,
            session=db_session,
            today=lambda: TODAY,
            service_key=FAKE_KEY,
            window=("2025-12", "2026-11"),
        )
        docs = c.fetch(seeded_region, snapshot, None)
    assert set(c.paths) == {"28", "41"}
    assert all(p.startswith(f"web(api 실패: apt 목록 {EMPTY_DATASET}") for p in c.paths.values()), c.paths
    api_rows = [d for d in docs if d.url.startswith(api.BASE)]
    assert [(d.source_kind, d.http_status, d.path, d.error_text) for d in api_rows] == [
        ("applyhome_list", 200, None, EMPTY_DATASET)
    ] * 2
    assert len(getattr(c, "empty_datasets", [])) == 2 and all("serviceKey" not in u for u in c.empty_datasets)
    web = [d for d in docs if not d.url.startswith(api.BASE)]
    assert web and any(d.source_kind == "applyhome_detail" for d in web), "웹 경로로 상세까지 받았다"


def test_original_refetch_with_empty_dataset_is_failure_rows(
    recording: Recording, http: HttpClient, db_session: Session, seeded_region: Region, snapshot: Snapshot
) -> None:
    """원 공고 다시 받기(번호 조회)도 빈 데이터셋이면 실패 행 + ``empty_datasets``(정상 '원 공고 없음'과 구분)."""
    with respx.mock() as router:
        router.route(host="api.odcloud.kr").respond(
            200, content=EMPTY, headers={"content-type": "application/json"}
        )
        c = ApplyhomeCollector(http=http, session=db_session, today=lambda: TODAY, service_key=FAKE_KEY)
        docs = c.fetch_originals(seeded_region, snapshot, ["2023000463"])
    assert [(d.http_status, d.path, d.error_text) for d in docs] == [(200, None, EMPTY_DATASET)] * 3
    assert len(getattr(c, "empty_datasets", [])) == 3

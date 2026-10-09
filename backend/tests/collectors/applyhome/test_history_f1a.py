"""R3 C1: 벤치마크용 과거 공고 조회 창(청약홈 공식 API, 기본 10년) — ``ApplyhomeCollector.fetch_history``.

- APT 분양정보 목록만 [기준일 − N년, 기준일] 로 받는다(잔여세대·임의공급 아님).
- 지역 안(사전 필터) · 입주예정월 ≤ 기준월 공고만 주택형별(Mdl)을 받는다 — 분양가(84㎡ 최고가)의 원문.
- 원문은 단지 행에 묶지 않는다(complex_id 없음, Complex 행을 만들지 않음): 수집 단계의 정규화(store)로 넘기지 않는다.
- 이미 받은 Mdl 원문(과거 공고는 바뀌지 않음)은 다시 받지 않는다.
- 키가 없으면 [] (웹 목록은 조회 기간 제한이 있어 과거 N년을 받지 못한다).
"""

from __future__ import annotations

import json
from datetime import date

import httpx
import pytest
import respx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collectors.applyhome import ApplyhomeCollector
from app.collectors.applyhome.collector import HISTORY_YEARS
from app.core.contracts_gen import Region
from app.core.http import HttpClient
from app.models import Complex
from app.models import RawDocument as RawRow

from .conftest import make_snapshot

FAKE_KEY = "TEST%2BKEY%3D%3D"


def _row(hm: str, address: str, move_in: str, area: str) -> dict[str, object]:
    return {
        "HOUSE_MANAGE_NO": hm,
        "PBLANC_NO": hm,
        "HOUSE_NM": f"단지 {hm}",
        "HSSPLY_ADRES": address,
        "RCRIT_PBLANC_DE": "2021-05-01",
        "MVN_PREARNGE_YM": move_in,
        "HOUSE_DTL_SECD_NM": "민영",
        "SUBSCRPT_AREA_CODE_NM": area,
    }


LISTS = {
    "인천": [
        _row("2021000001", "인천광역시 연수구 송도동 1", "202406", "인천"),  # 지역 안·입주 완료 → Mdl
        _row("2021000002", "인천광역시 연수구 송도동 2", "202812", "인천"),  # 입주 전 → Mdl 안 받음
        _row("2021000003", "인천광역시 부평구 부평동 3", "202312", "인천"),  # 지역 밖
    ],
    "경기": [_row("2021000004", "경기도 김포시 장기동 4", "202501", "경기")],
}


class Api:
    def __init__(self) -> None:
        self.calls: list[httpx.URL] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request.url)
        p = request.url.params
        path = request.url.path
        if path.endswith("getAPTLttotPblancDetail"):
            rows = LISTS[p["cond[SUBSCRPT_AREA_CODE_NM::EQ]"]]
            return httpx.Response(200, json={"data": rows, "matchCount": len(rows), "page": 1, "perPage": 100})
        if path.endswith("getAPTLttotPblancMdl"):
            hm = p["cond[HOUSE_MANAGE_NO::EQ]"]
            data = [{"HOUSE_MANAGE_NO": hm, "PBLANC_NO": hm, "HOUSE_TY": "084.9000A", "LTTOT_TOP_AMOUNT": "60000"}]
            return httpx.Response(200, json={"data": data, "matchCount": 1})
        raise AssertionError(f"예상 밖 요청: {request.url}")


@pytest.fixture
def client() -> HttpClient:
    return HttpClient(sleep=lambda _s: None, max_retries=0, jitter=0)


def test_history_window_and_model_pages(db_session: Session, seeded_region: Region, client: HttpClient) -> None:
    api = Api()
    snap = make_snapshot(asof="2026-10-08")
    with respx.mock() as router:
        router.route(host="api.odcloud.kr").mock(side_effect=api)
        col = ApplyhomeCollector(http=client, session=db_session, today=lambda: date(2026, 10, 8), service_key=FAKE_KEY)
        docs = col.fetch_history(seeded_region, snap)

    lists = [u for u in api.calls if u.path.endswith("Detail")]
    assert {u.params["cond[SUBSCRPT_AREA_CODE_NM::EQ]"] for u in lists} == {"인천", "경기"}
    assert all(u.params["cond[RCRIT_PBLANC_DE::GTE]"] == f"{2026 - HISTORY_YEARS}-10-01" for u in lists)
    assert all(u.params["cond[RCRIT_PBLANC_DE::LTE]"] == "2026-10-08" for u in lists)
    assert not any("Remndr" in u.path or "OPT" in u.path or "Cmpet" in u.path for u in api.calls)
    models = sorted(u.params["cond[HOUSE_MANAGE_NO::EQ]"] for u in api.calls if u.path.endswith("Mdl"))
    assert models == ["2021000001", "2021000004"]

    assert {d.source_kind for d in docs} == {"applyhome_list", "applyhome_detail"}
    assert all(d.complex_id is None and d.region_id == seeded_region.id for d in docs)
    assert all("serviceKey" not in d.url for d in docs)
    assert db_session.scalar(select(func.count()).select_from(Complex)) == 0
    assert col.history_stats == {"lists": 2, "notices_in_region": 2, "models_fetched": 2, "models_reused": 0}

    # 두 번째: Mdl 은 이미 받은 원문을 쓴다(과거 공고는 바뀌지 않는다)
    api2 = Api()
    with respx.mock() as router:
        router.route(host="api.odcloud.kr").mock(side_effect=api2)
        col.fetch_history(seeded_region, snap)
    assert not any(u.path.endswith("Mdl") for u in api2.calls)
    assert col.history_stats["models_reused"] == 2


def test_history_without_key_is_empty(db_session: Session, seeded_region: Region, client: HttpClient) -> None:
    col = ApplyhomeCollector(http=client, session=db_session, service_key=None)
    assert col.fetch_history(seeded_region, make_snapshot()) == []
    assert db_session.scalar(select(func.count()).select_from(RawRow)) == 0


def test_history_list_failure_is_a_row_not_an_exception(
    db_session: Session, seeded_region: Region, client: HttpClient
) -> None:
    with respx.mock() as router:
        router.route(host="api.odcloud.kr").respond(500, json={"code": -500, "msg": "x"})
        col = ApplyhomeCollector(http=client, session=db_session, service_key=FAKE_KEY)
        docs = col.fetch_history(seeded_region, make_snapshot())
    assert docs and all(d.http_status == 500 for d in docs)
    assert json.dumps(col.history_stats)  # 직렬화 가능(잡 stats)

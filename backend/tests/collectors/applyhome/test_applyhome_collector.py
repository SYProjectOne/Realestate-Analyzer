"""청약홈 수집기 — 녹화 재생(respx) 오프라인 테스트 (WP1a 완료 기준).

- 녹화 HTTP 픽스처 재생
- 목록 → 시군구 사전 필터 → 상세 수 검증
- 같은 입력 2회 → raw_document 증가 0 (임시 sqlite + app.models)
- 403·timeout·DNS → 실패 행, 예외 없음
- 지역 1개 일일 수집 녹화 재생 기준 10분 이내(속도 제한 1 req/s 를 가짜 시계로 계산)
"""

from __future__ import annotations

import hashlib
import time
from collections import Counter

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collectors.applyhome import ApplyhomeCollector, site
from app.collectors.applyhome.parse import detail_supply_address
from app.core.contracts_gen import Region, Snapshot
from app.core.http import HttpClient
from app.models import RawDocument as RawRow

from .conftest import TODAY, FakeClock, make_region
from .replay import Recording

# 녹화 지역의 사전 필터 기대값 — 수집기 코드(area.py)와 독립적으로 녹화 원문에서 계산한다
TARGET_TOKENS = {"인천": {"연수구", "서구", "검단구", "계양구"}, "경기": {"김포시"}}
DAILY_LIMIT_S = 600.0


def _count(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(RawRow)) or 0)


def _expected(recording: Recording) -> dict[str, int]:
    """녹화 manifest 에서 목록 페이지 수·상세 수·지역 안 상세 수·지역 안 경쟁률 원문 수(같은 내용은 한 행)."""
    lists = details = hits = 0
    comp_shas: set[str] = set()
    for e in recording.entries.values():
        if e.method == "POST":
            lists += 1
            continue
        for ep in site.ENDPOINTS.values():
            if not e.url.startswith(site.BASE + ep.detail_path):
                continue
            details += 1
            address = detail_supply_address(recording.body(e).decode("utf-8")) or ""
            area = "인천" if address.startswith("인천") else "경기"
            tokens = set(address.replace("(", " ").replace(")", " ").replace(",", " ").split())
            located = any(t.endswith(("시", "도", "군", "구")) and not t.endswith("신도시") for t in tokens)
            if tokens & TARGET_TOKENS[area] or not located:  # 시군구 없는 공급위치는 버리지 않는다
                hits += 1
                comp_url = e.url.replace(ep.detail_path, ep.competition_path)
                comp = next(c for c in recording.entries.values() if c.url == comp_url)
                comp_shas.add(hashlib.sha256(recording.body(comp)).hexdigest())
    return {"lists": lists, "details": details, "hits": hits, "comps": len(comp_shas)}


def _collector(http: HttpClient, session: Session, **kw: object) -> ApplyhomeCollector:
    return ApplyhomeCollector(http=http, session=session, today=lambda: TODAY, **kw)  # type: ignore[arg-type]


def test_full_replay_filter_counts_idempotent_and_daily_time(
    recording: Recording,
    http: HttpClient,
    clock: FakeClock,
    db_session: Session,
    seeded_region: Region,
    snapshot: Snapshot,
    raw_dir: object,
) -> None:
    exp = _expected(recording)
    assert exp["lists"] >= 40 and exp["details"] >= 400 and exp["hits"] >= 40  # 녹화 규모 확인

    # 1) 최초 수집(부트스트랩): 목록 전 페이지 → 행마다 상세 → 지역 안이면 경쟁률
    t0, real0 = clock.now, time.perf_counter()
    with recording.mock():
        docs = _collector(http, db_session).fetch(seeded_region, snapshot, None)
    bootstrap_s = clock.now - t0 + (time.perf_counter() - real0)
    kinds = Counter(d.source_kind for d in docs)
    details = [d for d in docs if "Competition" not in d.url and d.source_kind == "applyhome_detail"]
    comps = [d for d in docs if "Competition" in d.url]
    assert kinds["applyhome_list"] == exp["lists"]
    assert len(details) == exp["hits"]  # 목록 → 시군구 사전 필터 → 상세
    assert len(comps) == exp["comps"]  # 내용이 같은 경쟁률 원문은 한 행(sha256 유일)
    assert all(d.http_status == 200 and d.path and d.region_id == seeded_region.id for d in docs)
    # 지역 밖 상세도 원문으로는 남는다(region_id 없음) — 다음 실행에서 다시 받지 않기 위해
    rows = _count(db_session)
    stored_details = db_session.scalar(
        select(func.count()).select_from(RawRow).where(RawRow.source_kind == "applyhome_detail")
    )
    assert stored_details == exp["details"] + exp["comps"]
    assert rows == exp["lists"] + exp["details"] + exp["comps"]

    # 2) 같은 입력 2회 → raw_document 증가 0, 같은 행을 돌려준다
    recording.calls.clear()
    with recording.mock():
        again = _collector(http, db_session).fetch(seeded_region, snapshot, None)
    assert _count(db_session) == rows
    assert sorted(d.id or 0 for d in again) == sorted(d.id or 0 for d in docs)
    # 지역 밖 상세는 저장된 원문으로 판단해 다시 받지 않는다
    assert recording.calls["www.applyhome.co.kr"] == exp["lists"] + 2 * exp["hits"]

    # 3) 일일 수집(since=어제): 목록 + 아직 일정이 남은 지역 안 단지만 → 10분 이내
    recording.calls.clear()
    t1, real1 = clock.now, time.perf_counter()
    with recording.mock():
        daily = _collector(http, db_session).fetch(seeded_region, snapshot, "2026-10-08T06:00:00+09:00")
    daily_s = clock.now - t1 + (time.perf_counter() - real1)
    assert _count(db_session) == rows
    assert {d.id for d in daily} == {d.id for d in docs}  # 다시 받지 않은 단지도 기존 행으로 돌려준다
    assert recording.calls["www.applyhome.co.kr"] < exp["lists"] + 2 * exp["hits"]
    print(f"\n[timing] bootstrap {bootstrap_s:.0f}s, daily {daily_s:.0f}s (rate 1 req/s, 녹화 재생)")
    assert daily_s < DAILY_LIMIT_S


def _small_region() -> Region:
    return make_region(sido_codes=["28"], selections=[REGION_SEL_ICN])


REGION_SEL_ICN = {"kind": "sigungu", "code": "28185", "full_name": "인천광역시 연수구"}


def test_failures_are_rows_not_exceptions(
    recording: Recording,
    http: HttpClient,
    db_session: Session,
    seeded_region: Region,
    snapshot: Snapshot,
    raw_dir: object,
) -> None:
    region = _small_region()
    list_form = site.list_form("인천", "202512", "202611", 1)
    # 목록 1쪽은 403, 잔여세대 1쪽은 정상 → 그 행들의 상세 중 하나는 timeout, 하나는 DNS 실패
    recording.override("POST", site.list_url("apt"), httpx.Response(403, text="Forbidden"), form=list_form)
    rows = _remndr_rows(recording)
    hm1, pb1 = rows[0]
    hm2, pb2 = rows[1]

    def timeout(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=req)

    def dns(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("[Errno 11001] getaddrinfo failed", request=req)

    recording.override("GET", site.detail_url("remndr", hm1, pb1), timeout)
    recording.override("GET", site.detail_url("remndr", hm2, pb2), dns)
    with recording.mock():
        docs = _collector(http, db_session, max_pages=1).fetch(region, snapshot, None)
        n1 = _count(db_session)
        docs2 = _collector(http, db_session, max_pages=1).fetch(region, snapshot, None)

    forbidden = [d for d in docs if d.http_status == 403]
    assert len(forbidden) == 1 and forbidden[0].source_kind == "applyhome_list" and forbidden[0].path is None
    timeouts = [d for d in docs if d.error_text == "timeout"]
    dns = [d for d in docs if d.error_text == "DNS"]
    assert len(timeouts) == 1 and timeouts[0].http_status is None and timeouts[0].path is None
    assert len(dns) == 1 and dns[0].http_status is None
    # 실패 행도 같은 날 재시도는 증가 0
    assert _count(db_session) == n1
    assert {d.id for d in docs2 if d.path is None} == {d.id for d in docs if d.path is None}


def _remndr_rows(recording: Recording) -> list[tuple[str, str]]:
    from app.collectors.applyhome.parse import parse_list

    entry = recording.entries[_list_key("remndr", "인천", 1)]
    page = parse_list(recording.body(entry).decode("utf-8"), "remndr")
    return [(r.house_manage_no, r.pblanc_no) for r in page.rows]


def _list_key(
    kind: site.ListKind, area: str, page: int
) -> tuple[str, str, tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    from .replay import request_key

    return request_key("POST", site.list_url(kind), site.list_form(area, "202512", "202611", page))


@pytest.mark.live
def test_live_list_and_detail(tmp_path: object, test_settings: object) -> None:
    """실제 청약홈: 목록 1쪽 → 첫 행 상세의 공급위치."""
    from app.collectors.applyhome.parse import parse_list

    with HttpClient() as c:
        r = c.post(site.list_url("apt"), data=site.list_form("인천", "202512", "202611", 1))
        assert r.ok
        page = parse_list(r.text(), "apt")
        assert page.total is not None and page.rows
        row = page.rows[0]
        d = c.get(site.detail_url("apt", row.house_manage_no, row.pblanc_no))
        assert d.ok and detail_supply_address(d.text())

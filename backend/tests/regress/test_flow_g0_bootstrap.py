"""e2e 흐름 (a) G0 지역 입력 → region.bootstrap → G1 의 백엔드 재현(DECISIONS D2·D2-4·D2-6).

자유 지명 '송도' → /regions/resolve 후보 중 '인천광역시 연수구 송도동'(법정동) → POST /regions(201, job_id) →
worker(runner.main --once)에 청약홈 웹 녹화 재생 수집기(``e2e/support/offline.py`` — e2e 와 같은 재생기,
네트워크 없음) + Mock 판정기 → 잡 done·지역 ready → G1(대시보드)·G2(리스트) API 가 오류 없이 새 지역 결과를 준다.
같은 DB 의 기존 지역(픽스처 지역 1)은 새 지역 bootstrap 으로 바뀌지 않는다(지역마다 독립 — 단지·변경 이력).
"""

# ruff: noqa: E501

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy import select

from .conftest import REPO, WRITE, RegressEnv

pytestmark = pytest.mark.regress

RECORDING = REPO / "backend" / "tests" / "collectors" / "applyhome" / "fixtures" / "applyhome_2026-10-09.zip"
OFFLINE = REPO / "e2e" / "support" / "offline.py"
TODAY = date(2026, 10, 9)  # 녹화일(목록 조회 창)
PICK = "인천광역시 연수구 송도동"


def _offline() -> ModuleType:
    spec = importlib.util.spec_from_file_location("wp9_e2e_offline", OFFLINE)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class _Empty:
    def fetch(self, region: Any, snapshot: Any, since: str | None) -> list[Any]:
        return []


@pytest.fixture
def boot(env: RegressEnv) -> dict[str, Any]:
    """POST /regions → bootstrap(재생) 1회. 전·후 기존 지역 단지 상태와 새 지역 id 를 돌려준다."""
    from app.collectors.applyhome import ApplyhomeCollector
    from app.core.http import HttpClient
    from app.models import Complex, JobRun, Region
    from app.scheduler.context import default_collectors

    off = _offline()
    with env.session() as s:
        before = {c.id: (c.region_id, c.name, c.builder) for c in s.scalars(select(Complex).where(Complex.region_id == 1))}
    cands = env.client.get("/api/regions/resolve", headers=WRITE, params={"q": "송도"}).json()
    pick = next(c for c in cands if c["kind"] == "legal_dong" and c["full_name"] == PICK)
    r = env.client.post(
        "/api/regions", headers=WRITE,
        json={"name": "송도 회귀", "query_text": "송도", "selections": [{k: pick[k] for k in ("kind", "code", "full_name")}]},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    rid, job_id = body["region"]["id"], body["job_id"]
    web = HttpClient(max_retries=0, jitter=0.0, rate_per_host=1000.0, sleep=lambda _s: None, transport=off.replay_transport(RECORDING))
    base = default_collectors()
    env.clock.day = TODAY
    ctx = env.ctx(
        "mock",
        collectors={
            "applyhome": lambda c: ApplyhomeCollector(http=web, today=lambda: TODAY, service_key=None),
            "notice_pdf": lambda c: _Empty(),
            "official_site": lambda c: _Empty(),
            "stats": lambda c: _Empty(),
            "rtms": base["rtms"],
            "news": base["news"],
        },
    )
    try:
        assert env.worker(ctx) == 0
    finally:
        web.close()
    with env.session() as s:
        job = s.get(JobRun, job_id)
        region = s.get(Region, rid)
        assert job is not None and job.status == "done", (job.status if job else None, job.error_text if job else None)
        assert region is not None and region.status == "ready"
        after = {c.id: (c.region_id, c.name, c.builder) for c in s.scalars(select(Complex).where(Complex.id.in_(list(before))))}
        stats = dict(job.stats or {})
    return {"region_id": rid, "snapshot_id": stats["snapshot_id"], "before": before, "after": after, "stats": stats}


def test_g0_bootstrap_creates_region_complexes(env: RegressEnv, boot: dict[str, Any]) -> None:
    body = env.client.get(f"/api/snapshots/{boot['snapshot_id']}/complexes", headers=WRITE, params={"size": 200})
    assert body.status_code == 200, body.text[:300]
    items = body.json()["items"]
    assert items, "새 지역 단지 0개"
    names = " ".join(i["name"] for i in items)
    assert "송도" in names


def test_g0_bootstrap_dashboard_ok(env: RegressEnv, boot: dict[str, Any]) -> None:
    """G1: 새 지역 최신 스냅샷 대시보드 200(dev 에서 contract_violation 없음)."""
    r = env.client.get(f"/api/snapshots/{boot['snapshot_id']}/dashboard", headers=WRITE)
    assert r.status_code == 200, r.text[:300]
    assert len(r.json()["kpis"]) == 5


def test_g0_bootstrap_does_not_touch_other_region(env: RegressEnv, boot: dict[str, Any]) -> None:
    """기존 지역 1 의 단지 행(이름·시공사·소속)과 변경 이력은 새 지역 bootstrap 과 무관해야 한다."""
    from app.models import ChangeEvent

    changed = {cid: (boot["before"][cid], boot["after"].get(cid)) for cid in boot["before"] if boot["before"][cid] != boot["after"].get(cid)}
    with env.session() as s:
        foreign = [
            (e.complex_id, e.field, e.old_text, e.new_text)
            for e in s.scalars(select(ChangeEvent).where(ChangeEvent.snapshot_id == boot["snapshot_id"], ChangeEvent.complex_id.in_(list(boot["before"]))))
        ]
    assert not changed and not foreign, f"지역 1 단지가 지역 {boot['region_id']} bootstrap 으로 바뀜: {changed} / 새 스냅샷의 지역 1 변경 이벤트: {foreign[:6]}"

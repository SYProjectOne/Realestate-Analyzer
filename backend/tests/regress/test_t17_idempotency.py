"""T17 멱등성 (RA §9) — 시스템 경계: collect.daily 잡 2회 · rejudge 잡 2회(worker) · 같은 payload 2회(운영 어댑터).

RA §9 기대 결과(원문 그대로): "`raw_document` 증가 0; 판정기 실제 호출 1회, 두 번째는 cached=true"
(케이스: 수집 2회, 재판정 2회). 픽스처: ``raw/applyhome_list/2026-10-07.json`` ``raw/documents.json`` ``judgments/_index.json``.

- 수집: 같은 원문(목록·팝업·새 HTML 1건·403 실패 행)을 같은 날 2회 → 두 번째 raw_document 증가 0(실패 행도 날마다 1행).
- 재판정: 같은 rejudge 잡 2회 → 두 번째 FakeJev 실제 호출 0, 잡 stats judge_calls 0·cached > 0, judgment_log 증가 0.
- 어댑터: 같은 payload 2회 → 전송 호출 1, 두 번째 봉투 cached=true(같은 judgment_seq).
"""

# ruff: noqa: E501

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .conftest import FIXTURE, SNAP, WRITE, RegressEnv, api_get, load_json

pytestmark = pytest.mark.regress

LIST_URL = "https://www.applyhome.co.kr/ai/aia/selectAPTLttotPblancListView.do"
HTML = "<html><body><h1>T17 회귀 공식 홈페이지</h1><p>견본주택 운영 안내</p></body></html>".encode()


def _count(s: Session, model: Any, *where: Any) -> int:
    return int(s.scalar(select(func.count()).select_from(model).where(*where)) or 0)


class ListCollector:
    """청약홈 목록 원문(픽스처 바이트) → WP1 RawStore(같은 sha256 이면 기존 행)."""

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx

    def fetch(self, region: Any, snapshot: Any, since: str | None) -> list[Any]:
        from app.collectors.reference.rawstore import RawStore

        with self.ctx.session_factory() as s:
            store = RawStore(s)
            out = [
                store.save_content(
                    source_kind="applyhome_list",
                    url=LIST_URL,
                    content=(FIXTURE / "raw" / "applyhome_list" / "2026-10-07.json").read_bytes(),
                    ext="json",
                    content_type="application/json",
                    fetched_at=self.ctx.now(),
                    region_id=region.id,
                )
            ]
            s.commit()
        return out


class SiteCollector:
    """공식 홈페이지: 팝업 PNG(픽스처 rd 9062 와 같은 바이트) + 새 HTML 1건(단지 3) + 403 실패 행(단지 4)."""

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx

    def fetch(self, region: Any, snapshot: Any, since: str | None) -> list[Any]:
        from app.collectors.reference.rawstore import Failure, RawStore

        pop = load_json(FIXTURE / "raw" / "official_site" / "t8_popup_pairs.json")["yesterday"]
        now = self.ctx.now()
        with self.ctx.session_factory() as s:
            store = RawStore(s)
            out = [
                store.save_content(
                    source_kind="official_site",
                    url=pop["url"],
                    content=(FIXTURE / "raw" / pop["path"]).read_bytes(),
                    ext="png",
                    content_type="image/png",
                    fetched_at=now,
                    region_id=region.id,
                    complex_id=pop["complex_id"],
                    image_hash=pop["image_hash"],
                ),
                store.save_content(
                    source_kind="official_site",
                    url="https://t17.example.invalid/",
                    content=HTML,
                    ext="html",
                    content_type="text/html; charset=utf-8",
                    fetched_at=now,
                    region_id=region.id,
                    complex_id=3,
                    text="T17 회귀 공식 홈페이지 견본주택 운영 안내",
                ),
                store.save_failure(
                    source_kind="official_site",
                    url="https://t17-switzen.example.invalid/",
                    failure=Failure(403, None),
                    fetched_at=now,
                    region_id=region.id,
                    complex_id=4,
                ),
            ]
            s.commit()
        return out


def _prewarm(env: RegressEnv) -> None:
    """정상 운영 상태: 판정기(FakeJev) 버전이 judgment_log 에 이미 기록돼 있다(D6 버전 변경 재판정과 분리)."""
    from app.judge.jev_mcp import JevMcpAdapter

    a = JevMcpAdapter(transport=env.jev, session_factory=env.factory, secrets=[])
    a.call("screen", {"text": "regress warm-up", "purpose": "warm"}, "screen:regress:t17-warm")
    env.jev.calls.clear()


def _post(env: RegressEnv, job_name: str, payload: dict[str, Any]) -> int:
    r = env.client.post("/api/jobs", headers=WRITE, json={"job_name": job_name, "payload": payload})
    assert r.status_code == 202, r.text
    return int(r.json()["id"])


def test_t17_collect_twice_raw_document_increase_zero(env: RegressEnv) -> None:
    from app.models import RawDocument

    env.clock.day = date(2026, 10, 9)
    collectors = {"applyhome": ListCollector, "official_site": SiteCollector}
    payload = {"region_id": 1, "sources": ["applyhome_list", "official_site"]}
    with env.session() as s:
        n0 = _count(s, RawDocument)
    first = _post(env, "collect.daily", payload)
    env.worker(env.ctx("fake", collectors=collectors))
    j1 = api_get(env, f"/jobs/{first}")
    assert j1["status"] == "done", j1
    with env.session() as s:
        n1 = _count(s, RawDocument)
    # 첫 수집: 새 HTML 1(DOM 텍스트는 같은 행 text_path) + 403 실패 행 1, 목록·팝업은 픽스처 행 재사용
    assert n1 - n0 == 2, (n0, n1)
    second = _post(env, "collect.daily", payload)
    env.worker(env.ctx("fake", collectors=collectors))
    j2 = api_get(env, f"/jobs/{second}")
    assert j2["status"] == "done", j2
    assert j2["stats"]["documents"] == j1["stats"]["documents"] == {"applyhome": 1, "official_site": 3}
    with env.session() as s:
        assert _count(s, RawDocument) == n1  # 두 번째 수집: raw_document 증가 0
        dup = s.execute(
            select(RawDocument.sha256, func.count()).group_by(RawDocument.sha256).having(func.count() > 1)
        ).all()
        assert dup == []
    assert env.jev.calls == []


def test_t17_same_payload_twice_one_real_call_second_cached(env: RegressEnv) -> None:
    from app.judge.jev_mcp import JevMcpAdapter
    from app.models import JudgmentLog

    idx = load_json(FIXTURE / "judgments" / "_index.json")
    row = next(r for r in idx if r["tool"] == "screen")  # 녹화 payload(보고서 입력 재구성) 그대로
    a = JevMcpAdapter(transport=env.jev, session_factory=env.factory, secrets=[])
    with env.session() as s:
        n0 = _count(s, JudgmentLog)
    e1 = a.call(row["tool"], row["payload"], row["purpose"], snapshot_id=SNAP)
    # 재시작한 worker 의 새 어댑터
    b = JevMcpAdapter(transport=env.jev, session_factory=env.factory, secrets=[])
    e2 = b.call(row["tool"], row["payload"], row["purpose"], snapshot_id=SNAP)
    assert len(env.jev.calls) == 1  # 판정기 실제 호출 1회
    assert (e1.cached, e2.cached) == (False, True)
    assert (
        e1.judgment_seq == e2.judgment_seq
        and e1.input_hash == e2.input_hash
        and e1.status == e2.status == "ok"
    )
    with env.session() as s:
        assert _count(s, JudgmentLog) == n0 + 1


def test_t17_rejudge_twice_second_run_zero_judge_calls(env: RegressEnv) -> None:
    from app.models import JobRun, JudgmentLog

    _prewarm(env)
    payload = {"snapshot_id": SNAP, "scenario_id": None, "complex_ids": [1, 2], "reason": "T17 재판정"}
    first = _post(env, "rejudge", payload)
    env.worker(env.ctx("fake"))
    j1 = api_get(env, f"/jobs/{first}")
    assert j1["status"] == "done", j1
    calls1 = len(env.jev.calls)
    assert calls1 > 0 and j1["stats"]["judge_calls"] > 0, j1["stats"]
    with env.session() as s:
        jl1 = _count(s, JudgmentLog)
        rj = _count(s, JobRun, JobRun.job_name == "rejudge")

    second = _post(env, "rejudge", payload)
    env.worker(env.ctx("fake"))
    j2 = api_get(env, f"/jobs/{second}")
    assert j2["status"] == "done", j2
    new_calls = env.jev.calls[calls1:]
    assert new_calls == [], (
        f"두 번째 재판정의 실제 호출 {len(new_calls)}회: {sorted({t for t, _ in new_calls})}"
    )
    assert j2["stats"]["judge_calls"] == 0, j2["stats"]
    assert j2["stats"]["cached"] >= j1["stats"]["judge_calls"], (j1["stats"], j2["stats"])
    with env.session() as s:
        assert _count(s, JudgmentLog) == jl1  # 새 판정 행 0
        assert _count(s, JobRun, JobRun.job_name == "rejudge") == rj + 1  # 연쇄 재판정 없음

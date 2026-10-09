"""T8 변경 없는 날 (RA §9) — 시스템 경계: 가짜 수집기(원문 바이트 → WP1 RawStore) → collect.daily 잡 → worker → DB·API.

RA §9 기대 결과(원문 그대로): "`change_event` 0, rejudge job 0, 판정기 실제 호출 0"
(케이스: 어제와 동일한 목록·팝업 해시). 픽스처 README: "같은 목록·같은 해시 → change_event 0·판정 0; 변경 쌍 → critical 1".

시나리오(기준일 = ctx 시계)
- N(2026-10-09): 청약홈 목록(``raw/applyhome_list/2026-10-08.json``) + 엘리프 팝업(``elif_popup_2026-10-08_same.png``).
- N+1(2026-10-10): 같은 원문 → change_event 0 · rejudge 0 · FakeJev 호출 0 · raw_document 증가 0 · 이전 판정 복사 후 publish.
- N+2(2026-10-11): 팝업만 ``elif_popup_2026-10-08_changed.png`` → critical 1(official_popup_hash, 단지 2) + rejudge 1(단지 [2]).
"""

# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .conftest import FIXTURE, SNAP, WRITE, RegressEnv, api_get, load_json

pytestmark = pytest.mark.regress

PAIRS = FIXTURE / "raw" / "official_site" / "t8_popup_pairs.json"
LIST_URL = "https://www.applyhome.co.kr/ai/aia/selectAPTLttotPblancListView.do"


def _count(s: Session, model: Any, *where: Any) -> int:
    return int(s.scalar(select(func.count()).select_from(model).where(*where)) or 0)


@dataclass
class Doc:
    source_kind: str
    url: str
    file: str  # FIXTURE/raw 기준
    ext: str
    content_type: str
    complex_id: int | None = None
    image_hash: str | None = None


class FixtureCollector:
    """수집기 계약(fetch → RawDocument DTO). 원문 바이트를 WP1 RawStore 로 저장(같은 sha256 이면 기존 행)."""

    def __init__(self, ctx: Any, docs: list[Doc]) -> None:
        self.ctx = ctx
        self.docs = docs
        self.created = 0

    def fetch(self, region: Any, snapshot: Any, since: str | None) -> list[Any]:
        from app.collectors.reference.rawstore import RawStore

        with self.ctx.session_factory() as s:
            store = RawStore(s)
            out = [
                store.save_content(
                    source_kind=d.source_kind,
                    url=d.url,
                    content=(FIXTURE / "raw" / d.file).read_bytes(),
                    ext=d.ext,
                    content_type=d.content_type,
                    fetched_at=self.ctx.now(),
                    http_status=200,
                    region_id=region.id,
                    complex_id=d.complex_id,
                    image_hash=d.image_hash,
                )
                for d in self.docs
            ]
            s.commit()
            self.created += store.created
        return out


def _popup(key: str) -> Doc:
    p = load_json(PAIRS)[key]
    return Doc(
        "official_site",
        p["url"],
        p["path"],
        "png",
        "image/png",
        complex_id=p["complex_id"],
        image_hash=p["image_hash"],
    )


LIST_DOC = Doc("applyhome_list", LIST_URL, "applyhome_list/2026-10-08.json", "json", "application/json")


def _prewarm(env: RegressEnv) -> None:
    """정상 운영 상태: 판정기(FakeJev) 버전이 judgment_log 에 이미 기록돼 있다(D6 버전 변경 재판정과 분리)."""
    from app.judge.jev_mcp import JevMcpAdapter

    a = JevMcpAdapter(transport=env.jev, session_factory=env.factory, secrets=[])
    a.call("screen", {"text": "regress warm-up", "purpose": "warm"}, "screen:regress:t08-warm")
    env.jev.calls.clear()


def _daily(
    env: RegressEnv, day: date, docs_list: list[Doc], docs_site: list[Doc]
) -> tuple[dict[str, Any], FixtureCollector, FixtureCollector]:
    env.clock.day = day
    r = env.client.post(
        "/api/jobs",
        headers=WRITE,
        json={
            "job_name": "collect.daily",
            "payload": {"region_id": 1, "sources": ["applyhome_list", "official_site"]},
        },
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]
    holder: dict[str, FixtureCollector] = {}

    def ah(ctx: Any) -> FixtureCollector:
        holder["applyhome"] = FixtureCollector(ctx, docs_list)
        return holder["applyhome"]

    def site(ctx: Any) -> FixtureCollector:
        holder["official_site"] = FixtureCollector(ctx, docs_site)
        return holder["official_site"]

    assert env.worker(env.ctx("fake", collectors={"applyhome": ah, "official_site": site})) == 0
    job = api_get(env, f"/jobs/{job_id}")
    assert job["status"] == "done", job
    return job, holder["applyhome"], holder["official_site"]


def test_t08_same_list_and_popup_hash_no_event_no_rejudge_no_judge_call(env: RegressEnv) -> None:
    from app.models import ChangeEvent, JobRun, JudgmentLog, RawDocument, ScoreRun, Snapshot

    _prewarm(env)
    same = [_popup("today_same")]
    # N: 기준선(어제 = 픽스처 2026-10-07 원문과 같은 바이트)
    job_n, ah_n, site_n = _daily(env, date(2026, 10, 9), [LIST_DOC], same)
    # 픽스처 DB 의 어제 원문(rd 9064 목록·rd 9062 팝업)과 같은 바이트 → 이 날도 변경 없음
    assert (ah_n.created, site_n.created) == (0, 0)
    assert job_n["stats"]["change_events"] == 0 and "rejudge_job_id" not in job_n["stats"], job_n["stats"]
    assert job_n["stats"]["carry_forward"]["from_snapshot_id"] == SNAP, job_n["stats"]
    assert env.jev.calls == []
    with env.session() as s:
        raw_n = _count(s, RawDocument)
        rejudge_n = _count(s, JobRun, JobRun.job_name == "rejudge")
        jl_n = _count(s, JudgmentLog)
        snap_n = s.scalars(select(Snapshot).where(Snapshot.asof_date == "2026-10-09")).one()
        assert snap_n.status == "published", (snap_n.status, job_n["stats"])

    # N+1: 같은 목록·같은 팝업 해시
    job, ah, site = _daily(env, date(2026, 10, 10), [LIST_DOC], same)
    st = job["stats"]
    assert st["documents"] == {"applyhome": 1, "official_site": 1}, st
    assert ah.created == 0 and site.created == 0  # 같은 sha256 → 기존 행
    assert st["change_events"] == 0 and "rejudge_job_id" not in st, st
    assert env.jev.calls == []  # 판정기 실제 호출 0
    with env.session() as s:
        snap = s.scalars(select(Snapshot).where(Snapshot.asof_date == "2026-10-10")).one()
        assert _count(s, ChangeEvent, ChangeEvent.snapshot_id == snap.id) == 0
        assert _count(s, JobRun, JobRun.job_name == "rejudge") == rejudge_n  # rejudge job 0
        assert _count(s, RawDocument) == raw_n
        assert _count(s, JudgmentLog) == jl_n  # 캐시 적중 기록도 새 행 없음
        assert snap.status == "published" and not snap.degraded
        assert (
            _count(s, ScoreRun, ScoreRun.snapshot_id == snap.id)
            == _count(s, ScoreRun, ScoreRun.snapshot_id == snap_n.id)
            > 0
        )
        sid = snap.id
    # API(G1): 오늘 스냅샷 변경 0
    assert api_get(env, f"/snapshots/{sid}/changes") == []
    dash = api_get(env, f"/snapshots/{sid}/dashboard", scenario="base")
    assert dash["changes"] == [] and dash["degraded"] is False and len(dash["top5"]) >= 5


def test_t08_changed_popup_one_critical_one_rejudge(env: RegressEnv) -> None:
    from app.models import ChangeEvent, JobRun, Snapshot

    _prewarm(env)
    _daily(env, date(2026, 10, 9), [LIST_DOC], [_popup("today_same")])
    _daily(env, date(2026, 10, 10), [LIST_DOC], [_popup("today_same")])
    with env.session() as s:
        before = {j.id for j in s.scalars(select(JobRun).where(JobRun.job_name == "rejudge"))}
    pairs = load_json(PAIRS)
    job, _, site = _daily(env, date(2026, 10, 11), [LIST_DOC], [_popup("today_changed")])
    assert site.created == 1
    st = job["stats"]
    with env.session() as s:
        snap = s.scalars(select(Snapshot).where(Snapshot.asof_date == "2026-10-11")).one()
        events = list(s.scalars(select(ChangeEvent).where(ChangeEvent.snapshot_id == snap.id)))
        assert [(e.severity, e.field, e.complex_id, e.triggers_rejudge) for e in events] == [
            ("critical", "official_popup_hash", 2, True)
        ], [(e.entity, e.field, e.severity) for e in events]
        ev = events[0]
        assert (
            ev.old_text == pairs["today_same"]["image_hash"]
            and ev.new_text == pairs["today_changed"]["image_hash"]
        )
        new = [j for j in s.scalars(select(JobRun).where(JobRun.job_name == "rejudge")) if j.id not in before]
        assert len(new) == 1, [(j.payload, j.status) for j in new]
        assert new[0].id == st["rejudge_job_id"]
        assert new[0].payload["complex_ids"] == [2] and new[0].payload["change_event_ids"] == [ev.id]
        assert new[0].status == "done", new[0].error_text
        assert new[0].stats["targets"] == 1
    assert env.jev.calls, "변경 단지 재판정은 판정기를 불러야 한다"
